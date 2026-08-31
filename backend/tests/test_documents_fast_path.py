import unittest
from unittest.mock import MagicMock, patch

from documents import extract_pdf_text_lines, has_usable_text_layer


class DocumentFastPathTests(unittest.TestCase):
    @patch("documents.pdfium.PdfDocument")
    def test_pdf_text_layer_is_extracted_without_document_data_fixture(self, constructor):
        document = MagicMock()
        document.__len__.return_value = 1
        page = MagicMock()
        text_page = MagicMock()
        text_page.get_text_range.return_value = (
            "ÖRNEK KURUMU\nTEST BELGE NUMARASI 000000\n"
            "Bu içerik yalnız sentetik otomasyon testi içindir."
        )
        page.get_textpage.return_value = text_page
        document.__getitem__.return_value = page
        constructor.return_value = document

        lines = extract_pdf_text_lines(MagicMock(), max_pages=3)

        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0]["source"], "pdf_text_layer")
        self.assertTrue(has_usable_text_layer(lines, minimum_characters=30))

    def test_short_or_empty_text_layer_falls_back_to_ocr(self):
        lines = [{"text": "TEST"}]

        self.assertFalse(has_usable_text_layer(lines, minimum_characters=30))


if __name__ == "__main__":
    unittest.main()
