import unittest

from field_rules import apply_deterministic_field_rules


def value(text=None, line_ids=None):
    return {"value": text, "source_line_ids": line_ids or []}


class FieldRuleTests(unittest.TestCase):
    def test_synthetic_document_fields_are_taken_from_semantic_evidence(self):
        lines = [
            {"id": 1, "text": "T.C. TEST BELEDİYESİ Gelirler Müdürlüğü"},
            {"id": 2, "text": "Sayı : E-70010020 - 100.20 - 3004 - 50060"},
            {"id": 3, "text": "Tarih : 15.01.2030"},
            {"id": 4, "text": "TEST ENERJİ DAĞITIM A.Ş."},
            {
                "id": 5,
                "text": "İlgi : ÖRNEK KİŞİ'nin 15.01.2030 tarihli dilekçesi.",
            },
            {
                "id": 6,
                "text": (
                    "İlçemiz Test Mah. 700 Ada 80 Parsel dış kapı:90 nolu "
                    "taşınmazın rayiç bedeli"
                ),
            },
            {
                "id": 7,
                "text": "Belge Doğrulama Kodu:9001002~U0VOVEVUSUtLT0Q~",
            },
            {
                "id": 8,
                "text": (
                    "Belge Doğrulama Adresi: "
                    "https://verify.example.bel.tr/document?id=42"
                ),
            },
            {
                "id": 9,
                "text": "Deneme Mah. Test Cad. No:10 00000-TEST",
            },
        ]
        model_fields = {
            "belge_no": value("70010020 - 100.20 -", [2]),
            "tarih": value(),
            "muhatap": value("ÖRNEK KİŞİ", [5]),
            "kisi_kurum": value("TEST ENERJİ DAĞITIM A.Ş.", [4]),
            "adres": value("Deneme Mah. Test Cad. No:10", [9]),
            "dogrulama_kodu": value(),
            "dogrulama_adresi": value(),
        }

        result = apply_deterministic_field_rules(model_fields, lines)

        self.assertEqual(
            result["belge_no"]["value"],
            "E-70010020 - 100.20 - 3004 - 50060",
        )
        self.assertEqual(result["tarih"]["value"], "15.01.2030")
        self.assertEqual(
            result["muhatap"]["value"],
            "TEST ENERJİ DAĞITIM A.Ş.",
        )
        self.assertEqual(result["kisi_kurum"]["value"], "ÖRNEK KİŞİ")
        self.assertEqual(result["adres"]["value"], "Test Mah. 700 Ada 80 Parsel")
        self.assertEqual(
            result["dogrulama_kodu"]["value"],
            "9001002~U0VOVEVUSUtLT0Q~",
        )
        self.assertEqual(
            result["dogrulama_adresi"]["value"],
            "https://verify.example.bel.tr/document?id=42",
        )

    def test_missing_labels_and_property_pattern_do_not_invent_values(self):
        fields = {
            "muhatap": value(),
            "kisi_kurum": value(),
            "adres": value(),
            "dogrulama_kodu": value(),
        }

        result = apply_deterministic_field_rules(
            fields,
            [{"id": 1, "text": "Genel açıklama ve iletişim bilgileri"}],
        )

        self.assertEqual(result, fields)

    def test_ocr_company_suffix_and_apostrophe_variants_keep_roles(self):
        fields = {
            "muhatap": value("ÖRNEK KİŞİ", [2]),
            "kisi_kurum": value("ÖRNEK KİŞİ' nin", [2]),
        }
        lines = [
            {"id": 1, "text": "TEST ENERJI DAGITIM AS"},
            {"id": 2, "text": "İlgi : ÖRNEK KİŞİ' nin 15.01.2030 tarihli dilekçesi"},
        ]

        result = apply_deterministic_field_rules(fields, lines)

        self.assertEqual(result["muhatap"]["value"], lines[0]["text"])
        self.assertEqual(result["kisi_kurum"]["value"], "ÖRNEK KİŞİ")


if __name__ == "__main__":
    unittest.main()
