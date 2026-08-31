import hashlib
import unittest
from unittest.mock import patch

from official_search import search_official_documents
from settings import Settings
from url_security import FetchResult, SecurityError


HOST = "verify.example.bel.tr"
ROOT_URL = f"https://{HOST}/verify?id=1"


def fetched(url, content_type, body):
    return FetchResult(
        original_url=url,
        final_url=url,
        transport_upgraded=False,
        status_code=200,
        content_type=content_type,
        content_length=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        connected_ip="203.0.113.10",
        redirects=[],
        body=body,
    )


def evaluation(metadata, matched, confidence):
    comparison = {
        "decision": "match" if matched else "mismatch",
        "matched": matched,
        "match_confidence": confidence,
        "confidence": confidence,
        "comparable_fields": 4,
        "matched_field_names": ["belge_no", "tarih"] if matched else ["tarih"],
        "mismatched_field_names": [] if matched else ["belge_no"],
        "fields": [
            {
                "field": "belge_no",
                "status": "match" if matched else "mismatch",
            }
        ],
    }
    return {
        "official": {"source": metadata, "fields": {}, "lines": []},
        "comparison": comparison,
    }


class OfficialSearchTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(
            max_official_documents=5,
            max_official_depth=2,
            max_official_urls=12,
            max_total_processing_seconds=60,
        )

    @patch("official_search.safe_fetch")
    def test_direct_matching_document_stops_after_first_request(self, safe_fetch):
        safe_fetch.return_value = fetched(ROOT_URL, "application/pdf", b"%PDF-right")
        evaluations = []

        def evaluate(body, content_type, metadata, remaining):
            evaluations.append(metadata["matched_document_url"])
            return evaluation(metadata, True, 0.98)

        result = search_official_documents(ROOT_URL, self.settings, evaluate)

        self.assertEqual(result["status"], "MATCHED")
        self.assertTrue(result["matched"])
        self.assertTrue(result["search_stopped_early"])
        self.assertEqual(result["matched_document_url"], ROOT_URL)
        self.assertEqual(safe_fetch.call_count, 1)
        self.assertEqual(evaluations, [ROOT_URL])

    @patch("official_search.safe_fetch")
    def test_first_html_candidate_match_skips_remaining_links(self, safe_fetch):
        first = f"https://{HOST}/first.pdf"
        second = f"https://{HOST}/second.pdf"
        responses = {
            ROOT_URL: fetched(
                ROOT_URL,
                "text/html",
                b"<a href='/first.pdf'>PDF</a><a href='/second.pdf'>PDF</a>",
            ),
            first: fetched(first, "application/pdf", b"%PDF-first"),
            second: fetched(second, "application/pdf", b"%PDF-second"),
        }
        requested = []

        def fetch(url, policy):
            requested.append(url)
            return responses[url]

        safe_fetch.side_effect = fetch
        result = search_official_documents(
            ROOT_URL,
            self.settings,
            lambda body, kind, metadata, remaining: evaluation(metadata, True, 0.96),
        )

        self.assertEqual(result["status"], "MATCHED")
        self.assertEqual(requested, [ROOT_URL, first])
        self.assertNotIn(second, requested)
        self.assertEqual(result["source_page_url"], ROOT_URL)

    @patch("official_search.safe_fetch")
    def test_second_candidate_match_stops_before_third(self, safe_fetch):
        urls = [f"https://{HOST}/candidate-{index}.pdf" for index in range(1, 4)]
        page = "".join(f"<iframe src='{url}'></iframe>" for url in urls).encode()
        responses = {ROOT_URL: fetched(ROOT_URL, "text/html", page)}
        responses.update(
            {url: fetched(url, "application/pdf", b"%PDF-candidate") for url in urls}
        )
        requested = []
        evaluated = 0

        def fetch(url, policy):
            requested.append(url)
            return responses[url]

        def evaluate(body, kind, metadata, remaining):
            nonlocal evaluated
            evaluated += 1
            return evaluation(metadata, evaluated == 2, 0.95 if evaluated == 2 else 0.31)

        safe_fetch.side_effect = fetch
        result = search_official_documents(ROOT_URL, self.settings, evaluate)

        self.assertEqual(result["status"], "MATCHED")
        self.assertEqual(requested, [ROOT_URL, urls[0], urls[1]])
        self.assertNotIn(urls[2], requested)
        self.assertEqual(result["evaluated_document_count"], 2)

    @patch("official_search.safe_fetch")
    def test_unrelated_pdf_is_not_reported_as_match(self, safe_fetch):
        safe_fetch.return_value = fetched(ROOT_URL, "application/pdf", b"%PDF-unrelated")

        result = search_official_documents(
            ROOT_URL,
            self.settings,
            lambda body, kind, metadata, remaining: evaluation(metadata, False, 0.22),
        )

        self.assertEqual(result["status"], "NOT_MATCHED")
        self.assertFalse(result["matched"])
        self.assertIsNone(result["matched_document_url"])
        self.assertEqual(result["search_stop_reason"], "search_exhausted_without_match")

    @patch("official_search.safe_fetch")
    def test_closest_text_candidate_is_selected_even_after_qwen_rejection(self, safe_fetch):
        first = f"https://{HOST}/first.pdf"
        second = f"https://{HOST}/second.pdf"
        responses = {
            ROOT_URL: fetched(
                ROOT_URL,
                "text/html",
                b"<a href='/first.pdf'>PDF</a><a href='/second.pdf'>PDF</a>",
            ),
            first: fetched(first, "application/pdf", b"%PDF-first"),
            second: fetched(second, "application/pdf", b"%PDF-second"),
        }
        safe_fetch.side_effect = lambda url, policy: responses[url]

        def evaluate(body, kind, metadata, remaining):
            is_first = metadata["matched_document_url"] == first
            result = evaluation(metadata, False, 0.82 if is_first else 0.21)
            result["comparison"]["qwen_judgment"] = {
                "verdict": "different",
                "confidence": 0.99,
            }
            return result

        result = search_official_documents(
            ROOT_URL,
            self.settings,
            evaluate,
        )

        self.assertEqual(
            result["selected_evaluation"]["official"]["source"]["matched_document_url"],
            first,
        )

    @patch("official_search.safe_fetch")
    def test_redirect_to_disallowed_domain_blocks_search(self, safe_fetch):
        safe_fetch.side_effect = SecurityError(
            "host_not_allowed",
            "Yönlendirme izin verilmeyen alana gidiyor.",
        )

        result = search_official_documents(
            ROOT_URL,
            self.settings,
            lambda body, kind, metadata, remaining: evaluation(metadata, True, 1.0),
        )

        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["matched"])
        self.assertEqual(result["official_error"]["code"], "host_not_allowed")
        self.assertEqual(safe_fetch.call_count, 1)

    @patch("official_search.safe_fetch")
    def test_no_match_respects_visited_url_limit(self, safe_fetch):
        settings = Settings(
            max_official_documents=5,
            max_official_depth=2,
            max_official_urls=3,
            max_total_processing_seconds=60,
        )
        urls = [f"https://{HOST}/candidate-{index}.pdf" for index in range(1, 5)]
        page = "".join(f"<a href='{url}'>Belge PDF</a>" for url in urls).encode()
        responses = {ROOT_URL: fetched(ROOT_URL, "text/html", page)}
        responses.update(
            {url: fetched(url, "application/pdf", b"%PDF-no-match") for url in urls}
        )
        requested = []

        def fetch(url, policy):
            requested.append(url)
            return responses[url]

        safe_fetch.side_effect = fetch
        result = search_official_documents(
            ROOT_URL,
            settings,
            lambda body, kind, metadata, remaining: evaluation(metadata, False, 0.2),
        )

        self.assertEqual(result["status"], "NOT_MATCHED")
        self.assertFalse(result["matched"])
        self.assertLessEqual(len(requested), settings.max_official_urls)
        self.assertEqual(result["evaluated_document_count"], 2)
        self.assertIn(
            result["search_stop_reason"],
            {"search_exhausted_without_match", "visited_url_limit_reached"},
        )


if __name__ == "__main__":
    unittest.main()
