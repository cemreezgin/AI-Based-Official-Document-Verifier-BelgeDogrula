"""Self-contained acceptance test for the complete HTTP verification flow.

The fixture is generated in memory, contains only explicit TEST data, performs
real QR decoding with the three production decoders, and never accesses the
network. OCR output and the official HTTPS response are deterministic test
adapters so CI does not download model weights or contact an institution.
"""
from __future__ import annotations

import hashlib
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient

from main import app
from url_security import FetchResult


OFFICIAL_URL = "https://verify.example.bel.tr/synthetic-document.png"
SYNTHETIC_LINES = [
    {"id": 1, "page": 1, "text": "SENTETİK TEST BELGESİ", "ocr_confidence": 0.99},
    {"id": 2, "page": 1, "text": "Belge No: TEST-2026-0001", "ocr_confidence": 0.99},
    {"id": 3, "page": 1, "text": "Gerçek kişi veya kurum bilgisi içermez.", "ocr_confidence": 0.99},
]


def synthetic_document_png() -> bytes:
    qr = cv2.QRCodeEncoder_create().encode(OFFICIAL_URL)
    qr = cv2.resize(qr, None, fx=10, fy=10, interpolation=cv2.INTER_NEAREST)
    canvas = np.full((700, 900, 3), 255, dtype=np.uint8)
    height, width = qr.shape
    canvas[30 : 30 + height, 30 : 30 + width] = cv2.cvtColor(
        qr, cv2.COLOR_GRAY2BGR
    )
    cv2.putText(
        canvas,
        "SENTETIK TEST BELGESI",
        (30, 430),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    ok, encoded = cv2.imencode(".png", canvas)
    if not ok:
        raise RuntimeError("Sentetik PNG üretilemedi.")
    return encoded.tobytes()


class SyntheticEndToEndAcceptanceTests(unittest.TestCase):
    @patch("pipeline.OCRSession.run", return_value=SYNTHETIC_LINES)
    @patch("official_search.safe_fetch")
    def test_upload_qr_fetch_ocr_compare_and_decision_flow(
        self,
        safe_fetch,
        ocr_run,
    ):
        document = synthetic_document_png()
        safe_fetch.return_value = FetchResult(
            original_url=OFFICIAL_URL,
            final_url=OFFICIAL_URL,
            transport_upgraded=False,
            status_code=200,
            content_type="image/png",
            content_length=len(document),
            sha256=hashlib.sha256(document).hexdigest(),
            connected_ip="203.0.113.10",
            redirects=[],
            body=document,
        )

        response = TestClient(app).post(
            "/api/v1/verify",
            content=document,
            headers={
                "content-type": "image/png",
                "x-request-id": "synthetic-e2e-2026",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "MATCHED")
        self.assertTrue(payload["matched"])
        self.assertEqual(payload["matched_document_url"], OFFICIAL_URL)
        self.assertEqual(payload["qr"]["report"]["confirmed_contents"], [OFFICIAL_URL])
        agreeing_decoders = {
            item["decoder"]
            for item in payload["qr"]["report"]["decoder_outputs"]
            if OFFICIAL_URL in item["contents"]
        }
        self.assertGreaterEqual(len(agreeing_decoders), 2)
        self.assertEqual(payload["comparison"]["decision"], "match")
        self.assertEqual(payload["comparison"]["match_confidence"], 1.0)
        self.assertEqual(ocr_run.call_count, 2)
        safe_fetch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
