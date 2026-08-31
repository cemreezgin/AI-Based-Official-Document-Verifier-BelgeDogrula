from __future__ import annotations

import re
_COMPANY_MARKER = re.compile(
    r"(?:\bA\.?\s*[ŞS]\.?\s*$|\bLTD\.?\b|\bŞTİ\.?\b|"
    r"\bBELED[İI]YES[İI]\b|\bM[ÜU]D[ÜU]RL[ÜU][ĞG][ÜU]\b|"
    r"\bELEKTR[İI]K\b|\bDA[ĞG]ITIM\b)",
    re.IGNORECASE,
)
_DATE = re.compile(r"\b\d{2}[./-]\d{2}[./-]\d{4}\b")
_PROPERTY_ADDRESS = re.compile(
    r"\b([A-ZÇĞİÖŞÜa-zçğıöşü][\wÇĞİÖŞÜçğıöşü'’-]*)\s+"
    r"Mah(?:allesi)?\.?\s+\d+\s+Ada\s+\d+\s+Parsel\b",
    re.IGNORECASE,
)
_VERIFICATION_CODE = re.compile(r"[A-Za-z0-9~_-]{6,}")
_URL = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)


def _payload(value: str, source_ids: list[int]) -> dict:
    return {"value": value.strip(), "source_line_ids": source_ids}


def _line_records(lines: list[dict]) -> list[tuple[int, str]]:
    return [
        (int(line["id"]), str(line.get("text", "")).strip())
        for line in lines
        if str(line.get("text", "")).strip()
    ]


def _extract_label_value(
    records: list[tuple[int, str]],
    index: int,
    label_pattern: re.Pattern,
) -> tuple[str, list[int]] | None:
    line_id, text = records[index]
    match = label_pattern.search(text)
    if not match:
        return None
    value = match.group(1).strip(" :;\t")
    source_ids = [line_id]
    if not value and index + 1 < len(records):
        next_id, next_text = records[index + 1]
        value = next_text.strip()
        source_ids.append(next_id)
    return (value, source_ids) if value else None


def _find_verification_code(
    records: list[tuple[int, str]],
) -> tuple[str, list[int]] | None:
    label = re.compile(
        r"(?:Belge\s+)?Do[ğg]rulama\s+Kodu\s*[:;]?\s*(.*)",
        re.IGNORECASE,
    )
    for index in range(len(records)):
        extracted = _extract_label_value(records, index, label)
        if not extracted:
            continue
        value, source_ids = extracted
        code = _VERIFICATION_CODE.search(value)
        if code:
            return code.group(0), source_ids
    return None


def _find_verification_url(
    records: list[tuple[int, str]],
) -> tuple[str, list[int]] | None:
    label = re.compile(
        r"(?:Belge\s+)?Do[ğg]rulama\s+Adres[ıi]\s*[:;]?\s*(.*)",
        re.IGNORECASE,
    )
    for index in range(len(records)):
        extracted = _extract_label_value(records, index, label)
        if not extracted:
            continue
        value, source_ids = extracted
        url = _URL.search(value)
        if url:
            return url.group(0).rstrip(".,;)"), source_ids
    return None


def _find_property_address(
    records: list[tuple[int, str]],
) -> tuple[str, list[int]] | None:
    for index, (line_id, text) in enumerate(records):
        match = _PROPERTY_ADDRESS.search(text)
        if match:
            return match.group(0), [line_id]
        if index + 1 < len(records):
            next_id, next_text = records[index + 1]
            combined = f"{text} {next_text}"
            match = _PROPERTY_ADDRESS.search(combined)
            if match:
                return match.group(0), [line_id, next_id]
    return None


def _find_roles(
    records: list[tuple[int, str]],
) -> tuple[tuple[str, list[int]] | None, tuple[str, list[int]] | None]:
    ilgi = re.compile(r"\b[İIıi]lgi\s*[:;]?\s*(.+)", re.IGNORECASE)
    person_end = re.compile(
        r"(?=['’]\s*(?:[ıi]n|nin|nun|nün)\b|\s+\d{2}[./-]\d{2}[./-]\d{4}\b)",
        re.IGNORECASE,
    )
    for index, (line_id, text) in enumerate(records):
        match = ilgi.search(text)
        if not match:
            continue
        raw_person = match.group(1).strip()
        end = person_end.search(raw_person)
        person = raw_person[: end.start()].strip(" :;,-") if end else ""
        person_result = (person, [line_id]) if len(person) >= 3 else None

        addressee_result = None
        for previous_index in range(index - 1, max(-1, index - 5), -1):
            previous_id, previous_text = records[previous_index]
            if _COMPANY_MARKER.search(previous_text):
                addressee_result = (previous_text.strip(), [previous_id])
                break
        return addressee_result, person_result
    return None, None


def _find_document_number(
    records: list[tuple[int, str]],
) -> tuple[str, list[int]] | None:
    label = re.compile(r"\b(?:Say[ıi]|Say1)\s*[:;]?\s*(.+)", re.IGNORECASE)
    numeric_continuation = re.compile(r"^[E0-9./\s-]+$", re.IGNORECASE)
    for index in range(len(records)):
        extracted = _extract_label_value(records, index, label)
        if not extracted:
            continue
        value, source_ids = extracted
        if index + 1 < len(records):
            next_id, next_text = records[index + 1]
            if value.rstrip().endswith("-") and numeric_continuation.fullmatch(next_text):
                value = f"{value} {next_text}"
                source_ids.append(next_id)
        return value.strip(), source_ids
    return None


def _find_date(records: list[tuple[int, str]]) -> tuple[str, list[int]] | None:
    labelled = re.compile(r"\bTarih\s*[:;]?\s*(.*)", re.IGNORECASE)
    for index in range(len(records)):
        extracted = _extract_label_value(records, index, labelled)
        if not extracted:
            continue
        value, source_ids = extracted
        match = _DATE.search(value)
        if match:
            return match.group(0), source_ids
    for line_id, text in records:
        match = _DATE.search(text)
        if match:
            return match.group(0), [line_id]
    return None


def apply_deterministic_field_rules(fields: dict, lines: list[dict]) -> dict:
    """Correct high-confidence fields using only explicit OCR evidence.

    The rules deliberately require document labels or the strong
    ``Mah. ... Ada ... Parsel`` structure. They never synthesize absent values.
    """
    corrected = {
        name: {
            "value": payload.get("value"),
            "source_line_ids": list(payload.get("source_line_ids") or []),
        }
        for name, payload in fields.items()
    }
    records = _line_records(lines)

    replacements = {
        "belge_no": _find_document_number(records),
        "tarih": _find_date(records),
        "adres": _find_property_address(records),
        "dogrulama_kodu": _find_verification_code(records),
        "dogrulama_adresi": _find_verification_url(records),
    }
    addressee, referenced_person = _find_roles(records)
    replacements["muhatap"] = addressee
    replacements["kisi_kurum"] = referenced_person

    for field_name, replacement in replacements.items():
        if replacement and field_name in corrected:
            corrected[field_name] = _payload(*replacement)
    return corrected
