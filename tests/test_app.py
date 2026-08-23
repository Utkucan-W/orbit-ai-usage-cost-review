import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import app


class AppTests(unittest.TestCase):
    def test_mask_email(self):
        self.assertEqual(app.mask_email("utkucan@example.com"), "ut•••••@example.com")
        self.assertEqual(app.mask_email("Bağlı hesap"), "Bağlı hesap")

    def test_display_formatting_has_one_currency_symbol(self):
        self.assertEqual(app.money(12.5), "$12.50")
        self.assertEqual(app.compact_number(1_500_000), "1.5M")
        self.assertEqual(app.token_count("$1,500,000"), "1.5M token")
        self.assertNotIn("$", app.token_count("$1,500,000"))

    def test_theme_styles_are_available(self):
        self.assertIn("#f5f7fb", app.style_for_theme("light"))
        self.assertIn("#12151b", app.style_for_theme("dark"))
        self.assertEqual(app.style_for_theme("unknown"), app.LIGHT_STYLE)

    def test_token_history_keeps_one_year_and_groups_months(self):
        today = date(2026, 8, 23)
        history = app.merge_token_history(
            {"2025-08-23": 10, "2025-08-24": 20},
            {"2026-08-22": 1_500_000, "2026-08-23": 2_500_000},
            today,
        )
        self.assertNotIn("2025-08-23", history)
        self.assertEqual(history["2026-08-23"], 2_500_000)
        months = dict(app.monthly_token_totals(history, today))
        self.assertEqual(months["Ağu 26"], 4_000_000)

    def test_extract_daily_tokens(self):
        cost = {"daily": [
            {"date": "2026-08-22", "totalTokens": "1,200"},
            {"date": "invalid", "totalTokens": 3},
            {"date": "2026-08-23", "totalTokens": -1},
        ]}
        self.assertEqual(app.extract_daily_tokens(cost), {"2026-08-22": 1200})

    def test_token_history_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "token-history.json"
            app.save_token_history({"2026-08-23": 42}, path)
            self.assertEqual(app.load_token_history(path), {"2026-08-23": 42})

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
