import json
import tempfile
import unittest
from pathlib import Path

import app


class AppTests(unittest.TestCase):
    def test_mask_email(self):
        self.assertEqual(app.mask_email("utkucan@example.com"), "ut•••••@example.com")
        self.assertEqual(app.mask_email("Bağlı hesap"), "Bağlı hesap")

    def test_display_formatting_has_one_currency_symbol(self):
        self.assertEqual(app.money(12.5), "$12.50")
        self.assertEqual(app.compact_number(1_500_000), "1.5M")

    def test_normalize_provider_payload(self):
        providers, error = app.normalize_providers([{"provider":"Codex", "usage":{"primary":{"usedPercent":120}}}])
        self.assertIsNone(error)
        self.assertEqual(providers[0]["name"], "Codex")
        self.assertEqual(providers[0]["windows"][0]["left"], 0)

    def test_fixture_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "usage.json"
            path.write_text(json.dumps([{"provider":"Test", "usage":{"primary":{"usedPercent":5}}}]))
            providers, error = app.read_usage("unused", str(path))
        self.assertIsNone(error)
        self.assertEqual(providers[0]["name"], "Test")

    def test_upstream_window_shape(self):
        payload = [{"provider": "codex", "usage": {
            "primary": None,
            "secondary": {"usedPercent": 15, "resetDescription": "Aug 27 at 4:39 PM"},
        }}]
        providers, error = app.normalize_providers(payload)
        self.assertIsNone(error)
        self.assertEqual(providers[0]["windows"][0]["label"], "Weekly")
        self.assertEqual(providers[0]["windows"][0]["left"], 85)
        self.assertIn("Aug 27", providers[0]["windows"][0]["reset"])


if __name__ == "__main__":
    unittest.main()
