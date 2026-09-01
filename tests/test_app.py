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

    def test_translation_tables_have_identical_keys(self):
        """A key present in one language and missing in the other silently falls
        back, so the UI would render half-translated without anyone noticing."""
        turkish = set(app.TRANSLATIONS["tr"])
        english = set(app.TRANSLATIONS["en"])
        self.assertEqual(turkish - english, set())
        self.assertEqual(english - turkish, set())

    def test_language_switch_changes_rendered_strings(self):
        self.addCleanup(app.set_language, "tr")
        app.set_language("tr")
        self.assertEqual(app.t("tab.usage"), "Kullanım")
        self.assertEqual(app.month_names()[7], "Ağu")
        self.assertEqual(app.percent_text(42), "%42")
        self.assertEqual(app.provider_label(app.UNKNOWN_PROVIDER), "Kaynağı bilinmeyen")
        app.set_language("en")
        self.assertEqual(app.t("tab.usage"), "Usage")
        self.assertEqual(app.month_names()[7], "Aug")
        self.assertEqual(app.percent_text(42), "42%")
        self.assertEqual(app.provider_label(app.UNKNOWN_PROVIDER), "Unattributed")

    def test_unknown_language_falls_back_to_turkish(self):
        self.addCleanup(app.set_language, "tr")
        self.assertEqual(app.set_language("de"), "tr")
        self.assertEqual(app.set_language(None), "tr")
        self.assertEqual(app.set_language("EN"), "en")

    def test_unknown_key_renders_as_itself(self):
        """Cached provider data from an older build still carries plain labels."""
        self.addCleanup(app.set_language, "tr")
        self.assertEqual(app.t("Haftalık"), "Haftalık")

    def test_turkish_uppercase_keeps_the_dotted_i(self):
        self.addCleanup(app.set_language, "tr")
        app.set_language("tr")
        self.assertEqual(app.upper("birleşik"), "BİRLEŞİK")
        self.assertEqual(app.upper("yalnız"), "YALNIZ")
        app.set_language("en")
        self.assertEqual(app.upper("combined"), "COMBINED")

    def test_pace_summary_follows_the_active_language(self):
        self.addCleanup(app.set_language, "tr")
        windows = [{"label": "window.session", "used": 90, "left": 10, "reset": "48 dk."}]
        app.set_language("tr")
        turkish = app.pace_summary(windows)
        self.assertEqual(turkish["headline"], "Kapasite kritik")
        self.assertIn("Oturum", turkish["detail"])
        self.assertEqual(turkish["remaining"], "%10")
        app.set_language("en")
        english = app.pace_summary(windows)
        self.assertEqual(english["headline"], "Capacity critical")
        self.assertIn("Session", english["detail"])
        self.assertEqual(english["remaining"], "10%")

    def test_english_ui_keeps_upstream_duration_text(self):
        """The Turkish rewrite of '2h 14m' must not leak into the English UI."""
        self.addCleanup(app.set_language, "tr")
        app.set_language("tr")
        self.assertEqual(app.localize_reset_description("2h 14m"), "2 sa. 14 dk.")
        app.set_language("en")
        self.assertIsNone(app.localize_reset_description("2h 14m"))

    def test_no_turkish_text_escapes_the_translation_table(self):
        """Codex found `$1.00 harcandı` in the English UI: two strings were painted
        and tooltipped directly, so they never went through `t()`. Grepping for
        QLabel(...) missed them. This walks every string literal instead."""
        import ast

        source = Path(app.__file__).read_text()
        tree = ast.parse(source)

        # The translation tables and the Turkish month names are supposed to
        # hold Turkish; everything else must reach the UI through t().
        skip: set[int] = set()
        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            names = {item.id for item in targets if isinstance(item, ast.Name)}
            if names & {"TRANSLATIONS", "MONTH_NAMES_BY_LANGUAGE"} and node.value is not None:
                skip.update(id(child) for child in ast.walk(node.value))

        docstrings: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                first = node.body[0] if node.body else None
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    docstrings.add(id(first.value))

        # Turkish-only letters; 'ç/ö/ü' also occur in other languages but not in
        # this file's English strings, so they stay in the signal set.
        turkish = set("çğışöüÇĞİŞÖÜ")
        allowed = {
            "bilinmeyen",  # storage key in token-history.json, not display text
            "ı", "İ",      # upper()'s Turkish casing pair
            "gün", "sa.", "dk.", " gün", " sa.", " dk.",  # the Turkish-only reset rewrite
        }
        leaks = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in skip or id(node) in docstrings:
                continue
            if node.value in allowed or not (turkish & set(node.value)):
                continue
            leaks.append((node.lineno, node.value))
        self.assertEqual(leaks, [], f"t() dışında kalan Türkçe metin: {leaks}")

    def test_chart_strings_follow_the_active_language(self):
        self.addCleanup(app.set_language, "tr")
        app.set_language("en")
        self.assertEqual(app.t("chart.spent", amount="$1.00"), "$1.00 spent")
        self.assertEqual(app.t("chart.noDailyCost"), "No daily cost data to chart")
        app.set_language("tr")
        self.assertEqual(app.t("chart.spent", amount="$1.00"), "$1.00 harcandı")

    def test_theme_styles_are_available(self):
        light, dark = app.style_for_theme("light"), app.style_for_theme("dark")
        self.assertIn("#eef2fa", light)
        self.assertIn("#141926", dark)
        self.assertEqual(app.style_for_theme("unknown"), app.LIGHT_STYLE)
        for style in (light, dark):
            # The glass surfaces only read as layers if the ground is a gradient
            # and the cards above it stay translucent.
            self.assertIn("qlineargradient", style)
            self.assertIn("#heroCard", style)
            self.assertIn("QWidget { background:transparent;", style)

    def test_caption_scale_stays_large_enough_for_turkish_diacritics(self):
        """Below ~10px the dot on İ and the umlaut on Ü drop out when rendered."""
        for style in (app.LIGHT_STYLE, app.DARK_STYLE):
            rule = next(line for line in style.splitlines() if line.startswith("#cardCaption, #statLabel"))
            size = float(rule.split("font-size:")[1].split("px")[0])
            self.assertGreaterEqual(size, 10.5)

    def test_token_history_keeps_one_year_and_groups_months(self):
        today = date(2026, 8, 23)
        history = app.merge_token_history(
            {"2025-08-23": {"codex": 10}, "2025-08-24": {"codex": 20}},
            {"2026-08-22": 1_500_000, "2026-08-23": 2_500_000},
            "codex",
            today,
        )
        self.assertNotIn("2025-08-23", history)
        self.assertEqual(history["2026-08-23"], {"codex": 2_500_000})
        months = {label: sum(entries.values()) for label, entries in app.monthly_token_totals(history, today)}
        self.assertEqual(months["Ağu 26"], 4_000_000)

    def test_providers_no_longer_overwrite_each_other_on_the_same_day(self):
        """Regression: the single-number schema let the last refreshed provider win."""
        today = date(2026, 8, 31)
        history = app.merge_token_history({}, {"2026-08-31": 48_618_223}, "codex", today)
        history = app.merge_token_history(history, {"2026-08-31": 27_347_751}, "claude", today)
        self.assertEqual(history["2026-08-31"], {"claude": 27_347_751, "codex": 48_618_223})
        self.assertEqual(app.day_total(history["2026-08-31"]), 75_965_974)
        self.assertEqual(app.day_total(history["2026-08-31"], "codex"), 48_618_223)
        self.assertEqual(app.provider_totals(history), {"codex": 48_618_223, "claude": 27_347_751})

    def test_legacy_single_number_day_is_kept_as_unattributable(self):
        history = app.merge_token_history({"2026-08-20": 6_494_046}, {}, "codex", date(2026, 8, 31))
        self.assertEqual(history["2026-08-20"], {app.UNKNOWN_PROVIDER: 6_494_046})

    def test_attributed_day_drops_the_unattributable_duplicate(self):
        """Regression: the legacy scalar is the last writer's own total, so keeping
        it beside the attributed value counted every migrated day twice."""
        today = date(2026, 8, 31)
        history = app.merge_token_history({"2026-08-20": 6_494_046}, {}, "codex", today)
        history = app.merge_token_history(history, {"2026-08-20": 6_494_046}, "codex", today)
        self.assertEqual(history["2026-08-20"], {"codex": 6_494_046})
        self.assertEqual(app.day_total(history["2026-08-20"]), 6_494_046)

    def test_reconciliation_is_stable_across_repeated_refreshes(self):
        """Merging runs on every refresh; the day must not erode a little each time."""
        today = date(2026, 8, 31)
        history = {"2026-08-20": {app.UNKNOWN_PROVIDER: 100, "codex": 30}}
        for _ in range(3):
            history = app.merge_token_history(history, {"2026-08-20": 30}, "codex", today)
            self.assertEqual(history["2026-08-20"], {"codex": 30})

    def test_unattributed_day_survives_a_zero_provider_reading(self):
        today = date(2026, 8, 31)
        history = app.merge_token_history({"2026-08-20": 6_494_046}, {"2026-08-20": 0}, "codex", today)
        self.assertEqual(history["2026-08-20"], {app.UNKNOWN_PROVIDER: 6_494_046, "codex": 0})

    def test_stored_duplicate_is_repaired_when_history_is_read(self):
        """The file already on disk carries the duplicate, so loading must repair it."""
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "token-history.json"
            path.write_text(json.dumps({"days": {
                "2026-08-20": {app.UNKNOWN_PROVIDER: 6_494_046, "codex": 6_494_046},
                "2026-08-31": {app.UNKNOWN_PROVIDER: 84_640_980, "claude": 84_640_980, "codex": 89_167_575},
            }}))
            history = app.load_token_history(path)
        self.assertEqual(history["2026-08-20"], {"codex": 6_494_046})
        self.assertEqual(history["2026-08-31"], {"claude": 84_640_980, "codex": 89_167_575})
        self.assertEqual(app.history_total(history), 180_302_601)

    def test_scope_filters_totals_and_history(self):
        days = {"2026-08-30": {"codex": 40, "claude": 60}, "2026-08-31": {"claude": 10}}
        self.assertEqual(app.history_total(days), 110)
        self.assertEqual(app.history_total(days, "codex"), 40)
        self.assertEqual(app.scoped_entries(days["2026-08-31"], "codex"), {})
        rows = app.recent_token_days(days, 31, "codex")
        self.assertEqual(rows, [("2026-08-30", {"codex": 40})])

    def test_history_provider_order_is_stable(self):
        days = {"2026-08-30": {"claude": 1, "zeta": 2}, "2026-08-31": {"codex": 3}}
        self.assertEqual(app.history_providers(days), ["codex", "claude", "zeta"])

    def test_breakdown_tooltip_names_both_providers_with_shares(self):
        colors = {"codex": "#25c2c2", "claude": "#e99169"}
        tooltip = app.breakdown_tooltip("31 Ağu 2026", {"codex": 48_618_223, "claude": 27_347_751}, colors)
        self.assertIn("76.0M token", tooltip)
        self.assertIn("Codex", tooltip)
        self.assertIn("Claude", tooltip)
        self.assertIn("%64", tooltip)
        self.assertIn("%36", tooltip)
        self.assertIn("#25c2c2", tooltip)

    def test_single_provider_tooltip_omits_the_breakdown_lines(self):
        tooltip = app.breakdown_tooltip("Ağu 26", {"codex": 5}, {"codex": "#25c2c2"})
        self.assertNotIn("%", tooltip)

    def test_provider_colors_differ_per_provider_and_theme(self):
        self.assertNotEqual(app.provider_color("codex", "dark"), app.provider_color("claude", "dark"))
        self.assertNotEqual(app.provider_color("codex", "dark"), app.provider_color("codex", "light"))
        self.assertTrue(app.provider_color("yeni-saglayici", "dark").startswith("#"))

    def test_narrowest_window_leads_the_combined_pace(self):
        providers = [
            {"name": "Codex", "windows": [{"label": "Oturum", "used": 42, "left": 58, "reset": "2 sa."}]},
            {"name": "Claude", "windows": [{"label": "Oturum", "used": 91, "left": 9, "reset": "48 dk."}]},
        ]
        windows = app.narrowest_window(providers)
        self.assertEqual(windows[0]["label"], "Claude · Oturum")
        self.assertEqual(app.pace_summary(windows)["headline"], "Kapasite kritik")

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

    def test_extract_model_costs_folds_day_breakdowns_per_model(self):
        cost = {"projects": [], "daily": [
            {"date": "2026-08-31", "modelBreakdowns": [
                {"modelName": "claude-opus-5", "cost": 27.4},
                {"modelName": "claude-sonnet-5", "cost": 15.3},
            ]},
            {"date": "2026-09-01", "modelBreakdowns": [
                {"modelName": "claude-opus-5", "cost": "15.4"},
                {"modelName": "", "cost": 9},
                {"modelName": "claude-sonnet-5", "cost": -1},
            ]},
        ]}
        self.assertEqual(
            app.extract_model_costs(cost),
            {"claude-opus-5": 42.8, "claude-sonnet-5": 15.3},
        )

    def test_extract_model_costs_falls_back_to_projects_when_no_daily_rows(self):
        cost = {"daily": [], "projects": [
            {"modelBreakdowns": [{"modelName": "gpt-5.6-terra", "cost": 3.0}]},
        ]}
        self.assertEqual(app.extract_model_costs(cost), {"gpt-5.6-terra": 3.0})

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
            expected = {"2026-08-23": {"codex": 42}}
            app.save_token_history(expected, path)
            self.assertEqual(app.load_token_history(path), expected)

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
                self.assertEqual(app.load_token_history(), {"2026-08-23": {app.UNKNOWN_PROVIDER: 77}})
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
        # The label stays a translation key so switching language never has to
        # re-fetch or re-parse provider data.
        self.assertEqual(providers[0]["windows"][0]["label"], "window.weekly")
        self.assertEqual(providers[0]["windows"][0]["left"], 85)
        # The raw upstream value is stored; the language decides how it reads.
        self.addCleanup(app.set_language, "tr")
        window = providers[0]["windows"][0]
        self.assertEqual(window["reset_raw"], "Aug 27 at 4:39 PM")
        app.set_language("tr")
        self.assertEqual(app.reset_text(window), "27 Ağu 16:39")
        app.set_language("en")
        self.assertEqual(app.reset_text(window), "27 Aug 16:39")

    def test_reset_text_accepts_cached_data_from_an_older_build(self):
        """Providers cached before this change only carry the formatted string."""
        self.assertEqual(app.reset_text({"reset": "2 sa. 14 dk."}), "2 sa. 14 dk.")
        self.assertEqual(app.reset_text({}), app.t("usage.resetUnknown"))

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

    def test_orbit_migrates_unset_legacy_preferences_without_overwriting_new_ones(self):
        class Settings:
            def __init__(self, values=None):
                self.values = dict(values or {})

            def contains(self, key):
                return key in self.values

            def value(self, key, default=""):
                return self.values.get(key, default)

            def setValue(self, key, value):
                self.values[key] = value

        orbit = Settings({"theme": "light"})
        legacy = Settings({"theme": "dark", "token_history_view": "daily", app.CACHED_PROVIDERS_KEY: "[]"})
        app.migrate_legacy_settings(orbit, legacy)
        self.assertEqual(orbit.value("theme"), "light")
        self.assertEqual(orbit.value("token_history_view"), "daily")
        self.assertEqual(orbit.value(app.CACHED_PROVIDERS_KEY), "[]")


if __name__ == "__main__":
    unittest.main()
