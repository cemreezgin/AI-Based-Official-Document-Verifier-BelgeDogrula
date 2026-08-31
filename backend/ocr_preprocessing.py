"""Deterministic, content-preserving preparation for noisy OCR page images."""
from __future__ import annotations

import shutil
from pathlib import Path

import cv2


def _noise_score(gray) -> float:
    median = cv2.medianBlur(gray, 3)
    residual = gray.astype("float32") - median.astype("float32")
    import numpy as np

    center = np.median(residual)
    return float(1.4826 * np.median(np.abs(residual - center)))


def prepare_ocr_pages(
    pages_dir: Path,
    output_dir: Path,
    *,
    denoise_min_score: float,
) -> tuple[Path, list[dict]]:
    """Copy clean pages and denoise only objectively noisy pages."""
    output_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict] = []
    for source in sorted(path for path in pages_dir.iterdir() if path.is_file()):
        image = cv2.imread(str(source), cv2.IMREAD_GRAYSCALE)
        if image is None:
            shutil.copy2(source, output_dir / source.name)
            reports.append({"page": source.name, "denoised": False, "noise_score": None})
            continue
        score = _noise_score(image)
        denoised = score >= denoise_min_score
        if denoised:
            target = output_dir / f"{source.stem}.png"
            # Conservative strength removes scan speckles without inventing glyphs.
            prepared = cv2.fastNlMeansDenoising(
                image, None, h=7, templateWindowSize=7, searchWindowSize=21
            )
            cv2.imwrite(str(target), prepared, [cv2.IMWRITE_PNG_COMPRESSION, 3])
        else:
            target = output_dir / source.name
            shutil.copy2(source, target)
        reports.append(
            {"page": source.name, "denoised": denoised, "noise_score": round(score, 2)}
        )
    return output_dir, reports
