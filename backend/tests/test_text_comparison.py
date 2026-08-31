import unittest

from text_comparison import compare_ocr_prefixes, compare_ocr_texts


def lines(*values):
    return [{"id": index, "text": value} for index, value in enumerate(values, 1)]


class DirectTextComparisonTests(unittest.TestCase):
    def test_isolated_ocr_glyph_errors_do_not_drop_whole_words(self):
        uploaded = lines(
            "ORNEK TEST KURUMU",
            "Belge numarası TEST-70010020",
            "Sentetik başvuru metni gönderilmiştir",
        )
        official = lines(
            "ÖRNEK TEST KURUMU",
            "Belge numarasi TEST-700I0020",
            "Sentetik basvuru metni gonderilmistir",
        )

        result = compare_ocr_texts(uploaded, official)

        self.assertGreater(result["character_similarity"], 0.95)
        self.assertTrue(result["matched"])

    def test_identical_text_matches_without_field_extraction(self):
        uploaded = lines(
            "TEST BELEDİYESİ",
            "Sayı : E-70010020 - 100.20 - 3004 - 50060",
            "Test Mah. 700 Ada 80 Parsel",
        )
        official = list(uploaded)

        result = compare_ocr_texts(uploaded, official)

        self.assertTrue(result["matched"])
        self.assertTrue(result["exact_match"])
        self.assertEqual(result["match_confidence"], 1.0)
        self.assertEqual(result["differences"], [])

    def test_line_wrapping_and_repeated_whitespace_do_not_change_content(self):
        uploaded = lines("Test Mah. 700 Ada", "80 Parsel")
        official = lines("Test   Mah. 700 Ada 80", "Parsel")

        result = compare_ocr_texts(uploaded, official)

        self.assertTrue(result["matched"])
        self.assertEqual(result["difference_count"], 0)

    def test_different_words_are_returned_side_by_side(self):
        uploaded = lines("Test Mah. 700 Ada 80 Parsel", "15.01.2030")
        official = lines("Test Mah. 700 Ada 81 Parsel", "16.01.2030")

        result = compare_ocr_texts(uploaded, official)

        self.assertFalse(result["matched"])
        self.assertEqual(result["decision"], "mismatch")
        self.assertEqual(result["difference_count"], 2)
        self.assertEqual(
            [(item["uploaded"], item["official"]) for item in result["differences"]],
            [("80", "81"), ("15.01.2030", "16.01.2030")],
        )

    def test_case_punctuation_and_turkish_characters_are_equivalent(self):
        result = compare_ocr_texts(
            lines("TEST IŞIKLI ÇÖĞÜŞ AŞ."),
            lines("test isikli cogus as"),
        )

        self.assertTrue(result["matched"])
        self.assertTrue(result["exact_match"])
        self.assertEqual(result["match_confidence"], 1.0)

    def test_overall_similarity_threshold_controls_final_decision(self):
        uploaded = lines("ÖRNEK TEST METNİ ALFA BETA GAMMA DELTA")
        official = lines("ORNEK TEST METNI ALFA BETA GAMMA FARKLI")

        accepted = compare_ocr_texts(uploaded, official, match_threshold=0.80)
        rejected = compare_ocr_texts(uploaded, official, match_threshold=0.90)

        self.assertTrue(accepted["matched"])
        self.assertEqual(accepted["decision"], "match")
        self.assertFalse(rejected["matched"])
        self.assertEqual(rejected["decision"], "mismatch")

    def test_missing_text_cannot_match(self):
        result = compare_ocr_texts([], lines("Resmî belge"))

        self.assertFalse(result["matched"])
        self.assertEqual(result["match_confidence"], 0.0)

    def test_matching_first_lines_accept_candidate_prefix(self):
        uploaded = lines(
            "T.C. TEST KURUMU",
            "ÖRNEK EVRAK BİRİMİ",
            "BELGE NO TEST-2030-100",
            "KONU ÖRNEK BAŞVURU",
        )
        official = lines(
            "TC TEST KURUMU",
            "ORNEK EVRAK BIRIMI",
            "BELGE NO TEST-2030-100",
            "KONU ORNEK BASVURU",
        )

        result = compare_ocr_prefixes(uploaded, official)

        self.assertTrue(result["matched"])
        self.assertGreaterEqual(result["similarity"], result["threshold"])

    def test_unrelated_first_lines_reject_candidate_prefix(self):
        uploaded = lines(
            "T.C. TEST KURUMU",
            "ÖRNEK DEĞER YAZISI",
            "BELGE NO TEST-2030-100",
        )
        official = lines(
            "SENTETİK VERGİ FORMU",
            "ÖRNEK BAŞVURU TABLOSU",
            "DOSYA NO TEST-900",
        )

        result = compare_ocr_prefixes(uploaded, official)

        self.assertFalse(result["matched"])


if __name__ == "__main__":
    unittest.main()
