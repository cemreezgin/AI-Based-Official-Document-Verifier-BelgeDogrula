import json
from pathlib import Path
import unicodedata
import unittest

from PIL import Image


BACKEND_DIR = Path(__file__).resolve().parents[1]
LEGACY_FIXTURE_DIR = BACKEND_DIR / "legacy" / "paddleocr_qwen"
OUTPUT_DIR = LEGACY_FIXTURE_DIR / "output"


class SyntheticLegacyArtifactTests(unittest.TestCase):
    def test_only_synthetic_named_ocr_artifacts_remain(self):
        names = sorted(path.name for path in OUTPUT_DIR.iterdir() if path.is_file())

        self.assertEqual(
            names,
            [
                "synthetic_document_a_ocr_res_img.png",
                "synthetic_document_a_res.json",
                "synthetic_document_b_ocr_res_img.png",
                "synthetic_document_b_res.json",
            ],
        )

    def test_coordinate_arrays_and_synthetic_texts_stay_aligned(self):
        for path in OUTPUT_DIR.glob("synthetic_document_*_res.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            line_count = len(payload["rec_texts"])

            self.assertTrue(payload["synthetic_fixture"])
            self.assertTrue(payload["input_path"].startswith("/synthetic/fixtures/"))
            self.assertEqual(line_count, len(payload["dt_polys"]))
            self.assertEqual(line_count, len(payload["rec_polys"]))
            self.assertEqual(line_count, len(payload["rec_boxes"]))
            self.assertEqual(line_count, len(payload["rec_scores"]))
            self.assertTrue(
                all(
                    "test" in self._ascii_fold(text)
                    or "orne" in self._ascii_fold(text)
                    or "sentetik" in self._ascii_fold(text)
                    or text in {"Bilgilerinize sunulur.", "Gerçek kişi veya kurum bilgisi içermez."}
                    for text in payload["rec_texts"]
                )
            )

    @staticmethod
    def _ascii_fold(text: str) -> str:
        decomposed = unicodedata.normalize("NFKD", text.replace("ı", "i"))
        return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()

    def test_visualizations_are_marked_as_synthetic(self):
        for path in OUTPUT_DIR.glob("synthetic_document_*_ocr_res_img.png"):
            with Image.open(path) as image:
                self.assertIn("SENTETİK TEST BELGESİ", image.info["Description"])
                self.assertEqual(image.width % 2, 0)


if __name__ == "__main__":
    unittest.main()
