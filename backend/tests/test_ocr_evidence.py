import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ocr_adapter import _find_executable, _lines_from_pages, enforce_source_evidence


class OCREvidenceTests(unittest.TestCase):
    def test_executable_is_found_beside_virtual_environment_python(self):
        with TemporaryDirectory() as temp:
            bin_dir = Path(temp) / "bin"
            bin_dir.mkdir()
            python = bin_dir / "python"
            executable = bin_dir / "paddleocr"
            python.touch()
            executable.touch()

            with patch("ocr_adapter.sys.executable", str(python)), patch(
                "ocr_adapter.shutil.which", return_value=None
            ):
                self.assertEqual(_find_executable("paddleocr"), str(executable))

    def test_value_without_source_evidence_is_removed(self):
        fields = {
            "belge_no": {"value": "123", "source_line_ids": []},
            "tarih": {"value": "01.01.2026", "source_line_ids": [2]},
        }

        trusted = enforce_source_evidence(
            fields,
            [{"id": 2, "text": "01.01.2026"}],
        )

        self.assertEqual(
            trusted["belge_no"],
            {"value": None, "source_line_ids": []},
        )
        self.assertEqual(
            trusted["tarih"],
            {"value": "01.01.2026", "source_line_ids": [2]},
        )

    def test_invalid_source_ids_are_not_trusted(self):
        fields = {
            "adres": {"value": "Örnek Sokak", "source_line_ids": [99]},
        }

        trusted = enforce_source_evidence(
            fields,
            [{"id": 1, "text": "Başlık"}],
        )

        self.assertEqual(
            trusted["adres"],
            {"value": None, "source_line_ids": []},
        )

    def test_value_not_present_in_claimed_source_line_is_removed(self):
        trusted = enforce_source_evidence(
            {
                "belge_no": {
                    "value": "HALLUCINATED-999",
                    "source_line_ids": [1],
                }
            },
            [{"id": 1, "text": "Sayı: E-2026/41"}],
        )

        self.assertEqual(
            trusted["belge_no"],
            {"value": None, "source_line_ids": []},
        )

    def test_ada_and_parsel_are_removed_from_output(self):
        fields = {
            "belge_no": {"value": "A-1", "source_line_ids": [1]},
            "ada": {"value": "114", "source_line_ids": [2]},
            "parsel": {"value": "26", "source_line_ids": [2]},
        }

        trusted = enforce_source_evidence(
            fields,
            [{"id": 1, "text": "A-1"}, {"id": 2, "text": "700 Ada 80 Parsel"}],
        )

        self.assertEqual(set(trusted), {"belge_no"})

    def test_warm_worker_pages_are_converted_to_stable_line_ids(self):
        lines = _lines_from_pages(
            [
                {"res": {"rec_texts": ["ÖRNEK BELGE", "TEST 0001"], "rec_scores": [0.98, 0.96]}},
                {"res": {"rec_texts": ["SENTETİK İÇERİK"], "rec_scores": [0.94]}},
            ]
        )

        self.assertEqual([line["id"] for line in lines], [1, 2, 3])
        self.assertEqual([line["page"] for line in lines], [1, 1, 2])
        self.assertEqual(lines[2]["text"], "SENTETİK İÇERİK")


if __name__ == "__main__":
    unittest.main()
