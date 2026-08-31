from __future__ import annotations

import sys
import time
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from documents import (
    extract_pdf_text_lines,
    has_usable_text_layer,
    pdf_page_count,
    render_pages,
)
from official_search import (
    DocumentLinkParser,
    SearchDeadlineExceeded,
    search_official_documents,
)
from ocr_adapter import OCRSession, OCRTimeoutError
from ocr_preprocessing import prepare_ocr_pages
from qwen_text_judge import (
    TextJudgeError,
    TextJudgeTimeout,
    finalize_hybrid_decision,
    judge_texts,
    needs_qwen_review,
)
from settings import Settings
from text_comparison import compare_ocr_texts


ROOT = Path(__file__).resolve().parent
QR_HOME = ROOT / "legacy" / "qr_document_verifier"
if str(QR_HOME) not in sys.path:
    sys.path.insert(0, str(QR_HOME))

from qr_reader import read_qr_image  # noqa: E402


_FrameParser = DocumentLinkParser
ProgressCallback = Callable[[float, str, float, float], None]


def _notify_progress(
    callback: ProgressCallback | None,
    percent: float,
    phase: str,
    ceiling: float,
    expected_seconds: float,
) -> None:
    if not callback:
        return
    try:
        callback(percent, phase, ceiling, expected_seconds)
    except Exception:
        # Progress reporting must never fail document verification.
        pass


def _scan_qr(pages: list[Path], settings: Settings) -> dict:
    reports = []
    # Try every page with deterministic recovery first. Restormer is loaded only
    # when no page reaches decoder consensus in this cheap pass.
    for page_index, page in enumerate(pages, start=1):
        report = read_qr_image(page, enable_restormer=False)
        reports.append({"page": page_index, **report.to_dict()})
        if report.status == "confirmed" and len(report.confirmed_contents) == 1:
            return {"selected_page": page_index, "report": report.to_dict(), "pages": reports}
    if settings.enable_restormer:
        for page_index, page in enumerate(pages, start=1):
            report = read_qr_image(page, enable_restormer=True)
            reports.append({"page": page_index, "enhanced_retry": True, **report.to_dict()})
            if report.status == "confirmed" and len(report.confirmed_contents) == 1:
                return {"selected_page": page_index, "report": report.to_dict(), "pages": reports}
    return {"selected_page": None, "report": reports[0] if reports else None, "pages": reports}


def _finish_timings(response: dict, started: float, phases: dict, candidates: list) -> dict:
    response["timings"] = {
        "total_seconds": round(time.monotonic() - started, 3),
        "phases": {name: round(value, 3) for name, value in phases.items()},
        "candidates": candidates,
    }
    return response


def _select_best_candidate(candidates: list[dict]) -> dict:
    decision_priority = {"mismatch": 0, "match": 1}

    def rank(candidate: dict) -> tuple[int, float, int]:
        comparison = candidate["comparison"]
        return (
            decision_priority.get(comparison["decision"], -1),
            comparison.get("match_confidence", comparison.get("confidence", 0.0)),
            comparison.get(
                "compared_token_count",
                comparison.get("comparable_fields", 0),
            ),
        )

    return max(candidates, key=rank)


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise SearchDeadlineExceeded("Toplam işlem zaman sınırı aşıldı.")
    return remaining


def _ocr_document(
    pages_dir: Path,
    work_dir: Path,
    settings: Settings,
    deadline: float,
    ocr_session: OCRSession,
) -> dict:
    prepared_dir, preprocessing = prepare_ocr_pages(
        pages_dir,
        work_dir / "prepared-pages",
        denoise_min_score=settings.ocr_denoise_min_score,
    )
    try:
        lines = ocr_session.run(
            prepared_dir,
            work_dir / "ocr-output",
            timeout_seconds=min(
                settings.ocr_timeout_seconds,
                _remaining_seconds(deadline),
            ),
        )
    except OCRTimeoutError as exc:
        raise SearchDeadlineExceeded(str(exc)) from exc
    return {
        "lines": lines,
        "line_count": len(lines),
        "preprocessing": preprocessing,
    }


def verify_document(
    uploaded_path: Path,
    media_type: str,
    settings: Settings,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    started = time.monotonic()
    phase_timings: dict[str, float] = {}
    candidate_timings: list[dict] = []
    deadline = time.monotonic() + settings.max_total_processing_seconds
    with TemporaryDirectory(prefix="belgedogrula-pipeline-") as temp, OCRSession(settings) as ocr_session:
        _notify_progress(progress_callback, 2, "upload_validation", 7, 3)
        work_dir = Path(temp)
        uploaded_pages_dir = work_dir / "uploaded-pages"
        phase_started = time.monotonic()
        uploaded_pages = render_pages(
            uploaded_path,
            media_type,
            uploaded_pages_dir,
            settings.max_pdf_pages,
        )
        phase_timings["uploaded_render"] = time.monotonic() - phase_started
        _notify_progress(progress_callback, 8, "qr_analysis", 18, 25)
        phase_started = time.monotonic()
        qr = _scan_qr(uploaded_pages, settings)
        phase_timings["qr_analysis"] = time.monotonic() - phase_started
        _notify_progress(progress_callback, 18, "uploaded_ocr", 45, 90)
        phase_started = time.monotonic()
        uploaded_ocr = _ocr_document(
            uploaded_pages_dir,
            work_dir / "uploaded",
            settings,
            deadline,
            ocr_session,
        )
        phase_timings["uploaded_ocr"] = time.monotonic() - phase_started
        _notify_progress(progress_callback, 45, "official_search", 52, 20)
        uploaded = {"line_count": uploaded_ocr["line_count"]}
        response: dict = {
            "status": "uploaded_document_analyzed",
            "matched": False,
            "matched_document_url": None,
            "source_page_url": None,
            "match_confidence": 0.0,
            "compared_fields": [],
            "matched_fields": [],
            "mismatched_fields": [],
            "search_stopped_early": False,
            "search_stop_reason": None,
            "qr": qr,
            "uploaded": uploaded,
            "official": None,
            "official_candidates": [],
            "comparison": None,
        }

        report = qr.get("report") or {}
        confirmed = report.get("confirmed_contents") or []
        if len(confirmed) != 1:
            response["status"] = "qr_not_confirmed"
            response["search_stop_reason"] = "qr_not_confirmed"
            return _finish_timings(response, started, phase_timings, candidate_timings)
        if not settings.fetch_official_document:
            response["status"] = "qr_confirmed"
            response["search_stop_reason"] = "official_search_disabled"
            return _finish_timings(response, started, phase_timings, candidate_timings)

        suffixes = {
            "application/pdf": ".pdf",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/tiff": ".tiff",
        }

        def evaluate_document(
            body: bytes,
            candidate_type: str,
            metadata: dict,
            remaining_seconds: float,
        ) -> dict:
            candidate_deadline = min(
                deadline,
                time.monotonic() + remaining_seconds,
            )
            index = metadata["document_index"]
            candidate_base = min(52 + ((index - 1) * 10), 82)
            _notify_progress(
                progress_callback,
                candidate_base,
                "official_document",
                min(candidate_base + 3, 92),
                8,
            )
            official_path = work_dir / f"official-{index}{suffixes[candidate_type]}"
            official_path.write_bytes(body)
            metrics = {"candidate_index": index, "text_source": "ocr"}
            candidate_started = time.monotonic()
            official_lines: list[dict] = []
            if candidate_type == "application/pdf":
                text_started = time.monotonic()
                official_lines = extract_pdf_text_lines(
                    official_path, settings.max_pdf_pages
                )
                metrics["pdf_text_layer_seconds"] = round(
                    time.monotonic() - text_started, 3
                )
                if has_usable_text_layer(
                    official_lines, settings.pdf_text_layer_min_characters
                ):
                    metrics["text_source"] = "pdf_text_layer"
                else:
                    official_lines = []

            official_pages_dir = work_dir / f"official-{index}-pages"
            if not official_lines:
                render_started = time.monotonic()
                first_pages = render_pages(
                    official_path, candidate_type, official_pages_dir,
                    settings.max_pdf_pages,
                    page_indices=(0,) if candidate_type == "application/pdf" else None,
                )
                metrics["first_page_render_seconds"] = round(time.monotonic() - render_started, 3)
                ocr_started = time.monotonic()
                first_ocr = _ocr_document(
                    official_pages_dir, work_dir / f"official-{index}-prefix",
                    settings, candidate_deadline,
                    ocr_session,
                )
                metrics["first_page_ocr_seconds"] = round(time.monotonic() - ocr_started, 3)
                official_lines = first_ocr["lines"]
                if candidate_type == "application/pdf":
                    page_count = pdf_page_count(official_path, settings.max_pdf_pages)
                    if page_count > 1:
                        remaining_dir = work_dir / f"official-{index}-remaining-pages"
                        render_started = time.monotonic()
                        render_pages(
                            official_path, candidate_type, remaining_dir,
                            settings.max_pdf_pages,
                            page_indices=tuple(range(1, page_count)),
                        )
                        metrics["remaining_render_seconds"] = round(
                            time.monotonic() - render_started, 3
                        )
                        ocr_started = time.monotonic()
                        remaining_ocr = _ocr_document(
                            remaining_dir, work_dir / f"official-{index}-remaining",
                            settings, candidate_deadline,
                            ocr_session,
                        )
                        metrics["remaining_ocr_seconds"] = round(
                            time.monotonic() - ocr_started, 3
                        )
                        for line in remaining_ocr["lines"]:
                            merged = dict(line)
                            merged["id"] = len(official_lines) + 1
                            merged["page"] = int(merged.get("page", 1)) + 1
                            official_lines.append(merged)
            _notify_progress(
                progress_callback,
                min(candidate_base + 3, 88),
                "official_ocr",
                min(candidate_base + 20, 92),
                90,
            )
            official_ocr = {"lines": official_lines, "line_count": len(official_lines)}
            comparison = compare_ocr_texts(
                uploaded_ocr["lines"],
                official_ocr["lines"],
                match_threshold=settings.minimum_match_confidence,
            )
            judgment = None
            if needs_qwen_review(comparison, settings):
                # Qwen and PaddleOCR must not coexist on the 8 GB target.
                ocr_session.close()
                qwen_start = min(candidate_base + 20, 92)
                _notify_progress(
                    progress_callback,
                    qwen_start,
                    "qwen_judgment",
                    min(candidate_base + 38, 97),
                    settings.qwen_timeout_seconds,
                )
                try:
                    judgment = judge_texts(
                        comparison["uploaded_text"],
                        comparison["official_text"],
                        comparison["differences"],
                        settings,
                        timeout_seconds=min(
                            settings.qwen_timeout_seconds,
                            _remaining_seconds(candidate_deadline),
                        ),
                        overall_similarity=comparison["match_confidence"],
                    )
                except TextJudgeTimeout as exc:
                    raise SearchDeadlineExceeded(str(exc)) from exc
                except TextJudgeError:
                    raise
            comparison = finalize_hybrid_decision(
                comparison,
                settings,
                judgment,
            )
            _notify_progress(
                progress_callback,
                min(candidate_base + (38 if judgment else 22), 97),
                "official_search",
                min(candidate_base + (41 if judgment else 25), 98),
                15,
            )
            metrics["total_seconds"] = round(time.monotonic() - candidate_started, 3)
            metrics["stopped_after_prefix"] = False
            candidate_timings.append(metrics)
            return {
                "official": {
                    "source": metadata,
                    "line_count": official_ocr["line_count"],
                    "text_source": metrics["text_source"],
                },
                "comparison": comparison,
            }

        phase_started = time.monotonic()
        search = search_official_documents(
            confirmed[0],
            settings,
            evaluate_document,
            deadline=deadline,
        )
        phase_timings["official_search"] = time.monotonic() - phase_started
        _notify_progress(progress_callback, 98, "finalizing", 99, 8)
        selected = search.pop("selected_evaluation")
        response.update(search)
        if selected:
            response["official"] = selected["official"]
            response["comparison"] = selected["comparison"]
        return _finish_timings(response, started, phase_timings, candidate_timings)
