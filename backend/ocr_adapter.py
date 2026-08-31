from __future__ import annotations

import json
import re
import shutil
import selectors
import subprocess
import sys
import unicodedata
from pathlib import Path

import httpx
from ollama import Client

from field_rules import apply_deterministic_field_rules
from settings import Settings


ROOT = Path(__file__).resolve().parent
QWEN_HOME = ROOT / "legacy" / "paddleocr_qwen"
if str(QWEN_HOME) not in sys.path:
    sys.path.insert(0, str(QWEN_HOME))

import qwen_bridge  # noqa: E402


class OCRError(RuntimeError):
    pass


class OCRTimeoutError(OCRError):
    pass


EXCLUDED_FIELDS = {"ada", "parsel"}
WORKER_MARKER = "__BELGEDOGRULA_OCR__"


def _normalize_evidence(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value).casefold())
    normalized = "".join(
        character for character in normalized if not unicodedata.combining(character)
    ).replace("ı", "i")
    return re.sub(r"[^0-9a-z]+", "", normalized)


def enforce_source_evidence(fields: dict, lines: list[dict]) -> dict:
    """Remove model values that are not backed by an OCR source line."""
    valid_ids = {line["id"] for line in lines}
    lines_by_id = {line["id"]: str(line.get("text", "")) for line in lines}
    trusted: dict = {}
    for field_name, payload in fields.items():
        if field_name in EXCLUDED_FIELDS:
            continue
        value = payload.get("value")
        source_ids = payload.get("source_line_ids") or []
        valid_source_ids = [line_id for line_id in source_ids if line_id in valid_ids]
        evidence = _normalize_evidence(
            " ".join(lines_by_id[line_id] for line_id in valid_source_ids)
        )
        value_in_evidence = bool(
            value
            and evidence
            and _normalize_evidence(value) in evidence
        )
        if value and (not valid_source_ids or not value_in_evidence):
            trusted[field_name] = {"value": None, "source_line_ids": []}
        else:
            trusted[field_name] = {
                "value": value,
                "source_line_ids": valid_source_ids,
            }
    return trusted


def _find_executable(configured: str) -> str:
    candidate = Path(configured).expanduser()
    if candidate.is_file():
        return str(candidate)

    # Launching a virtual-environment entry point by its absolute path does not
    # activate that environment or add its bin directory to PATH. Prefer the
    # PaddleOCR entry point installed beside the running Python interpreter so
    # the CLI and imported packages always come from the same environment.
    if len(candidate.parts) == 1:
        environment_candidate = Path(sys.executable).parent / configured
        if environment_candidate.is_file():
            return str(environment_candidate)

    resolved = shutil.which(configured)
    if not resolved:
        raise OCRError(
            "PaddleOCR çalıştırıcısı bulunamadı. PADDLEOCR_EXECUTABLE ayarını kontrol edin."
        )
    return resolved


def run_paddleocr(
    pages_dir: Path,
    output_dir: Path,
    settings: Settings,
    timeout_seconds: float | None = None,
) -> list[dict]:
    executable = _find_executable(settings.paddleocr_executable)
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        executable,
        "ocr",
        "-i",
        str(pages_dir),
        "--lang",
        "tr",
        "--ocr_version",
        settings.paddleocr_version,
        "--use_doc_orientation_classify",
        "False",
        "--use_doc_unwarping",
        "False",
        "--use_textline_orientation",
        "False",
        "--save_path",
        str(output_dir),
        "--device",
        settings.paddleocr_device,
        "--engine",
        settings.paddleocr_engine,
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds or settings.ocr_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise OCRTimeoutError("PaddleOCR zaman aşımına uğradı.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "bilinmeyen hata")[-2000:]
        raise OCRError(f"PaddleOCR çalışmadı: {detail}") from exc

    json_files = sorted(output_dir.rglob("*.json"))
    if not json_files:
        raise OCRError("PaddleOCR sonuç JSON dosyası üretmedi.")
    lines: list[dict] = []
    line_id = 1
    for page_index, json_path in enumerate(json_files, start=1):
        data = json.loads(json_path.read_text(encoding="utf-8"))
        result = data.get("res", data)
        texts = result.get("rec_texts", [])
        scores = result.get("rec_scores", [])
        for index, text in enumerate(texts):
            text = str(text).strip()
            if not text:
                continue
            score = round(float(scores[index]), 4) if index < len(scores) else None
            lines.append(
                {
                    "id": line_id,
                    "page": page_index,
                    "text": text,
                    "ocr_confidence": score,
                }
            )
            line_id += 1
    if not lines:
        raise OCRError("Belgeden okunabilir metin çıkarılamadı.")
    return lines


def _lines_from_pages(pages: list[dict]) -> list[dict]:
    lines: list[dict] = []
    for page_index, data in enumerate(pages, start=1):
        result = data.get("res", data)
        texts = result.get("rec_texts", [])
        scores = result.get("rec_scores", [])
        for index, raw_text in enumerate(texts):
            value = str(raw_text).strip()
            if not value:
                continue
            score = round(float(scores[index]), 4) if index < len(scores) else None
            lines.append({"id": len(lines) + 1, "page": page_index, "text": value, "ocr_confidence": score})
    if not lines:
        raise OCRError("Belgeden okunabilir metin çıkarılamadı.")
    return lines


class OCRSession:
    """One warm PaddleOCR subprocess, explicitly released before Qwen runs."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.process: subprocess.Popen | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def _start(self) -> None:
        if self.process and self.process.poll() is None:
            return
        worker = Path(__file__).with_name("ocr_worker.py")
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                str(worker),
                self.settings.paddleocr_device,
                self.settings.paddleocr_engine,
                self.settings.paddleocr_version,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

    def run(self, pages_dir: Path, output_dir: Path, timeout_seconds: float) -> list[dict]:
        if not self.settings.paddleocr_warm_worker:
            return run_paddleocr(pages_dir, output_dir, self.settings, timeout_seconds)
        self._start()
        assert self.process and self.process.stdin and self.process.stdout
        paths = [str(path) for path in sorted(pages_dir.iterdir()) if path.is_file()]
        request = json.dumps({"command": "predict", "paths": paths})
        try:
            self.process.stdin.write(request + "\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            self.close()
            raise OCRError("PaddleOCR sıcak işçisi başlatılamadı.") from exc

        selector = selectors.DefaultSelector()
        selector.register(self.process.stdout, selectors.EVENT_READ)
        try:
            import time
            deadline = time.monotonic() + timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.close()
                    raise OCRTimeoutError("PaddleOCR zaman aşımına uğradı.")
                if not selector.select(remaining):
                    self.close()
                    raise OCRTimeoutError("PaddleOCR zaman aşımına uğradı.")
                line = self.process.stdout.readline()
                if not line:
                    self.close()
                    raise OCRError("PaddleOCR sıcak işçisi beklenmedik biçimde durdu.")
                if not line.startswith(WORKER_MARKER):
                    continue
                response = json.loads(line[len(WORKER_MARKER):])
                if not response.get("ok"):
                    self.close()
                    raise OCRError(f"PaddleOCR sıcak işçisi çalışmadı: {response.get('error', 'bilinmeyen hata')}")
                return _lines_from_pages(response.get("pages") or [])
        finally:
            selector.close()

    def close(self) -> None:
        process, self.process = self.process, None
        if process is None:
            return
        if process.poll() is None:
            try:
                if process.stdin:
                    process.stdin.write('{"command":"close"}\n')
                    process.stdin.flush()
                process.wait(timeout=5)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        for stream in (process.stdin, process.stdout):
            if stream:
                stream.close()


def extract_fields(
    lines: list[dict],
    settings: Settings,
    timeout_seconds: float | None = None,
) -> dict:
    original_client = qwen_bridge.Client

    class ConfiguredClient:
        def __init__(self):
            self.client = Client(
                host=settings.ollama_host,
                timeout=timeout_seconds or settings.ocr_timeout_seconds,
            )

        def chat(self, **kwargs):
            kwargs["model"] = settings.ollama_model
            return self.client.chat(**kwargs)

    def configured_client(host: str):
        return ConfiguredClient()

    qwen_bridge.Client = configured_client
    try:
        fields = qwen_bridge.extract_fields(lines)
        validation_errors = qwen_bridge.validate_source_lines(fields, lines)
    except httpx.TimeoutException as exc:
        raise OCRTimeoutError("Qwen alan çıkarma zaman aşımına uğradı.") from exc
    except Exception as exc:
        raise OCRError(f"Qwen alan çıkarma başarısız: {exc}") from exc
    finally:
        qwen_bridge.Client = original_client
    trusted_fields = enforce_source_evidence(fields.model_dump(), lines)
    trusted_fields = apply_deterministic_field_rules(trusted_fields, lines)
    trusted_fields = enforce_source_evidence(trusted_fields, lines)
    return {
        "model": settings.ollama_model,
        "fields": trusted_fields,
        "validation_errors": validation_errors,
        "line_count": len(lines),
    }
