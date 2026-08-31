from __future__ import annotations

import sys
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

from documents import DocumentError, detect_type
from settings import Settings


ROOT = Path(__file__).resolve().parent
QR_HOME = ROOT / "legacy" / "qr_document_verifier"
if str(QR_HOME) not in sys.path:
    sys.path.insert(0, str(QR_HOME))

from url_security import Policy, SecurityError, prepare, safe_fetch  # noqa: E402


DOCUMENT_CONTENT_TYPES = frozenset(
    {"application/pdf", "image/png", "image/jpeg", "image/tiff"}
)
GENERIC_DOWNLOAD_TYPE = "application/octet-stream"
HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
DOCUMENT_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff")
DOCUMENT_SIGNALS = (
    "pdf",
    "document",
    "belge",
    "dosya",
    "download",
    "indir",
    "evrak",
    "viewer",
    "goruntu",
    "görüntü",
    "image",
)


class SearchDeadlineExceeded(RuntimeError):
    pass


class DocumentLinkParser(HTMLParser):
    """Collect only elements that can plausibly expose a digital document."""

    def __init__(self):
        super().__init__()
        self.sources: list[str] = []
        self._anchor: tuple[str, bool] | None = None

    def _add(self, value: str | None) -> None:
        if value and value not in self.sources:
            self.sources.append(value)

    @staticmethod
    def _has_document_signal(value: str) -> bool:
        lowered = unquote(value).casefold()
        path = urlsplit(lowered).path
        return path.endswith(DOCUMENT_EXTENSIONS) or any(
            signal in lowered for signal in DOCUMENT_SIGNALS
        )

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        tag = tag.casefold()
        if tag in {"iframe", "frame", "embed"}:
            self._add(values.get("src"))
            return
        if tag == "object":
            self._add(values.get("data"))
            return
        if tag == "img":
            source = values.get("src")
            attributes = " ".join(values.values())
            if source and self._has_document_signal(f"{source} {attributes}"):
                self._add(source)
            return
        if tag == "a":
            href = values.get("href")
            attributes = " ".join(values.values())
            signaled = (
                "download" in values
                or values.get("type", "").casefold() in DOCUMENT_CONTENT_TYPES
                or bool(href and self._has_document_signal(f"{href} {attributes}"))
            )
            self._anchor = (href, signaled) if href else None
            if signaled:
                self._add(href)

    def handle_data(self, data: str) -> None:
        if self._anchor and self._has_document_signal(data):
            self._add(self._anchor[0])

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a":
            self._anchor = None


@dataclass(frozen=True)
class SearchEntry:
    url: str
    depth: int
    source_page_url: str | None


DocumentEvaluator = Callable[[bytes, str, dict, float], dict]


def _candidate_rank(comparison: dict) -> tuple[float, float, int]:
    similarity = float(
        comparison.get(
            "direct_similarity",
            comparison.get("match_confidence", 0.0),
        )
    )
    return (
        1.0 if comparison.get("matched") else 0.0,
        similarity,
        int(
            comparison.get(
                "compared_token_count",
                comparison.get("comparable_fields", 0),
            )
        ),
    )


def _result(
    *,
    status: str,
    matched: bool,
    stop_reason: str,
    stopped_early: bool,
    visited_count: int,
    candidate_count: int,
    candidates: list[dict],
    selected: dict | None = None,
    error: SecurityError | None = None,
) -> dict:
    selected = selected or {}
    comparison = selected.get("comparison")
    source = selected.get("official", {}).get("source", {})
    return {
        "status": status,
        "matched": matched,
        "matched_document_url": source.get("matched_document_url") if matched else None,
        "source_page_url": source.get("source_page_url") if matched else None,
        "match_confidence": (
            comparison.get("match_confidence") if comparison else 0.0
        ),
        "compared_fields": [],
        "matched_fields": [],
        "mismatched_fields": [],
        "search_stopped_early": stopped_early,
        "search_stop_reason": stop_reason,
        "visited_url_count": visited_count,
        "evaluated_document_count": candidate_count,
        "official_candidates": candidates,
        "selected_evaluation": selected or None,
        "official_error": error.to_dict() if error else None,
    }


def search_official_documents(
    initial_url: str,
    settings: Settings,
    evaluate_document: DocumentEvaluator,
    *,
    clock: Callable[[], float] = time.monotonic,
    deadline: float | None = None,
) -> dict:
    """Safely discover and evaluate candidates in order, returning on first match."""
    started = clock()
    deadline = deadline or (started + settings.max_total_processing_seconds)
    policy = Policy(
        max_redirects=settings.max_official_redirects,
        timeout=settings.official_request_timeout_seconds,
        max_bytes=settings.max_official_download_bytes,
        allowed_types=(
            DOCUMENT_CONTENT_TYPES | HTML_CONTENT_TYPES | {GENERIC_DOWNLOAD_TYPE}
        ),
    )
    try:
        initial_target = prepare(initial_url, policy)
    except SecurityError as exc:
        return _result(
            status="BLOCKED",
            matched=False,
            stop_reason="security_policy_blocked",
            stopped_early=True,
            visited_count=0,
            candidate_count=0,
            candidates=[],
            error=exc,
        )
    pinned_policy = policy.pin(initial_target.hostname)
    queue = deque([SearchEntry(initial_target.url, 0, None)])
    queued = {initial_target.url}
    visited: set[str] = set()
    candidate_summaries: list[dict] = []
    selected: dict | None = None
    candidate_count = 0

    while queue:
        remaining = deadline - clock()
        if remaining <= 0:
            return _result(
                status="NOT_MATCHED",
                matched=False,
                stop_reason="total_time_limit_reached",
                stopped_early=True,
                visited_count=len(visited),
                candidate_count=candidate_count,
                candidates=candidate_summaries,
                selected=selected,
            )
        if len(visited) >= settings.max_official_urls:
            return _result(
                status="NOT_MATCHED",
                matched=False,
                stop_reason="visited_url_limit_reached",
                stopped_early=True,
                visited_count=len(visited),
                candidate_count=candidate_count,
                candidates=candidate_summaries,
                selected=selected,
            )
        if candidate_count >= settings.max_official_documents:
            return _result(
                status="NOT_MATCHED",
                matched=False,
                stop_reason="document_limit_reached",
                stopped_early=True,
                visited_count=len(visited),
                candidate_count=candidate_count,
                candidates=candidate_summaries,
                selected=selected,
            )

        entry = queue.popleft()
        queued.discard(entry.url)
        try:
            canonical = prepare(entry.url, pinned_policy).url
            if canonical in visited:
                continue
            visited.add(canonical)
            fetched = safe_fetch(canonical, pinned_policy)
        except SecurityError as exc:
            return _result(
                status="BLOCKED",
                matched=False,
                stop_reason="security_policy_blocked",
                stopped_early=True,
                visited_count=len(visited),
                candidate_count=candidate_count,
                candidates=candidate_summaries,
                selected=selected,
                error=exc,
            )

        if fetched.content_type in HTML_CONTENT_TYPES:
            if entry.depth >= settings.max_official_depth:
                continue
            parser = DocumentLinkParser()
            parser.feed(fetched.body.decode("utf-8", errors="replace"))
            for source in parser.sources:
                discovered = urljoin(fetched.final_url, source)
                try:
                    candidate_url = prepare(discovered, pinned_policy).url
                except SecurityError:
                    # The link is rejected before any network access. A redirect to
                    # an untrusted host is instead caught by safe_fetch and blocks.
                    continue
                if candidate_url in visited or candidate_url in queued:
                    continue
                if len(visited) + len(queued) >= settings.max_official_urls:
                    break
                queued.add(candidate_url)
                queue.append(
                    SearchEntry(candidate_url, entry.depth + 1, fetched.final_url)
                )
            continue

        if fetched.content_type not in DOCUMENT_CONTENT_TYPES | {GENERIC_DOWNLOAD_TYPE}:
            continue
        try:
            detected_type = detect_type(fetched.body, fetched.content_type)
        except DocumentError as exc:
            candidate_summaries.append(
                {
                    "source": {
                        "matched_document_url": fetched.final_url,
                        "source_page_url": entry.source_page_url,
                        "document": fetched.metadata(),
                    },
                    "rejected": True,
                    "reason": str(exc),
                }
            )
            continue
        if (
            fetched.content_type != GENERIC_DOWNLOAD_TYPE
            and detected_type != fetched.content_type
        ):
            candidate_summaries.append(
                {
                    "source": {
                        "matched_document_url": fetched.final_url,
                        "source_page_url": entry.source_page_url,
                        "document": fetched.metadata(),
                    },
                    "rejected": True,
                    "reason": "İçerik türü ile dosya imzası eşleşmiyor.",
                }
            )
            continue

        candidate_count += 1
        source_metadata = {
            "hostname": initial_target.hostname,
            "target": initial_target.url,
            "document_index": candidate_count,
            "matched_document_url": fetched.final_url,
            "source_page_url": entry.source_page_url or fetched.final_url,
            "document": fetched.metadata(),
        }
        try:
            evaluation = evaluate_document(
                fetched.body,
                detected_type,
                source_metadata,
                max(0.0, deadline - clock()),
            )
        except SearchDeadlineExceeded:
            return _result(
                status="NOT_MATCHED",
                matched=False,
                stop_reason="total_time_limit_reached",
                stopped_early=True,
                visited_count=len(visited),
                candidate_count=candidate_count,
                candidates=candidate_summaries,
                selected=selected,
            )

        comparison = evaluation["comparison"]
        summary = {
            "source": source_metadata,
            "comparison": {
                key: comparison[key]
                for key in (
                    "mode",
                    "decision",
                    "matched",
                    "exact_match",
                    "match_confidence",
                    "confidence",
                    "compared_token_count",
                    "matching_token_count",
                    "difference_count",
                    "match_threshold",
                    "ordered_similarity",
                    "bag_similarity",
                    "normalization",
                    "review_min_similarity",
                    "auto_match_similarity",
                    "decision_source",
                    "prefix_check",
                    "direct_similarity",
                    "direct_exact_match",
                    "qwen_judgment",
                )
                if key in comparison
            },
        }
        candidate_summaries.append(summary)
        if selected is None or _candidate_rank(comparison) > _candidate_rank(
            selected["comparison"]
        ):
            selected = evaluation
        if comparison["matched"]:
            return _result(
                status="MATCHED",
                matched=True,
                stop_reason="matched_document_verified",
                stopped_early=True,
                visited_count=len(visited),
                candidate_count=candidate_count,
                candidates=candidate_summaries,
                selected=evaluation,
            )

    return _result(
        status="NOT_MATCHED",
        matched=False,
        stop_reason="search_exhausted_without_match",
        stopped_early=False,
        visited_count=len(visited),
        candidate_count=candidate_count,
        candidates=candidate_summaries,
        selected=selected,
    )
