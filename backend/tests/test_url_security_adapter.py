import unittest
from unittest.mock import patch

from official_search import Policy, SecurityError
from url_security import safe_fetch


class RedirectSecurityAdapterTests(unittest.TestCase):
    @patch("url_security._request")
    @patch("url_security.resolve_public", return_value=["203.0.113.10"])
    def test_redirect_target_is_revalidated_before_second_request(
        self,
        resolve_public,
        request,
    ):
        request.return_value = (
            302,
            {"location": "https://attacker.example/document.pdf"},
            b"",
        )
        policy = Policy(allowed_hosts=frozenset({"verify.example.bel.tr"}))

        with self.assertRaises(SecurityError) as caught:
            safe_fetch("https://verify.example.bel.tr/start", policy)

        self.assertEqual(caught.exception.code, "host_not_allowed")
        self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
