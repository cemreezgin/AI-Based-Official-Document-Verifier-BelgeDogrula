import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np

from ocr_preprocessing import prepare_ocr_pages


class OCRPreprocessingTests(unittest.TestCase):
    def test_only_noisy_synthetic_page_is_denoised(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            pages = root / "pages"
            pages.mkdir()
            clean = np.full((500, 800), 255, dtype=np.uint8)
            cv2.putText(clean, "ORNEK TEST 0001", (40, 220), cv2.FONT_HERSHEY_SIMPLEX, 2, 0, 4)
            rng = np.random.default_rng(2030)
            noisy = np.clip(
                clean.astype(np.int16) + rng.normal(0, 18, clean.shape), 0, 255
            ).astype(np.uint8)
            cv2.imwrite(str(pages / "page-001.png"), clean)
            cv2.imwrite(str(pages / "page-002.png"), noisy)

            _, reports = prepare_ocr_pages(
                pages, root / "prepared", denoise_min_score=3.5
            )

            self.assertFalse(reports[0]["denoised"])
            self.assertTrue(reports[1]["denoised"])
            self.assertGreater(reports[1]["noise_score"], reports[0]["noise_score"])


if __name__ == "__main__":
    unittest.main()
