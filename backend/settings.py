from __future__ import annotations

import os
from dataclasses import dataclass


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen3:4b")
    paddleocr_executable: str = os.getenv("PADDLEOCR_EXECUTABLE", "paddleocr")
    paddleocr_device: str = os.getenv("PADDLEOCR_DEVICE", "cpu")
    paddleocr_engine: str = os.getenv("PADDLEOCR_ENGINE", "transformers")
    paddleocr_version: str = os.getenv("PADDLEOCR_VERSION", "PP-OCRv6")
    paddleocr_warm_worker: bool = _boolean("PADDLEOCR_WARM_WORKER", True)
    ocr_denoise_min_score: float = float(os.getenv("OCR_DENOISE_MIN_SCORE", "3.5"))
    enable_restormer: bool = _boolean("ENABLE_RESTORMER", True)
    fetch_official_document: bool = _boolean("FETCH_OFFICIAL_DOCUMENT", True)
    max_upload_bytes: int = int(os.getenv("MAX_UPLOAD_MB", "15")) * 1024 * 1024
    max_pdf_pages: int = int(os.getenv("MAX_PDF_PAGES", "10"))
    max_official_documents: int = int(os.getenv("MAX_OFFICIAL_DOCUMENTS", "5"))
    max_official_depth: int = int(os.getenv("MAX_OFFICIAL_DEPTH", "2"))
    max_official_urls: int = int(os.getenv("MAX_OFFICIAL_URLS", "12"))
    max_official_redirects: int = int(os.getenv("MAX_OFFICIAL_REDIRECTS", "3"))
    max_official_download_bytes: int = (
        int(os.getenv("MAX_OFFICIAL_DOWNLOAD_MB", "20")) * 1024 * 1024
    )
    official_request_timeout_seconds: float = float(
        os.getenv("OFFICIAL_REQUEST_TIMEOUT_SECONDS", "15")
    )
    max_total_processing_seconds: float = float(
        os.getenv("MAX_TOTAL_PROCESSING_SECONDS", "1800")
    )
    ocr_timeout_seconds: float = float(os.getenv("OCR_TIMEOUT_SECONDS", "600"))
    qwen_timeout_seconds: float = float(os.getenv("QWEN_TIMEOUT_SECONDS", "120"))
    qwen_review_min_similarity: float = float(
        os.getenv("QWEN_REVIEW_MIN_SIMILARITY", "0.75")
    )
    auto_match_similarity: float = float(
        os.getenv("AUTO_MATCH_SIMILARITY", "0.85")
    )
    candidate_prefix_lines: int = int(os.getenv("CANDIDATE_PREFIX_LINES", "12"))
    candidate_prefix_similarity: float = float(
        os.getenv("CANDIDATE_PREFIX_SIMILARITY", "0.35")
    )
    pdf_text_layer_min_characters: int = int(
        os.getenv("PDF_TEXT_LAYER_MIN_CHARACTERS", "80")
    )
    minimum_text_similarity: float = float(
        os.getenv("MINIMUM_TEXT_SIMILARITY", "0.55")
    )
    minimum_match_confidence: float = float(
        os.getenv("MINIMUM_MATCH_CONFIDENCE", "0.80")
    )
    allowed_origins: tuple[str, ...] = tuple(
        item.strip()
        for item in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
        if item.strip()
    )

    def __post_init__(self) -> None:
        positive_limits = {
            "max_upload_bytes": self.max_upload_bytes,
            "max_pdf_pages": self.max_pdf_pages,
            "max_official_documents": self.max_official_documents,
            "max_official_urls": self.max_official_urls,
            "max_official_redirects": self.max_official_redirects,
            "candidate_prefix_lines": self.candidate_prefix_lines,
            "pdf_text_layer_min_characters": self.pdf_text_layer_min_characters,
            "max_official_download_bytes": self.max_official_download_bytes,
            "official_request_timeout_seconds": self.official_request_timeout_seconds,
            "max_total_processing_seconds": self.max_total_processing_seconds,
            "ocr_timeout_seconds": self.ocr_timeout_seconds,
            "qwen_timeout_seconds": self.qwen_timeout_seconds,
            "ocr_denoise_min_score": self.ocr_denoise_min_score,
        }
        for name, value in positive_limits.items():
            if value <= 0:
                raise ValueError(f"{name} sıfırdan büyük olmalıdır.")
        if self.max_official_depth < 0:
            raise ValueError("max_official_depth negatif olamaz.")
        for name, value in {
            "minimum_text_similarity": self.minimum_text_similarity,
            "minimum_match_confidence": self.minimum_match_confidence,
            "qwen_review_min_similarity": self.qwen_review_min_similarity,
            "auto_match_similarity": self.auto_match_similarity,
            "candidate_prefix_similarity": self.candidate_prefix_similarity,
        }.items():
            if not 0 <= value <= 1:
                raise ValueError(f"{name} 0 ile 1 arasında olmalıdır.")
        if self.qwen_review_min_similarity >= self.auto_match_similarity:
            raise ValueError(
                "QWEN_REVIEW_MIN_SIMILARITY, AUTO_MATCH_SIMILARITY değerinden "
                "küçük olmalıdır."
            )


settings = Settings()
