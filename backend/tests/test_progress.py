import unittest

from progress import ProgressRegistry


class FakeClock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


class ProgressRegistryTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.registry = ProgressRegistry(clock=self.clock)
        self.registry.start("test-request-001")

    def test_progress_interpolates_but_does_not_reach_phase_ceiling_early(self):
        self.registry.update("test-request-001", 20, "uploaded_ocr", 45, 100)
        self.clock.advance(50)

        result = self.registry.snapshot("test-request-001")

        self.assertEqual(result["phase"], "uploaded_ocr")
        self.assertEqual(result["percent"], 32.5)
        self.assertGreater(result["estimated_remaining_seconds"], 0)

    def test_reported_progress_never_moves_backwards(self):
        self.registry.update("test-request-001", 60, "official_ocr", 75, 60)
        self.registry.update("test-request-001", 40, "official_search", 50, 10)

        result = self.registry.snapshot("test-request-001")

        self.assertEqual(result["percent"], 60.0)

    def test_completion_is_exactly_one_hundred_percent(self):
        self.registry.complete("test-request-001")

        result = self.registry.snapshot("test-request-001")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["percent"], 100.0)
        self.assertEqual(result["estimated_remaining_seconds"], 0)

    def test_unknown_request_has_no_progress(self):
        self.assertIsNone(self.registry.snapshot("missing-request"))


if __name__ == "__main__":
    unittest.main()
