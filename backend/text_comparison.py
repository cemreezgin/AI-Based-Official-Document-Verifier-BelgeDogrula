from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher


def _document_text(lines: list[dict]) -> str:
    return "\n".join(
        str(line.get("text", "")).strip()
        for line in lines
        if str(line.get("text", "")).strip()
    )


def _spaced_tokens(text: str) -> list[str]:
    # Keep original whitespace for display, but do not let line wrapping or
    # repeated spaces turn otherwise identical content into a mismatch.
    return re.findall(r"\S+\s*", text)


_TURKISH_EQUIVALENTS = str.maketrans(
    {
        "ı": "i",
        "İ": "i",
        "ğ": "g",
        "Ğ": "g",
        "ş": "s",
        "Ş": "s",
        "ç": "c",
        "Ç": "c",
        "ö": "o",
        "Ö": "o",
        "ü": "u",
        "Ü": "u",
    }
)


def _comparison_key(token: str) -> str:
    translated = token.translate(_TURKISH_EQUIVALENTS).casefold()
    return re.sub(r"[^a-z0-9]+", "", translated)


def _comparison_tokens(tokens: list[str]) -> tuple[list[str], list[str]]:
    visible: list[str] = []
    keys: list[str] = []
    for token in tokens:
        key = _comparison_key(token)
        if not key:
            continue
        visible.append(token)
        keys.append(key)
    return visible, keys


def _bag_similarity(uploaded: list[str], official: list[str]) -> float:
    if not uploaded or not official:
        return 0.0
    common = sum((Counter(uploaded) & Counter(official)).values())
    return (2.0 * common) / (len(uploaded) + len(official))


def _character_similarity(uploaded: list[str], official: list[str]) -> float:
    """Tolerate isolated OCR glyph errors without ignoring document order."""
    if not uploaded or not official:
        return 0.0
    return SequenceMatcher(
        None,
        "".join(uploaded),
        "".join(official),
        autojunk=False,
    ).ratio()


def _fuzzy_token_similarity(uploaded: list[str], official: list[str]) -> float:
    """Fuzzy-match alphabetic OCR words; numeric tokens remain exact-only."""
    if not uploaded or not official:
        return 0.0
    remaining = set(range(len(official)))
    score = 0.0
    for token in uploaded:
        best_index = None
        best_ratio = 0.0
        for index in remaining:
            candidate = official[index]
            if token == candidate:
                ratio = 1.0
            elif any(char.isdigit() for char in token + candidate):
                ratio = 0.0
            elif min(len(token), len(candidate)) < 4:
                ratio = 0.0
            else:
                ratio = SequenceMatcher(None, token, candidate, autojunk=False).ratio()
                if ratio < 0.80:
                    ratio = 0.0
            if ratio > best_ratio:
                best_index, best_ratio = index, ratio
        if best_index is not None:
            remaining.remove(best_index)
            score += best_ratio
    return (2.0 * score) / (len(uploaded) + len(official))


def _append_segment(segments: list[dict], text: str, status: str) -> None:
    if not text:
        return
    if segments and segments[-1]["status"] == status:
        segments[-1]["text"] += text
    else:
        segments.append({"text": text, "status": status})


def compare_ocr_texts(
    uploaded_lines: list[dict],
    official_lines: list[dict],
    *,
    match_threshold: float = 0.80,
) -> dict:
    """Compare normalized OCR content and decide using one overall threshold."""
    if not 0 <= match_threshold <= 1:
        raise ValueError("match_threshold 0 ile 1 arasında olmalıdır.")
    uploaded_text = _document_text(uploaded_lines)
    official_text = _document_text(official_lines)
    uploaded_tokens, uploaded_keys = _comparison_tokens(
        _spaced_tokens(uploaded_text)
    )
    official_tokens, official_keys = _comparison_tokens(
        _spaced_tokens(official_text)
    )
    matcher = SequenceMatcher(None, uploaded_keys, official_keys, autojunk=False)

    uploaded_segments: list[dict] = []
    official_segments: list[dict] = []
    differences: list[dict] = []
    matching_tokens = 0

    for tag, uploaded_start, uploaded_end, official_start, official_end in matcher.get_opcodes():
        uploaded_part = "".join(uploaded_tokens[uploaded_start:uploaded_end])
        official_part = "".join(official_tokens[official_start:official_end])
        if tag == "equal":
            matching_tokens += uploaded_end - uploaded_start
            _append_segment(uploaded_segments, uploaded_part, "equal")
            _append_segment(official_segments, official_part, "equal")
            continue

        _append_segment(uploaded_segments, uploaded_part, "different")
        _append_segment(official_segments, official_part, "different")
        differences.append(
            {
                "type": tag,
                "uploaded": uploaded_part.strip() or None,
                "official": official_part.strip() or None,
                "uploaded_token_range": [uploaded_start, uploaded_end],
                "official_token_range": [official_start, official_end],
            }
        )

    has_text = bool(uploaded_keys and official_keys)
    exact_match = has_text and uploaded_keys == official_keys
    ordered_similarity = matcher.ratio() if has_text else 0.0
    bag_similarity = _bag_similarity(uploaded_keys, official_keys) if has_text else 0.0
    character_similarity = (
        _character_similarity(uploaded_keys, official_keys) if has_text else 0.0
    )
    fuzzy_token_similarity = (
        _fuzzy_token_similarity(uploaded_keys, official_keys) if has_text else 0.0
    )
    similarity = max(ordered_similarity, bag_similarity, fuzzy_token_similarity)
    matched = has_text and similarity >= match_threshold
    return {
        "mode": "direct_text",
        "decision": "match" if matched else "mismatch",
        "matched": matched,
        "exact_match": exact_match,
        "match_confidence": round(similarity, 4),
        "confidence": round(similarity, 4),
        "match_threshold": match_threshold,
        "ordered_similarity": round(ordered_similarity, 4),
        "bag_similarity": round(bag_similarity, 4),
        "character_similarity": round(character_similarity, 4),
        "fuzzy_token_similarity": round(fuzzy_token_similarity, 4),
        "normalization": "turkish_character_case_punctuation_whitespace_ocr_glyph_tolerance",
        "compared_token_count": max(len(uploaded_keys), len(official_keys)),
        "matching_token_count": matching_tokens,
        "difference_count": len(differences),
        "uploaded_line_count": len(uploaded_lines),
        "official_line_count": len(official_lines),
        "uploaded_text": uploaded_text,
        "official_text": official_text,
        "uploaded_segments": uploaded_segments,
        "official_segments": official_segments,
        "differences": differences,
    }


def compare_ocr_prefixes(
    uploaded_lines: list[dict],
    official_lines: list[dict],
    *,
    max_lines: int = 12,
    match_threshold: float = 0.35,
) -> dict:
    """Check whether the first meaningful OCR lines begin matching."""
    if max_lines <= 0:
        raise ValueError("max_lines sıfırdan büyük olmalıdır.")
    comparison = compare_ocr_texts(
        uploaded_lines[:max_lines],
        official_lines[:max_lines],
        match_threshold=match_threshold,
    )
    return {
        "matched": comparison["matched"],
        "similarity": comparison["match_confidence"],
        "threshold": match_threshold,
        "line_limit": max_lines,
        "uploaded_line_count": comparison["uploaded_line_count"],
        "official_line_count": comparison["official_line_count"],
    }
