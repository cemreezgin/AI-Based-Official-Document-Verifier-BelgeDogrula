from __future__ import annotations

import shutil
import re
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image


class DocumentError(ValueError):
    pass


def detect_type(data: bytes, declared_type: str | None) -> str:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    raise DocumentError(
        f"Desteklenmeyen veya bozuk dosya türü: {declared_type or 'bilinmiyor'}"
    )


def save_upload(data: bytes, declared_type: str | None, directory: Path) -> tuple[Path, str]:
    media_type = detect_type(data, declared_type)
    suffix = {
        "application/pdf": ".pdf",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/tiff": ".tiff",
    }[media_type]
    path = directory / f"uploaded{suffix}"
    path.write_bytes(data)
    return path, media_type


def render_pages(
    source: Path,
    media_type: str,
    output_dir: Path,
    max_pages: int,
    page_indices: tuple[int, ...] | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if media_type.startswith("image/"):
        try:
            with Image.open(source) as image:
                image.verify()
        except Exception as exc:
            raise DocumentError(f"Görüntü doğrulanamadı: {exc}") from exc
        target = output_dir / f"page-001{source.suffix.lower()}"
        shutil.copy2(source, target)
        return [target]

    try:
        document = pdfium.PdfDocument(source)
    except Exception as exc:
        raise DocumentError(f"PDF açılamadı: {exc}") from exc
    if len(document) == 0:
        raise DocumentError("PDF içinde sayfa bulunamadı.")
    if len(document) > max_pages:
        raise DocumentError(f"PDF en fazla {max_pages} sayfa olabilir.")

    selected = page_indices if page_indices is not None else tuple(range(len(document)))
    if any(index < 0 or index >= len(document) for index in selected):
        document.close()
        raise DocumentError("İstenen PDF sayfası bulunamadı.")
    pages: list[Path] = []
    try:
        for index in selected:
            bitmap = document[index].render(scale=2.0)
            image = bitmap.to_pil().convert("RGB")
            target = output_dir / f"page-{index + 1:03d}.png"
            image.save(target, format="PNG", optimize=True)
            pages.append(target)
    finally:
        document.close()
    return pages


def extract_pdf_text_lines(
    source: Path,
    max_pages: int,
    page_indices: tuple[int, ...] | None = None,
) -> list[dict]:
    """Extract an existing PDF text layer without rendering or OCR."""
    try:
        document = pdfium.PdfDocument(source)
    except Exception as exc:
        raise DocumentError(f"PDF açılamadı: {exc}") from exc
    if len(document) == 0:
        document.close()
        raise DocumentError("PDF içinde sayfa bulunamadı.")
    if len(document) > max_pages:
        document.close()
        raise DocumentError(f"PDF en fazla {max_pages} sayfa olabilir.")
    selected = page_indices if page_indices is not None else tuple(range(len(document)))
    if any(index < 0 or index >= len(document) for index in selected):
        document.close()
        raise DocumentError("İstenen PDF sayfası bulunamadı.")
    lines: list[dict] = []
    try:
        for index in selected:
            page = document[index]
            text_page = page.get_textpage()
            try:
                text = text_page.get_text_range()
            finally:
                text_page.close()
                page.close()
            for raw_line in text.splitlines():
                line = re.sub(r"\s+", " ", raw_line).strip()
                if line:
                    lines.append(
                        {
                            "id": len(lines) + 1,
                            "page": index + 1,
                            "text": line,
                            "source": "pdf_text_layer",
                        }
                    )
    finally:
        document.close()
    return lines


def has_usable_text_layer(lines: list[dict], minimum_characters: int) -> bool:
    text = " ".join(str(line.get("text", "")) for line in lines)
    searchable = sum(character.isalnum() for character in text)
    return len(lines) >= 3 and searchable >= minimum_characters


def pdf_page_count(source: Path, max_pages: int) -> int:
    try:
        document = pdfium.PdfDocument(source)
    except Exception as exc:
        raise DocumentError(f"PDF açılamadı: {exc}") from exc
    try:
        count = len(document)
        if count == 0:
            raise DocumentError("PDF içinde sayfa bulunamadı.")
        if count > max_pages:
            raise DocumentError(f"PDF en fazla {max_pages} sayfa olabilir.")
        return count
    finally:
        document.close()
