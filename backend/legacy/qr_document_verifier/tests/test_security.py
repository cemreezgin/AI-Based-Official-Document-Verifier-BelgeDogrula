import socket
import unittest
from unittest.mock import patch

from url_security import (
    INTERMEDIATE,
    INTERMEDIATE_SHA256,
    Policy,
    SecurityError,
    _tls_context,
    prepare,
    resolve_public,
)


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.policy = Policy(frozenset({"official.example"}))

    def test_http_upgrade_preserves_target(self):
        target = prepare("http://official.example/a?id=1", self.policy)
        self.assertEqual(target.url, "https://official.example/a?id=1")
        self.assertTrue(target.upgraded)

    def test_similar_host_is_blocked(self):
        with self.assertRaises(SecurityError):
            prepare("https://official.example.attacker.test/a", self.policy)

    def test_official_municipality_domain_is_discovered_automatically(self):
        policy = Policy()
        target = prepare(
            "http://e-belediye.alanya.bel.tr/document?id=1",
            policy,
        )
        self.assertEqual(target.hostname, "e-belediye.alanya.bel.tr")
        self.assertTrue(target.upgraded)

    def test_arbitrary_domain_is_blocked_in_automatic_mode(self):
        with self.assertRaises(SecurityError):
            prepare("https://example.com/document", Policy())

    def test_lookalike_official_suffix_is_blocked(self):
        with self.assertRaises(SecurityError):
            prepare("https://alanya.bel.tr.attacker.example/document", Policy())

    def test_bare_official_suffix_is_not_a_valid_institution(self):
        with self.assertRaises(SecurityError):
            prepare("https://bel.tr/document", Policy())

    def test_discovered_host_is_pinned_for_followup_requests(self):
        pinned = Policy().pin("e-belediye.alanya.bel.tr")
        prepare("https://e-belediye.alanya.bel.tr/document", pinned)
        with self.assertRaises(SecurityError):
            prepare("https://other.bel.tr/document", pinned)

    @patch("url_security.socket.getaddrinfo")
    def test_private_address_is_blocked(self, getaddrinfo):
        getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ]
        with self.assertRaises(SecurityError):
            resolve_public(prepare("https://official.example/a", self.policy))

    def test_intermediate_is_pinned_and_loadable(self):
        self.assertTrue(INTERMEDIATE.is_file())
        self.assertEqual(len(INTERMEDIATE_SHA256), 64)
        self.assertIsNotNone(_tls_context())


if __name__ == "__main__":
    unittest.main()
