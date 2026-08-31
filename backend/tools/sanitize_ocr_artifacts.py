"""Replace legacy OCR output artifacts with coordinate-preserving fake data.

The protected legacy implementation is not modified. This one-shot adapter
keeps only detection polygons and non-content model metadata, replaces every
recognized string, redraws the visualization, and removes the source artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin


ROOT = Path(__file__).resolve().parents[1]
LEGACY_DIR = ROOT / "legacy" / "paddleocr_qwen"
OUTPUT_DIR = LEGACY_DIR / "output"
ARTIFACTS = (
    (
        OUTPUT_DIR / "dsi_yazisi_res.json",
        OUTPUT_DIR / "dsi_yazisi_ocr_res_img.png",
        "synthetic_document_a",
    ),
    (
        OUTPUT_DIR / "ust_yazili_emlak_beyan_res.json",
        OUTPUT_DIR / "ust_yazili_emlak_beyan_ocr_res_img.png",
        "synthetic_document_b",
    ),
)

SYNTHETIC_TEXT = (
    "SENTETİK TEST BELGESİ",
    "T.C. TEST KURUMU",
    "ÖRNEK EVRAK BİRİMİ",
    "BELGE NO: TEST-2030-0001",
    "TEST TARİHİ: 01.01.2030",
    "KONU: ÖRNEK İŞLEM",
    "SAYIN ÖRNEK KİŞİ",
    "TEST ALICI KURUMU",
    "İLGİ: TEST-BAŞVURU-0001",
    "ÖRNEK MAH. 100 ADA 10 PARSEL",
    "Bu satır yalnızca sentetik test verisidir.",
    "Koordinat kutusu doğrulama örneğidir.",
    "Gerçek kişi veya kurum bilgisi içermez.",
    "TEST SOK. NO:10 ÖRNEKŞEHİR",
    "ÖRNEK AÇIKLAMA SATIRI",
    "Bilgilerinize sunulur.",
    "ÖRNEK YETKİLİ",
    "TEST GÖREVİ",
    "EK: SENTETİK BELGE",
    "DOĞRULAMA KODU: TEST-KOD-0001",
    "DOĞRULAMA ADRESİ: https://example.invalid/test",
    "TEST TELEFONU: 000 000 00 00",
    "TEST E-POSTA: test@example.invalid",
    "DAĞITIM: TEST BİRİMİ",
)

COLORS = (
    (65, 161, 222),
    (91, 190, 150),
    (173, 142, 214),
    (231, 155, 92),
    (213, 104, 119),
    (139, 177, 82),
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paths = (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    )
    for path in paths:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fake_lines(count: int) -> list[str]:
    return [
        SYNTHETIC_TEXT[index % len(SYNTHETIC_TEXT)]
        if index < len(SYNTHETIC_TEXT)
        else f"ÖRNEK TEST SATIRI {index + 1:02d}"
        for index in range(count)
    ]


def _bounds(poly: list[list[int]]) -> tuple[int, int, int, int]:
    xs = [point[0] for point in poly]
    ys = [point[1] for point in poly]
    return min(xs), min(ys), max(xs), max(ys)


def _fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    width: int,
    height: int,
) -> tuple[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    size = max(7, min(28, int(height * 0.68)))
    while size > 7:
        font = _font(size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max(8, width - 4):
            return text, font
        size -= 1
    font = _font(7)
    shortened = text
    while len(shortened) > 4:
        candidate = shortened[:-1] + "…"
        box = draw.textbbox((0, 0), candidate, font=font)
        if box[2] - box[0] <= max(8, width - 4):
            return candidate, font
        shortened = shortened[:-1]
    return "TEST", font


def _draw_panel(
    image: Image.Image,
    polygons: list[list[list[int]]],
    texts: list[str],
    x_offset: int,
    filled: bool,
) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    for index, (poly, text) in enumerate(zip(polygons, texts, strict=True)):
        shifted = [(point[0] + x_offset, point[1]) for point in poly]
        color = COLORS[index % len(COLORS)]
        if filled:
            draw.polygon(shifted, fill=(*color, 66), outline=(*color, 220), width=1)
        else:
            draw.line(shifted + [shifted[0]], fill=(*color, 230), width=1)
        left, top, right, bottom = _bounds(poly)
        fitted, font = _fit_text(draw, text, right - left, bottom - top)
        draw.text(
            (left + x_offset + 2, top + 1),
            fitted,
            fill=(24, 37, 54, 255),
            font=font,
        )


def _render_visualization(
    size: tuple[int, int],
    polygons: list[list[list[int]]],
    texts: list[str],
) -> Image.Image:
    width, height = size
    panel_width = width // 2
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image, "RGBA")
    draw.rectangle((0, 0, panel_width - 1, height), fill=(246, 249, 251, 255))
    draw.line((panel_width, 0, panel_width, height), fill=(98, 111, 124, 255), width=2)
    watermark_font = _font(max(28, min(64, panel_width // 16)))
    for offset in (0, panel_width):
        draw.text(
            (offset + panel_width // 2, height // 2),
            "SENTETİK TEST BELGESİ",
            anchor="mm",
            fill=(120, 135, 150, 38),
            font=watermark_font,
        )
    _draw_panel(image, polygons, texts, 0, filled=True)
    _draw_panel(image, polygons, texts, panel_width, filled=False)
    return image


def sanitize() -> list[Path]:
    written: list[Path] = []
    removals: list[Path] = []
    for json_path, image_path, stem in ARTIFACTS:
        new_json = OUTPUT_DIR / f"{stem}_res.json"
        new_image = OUTPUT_DIR / f"{stem}_ocr_res_img.png"
        if not json_path.exists():
            json_path = new_json
        if not image_path.exists():
            image_path = new_image
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        polygons = payload["dt_polys"]
        fake_lines = _fake_lines(len(polygons))
        original_size = Image.open(image_path).size

        payload["input_path"] = f"/synthetic/fixtures/{stem}.png"
        payload["rec_texts"] = fake_lines
        payload["synthetic_fixture"] = True
        payload["privacy_notice"] = "Contains only TEST/ÖRNEK synthetic data."

        new_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        png_info = PngImagePlugin.PngInfo()
        png_info.add_text("Description", "SENTETİK TEST BELGESİ - gerçek veri içermez")
        _render_visualization(original_size, polygons, fake_lines).save(
            new_image,
            pnginfo=png_info,
            optimize=True,
        )
        written.extend((new_json, new_image))
        removals.extend(
            path for path in (json_path, image_path) if path not in (new_json, new_image)
        )

    extracted_path = LEGACY_DIR / "extracted_fields.json"
    extracted = json.loads(extracted_path.read_text(encoding="utf-8"))
    extracted["source_ocr_file"] = "output/synthetic_document_a_res.json"
    extracted["synthetic_fixture"] = True
    extracted_path.write_text(
        json.dumps(extracted, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(extracted_path)

    for path in removals:
        path.unlink()
    return written


if __name__ == "__main__":
    outputs = sanitize()
    print(f"Sanitized {len(outputs)} OCR artifacts without printing document bodies.")
