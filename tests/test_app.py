import json
import tempfile
import unittest
from datetime import date, timezone, timedelta
from pathlib import Path

import app


class AppTests(unittest.TestCase):
    def test_orbit_brand_identity_is_consistent(self):
        self.assertEqual(app.APP_NAME, "Orbit")
        self.assertEqual(app.SETTINGS_APPLICATION, "Orbit")
        self.assertEqual(app.APP_DATA_DIRECTORY, "Orbit")
        self.assertEqual(app.LOGO_PATH.name, "orbit-logo.png")

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

    def test_extract_daily_costs_discards_invalid_rows_and_sorts(self):
        cost = {"daily": [
            {"date": "2026-08-23", "totalCost": "1.25"},
            {"date": "invalid", "totalCost": 3},
            {"date": "2026-08-22", "totalCostUSD": "$0.50"},
            {"date": "2026-08-24", "totalCost": -1},
        ]}
        self.assertEqual(app.extract_daily_costs(cost), [("2026-08-22", 0.5), ("2026-08-23", 1.25)])

    def test_pace_summary_is_turkish_and_actionable(self):
        summary = app.pace_summary([{"label": "Oturum", "used": 42, "left": 58, "reset": "2 sa. 14 dk."}])
        self.assertEqual(summary["headline"], "Kapasite dengeli")
        self.assertEqual(summary["detail"], "Oturum limitinin %42'si kullanıldı; %58 kapasite kaldı. Sıfırlanma: 2 sa. 14 dk.")
        self.assertIn("planlanan kullanım sürdürülebilir", summary["guidance"])
        self.assertIn("kullanım hızını tahmin etmez", summary["method"])
        self.assertEqual(summary["remaining"], "%58")
        self.assertEqual(summary["reset"], "2 sa. 14 dk.")

    def test_pace_summary_distinguishes_exhausted_limit(self):
        summary = app.pace_summary([{"label": "Oturum", "used": 100, "left": 0, "reset": "30 dk."}])
        self.assertEqual(summary["headline"], "Kapasite tükendi")
        self.assertIn("%0 kapasite kaldı", summary["detail"])
        self.assertIn("sıfırlanana kadar", summary["guidance"])

    def test_pace_summary_handles_missing_windows(self):
        self.assertEqual(app.pace_summary([])["headline"], "Tempo hesaplanamadı")
        self.assertEqual(app.pace_summary({})["headline"], "Tempo hesaplanamadı")

    def test_pace_summary_warns_before_the_limit_is_exhausted(self):
        summary = app.pace_summary([{"label": "Haftalık", "used": 91, "left": 9, "reset": "3 gün"}])
        self.assertEqual(summary["headline"], "Kapasite kritik")
        self.assertIn("yoğun işleri", summary["guidance"])

    def test_token_history_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "token-history.json"
            app.save_token_history({"2026-08-23": 42}, path)
            self.assertEqual(app.load_token_history(path), {"2026-08-23": 42})

    def test_token_history_uses_legacy_file_when_orbit_history_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            orbit = Path(tmp) / "Orbit" / "token-history.json"
            legacy = Path(tmp) / "CodexBarLinux" / "token-history.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(json.dumps({"days": {"2026-08-23": 77}}))
            original_orbit, original_legacy = app.app_data_path, app.legacy_app_data_path
            try:
                app.app_data_path = lambda: orbit
                app.legacy_app_data_path = lambda: legacy
                self.assertEqual(app.load_token_history(), {"2026-08-23": 77})
            finally:
                app.app_data_path, app.legacy_app_data_path = original_orbit, original_legacy

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
        self.assertEqual(providers[0]["windows"][0]["label"], "Haftalık")
        self.assertEqual(providers[0]["windows"][0]["left"], 85)
        self.assertEqual(providers[0]["windows"][0]["reset"], "27 Ağu 16:39")

    def test_absolute_reset_timestamp_uses_local_timezone(self):
        local_tz = timezone(timedelta(hours=3))
        self.assertEqual(app.format_reset("2026-08-27T13:39:00Z", local_tz), "27 Ağu 16:39")

    def test_relative_reset_description_is_preserved(self):
        self.assertIsNone(app.format_reset("2h 14m"))
        self.assertEqual(app.localize_reset_description("2h 14m"), "2 sa. 14 dk.")

    def test_cached_provider_snapshot_round_trip(self):
        class Settings:
            def __init__(self):
                self.values = {}

            def value(self, key, default=""):
                return self.values.get(key, default)

            def setValue(self, key, value):
                self.values[key] = value

        settings = Settings()
        providers = [{"id": "codex", "name": "Codex", "windows": []}]
        app.save_cached_providers(settings, providers)
        self.assertEqual(app.load_cached_providers(settings), providers)

    def test_malformed_cached_provider_snapshot_is_ignored(self):
        class Settings:
            def value(self, key, default=""):
                return "not-json"

        self.assertEqual(app.load_cached_providers(Settings()), [])


if __name__ == "__main__":
    unittest.main()
