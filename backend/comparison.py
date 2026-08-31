from __future__ import annotations

import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher


EXCLUDED_FIELDS = {"ada", "parsel"}
CRITICAL_FIELDS = {"belge_no", "tarih", "duzenleyen_kurum"}


def _normalize(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    value = value.replace("ı", "i")
    return re.sub(r"[^0-9a-z]+", "", value)


def _normalize_field(name: str, value: str | None) -> str:
    normalized = _normalize(value)
    if name == "belge_no":
        normalized = re.sub(r"^(?:sayi|say1)", "", normalized)
    elif name == "duzenleyen_kurum":
        normalized = re.sub(r"^tc", "", normalized)
    return normalized


def reconcile_role_fields(uploaded: dict, official: dict) -> tuple[dict, dict]:
    """Swap reversed official roles only when both cross-pairs strongly agree."""
    corrected = {
        name: {
            "value": payload.get("value"),
            "source_line_ids": list(payload.get("source_line_ids") or []),
        }
        for name, payload in official.items()
    }
    field_names = ("muhatap", "kisi_kurum")
    values = {
        (side, name): _normalize_field(name, source.get(name, {}).get("value"))
        for side, source in (("uploaded", uploaded), ("official", corrected))
        for name in field_names
    }
    if not all(values.values()):
        return corrected, {"roles_swapped": False, "reason": "insufficient_evidence"}

    current_scores = [
        SequenceMatcher(
            None,
            values[("uploaded", name)],
            values[("official", name)],
        ).ratio()
        for name in field_names
    ]
    crossed_scores = [
        SequenceMatcher(
            None,
            values[("uploaded", "muhatap")],
            values[("official", "kisi_kurum")],
        ).ratio(),
        SequenceMatcher(
            None,
            values[("uploaded", "kisi_kurum")],
            values[("official", "muhatap")],
        ).ratio(),
    ]
    current_total = sum(current_scores)
    crossed_total = sum(crossed_scores)
    should_swap = (
        min(crossed_scores) >= 0.90
        and crossed_total - current_total >= 0.35
    )
    if should_swap:
        corrected["muhatap"], corrected["kisi_kurum"] = (
            corrected["kisi_kurum"],
            corrected["muhatap"],
        )
    return corrected, {
        "roles_swapped": should_swap,
        "reason": "cross_pair_match" if should_swap else "roles_retained",
        "current_similarity": round(current_total / 2, 4),
        "cross_similarity": round(crossed_total / 2, 4),
    }


def _text_tokens(lines: list[dict]) -> list[str]:
    tokens: list[str] = []
    for line in lines:
        value = unicodedata.normalize("NFKD", str(line.get("text", "")).casefold())
        value = "".join(
            character for character in value if not unicodedata.combining(character)
        ).replace("ı", "i")
        tokens.extend(re.findall(r"[0-9a-z]+", value))
    return tokens


def compare_ocr_text(uploaded_lines: list[dict], official_lines: list[dict]) -> dict:
    """Deterministically compare OCR evidence without generating missing text."""
    uploaded_tokens = _text_tokens(uploaded_lines)
    official_tokens = _text_tokens(official_lines)
    if not uploaded_tokens or not official_tokens:
        return {
            "similarity": 0.0,
            "token_dice": 0.0,
            "sequence_similarity": 0.0,
            "uploaded_token_count": len(uploaded_tokens),
            "official_token_count": len(official_tokens),
        }

    uploaded_counter = Counter(uploaded_tokens)
    official_counter = Counter(official_tokens)
    shared = sum((uploaded_counter & official_counter).values())
    token_dice = (2 * shared) / (len(uploaded_tokens) + len(official_tokens))
    sequence_similarity = SequenceMatcher(
        None,
        " ".join(uploaded_tokens),
        " ".join(official_tokens),
    ).ratio()
    similarity = (0.7 * token_dice) + (0.3 * sequence_similarity)
    return {
        "similarity": round(similarity, 4),
        "token_dice": round(token_dice, 4),
        "sequence_similarity": round(sequence_similarity, 4),
        "uploaded_token_count": len(uploaded_tokens),
        "official_token_count": len(official_tokens),
    }


def compare_fields(uploaded: dict, official: dict) -> dict:
    rows = []
    comparable = 0
    matched = 0
    critical_mismatches = []

    for name in uploaded:
        if name in EXCLUDED_FIELDS:
            continue
        left = uploaded.get(name, {})
        right = official.get(name, {})
        left_value = left.get("value")
        right_value = right.get("value")
        left_normalized = _normalize_field(name, left_value)
        right_normalized = _normalize_field(name, right_value)
        status = "missing"
        similarity = None
        if left_normalized and right_normalized:
            comparable += 1
            similarity = SequenceMatcher(None, left_normalized, right_normalized).ratio()
            status = "match" if similarity >= 0.90 else "mismatch"
            if status == "match":
                matched += 1
            elif name in CRITICAL_FIELDS:
                critical_mismatches.append(name)
        rows.append(
            {
                "field": name,
                "uploaded": left_value,
                "official": right_value,
                "status": status,
                "similarity": round(similarity, 4) if similarity is not None else None,
                "uploaded_evidence": left.get("source_line_ids", []),
                "official_evidence": right.get("source_line_ids", []),
            }
        )

    score = matched / comparable if comparable else 0.0
    if critical_mismatches:
        decision = "mismatch"
    elif comparable >= 2 and score >= 0.75:
        decision = "match"
    else:
        decision = "inconclusive"
    return {
        "decision": decision,
        "confidence": round(score, 4),
        "matched_fields": matched,
        "comparable_fields": comparable,
        "critical_mismatches": critical_mismatches,
        "fields": rows,
    }


def compare_documents(
    uploaded_fields: dict,
    official_fields: dict,
    uploaded_lines: list[dict],
    official_lines: list[dict],
    *,
    minimum_text_similarity: float = 0.55,
    minimum_match_confidence: float = 0.72,
) -> dict:
    """Require field evidence and whole-text similarity for a secure match."""
    result = compare_fields(uploaded_fields, official_fields)
    text = compare_ocr_text(uploaded_lines, official_lines)
    matched_fields = [
        row["field"] for row in result["fields"] if row["status"] == "match"
    ]
    mismatched_fields = [
        row["field"] for row in result["fields"] if row["status"] == "mismatch"
    ]
    available_critical = {
        name
        for name in CRITICAL_FIELDS
        if _normalize_field(name, uploaded_fields.get(name, {}).get("value"))
    }
    matched_critical = available_critical.intersection(matched_fields)

    critical_evidence_sufficient = (
        len(available_critical) >= 2
        and available_critical.issubset(matched_critical)
    )

    combined_confidence = (
        0.65 * result["confidence"] + 0.35 * text["similarity"]
    )
    matched = all(
        (
            result["decision"] == "match",
            not result["critical_mismatches"],
            critical_evidence_sufficient,
            text["similarity"] >= minimum_text_similarity,
            combined_confidence >= minimum_match_confidence,
        )
    )
    result.update(
        {
            "matched": matched,
            "match_confidence": round(combined_confidence, 4),
            "matched_field_names": matched_fields,
            "mismatched_field_names": mismatched_fields,
            "matched_critical_fields": sorted(matched_critical),
            "critical_evidence_sufficient": critical_evidence_sufficient,
            "general_text": text,
            "minimum_text_similarity": minimum_text_similarity,
            "minimum_match_confidence": minimum_match_confidence,
        }
    )
    return result
