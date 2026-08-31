import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pipeline import _FrameParser, _scan_qr, _select_best_candidate
from settings import Settings


class PipelineSelectionTests(unittest.TestCase):
    def test_multiple_official_frames_are_discovered(self):
        parser = _FrameParser()
        parser.feed(
            "<iframe src='/main.pdf'></iframe>"
            "<iframe src='/attachment.pdf'></iframe>"
        )

        self.assertEqual(parser.sources, ["/main.pdf", "/attachment.pdf"])

    def test_candidate_with_higher_confidence_is_selected(self):
        candidates = [
            {
                "comparison": {
                    "decision": "match",
                    "compared_token_count": 70,
                    "match_confidence": 0.7143,
                }
            },
            {
                "comparison": {
                    "decision": "match",
                    "compared_token_count": 100,
                    "match_confidence": 0.1,
                }
            },
        ]

        self.assertIs(_select_best_candidate(candidates), candidates[0])

    @staticmethod
    def _report(status):
        contents = ["https://resmi.test.example/belge"] if status == "confirmed" else []
        payload = {"status": status, "confirmed_contents": contents}
        return SimpleNamespace(
            status=status,
            confirmed_contents=contents,
            to_dict=lambda: payload,
        )

    @patch("pipeline.read_qr_image")
    def test_restormer_is_not_loaded_when_later_page_confirms_cheaply(self, reader):
        reader.side_effect = [self._report("not_found"), self._report("confirmed")]

        result = _scan_qr([Path("page-1.png"), Path("page-2.png")], Settings())

        self.assertEqual(result["selected_page"], 2)
        self.assertEqual(reader.call_count, 2)
        self.assertTrue(all(call.kwargs["enable_restormer"] is False for call in reader.call_args_list))

    @patch("pipeline.read_qr_image")
    def test_restormer_runs_only_after_all_cheap_attempts_fail(self, reader):
        reader.side_effect = [
            self._report("not_found"),
            self._report("not_found"),
            self._report("confirmed"),
        ]

        result = _scan_qr([Path("page-1.png"), Path("page-2.png")], Settings())

        self.assertEqual(result["selected_page"], 1)
        self.assertEqual(
            [call.kwargs["enable_restormer"] for call in reader.call_args_list],
            [False, False, True],
        )


if __name__ == "__main__":
    unittest.main()
