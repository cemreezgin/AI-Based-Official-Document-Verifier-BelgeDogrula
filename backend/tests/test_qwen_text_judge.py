import unittest
from unittest.mock import Mock, patch

from qwen_text_judge import (
    apply_qwen_judgment,
    finalize_hybrid_decision,
    judge_texts,
    needs_qwen_review,
)
from text_comparison import compare_ocr_texts
from settings import Settings


class QwenTextJudgeTests(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()

    @patch("qwen_text_judge.Client")
    def test_returns_qwen_final_verdict(self, client_class):
        response = Mock()
        response.message.content = (
            '{"confidence":0.97,"reason_code":"layout_or_order_only",'
            '"uploaded_excerpt":null,"official_excerpt":null}'
        )
        client_class.return_value.chat.return_value = response

        result = judge_texts(
            "Başlık\nTest Mah. 700 Ada 80 Parsel",
            "Test Mah. 700 Ada 80 Parsel\nBaşlık",
            [],
            self.settings,
            timeout_seconds=10,
        )

        self.assertEqual(result["verdict"], "same")
        self.assertEqual(result["confidence"], 0.97)

    @patch("qwen_text_judge.Client")
    def test_invented_excerpts_are_removed(self, client_class):
        response = Mock()
        response.message.content = (
            '{"confidence":0.99,"reason_code":"substantive_text_difference",'
            '"uploaded_excerpt":"uydurulmuş",'
            '"official_excerpt":"81 Parsel"}'
        )
        client_class.return_value.chat.return_value = response

        result = judge_texts(
            "80 Parsel",
            "81 Parsel",
            [],
            self.settings,
            timeout_seconds=10,
        )

        self.assertIsNone(result["uploaded_excerpt"])
        self.assertEqual(result["official_excerpt"], "81 Parsel")

    @patch("qwen_text_judge.Client")
    def test_clear_paired_numeric_conflict_vetoes_false_positive(self, client_class):
        response = Mock()
        response.message.content = (
            '{"confidence":0.99,"reason_code":"exact_text",'
            '"uploaded_excerpt":null,"official_excerpt":null}'
        )
        client_class.return_value.chat.return_value = response

        result = judge_texts(
            "Belge No: 123",
            "Belge No: 999",
            [{"uploaded": "123", "official": "999"}],
            self.settings,
            timeout_seconds=10,
        )

        self.assertEqual(result["verdict"], "different")
        self.assertEqual(result["safety_veto"], "paired_content_conflict")

    @patch("qwen_text_judge.Client")
    def test_reordered_same_numbers_keep_qwen_same_verdict(self, client_class):
        response = Mock()
        response.message.content = (
            '{"confidence":0.95,"reason_code":"exact_text",'
            '"uploaded_excerpt":null,"official_excerpt":null}'
        )
        client_class.return_value.chat.return_value = response

        result = judge_texts(
            "Başlık\nBelge No: 123",
            "Belge No: 123\nBaşlık",
            [{"uploaded": "Başlık", "official": None}],
            self.settings,
            timeout_seconds=10,
        )

        self.assertEqual(result["verdict"], "same")
        self.assertEqual(result["reason_code"], "layout_or_order_only")
        self.assertIsNone(result["safety_veto"])

    @patch("qwen_text_judge.Client")
    def test_viewer_truncated_number_sequence_is_not_a_conflict(self, client_class):
        response = Mock()
        response.message.content = (
            '{"confidence":0.94,"reason_code":"layout_or_order_only",'
            '"uploaded_excerpt":null,"official_excerpt":null}'
        )
        client_class.return_value.chat.return_value = response

        result = judge_texts(
            "Sayı TEST-70010020-3004-50060 15.01.2030",
            "Sayı 70010020 E-İmza Tarihi",
            [
                {
                    "type": "replace",
                    "uploaded": "TEST-70010020-3004-50060 15.01.2030",
                    "official": "70010020 E-İmza Tarihi",
                }
            ],
            self.settings,
            timeout_seconds=10,
        )

        self.assertEqual(result["verdict"], "same")
        self.assertIsNone(result["safety_veto"])

    @patch("qwen_text_judge.Client")
    def test_large_footer_replacement_does_not_trigger_paired_veto(self, client_class):
        response = Mock()
        response.message.content = (
            '{"confidence":0.95,"reason_code":"layout_or_order_only",'
            '"uploaded_excerpt":null,"official_excerpt":null}'
        )
        client_class.return_value.chat.return_value = response

        result = judge_texts(
            "TEST ANA BELGE\nÖRNEK EK BİR İKİ ÜÇ DÖRT BEŞ",
            "TEST ANA BELGE\nÖRNEK ALT BİLGİ ALTI YEDİ SEKİZ DOKUZ",
            [
                {
                    "type": "replace",
                    "uploaded": "ÖRNEK EK BİR İKİ ÜÇ DÖRT BEŞ",
                    "official": "ÖRNEK ALT BİLGİ ALTI YEDİ SEKİZ DOKUZ",
                }
            ],
            self.settings,
            timeout_seconds=10,
        )

        self.assertEqual(result["verdict"], "same")
        self.assertIsNone(result["safety_veto"])

    def test_missing_text_is_uncertain_without_calling_model(self):
        result = judge_texts(
            "",
            "Resmî belge",
            [],
            self.settings,
            timeout_seconds=10,
        )

        self.assertEqual(result["verdict"], "uncertain")
        self.assertEqual(result["reason_code"], "insufficient_evidence")

    def test_qwen_same_verdict_overrides_non_exact_direct_comparison(self):
        direct = compare_ocr_texts(
            [{"text": "Başlık içerik"}],
            [{"text": "İçerik Başlık"}],
        )

        result = apply_qwen_judgment(
            direct,
            {
                "verdict": "same",
                "confidence": 0.96,
                "reason_code": "layout_or_order_only",
                "uploaded_excerpt": None,
                "official_excerpt": None,
            },
        )

        self.assertFalse(result["direct_exact_match"])
        self.assertTrue(result["matched"])

    def test_qwen_different_verdict_overrides_exact_direct_comparison(self):
        direct = compare_ocr_texts(
            [{"text": "Aynı metin"}],
            [{"text": "Aynı metin"}],
        )

        result = apply_qwen_judgment(
            direct,
            {
                "verdict": "different",
                "confidence": 0.91,
                "reason_code": "substantive_text_difference",
                "uploaded_excerpt": None,
                "official_excerpt": None,
            },
        )

        self.assertTrue(result["direct_exact_match"])
        self.assertFalse(result["matched"])

    def test_only_gray_zone_requires_qwen(self):
        low = {"match_confidence": 0.74}
        gray = {"match_confidence": 0.83}
        high = {"match_confidence": 0.85, "differences": []}

        self.assertFalse(needs_qwen_review(low, self.settings))
        self.assertTrue(needs_qwen_review(gray, self.settings))
        self.assertFalse(needs_qwen_review(high, self.settings))

    def test_high_score_with_clear_replacement_still_requires_qwen(self):
        comparison = {
            "match_confidence": 0.98,
            "differences": [{"uploaded": "TEST-100", "official": "TEST-900"}],
        }

        self.assertTrue(needs_qwen_review(comparison, self.settings))

    def test_high_score_with_number_to_label_alignment_auto_matches(self):
        comparison = {
            "match_confidence": 0.86,
            "confidence": 0.86,
            "matched": False,
            "decision": "mismatch",
            "differences": [
                {
                    "type": "replace",
                    "uploaded": "01.01.2030",
                    "official": "E-İmza Tarihi",
                },
                {
                    "type": "replace",
                    "uploaded": "ÖRNEK TEST EK BLOĞU BİR İKİ ÜÇ DÖRT",
                    "official": "ÖRNEK TEST ALT BİLGİ BEŞ ALTI YEDİ SEKİZ",
                },
            ],
        }

        self.assertFalse(needs_qwen_review(comparison, self.settings))
        result = finalize_hybrid_decision(comparison, self.settings)
        self.assertTrue(result["matched"])
        self.assertEqual(result["decision_source"], "similarity_auto_match")

    def test_high_similarity_auto_matches_without_qwen(self):
        comparison = {
            "match_confidence": 0.93,
            "confidence": 0.93,
            "matched": False,
            "decision": "mismatch",
        }

        result = finalize_hybrid_decision(comparison, self.settings)

        self.assertTrue(result["matched"])
        self.assertEqual(result["decision_source"], "similarity_auto_match")
        self.assertIsNone(result["qwen_judgment"])

    def test_low_similarity_auto_rejects_without_qwen(self):
        comparison = {
            "match_confidence": 0.62,
            "confidence": 0.62,
            "matched": True,
            "decision": "match",
        }

        result = finalize_hybrid_decision(comparison, self.settings)

        self.assertFalse(result["matched"])
        self.assertEqual(result["decision_source"], "similarity_auto_reject")
        self.assertIsNone(result["qwen_judgment"])

    def test_qwen_is_final_decision_in_gray_zone(self):
        comparison = {
            "match_confidence": 0.83,
            "confidence": 0.83,
            "matched": True,
            "decision": "match",
        }
        judgment = {
            "verdict": "different",
            "confidence": 0.96,
            "reason_code": "substantive_text_difference",
            "uploaded_excerpt": None,
            "official_excerpt": None,
            "safety_veto": None,
        }

        result = finalize_hybrid_decision(
            comparison,
            self.settings,
            judgment,
        )

        self.assertFalse(result["matched"])
        self.assertEqual(result["decision_source"], "qwen_gray_zone")
        self.assertEqual(result["match_confidence"], 0.83)


if __name__ == "__main__":
    unittest.main()
