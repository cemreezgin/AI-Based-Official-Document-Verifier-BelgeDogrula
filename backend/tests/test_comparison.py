import unittest

from comparison import compare_documents, compare_fields, reconcile_role_fields


def value(text):
    return {"value": text, "source_line_ids": [1] if text else []}


class ComparisonTests(unittest.TestCase):
    def test_reversed_official_roles_are_reconciled_from_both_cross_pairs(self):
        uploaded = {
            "muhatap": value("TEST ENERJİ DAĞITIM A.Ş."),
            "kisi_kurum": value("ÖRNEK KİŞİ"),
        }
        official = {
            "muhatap": value("ÖRNEK KİŞİ"),
            "kisi_kurum": value("TEST ENERJİ DAĞITIM A.Ş."),
        }

        corrected, metadata = reconcile_role_fields(uploaded, official)

        self.assertTrue(metadata["roles_swapped"])
        self.assertEqual(corrected["muhatap"], official["kisi_kurum"])
        self.assertEqual(corrected["kisi_kurum"], official["muhatap"])

    def test_role_reconciliation_does_not_swap_on_partial_evidence(self):
        uploaded = {
            "muhatap": value("TEST ENERJİ DAĞITIM A.Ş."),
            "kisi_kurum": value(None),
        }
        official = {
            "muhatap": value("ÖRNEK KİŞİ"),
            "kisi_kurum": value("TEST ENERJİ DAĞITIM A.Ş."),
        }

        corrected, metadata = reconcile_role_fields(uploaded, official)

        self.assertFalse(metadata["roles_swapped"])
        self.assertEqual(corrected, official)

    def test_document_match_requires_field_and_general_text_similarity(self):
        uploaded = {
            "belge_no": value("TEST-2030/41"),
            "tarih": value("15.01.2030"),
            "duzenleyen_kurum": value("Test Belediyesi"),
        }
        official = {
            "belge_no": value("TEST 2030 41"),
            "tarih": value("15.01.2030"),
            "duzenleyen_kurum": value("TEST BELEDİYESİ"),
        }
        lines = [
            {"text": "Test Belediyesi"},
            {"text": "Sayı TEST-2030/41 Tarih 15.01.2030"},
            {"text": "İmar durum belgesi düzenlenmiştir"},
        ]

        result = compare_documents(uploaded, official, lines, list(lines))

        self.assertTrue(result["matched"])
        self.assertGreaterEqual(result["general_text"]["similarity"], 0.99)

    def test_matching_fields_with_unrelated_text_are_not_secure_match(self):
        uploaded = {
            "belge_no": value("TEST-2030/41"),
            "tarih": value("15.01.2030"),
            "duzenleyen_kurum": value("Test Belediyesi"),
        }
        official = dict(uploaded)

        result = compare_documents(
            uploaded,
            official,
            [{"text": "İmar durum belgesi başvuru sahibi adres bilgileri"}],
            [{"text": "Personel maaş bordrosu ödeme banka hesap özeti"}],
        )

        self.assertEqual(result["decision"], "match")
        self.assertFalse(result["matched"])
        self.assertLess(result["general_text"]["similarity"], 0.55)

    def test_missing_available_critical_field_prevents_secure_match(self):
        uploaded = {
            "belge_no": value("TEST-2030/41"),
            "tarih": value("15.01.2030"),
            "duzenleyen_kurum": value("Test Belediyesi"),
        }
        official = {
            "belge_no": value("TEST-2030/41"),
            "tarih": value("15.01.2030"),
            "duzenleyen_kurum": value(None),
        }
        lines = [{"text": "Test Belediyesi TEST-2030/41 15.01.2030"}]

        result = compare_documents(uploaded, official, lines, list(lines))

        self.assertFalse(result["critical_evidence_sufficient"])
        self.assertFalse(result["matched"])

    def test_matching_critical_fields_are_accepted(self):
        uploaded = {
            "belge_no": value("TEST-2030/41"),
            "tarih": value("15.01.2030"),
            "duzenleyen_kurum": value("Test Belediyesi"),
        }
        official = {
            "belge_no": value("TEST 2030 41"),
            "tarih": value("15.01.2030"),
            "duzenleyen_kurum": value("TEST BELEDİYESİ"),
        }
        result = compare_fields(uploaded, official)
        self.assertEqual(result["decision"], "match")
        self.assertEqual(result["confidence"], 1.0)

    def test_critical_mismatch_rejects_document(self):
        uploaded = {"belge_no": value("TEST-A-1"), "tarih": value("15.01.2030")}
        official = {"belge_no": value("TEST-B-9"), "tarih": value("15.01.2030")}
        result = compare_fields(uploaded, official)
        self.assertEqual(result["decision"], "mismatch")
        self.assertEqual(result["critical_mismatches"], ["belge_no"])

    def test_ada_and_parsel_are_excluded_from_comparison(self):
        uploaded = {
            "belge_no": value("TEST-A-1"),
            "tarih": value("15.01.2030"),
            "ada": value("700"),
            "parsel": value("80"),
        }
        official = {
            "belge_no": value("TEST-A-1"),
            "tarih": value("15.01.2030"),
            "ada": value("701"),
            "parsel": value("81"),
        }

        result = compare_fields(uploaded, official)

        self.assertEqual(result["decision"], "match")
        self.assertEqual(result["comparable_fields"], 2)
        self.assertNotIn("ada", {row["field"] for row in result["fields"]})
        self.assertNotIn("parsel", {row["field"] for row in result["fields"]})

    def test_ocr_accents_and_sayi_label_do_not_create_false_mismatch(self):
        uploaded = {
            "duzenleyen_kurum": value("TEST BELEDÍYESİ"),
            "belge_no": value("Say1: E-70010020-100.20-3004-50060"),
            "tarih": value("15.01.2030"),
        }
        official = {
            "duzenleyen_kurum": value("T.C. TEST BELEDİYESİ"),
            "belge_no": value("E-70010020 - 100.20 - 3004 - 50060"),
            "tarih": value("15-01-2030"),
        }

        result = compare_fields(uploaded, official)

        self.assertEqual(result["decision"], "match")
        self.assertEqual(result["confidence"], 1.0)


if __name__ == "__main__":
    unittest.main()
