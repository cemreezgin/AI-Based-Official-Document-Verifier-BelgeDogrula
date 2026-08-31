"""QR okumadan önce güvenli, içerik üretmeyen görüntü iyileştirmeleri."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterator

import cv2
import numpy as np


@dataclass(frozen=True)
class ImageQuality:
    blur_score: float
    noise_score: float
    blur_level: str
    noise_level: str

    def to_dict(self) -> dict[str, float | str]:
        return asdict(self)


@dataclass(frozen=True)
class RestoredVariant:
    name: str
    image: np.ndarray


def _gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def measure_quality(image: np.ndarray) -> ImageQuality:
    """Karar vermek için yaklaşık bulanıklık ve gürültü ölçümleri üretir."""
    gray = _gray(image)
    sample = gray
    longest = max(gray.shape[:2])
    if longest > 1600:
        scale = 1600 / longest
        sample = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    blur_score = float(cv2.Laplacian(sample, cv2.CV_64F).var())
    median = cv2.medianBlur(sample, 3)
    residual = sample.astype(np.float32) - median.astype(np.float32)
    noise_score = float(1.4826 * np.median(np.abs(residual - np.median(residual))))

    blur_level = "high" if blur_score < 120 else "medium" if blur_score < 500 else "low"
    noise_level = "high" if noise_score > 12 else "medium" if noise_score > 5 else "low"
    return ImageQuality(
        blur_score=round(blur_score, 2),
        noise_score=round(noise_score, 2),
        blur_level=blur_level,
        noise_level=noise_level,
    )


def _unsharp(gray: np.ndarray, sigma: float, amount: float) -> np.ndarray:
    softened = cv2.GaussianBlur(gray, (0, 0), sigma)
    return cv2.addWeighted(gray, 1.0 + amount, softened, -amount, 0)


def opencv_restoration_variants(
    image: np.ndarray,
    quality: ImageQuality | None = None,
) -> Iterator[RestoredVariant]:
    """Gürültü ve bulanıklık için sınırlı, deterministik adaylar üretir."""
    quality = quality or measure_quality(image)
    gray = _gray(image)

    # Hafif iyileştirme her zaman denenir; QR modüllerini fazla yumuşatmaz.
    mild_denoise = cv2.fastNlMeansDenoising(gray, None, h=5, templateWindowSize=7)
    yield RestoredVariant("opencv_denoise_mild", mild_denoise)
    yield RestoredVariant(
        "opencv_denoise_mild_unsharp",
        _unsharp(mild_denoise, sigma=1.0, amount=1.1),
    )

    if quality.noise_level in {"medium", "high"}:
        strong_denoise = cv2.fastNlMeansDenoising(
            gray, None, h=9, templateWindowSize=7, searchWindowSize=21
        )
        yield RestoredVariant("opencv_denoise_strong", strong_denoise)
        yield RestoredVariant(
            "opencv_denoise_strong_unsharp",
            _unsharp(strong_denoise, sigma=1.2, amount=1.35),
        )
        yield RestoredVariant(
            "opencv_median_denoise",
            cv2.medianBlur(gray, 3),
        )

    if quality.blur_level in {"medium", "high"}:
        yield RestoredVariant(
            "opencv_unsharp_medium",
            _unsharp(gray, sigma=1.2, amount=1.4),
        )
        yield RestoredVariant(
            "opencv_unsharp_strong",
            _unsharp(gray, sigma=1.8, amount=2.0),
        )


def decoder_ready_variants(
    restored: RestoredVariant,
    upscale: int = 2,
) -> Iterator[RestoredVariant]:
    """İyileştirilmiş görüntüyü QR decoder'ların sevdiği biçimlere dönüştürür."""
    image = restored.image
    enlarged = cv2.resize(
        image, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_CUBIC
    )
    yield RestoredVariant(f"{restored.name}_upscaled", enlarged)
    yield RestoredVariant(
        f"{restored.name}_clahe",
        cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(enlarged),
    )
    yield RestoredVariant(
        f"{restored.name}_adaptive_threshold",
        cv2.adaptiveThreshold(
            enlarged,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            7,
        ),
    )
