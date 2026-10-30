import json
import tempfile
import time
import unittest
from datetime import date, datetime, timezone, timedelta
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
        self.assertEqual(app.style_for_theme("unknown"), app.style_for_theme("light"))
        for style in (light, dark):
            # The glass surfaces only read as layers if the ground is a gradient
            # and the cards above it stay translucent.
            self.assertIn("qlineargradient", style)
            self.assertIn("#heroCard", style)
            self.assertIn("QWidget { background:transparent;", style)

    def test_daily_chart_labels_shrink_to_fit_their_column(self):
        """A month of daily columns is a few pixels wide each; the raw ISO date
        the rows carry printed one smear of overlapping text."""
        self.addCleanup(app.set_language, "tr")
        app.set_language("en")
        self.assertEqual(app.chart_column_label("2026-08-04"), "4 Aug")
        # Monthly rows already arrive short and must survive untouched.
        self.assertEqual(app.chart_column_label("Sep 26"), "Sep")
        app.set_language("tr")
        self.assertEqual(app.chart_column_label("2026-08-04"), "4 Ağu")

    def test_pace_state_bands_cover_the_whole_range(self):
        """The card used to be green in the stylesheet regardless of the number
        next to it; the bands are what make it amber and red."""
        self.assertEqual(app.pace_state(5, 95), "high")
        self.assertEqual(app.pace_state(45, 55), "balanced")
        self.assertEqual(app.pace_state(65, 35), "declining")
        self.assertEqual(app.pace_state(95, 5), "critical")
        self.assertEqual(app.pace_state(100, 0), "exhausted")

    def test_amber_runs_from_50_down_to_25(self):
        """Utku set these edges: green above 50% left, amber down to 25%, red
        below it. Both boundaries belong to the calmer band."""
        green = ("high", "balanced")
        self.assertIn(app.pace_state(50, 50), green)
        self.assertEqual(app.pace_state(51, 49), "declining")
        self.assertEqual(app.pace_state(75, 25), "declining")
        self.assertEqual(app.pace_state(76, 24), "critical")

    def test_pace_styles_are_generated_per_state(self):
        for theme in ("light", "dark"):
            style = app.pace_style(theme)
            for state in ("high", "balanced", "declining", "critical", "exhausted", "unknown"):
                self.assertIn(f'#pace[paceState="{state}"]', style)
            # Amber and red have to differ from green, otherwise the property
            # selector is wired up but the card still looks the same.
            colors = {app.pace_color(state, theme)
                      for state in ("high", "declining", "critical")}
            self.assertEqual(len(colors), 3)
            # pace_color() paints the bars; the card chrome uses the same
            # palette entry as an rgba tint.
            tint = app.PACE_PALETTE["dark" if theme == "dark" else "light"]["critical"]["tint"]
            self.assertIn(f"rgba({tint}", style)

    def test_card_state_matches_the_worst_provider_row(self):
        """The chip and the rows are computed on two different paths; a chip
        reading "balanced" above a critical row would be worse than the bug
        this card was rebuilt to fix."""
        severity = ["exhausted", "critical", "declining", "balanced", "high"]
        for codex_used, claude_used in [(2, 5), (50, 45), (80, 30), (92, 40), (30, 88), (100, 10)]:
            payload = [
                {"provider": "Codex", "usage": {"primary": {"usedPercent": codex_used, "resetsAt": "2026-09-07T09:41:00Z"},
                                                "secondary": {"usedPercent": codex_used, "resetsAt": "2026-09-07T09:41:00Z"}}},
                {"provider": "Claude", "usage": {"primary": {"usedPercent": claude_used, "resetsAt": "2026-09-03T14:30:00Z"}}},
            ]
            providers, _ = app.normalize_providers(payload)
            rows = app.provider_pace_rows(providers)
            card = app.pace_summary(app.narrowest_window(providers))["state"]
            worst = min((row["state"] for row in rows), key=severity.index)
            self.assertEqual(card, worst, f"codex={codex_used} claude={claude_used} rows={rows}")

    def test_pace_card_lists_every_provider_instead_of_the_narrowest(self):
        """Guards the reported bug: the card showed only Codex's reset because
        it rendered narrowest_window() alone."""
        names = app.Dashboard.make_pace_card.__code__.co_names
        self.assertIn("provider_pace_rows", names)
        self.assertIn("setProperty", names)

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

    def test_cached_or_failed_usage_cannot_drive_capacity_guidance(self):
        now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
        providers = [{"id": "codex", "name": "Codex", "windows": [
            {"label": "window.session", "used": 12, "left": 88, "reset_raw": "2026-09-27T13:00:00Z"}],
            "credits": 40}]
        for observed_at in (None, now - timedelta(minutes=46)):
            shown = app.current_usage_providers(providers, observed_at, now)
            self.assertEqual(shown[0]["windows"], [])
            self.assertIsNone(shown[0]["credits"])
            self.assertTrue(shown[0]["has_unknown_windows"])
            self.assertEqual(app.pace_summary(app.narrowest_window(shown))["state"], "unknown")
        self.assertEqual(providers[0]["windows"][0]["left"], 88)

    def test_live_usage_excludes_expired_window_but_keeps_valid_window(self):
        now = datetime(2026, 9, 27, 12, tzinfo=timezone.utc)
        providers = [{"windows": [
            {"left": 95, "reset_raw": "2026-09-27T11:59:00Z"},
            {"left": 40, "reset_raw": "2026-09-27T12:30:00Z"},
            {"left": 60, "reset_raw": "30m"}], "credits": 10}]
        shown = app.current_usage_providers(providers, now, now)
        self.assertEqual([item["left"] for item in shown[0]["windows"]], [40, 60])
        self.assertEqual(shown[0]["credits"], 10)
        self.assertTrue(shown[0]["has_unknown_windows"])

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

    # ---- pace card: combined scope ------------------------------------

    def test_provider_pace_rows_keeps_every_provider(self):
        """narrowest_window() collapses the combined scope to one governing
        window, which hid every other provider on the current-state card."""
        providers = [
            {"id": "codex", "name": "Codex", "windows": [
                {"label": "window.session", "left": 58, "reset": "2 sa. 14 dk."},
                {"label": "window.weekly", "left": 82, "reset": "4 gün 6 sa."},
            ]},
            {"id": "claude", "name": "Claude", "windows": [
                {"label": "window.session", "left": 33, "reset": "48 dk."},
                {"label": "window.weekly", "left": 69, "reset": "3 gün 2 sa."},
            ]},
        ]
        rows = app.provider_pace_rows(providers)
        self.assertEqual([row["id"] for row in rows], ["claude", "codex"])
        self.assertEqual([row["left"] for row in rows], [33, 58])
        # Each row carries that provider's own tightest window, not the global one.
        self.assertEqual({row["label"] for row in rows}, {app.t("window.session")})

    def test_provider_pace_rows_skips_providers_without_windows(self):
        rows = app.provider_pace_rows([{"id": "codex", "name": "Codex", "windows": []}])
        self.assertEqual(rows, [])

    # ---- refresh runs off the GUI thread -------------------------------

    def test_cost_reads_overlap(self):
        """One slow provider must not delay the other provider's CLI call."""
        from threading import Barrier

        calls = []
        both_started = Barrier(2)

        def slow_cost(command, provider):
            calls.append(provider)
            both_started.wait(timeout=2)
            return {"provider": provider}, None

        self._patch(app, "read_cost", slow_cost)
        costs, error = app.read_all_costs("codexbar", ["codex", "claude"])
        self.assertIsNone(error)
        self.assertEqual(set(costs), {"codex", "claude"})
        self.assertEqual(len(calls), 2)

    def test_usage_is_emitted_before_cost_read_finishes(self):
        self._patch_live_reads({"codex": [{"id": "codex"}]})
        events = []

        def slow_costs(command, ids):
            events.append("cost-start")
            return {}, None

        self._patch(app, "read_all_costs", slow_costs)
        worker = app.RefreshWorker("codexbar", None, [])
        worker.usage_ready.connect(lambda result: events.append("usage-ready"))
        worker.done.connect(lambda result: events.append("done"))
        worker.run()
        # One emit carries the limits, one the compaction figures; both precede costs.
        self.assertEqual(events, ["usage-ready", "usage-ready", "cost-start", "done"])

    def test_refresh_click_queues_a_new_run_while_busy(self):
        class BusyDashboard:
            refresh_thread = object()
            refresh_pending = False

            def set_footer(self, key):
                self.footer = key

            def refresh(self):
                self.started = True

        dashboard = BusyDashboard()
        app.Dashboard.request_refresh(dashboard)
        self.assertTrue(dashboard.refresh_pending)
        self.assertEqual(dashboard.footer, "footer.refreshQueued")
        dashboard.refresh_thread = None
        app.Dashboard.request_refresh(dashboard)
        self.assertTrue(dashboard.started)

    def test_refresh_worker_gathers_usage_and_costs(self):
        calls = []

        def fake_costs(command, ids):
            calls.append(tuple(sorted(ids)))
            return {"codex": {"sessionTokens": 5}}, None

        asked = self._patch_live_reads({"codex": [{"id": "codex"}], "claude": [{"id": "claude"}]})
        self._patch(app, "read_all_costs", fake_costs)
        worker = app.RefreshWorker("codexbar", None, ["stale"])
        received = []
        worker.done.connect(received.append)
        worker.run()
        # A cached provider is asked again by name, alongside the defaults.
        self.assertEqual(sorted(asked), ["claude", "codex", "stale"])
        self.assertEqual(calls, [("claude", "codex")])
        self.assertEqual(sorted(item["id"] for item in received[0]["providers"]), ["claude", "codex"])
        self.assertEqual(received[0]["costs"], {"codex": {"sessionTokens": 5}})

    def test_refresh_worker_never_asks_upstream_for_every_provider_twice(self):
        """`--provider all` walks ~70 providers and took 35s per refresh; it may
        run once per launch to discover a new provider, never on every tick."""
        scans = []

        def full_scan(command, fixture):
            scans.append("all")
            return [{"id": "gemini"}, {"id": "codex", "stale": True}], None

        self._patch_live_reads({"codex": [{"id": "codex"}]})
        self._patch(app, "read_usage", full_scan)
        self._patch(app, "read_all_costs", lambda command, ids: ({}, None))
        received, late = [], []
        for discover in (True, False):
            worker = app.RefreshWorker("codexbar", None, [], discover=discover)
            worker.done.connect(received.append)
            worker.usage_ready.connect(lambda result: late.append(result) if received else None)
            worker.run()
        self.assertEqual(scans, ["all"])
        # The slow scan never holds back the result; it adds only what is new afterwards.
        self.assertEqual(received[0]["providers"], [{"id": "codex"}])
        self.assertEqual(late[0]["providers"], [{"id": "gemini"}])
        self.assertEqual(received[1]["providers"], [{"id": "codex"}])

    def test_claude_usage_prefers_oauth_and_falls_back_to_auto(self):
        """`auto` drives the Claude CLI on Linux and took 14.6s against 0.4s for OAuth."""
        asked = []
        entry = [{"provider": "claude", "source": "oauth", "usage": {"primary": {"usedPercent": 10}}}]

        def fake(command, arguments):
            asked.append("--source" in arguments)
            return (entry, None) if "--source" not in arguments or oauth_works else (None, "oauth missing")

        self._patch(app, "run_json", fake)
        for oauth_works in (True, False):
            asked.clear()
            providers, error = app.read_provider_usage("codexbar", "claude")
            self.assertEqual(providers[0]["id"], "claude")
            self.assertEqual(asked, [True] if oauth_works else [True, False])

    def test_cost_skips_session_mirrors_that_crash_codexbar(self):
        seen = []
        self._patch(app, "run_json", lambda command, arguments: (seen.append(arguments), ({}, None))[1])
        app.read_cost("codexbar", "claude")
        self.assertIn("--provider-native-only", seen[0])

    def test_codex_falls_back_to_its_own_cli_when_codexbar_cannot_start_it(self):
        """Codex 0.159 dropped `--ask-for-approval untrusted`, which CodexBar 0.53
        still passes: the app-server exits at once and Codex vanished from Orbit."""
        broken = [{"provider": "codex", "source": "auto",
                   "error": {"message": "codex app-server closed stdout", "code": 1}}]
        direct = app.codex_entry_from_rpc(
            {"rateLimits": {"planType": "plus",
                            "primary": {"usedPercent": 50, "resetsAt": 1790857345},
                            "secondary": {"usedPercent": 59, "resetsAt": 1791309939},
                            "credits": {"hasCredits": False, "balance": "0"}},
             "rateLimitResetCredits": {"availableCount": 2, "credits": [
                 {"status": "available", "expiresAt": 1792692576},
                 {"status": "available", "expiresAt": 1791150492},
                 {"status": "used", "expiresAt": 1790000000}]}},
            {"account": {"email": "utku@example.com", "planType": "plus"}})
        self._patch(app, "run_json", lambda command, arguments: (broken, None))
        self._patch(app, "read_codex_direct", lambda: (direct, None))
        providers, error = app.read_provider_usage("codexbar", "codex")
        self.assertIsNone(error)
        codex = providers[0]
        self.assertEqual((codex["id"], codex["source"], codex["email"]), ("codex", "codex-cli", "utku@example.com"))
        self.assertEqual([item["used"] for item in codex["windows"]], [50.0, 59.0])
        self.assertEqual(codex["windows"][0]["reset_raw"], "2026-10-01T12:22:25Z")
        self.assertEqual(codex["credits"], 0.0)
        # Only credits still available count, and the soonest expiry is the one shown.
        self.assertEqual(codex["reset_credits"], {"available": 2, "next_expiry": "2026-10-04T21:48:12Z"})

    def test_codex_failure_reports_the_upstream_reason(self):
        broken = [{"provider": "codex", "error": {"message": "codex app-server closed stdout"}}]
        self._patch(app, "run_json", lambda command, arguments: (broken, None))
        self._patch(app, "read_codex_direct", lambda: (None, "direct failed"))
        self.assertEqual(app.read_provider_usage("codexbar", "codex"), ([], "codex app-server closed stdout"))

    def test_working_codexbar_entry_only_gains_reset_credits(self):
        upstream = [{"provider": "codex", "source": "oauth",
                     "usage": {"primary": {"usedPercent": 10}, "accountEmail": "a@example.com"}}]
        direct = {"provider": "codex", "source": "codex-cli", "usage": {"primary": {"usedPercent": 99}},
                  "resetCredits": {"available": 3, "next_expiry": None}}
        self._patch(app, "run_json", lambda command, arguments: (upstream, None))
        self._patch(app, "read_codex_direct", lambda: (direct, None))
        codex = app.read_provider_usage("codexbar", "codex")[0][0]
        self.assertEqual((codex["source"], codex["windows"][0]["used"]), ("oauth", 10.0))
        self.assertEqual(codex["reset_credits"]["available"], 3)

    def test_compaction_rate_counts_sessions_compacted_in_the_window(self):
        now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        recent, old = "2026-09-30T10:00:00Z", "2026-09-01T10:00:00Z"
        with tempfile.TemporaryDirectory() as folder:
            claude, codex = Path(folder, "claude", "project"), Path(folder, "codex", "2026", "09", "30")
            claude.mkdir(parents=True)
            codex.mkdir(parents=True)

            def boundary(stamp):
                return json.dumps({"type": "system", "subtype": "compact_boundary", "timestamp": stamp})

            Path(claude, "twice.jsonl").write_text(boundary(recent) + "\n" + boundary(recent) + "\n")
            Path(claude, "quiet.jsonl").write_text(json.dumps({"type": "user", "timestamp": recent}) + "\n")
            # Still active, but its only compaction predates the window.
            Path(claude, "long-ago.jsonl").write_text(boundary(old) + "\n")
            # A user who merely types the marker is not a compaction.
            Path(claude, "mention.jsonl").write_text(
                json.dumps({"type": "user", "text": '"compact_boundary"', "timestamp": recent}) + "\n")
            Path(codex, "rollout-a.jsonl").write_text(
                json.dumps({"type": "compacted", "timestamp": recent, "payload": {}}) + "\n")
            # Codex replays an encrypted compaction item on every later turn; it is not a new event.
            Path(codex, "rollout-b.jsonl").write_text(
                json.dumps({"type": "response_item", "timestamp": recent, "payload": {"type": "compaction"}}) + "\n")
            sources = {"claude": (Path(folder, "claude"), "*/*.jsonl", b'"compact_boundary"'),
                       "codex": (Path(folder, "codex"), "**/*.jsonl", b'"compacted"')}
            self.assertEqual(app.compaction_stats("claude", now, sources),
                             {"sessions": 4, "compacted": 1, "events": 2, "rate": 25.0})
            self.assertEqual(app.compaction_stats("codex", now, sources),
                             {"sessions": 2, "compacted": 1, "events": 1, "rate": 50.0})
            self.assertIsNone(app.compaction_stats("gemini", now, sources))

    def test_each_provider_goes_stale_on_its_own_clock(self):
        """Codex answers in under a second and Claude in ~15; one shared timestamp
        would either hide the fast one or vouch for the slow one's old numbers."""
        now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        future = "2026-10-01T15:00:00Z"
        providers = [
            {"id": "codex", "windows": [{"reset_raw": future}], "credits": 0.0, "reset_credits": {"available": 3}},
            {"id": "claude", "windows": [{"reset_raw": future}], "credits": None},
        ]
        shown = app.current_usage_providers(providers, now, now, observed_by_id={"codex": now})
        self.assertEqual((len(shown[0]["windows"]), shown[0]["reset_credits"]), (1, {"available": 3}))
        self.assertFalse(shown[0]["has_unknown_windows"])
        self.assertEqual((shown[1]["windows"], shown[1]["has_unknown_windows"]), ([], True))

    def test_merge_keeps_a_failed_provider_and_its_position(self):
        current = [{"id": "claude", "v": 1}, {"id": "codex", "v": 1}]
        merged = app.merge_providers(current, [{"id": "codex", "v": 2}, {"id": "gemini", "v": 2}])
        self.assertEqual(merged, [{"id": "claude", "v": 1}, {"id": "codex", "v": 2}, {"id": "gemini", "v": 2}])

    def test_refresh_worker_does_not_block_the_caller(self):
        """The freeze was a blocking subprocess on the GUI thread: one CLI call
        per provider, each up to 25s, while the event loop waited."""
        from PyQt6.QtCore import QCoreApplication, QThread

        loop_app = QCoreApplication.instance() or QCoreApplication([])
        delay = 1.0

        def slow_usage(command, provider_id):
            time.sleep(delay)
            return ([{"id": "codex"}], None) if provider_id == "codex" else ([], "absent")

        self._patch(app, "read_provider_usage", slow_usage)
        self._patch(app, "read_compaction", lambda ids: {})
        self._patch(app, "read_all_costs", lambda command, ids: ({}, None))

        worker = app.RefreshWorker("codexbar", None, [])
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        results = []
        worker.done.connect(results.append)
        worker.done.connect(thread.quit)

        started = time.monotonic()
        thread.start()
        # The caller must come back immediately; the slow read is elsewhere.
        self.assertLess(time.monotonic() - started, delay / 2)

        deadline = time.monotonic() + delay * 5
        while not results and time.monotonic() < deadline:
            loop_app.processEvents()
            time.sleep(0.01)
        thread.wait(2000)
        self.assertEqual(results[0]["providers"], [{"id": "codex"}])

    def test_dashboard_refresh_dispatches_instead_of_reading_inline(self):
        """Guards the actual regression: the worker test alone would still pass
        if refresh() went back to calling the CLI on the GUI thread."""
        names = app.Dashboard.refresh.__code__.co_names
        self.assertIn("RefreshWorker", names)
        self.assertIn("QThread", names)
        self.assertNotIn("read_usage", names)
        self.assertNotIn("read_all_costs", names)

    def _patch_live_reads(self, by_provider: dict) -> list:
        """Stand in for the per-provider CLI reads; returns the ids that were asked."""
        asked = []

        def fake(command, provider_id):
            asked.append(provider_id)
            found = by_provider.get(provider_id)
            return (found, None) if found else ([], "absent")

        self._patch(app, "read_provider_usage", fake)
        self._patch(app, "read_compaction", lambda ids: {})
        return asked

    def _patch(self, target, name, value):
        original = getattr(target, name)
        setattr(target, name, value)
        self.addCleanup(setattr, target, name, original)


if __name__ == "__main__":
    unittest.main()
