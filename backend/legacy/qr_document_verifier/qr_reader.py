"""OpenCV, ZXing-C++ ve ZBar ile uzlaşmalı QR okuma."""
from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterator
from collections import defaultdict
from itertools import combinations
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
import zxingcpp
from image_restoration import (
    decoder_ready_variants,
    measure_quality,
    opencv_restoration_variants,
)
from restormer_adapter import available_tasks, restore as restormer_restore

if sys.platform == "darwin":
    for directory in (
        Path("/opt/homebrew/opt/zbar/lib"),
        Path("/usr/local/opt/zbar/lib"),
    ):
        if (directory / "libzbar.dylib").exists():
            key = "DYLD_FALLBACK_LIBRARY_PATH"
            paths = [p for p in os.environ.get(key, "").split(":") if p]
            if str(directory) not in paths:
                os.environ[key] = ":".join([str(directory), *paths])
            break

from pyzbar.pyzbar import ZBarSymbol  # noqa: E402
from pyzbar.pyzbar import decode as zbar_decode  # noqa: E402


@dataclass(frozen=True)
class DecoderOutput:
    decoder: str
    contents: list[str]
    error: str | None = None
    recovery_used: bool = False
    recovery_method: str | None = None


@dataclass(frozen=True)
class QRReport:
    status: str
    confirmed_contents: list[str]
    candidates: list[dict[str, object]]
    decoder_outputs: list[DecoderOutput]
    minimum_agreement: int = 2
    image_quality: dict[str, float | str] | None = None
    restoration: dict[str, object] | None = None
    diagnostics: list[dict[str, str]] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _opencv(image) -> list[str]:
    detector = cv2.QRCodeDetector()
    values: list[str] = []
    try:
        found, decoded, _, _ = detector.detectAndDecodeMulti(image)
        if found:
            values.extend(decoded)
    except cv2.error:
        pass
    text, _, _ = detector.detectAndDecode(image)
    if text:
        values.append(text)
    return _unique(values)


def _zxing(image) -> list[str]:
    return _unique(
        [
            result.text
            for result in zxingcpp.read_barcodes(
                image,
                formats=zxingcpp.BarcodeFormat.QRCode,
                return_errors=False,
            )
        ]
    )


def _zbar(image) -> list[str]:
    return _unique(
        [
            result.data.decode("utf-8")
            for result in zbar_decode(image, symbols=[ZBarSymbol.QRCODE])
        ]
    )


READERS = {"opencv": _opencv, "zxing": _zxing, "zbar": _zbar}


def _attempt(name: str, image) -> DecoderOutput:
    try:
        return DecoderOutput(name, READERS[name](image))
    except Exception as exc:
        return DecoderOutput(name, [], f"{type(exc).__name__}: {exc}")


def _vote_count(outputs: list[DecoderOutput]) -> int:
    votes: dict[str, set[str]] = defaultdict(set)
    for output in outputs:
        for value in output.contents:
            votes[value].add(output.decoder)
    return max((len(voters) for voters in votes.values()), default=0)


def _finder_pattern_regions(image) -> Iterator:
    """Üç QR köşe işaretini iç içe konturlardan yaklaşık olarak bulur."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )[1]
    contours, hierarchy = cv2.findContours(
        binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE
    )
    if hierarchy is None:
        return

    boxes = []
    for index, contour in enumerate(contours):
        x, y, width, height = cv2.boundingRect(contour)
        child_depth = 0
        child = index
        while hierarchy[0][child][2] != -1:
            child_depth += 1
            child = hierarchy[0][child][2]
        ratio = width / max(height, 1)
        if child_depth >= 2 and 0.7 <= ratio <= 1.4 and width >= 8:
            boxes.append((x, y, width, height, child_depth))

    image_height, image_width = image.shape[:2]
    ranked = []
    for group in combinations(boxes, 3):
        sizes = [max(box[2], box[3]) for box in group]
        if max(sizes) > min(sizes) * 1.6:
            continue
        centers = np.array(
            [
                (box[0] + box[2] / 2, box[1] + box[3] / 2)
                for box in group
            ],
            dtype=np.float32,
        )
        first = centers[1] - centers[0]
        second = centers[2] - centers[0]
        triangle_area = abs(
            float(first[0] * second[1] - first[1] * second[0])
        ) / 2
        mean_size = sum(sizes) / len(sizes)
        if triangle_area < mean_size * mean_size * 2:
            continue
        span_x = float(np.ptp(centers[:, 0]))
        span_y = float(np.ptp(centers[:, 1]))
        if min(span_x, span_y) < mean_size * 2:
            continue
        pad = int(round(mean_size * 1.1))
        x1 = max(0, min(box[0] for box in group) - pad)
        y1 = max(0, min(box[1] for box in group) - pad)
        x2 = min(
            image_width,
            max(box[0] + box[2] for box in group) + pad,
        )
        y2 = min(
            image_height,
            max(box[1] + box[3] for box in group) + pad,
        )
        score = triangle_area * sum(box[4] for box in group)
        ranked.append((score, x1, y1, x2, y2))

    seen = set()
    for _, x1, y1, x2, y2 in sorted(ranked, reverse=True):
        key = (x1 // 20, y1 // 20, x2 // 20, y2 // 20)
        if key in seen:
            continue
        seen.add(key)
        yield image[y1:y2, x1:x2]
        if len(seen) >= 3:
            break


def _regions(image):
    yield from _finder_pattern_regions(image)
    yield from _grid_regions(image)


def _grid_regions(image):
    height, width = image.shape[:2]
    crop_h, crop_w = int(height * 0.4), int(width * 0.4)
    ys = (height - crop_h, 0, (height - crop_h) // 2)
    xs = (width - crop_w, 0, (width - crop_w) // 2)
    order = (
        (ys[0], xs[0]), (ys[0], xs[1]), (ys[1], xs[0]), (ys[1], xs[1]),
        (ys[2], xs[2]), (ys[1], xs[2]), (ys[0], xs[2]),
        (ys[2], xs[1]), (ys[2], xs[0]),
    )
    for y, x in dict.fromkeys(order):
        yield image[y:y + crop_h, x:x + crop_w]


def _ai_regions(image):
    detected = list(_finder_pattern_regions(image))
    if detected:
        yield from detected
        return
    for index, region in enumerate(_grid_regions(image)):
        if index >= 3:
            break
        yield region


def _invalid_qr_diagnostics(image) -> list[dict[str, str]]:
    """Geçersiz kısmi içeriği kabul etmeden QR bütünlük hatasını bildirir."""
    diagnostics: list[dict[str, str]] = []
    for region in _ai_regions(image):
        try:
            results = zxingcpp.read_barcodes(
                region,
                formats=zxingcpp.BarcodeFormat.QRCode,
                return_errors=True,
                try_rotate=True,
                try_downscale=True,
                try_invert=True,
            )
        except Exception:
            continue
        for result in results:
            if result.valid or result.format != zxingcpp.BarcodeFormat.QRCode:
                continue
            error_type = str(result.error.type).rsplit(".", 1)[-1].lower()
            item = {
                "decoder": "zxing",
                "code": f"invalid_{error_type}",
                "message": (
                    "QR bulundu ancak hata düzeltme/bütünlük kontrolü geçmedi."
                    if error_type == "checksum"
                    else "QR bulundu ancak teknik olarak geçerli biçimde çözülemedi."
                ),
            }
            if item not in diagnostics:
                diagnostics.append(item)
    return diagnostics


def _variants(image):
    for region in _regions(image):
        nearest = cv2.resize(
            region, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST
        )
        yield nearest
        cubic = cv2.resize(
            region, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC
        )
        yield cubic
        gray = cv2.cvtColor(cubic, cv2.COLOR_BGR2GRAY)
        yield cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        yield cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 31, 7
        )


def _recover(
    image,
    direct: list[DecoderOutput],
    enable_restormer: bool = False,
    progress: Callable[[str], None] | None = None,
) -> list[DecoderOutput]:
    values = {item.decoder: list(item.contents) for item in direct}
    errors = {item.decoder: item.error for item in direct}
    methods: dict[str, str | None] = {name: None for name in READERS}
    for variant in _variants(image):
        for name, reader in READERS.items():
            if values[name]:
                continue
            try:
                found = reader(variant)
            except Exception as exc:
                errors[name] = errors[name] or f"{type(exc).__name__}: {exc}"
                continue
            if found:
                values[name], errors[name], methods[name] = (
                    _unique(found), None, "opencv_fast_recovery"
                )
        if all(values.values()):
            break
    if _vote_from_values(values) < 2:
        for region in _regions(image):
            region_quality = measure_quality(region)
            for restored in opencv_restoration_variants(region, region_quality):
                for variant in decoder_ready_variants(restored):
                    for name, reader in READERS.items():
                        if values[name]:
                            continue
                        try:
                            found = reader(variant.image)
                        except Exception as exc:
                            errors[name] = (
                                errors[name] or f"{type(exc).__name__}: {exc}"
                            )
                            continue
                        if found:
                            values[name], errors[name], methods[name] = (
                                _unique(found), None, variant.name
                            )
                    if all(values.values()):
                        break
                if all(values.values()):
                    break
            if all(values.values()):
                break
    if enable_restormer and _vote_from_values(values) < 2:
        tasks = available_tasks()
        if progress:
            progress(
                "OpenCV QR'ı doğrulayamadı; Restormer geri dönüşü başlatılıyor."
            )
        # İlk bölgeler konturla bulunan QR adaylarıdır; işlem süresi sınırlandırılır.
        ai_regions = list(_ai_regions(image))
        total_regions = len(ai_regions)
        for region_index, region in enumerate(ai_regions):
            for task in tasks:
                if progress:
                    progress(
                        f"Restormer {task}: aday bölge {region_index + 1}/"
                        f"{total_regions} "
                        "işleniyor..."
                    )
                try:
                    restored = restormer_restore(region, task)
                except Exception as exc:
                    for name in READERS:
                        errors[name] = errors[name] or (
                            f"Restormer {task}: {type(exc).__name__}: {exc}"
                        )
                    continue
                candidates = (
                    restored,
                    cv2.resize(
                        restored,
                        None,
                        fx=2,
                        fy=2,
                        interpolation=cv2.INTER_CUBIC,
                    ),
                )
                for candidate in candidates:
                    for name, reader in READERS.items():
                        if values[name]:
                            continue
                        try:
                            found = reader(candidate)
                        except Exception as exc:
                            errors[name] = (
                                errors[name] or f"{type(exc).__name__}: {exc}"
                            )
                            continue
                        if found:
                            values[name], errors[name], methods[name] = (
                                _unique(found), None, f"restormer_{task}"
                            )
                    if _vote_from_values(values) >= 2:
                        break
                if _vote_from_values(values) >= 2:
                    break
            if _vote_from_values(values) >= 2:
                break
    return [
        DecoderOutput(
            name,
            values[name],
            errors[name],
            recovery_used=methods[name] is not None,
            recovery_method=methods[name],
        )
        for name in READERS
    ]


def _vote_from_values(values: dict[str, list[str]]) -> int:
    votes: dict[str, set[str]] = defaultdict(set)
    for decoder, contents in values.items():
        for value in contents:
            votes[value].add(decoder)
    return max((len(voters) for voters in votes.values()), default=0)


def read_qr_image(
    path: str | Path,
    minimum_agreement: int = 2,
    enable_restormer: bool = True,
    progress: Callable[[str], None] | None = None,
) -> QRReport:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Görüntü bulunamadı: {source}")
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Görüntü açılamadı: {source}")
    outputs = [_attempt(name, image) for name in READERS]
    if _vote_count(outputs) < minimum_agreement:
        outputs = _recover(
            image,
            outputs,
            enable_restormer=enable_restormer,
            progress=progress,
        )
    votes: dict[str, set[str]] = defaultdict(set)
    for output in outputs:
        for value in output.contents:
            votes[value].add(output.decoder)
    candidates = sorted(
        [
            {"content": value, "decoders": sorted(voters), "vote_count": len(voters)}
            for value, voters in votes.items()
        ],
        key=lambda item: (-item["vote_count"], item["content"]),
    )
    confirmed = [
        item["content"] for item in candidates
        if item["vote_count"] >= minimum_agreement
    ]
    diagnostics = _invalid_qr_diagnostics(image) if not confirmed else []
    status = (
        "confirmed" if confirmed else "conflict" if len(candidates) > 1
        else "single_decoder" if candidates else "corrupted" if diagnostics
        else "not_found"
    )
    first_candidate = next(_ai_regions(image), image)
    quality = measure_quality(first_candidate).to_dict()
    quality["scope"] = "first_qr_candidate_region"
    restormer_tasks = available_tasks() if enable_restormer else []
    return QRReport(
        status,
        confirmed,
        candidates,
        outputs,
        minimum_agreement,
        image_quality=quality,
        restoration={
            "opencv_enabled": True,
            "restormer_enabled": enable_restormer,
            "restormer_available_tasks": restormer_tasks,
            "restormer_used": any(
                (output.recovery_method or "").startswith("restormer_")
                for output in outputs
            ),
        },
        diagnostics=diagnostics,
    )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument(
        "--restormer",
        dest="restormer",
        action="store_true",
        help="Uyumluluk seçeneği; Restormer artık varsayılan olarak otomatiktir.",
    )
    parser.add_argument(
        "--no-restormer",
        dest="restormer",
        action="store_false",
        help="Restormer geri dönüşünü kapat.",
    )
    parser.set_defaults(restormer=True)
    args = parser.parse_args()
    progress = lambda message: print(message, file=sys.stderr, flush=True)
    report = read_qr_image(
        args.image,
        enable_restormer=args.restormer,
        progress=progress,
    )
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    raise SystemExit(0 if report.status == "confirmed" else 2)
