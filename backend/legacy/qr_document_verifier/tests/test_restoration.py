import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import zxingcpp

from image_restoration import measure_quality
from qr_reader import READERS, read_qr_image


class RestorationTests(unittest.TestCase):
    def _degraded_qr_page(self) -> tuple[Path, str]:
        content = "https://example.com/blur-noise-test"
        qr = np.asarray(
            zxingcpp.create_barcode(
                content, zxingcpp.BarcodeFormat.QRCode
            ).to_image(scale=5)
        )
        if qr.ndim == 2:
            qr = cv2.cvtColor(qr, cv2.COLOR_GRAY2BGR)
        page = np.full((700, 700, 3), 255, dtype=np.uint8)
        height, width = qr.shape[:2]
        page[675 - height:675, 675 - width:675] = qr
        page = cv2.GaussianBlur(page, (13, 13), 0)
        noise = np.random.default_rng(42).normal(0, 25, page.shape).astype(np.int16)
        page = np.clip(page.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        path = Path(tempfile.gettempdir()) / "qr-restoration-test.png"
        self.assertTrue(cv2.imwrite(str(path), page))
        return path, content

    def test_quality_measurement_detects_added_noise(self):
        clean = np.full((200, 200, 3), 127, dtype=np.uint8)
        noisy = np.clip(
            clean.astype(np.int16)
            + np.random.default_rng(1).normal(0, 25, clean.shape).astype(np.int16),
            0,
            255,
        ).astype(np.uint8)
        self.assertLess(measure_quality(clean).noise_score, 1)
        self.assertEqual(measure_quality(noisy).noise_level, "high")

    def test_blur_noise_recovery_reaches_decoder_consensus(self):
        path, expected = self._degraded_qr_page()
        image = cv2.imread(str(path))
        direct_votes = sum(bool(reader(image)) for reader in READERS.values())
        self.assertLess(direct_votes, 2)

        report = read_qr_image(path)
        self.assertEqual(report.status, "confirmed")
        self.assertEqual(report.confirmed_contents, [expected])
        self.assertTrue(
            any(
                output.recovery_method
                and output.recovery_method.startswith("opencv_")
                for output in report.decoder_outputs
            )
        )

    def test_restormer_fallback_is_enabled_by_default(self):
        path = Path(tempfile.gettempdir()) / "blank-qr-test.png"
        self.assertTrue(
            cv2.imwrite(str(path), np.full((100, 100, 3), 255, dtype=np.uint8))
        )
        with patch("qr_reader._recover") as recover:
            recover.return_value = []
            read_qr_image(path)
        self.assertTrue(recover.call_args.kwargs["enable_restormer"])


if __name__ == "__main__":
    unittest.main()
