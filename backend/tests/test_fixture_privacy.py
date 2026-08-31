from pathlib import Path
import unittest


TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent
FORBIDDEN_REAL_FIXTURE_FRAGMENTS = (
    "alan" + "ya",
    "kadı" + "köy",
    "abd" + "ullah",
    "öz" + "kan",
    "akde" + "niz elektrik",
    "imam" + "lı mah",
    "eğri" + "köprü",
    "4552" + "9817",
    "3281" + "593",
    "tarım ve " + "orman bakanlığı",
    "devlet su " + "işleri",
    "tuba " + "karaca",
    "mustafa " + "gökdemir",
    "murat " + "çınar",
    "eğir" + "dir",
    "ispar" + "ta",
    "8835" + "5190",
    "6ed8" + "723e",
)


class FixturePrivacyTests(unittest.TestCase):
    def test_active_test_fixtures_do_not_contain_known_real_document_data(self):
        violations = []
        for path in TESTS_DIR.glob("test*.py"):
            if path == Path(__file__):
                continue
            content = path.read_text(encoding="utf-8").casefold()
            for fragment in FORBIDDEN_REAL_FIXTURE_FRAGMENTS:
                if fragment.casefold() in content:
                    violations.append(f"{path.name}: {fragment}")

        self.assertEqual(violations, [])

    def test_legacy_ocr_json_artifacts_contain_no_known_real_document_data(self):
        fixture_dir = BACKEND_DIR / "legacy" / "paddleocr_qwen"
        violations = []
        for path in fixture_dir.rglob("*.json"):
            content = path.read_text(encoding="utf-8").casefold()
            for fragment in FORBIDDEN_REAL_FIXTURE_FRAGMENTS:
                if fragment.casefold() in content:
                    violations.append(f"{path.relative_to(BACKEND_DIR)}: {fragment}")

        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
