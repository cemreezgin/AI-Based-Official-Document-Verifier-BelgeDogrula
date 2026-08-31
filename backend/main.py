from __future__ import annotations

import asyncio
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from ollama import Client
from documents import DocumentError, save_upload
from official_search import SearchDeadlineExceeded
from ocr_adapter import OCRError
from pipeline import verify_document
from progress import ProgressRegistry
from qwen_text_judge import TextJudgeError
from settings import settings


app = FastAPI(
    title="BelgeDoğrula API",
    version="0.1.0",
    description="Yerel QR, PaddleOCR ve birebir metin karşılaştırma servisi.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Filename", "X-Request-ID"],
)
_pipeline_lock = asyncio.Semaphore(1)
_progress = ProgressRegistry()
_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,80}$")


@app.get("/health")
def health() -> dict:
    ollama_status = "unavailable"
    try:
        models = Client(host=settings.ollama_host, timeout=2.0).list().models
        ollama_status = (
            "ready"
            if any(item.model == settings.ollama_model for item in models)
            else "model_missing"
        )
    except Exception:
        pass
    return {
        "status": "ok",
        "comparison_mode": "hybrid_similarity_with_qwen_gray_zone",
        "qwen_review_min_similarity": settings.qwen_review_min_similarity,
        "auto_match_similarity": settings.auto_match_similarity,
        "candidate_prefix_lines": settings.candidate_prefix_lines,
        "candidate_prefix_similarity": settings.candidate_prefix_similarity,
        "ollama": ollama_status,
        "ollama_model": settings.ollama_model,
        "pipeline_concurrency": 1,
    }


@app.get("/api/v1/progress/{request_id}")
def verification_progress(request_id: str) -> dict:
    if not _REQUEST_ID.fullmatch(request_id):
        raise HTTPException(status_code=400, detail="Geçersiz işlem kimliği.")
    snapshot = _progress.snapshot(request_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="İlerleme kaydı bulunamadı.")
    return snapshot


@app.post("/api/v1/verify")
async def verify(request: Request) -> dict:
    request_id = request.headers.get("x-request-id", "")
    tracking = bool(_REQUEST_ID.fullmatch(request_id))
    if tracking:
        _progress.start(request_id)
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > settings.max_upload_bytes:
            if tracking:
                _progress.fail(request_id)
            raise HTTPException(status_code=413, detail="Dosya 15 MB sınırını aşıyor.")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        if tracking:
            _progress.fail(request_id)
        raise HTTPException(status_code=400, detail="Dosya boş.")

    try:
        with TemporaryDirectory(prefix="belgedogrula-upload-") as temp:
            path, media_type = save_upload(
                data,
                request.headers.get("content-type"),
                Path(temp),
            )
            async with _pipeline_lock:
                result = await run_in_threadpool(
                    verify_document,
                    path,
                    media_type,
                    settings,
                    (
                        lambda percent, phase, ceiling, expected: _progress.update(
                            request_id,
                            percent,
                            phase,
                            ceiling,
                            expected,
                        )
                    )
                    if tracking
                    else None,
                )
                if tracking:
                    _progress.complete(request_id)
                return result
    except DocumentError as exc:
        if tracking:
            _progress.fail(request_id)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OCRError as exc:
        if tracking:
            _progress.fail(request_id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except TextJudgeError as exc:
        if tracking:
            _progress.fail(request_id)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SearchDeadlineExceeded as exc:
        if tracking:
            _progress.fail(request_id)
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        if tracking:
            _progress.fail(request_id)
        raise HTTPException(
            status_code=500,
            detail=f"Belge işlenemedi: {type(exc).__name__}: {exc}",
        ) from exc
