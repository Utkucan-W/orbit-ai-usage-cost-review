from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path

from PyQt6.QtCore import QSettings, QSharedMemory, QStandardPaths, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGraphicsDropShadowEffect, QGridLayout, QHBoxLayout, QLabel,
    QMainWindow, QMenu, QPushButton, QScrollArea, QSystemTrayIcon, QTabWidget, QToolTip, QVBoxLayout,
    QWidget,
)


DEFAULT_CLI = "/home/utkucan/.local/bin/codexbar-0540"
# Keep the shared-memory name stable so an already-running pre-Orbit build
# still prevents a duplicate tray process during the rebrand transition.
APP_INSTANCE_NAME = "codexbar-linux-single-instance-v1"
APP_NAME = "Orbit"
SETTINGS_ORGANIZATION = "Utku"
SETTINGS_APPLICATION = "Orbit"
LEGACY_SETTINGS_APPLICATION = "CodexBarLinux"
APP_DATA_DIRECTORY = "Orbit"
LEGACY_APP_DATA_DIRECTORY = "CodexBarLinux"
LOGO_PATH = Path(__file__).parent / "assets" / "orbit-logo.png"
LANGUAGE_KEY = "language"
DEFAULT_LANGUAGE = "tr"
SUPPORTED_LANGUAGES = ("tr", "en")
MONTH_NAMES_BY_LANGUAGE = {
    "tr": ("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}
# UI strings live behind keys so a language switch never has to re-fetch or
# re-parse provider data; only the render pass changes.
TRANSLATIONS: dict[str, dict[str, str]] = {
    "tr": {
        "app.subtitle": "AI kullanım ve maliyet özeti",
        "btn.refresh": "Yenile",
        "tip.refresh": "Kullanım verisini yenile",
        "tip.theme.light": "Açık temaya geç",
        "tip.theme.dark": "Koyu temaya geç",
        "tip.language": "Switch to English",
        "lang.next": "EN",
        "tab.usage": "Kullanım",
        "tab.cost": "Maliyet",
        "scope.all": "Tümü",
        "scope.caption.all": "Codex + Claude birleşik",
        "scope.caption.one": "yalnız {name}",
        "provider.unknown": "Kaynağı bilinmeyen",
        "window.session": "Oturum",
        "window.weekly": "Haftalık",
        "window.monthly": "Aylık",
        "window.generic": "Pencere",
        "provider.generic": "Sağlayıcı",
        "usage.left": "kaldı",
        "usage.reset": "Sıfırlanma: {value}",
        "usage.resetUnknown": "Reset zamanı bilinmiyor",
        "email.show": "E-postayı göster",
        "email.hide": "E-postayı gizle",
        "account.fallback": "Bağlı hesap",
        "stat.credit": "KREDİ",
        "stat.sessionCost": "BU OTURUM MALİYETİ",
        "stat.sessionTokens": "BU OTURUM TOKENLERİ",
        "stat.cost31": "SON 31 GÜN MALİYETİ",
        "stat.tokens31": "SON 31 GÜN TOKENLERİ",
        "stat.last31": "SON 31 GÜN",
        "pace.context": "ANLIK DURUM",
        "pace.contextNarrow": "ANLIK DURUM · EN DAR PENCERE",
        "pace.remaining": "KALAN KAPASİTE",
        "pace.resetLabel": "SIFIRLANMA",
        "pace.unknown.headline": "Tempo hesaplanamadı",
        "pace.unknown.detail": "Kullanım penceresi verisi geldiğinde kalan kapasiteyi ve sıfırlanma zamanını burada göreceksin.",
        "pace.unknown.guidance": "Sağlayıcı limit bilgisini yenilediğinde durum otomatik yorumlanır.",
        "pace.unknown.method": "Bu özet, mevcut limit verisine dayanır.",
        "pace.exhausted.headline": "Kapasite tükendi",
        "pace.exhausted.guidance": "Bu pencere sıfırlanana kadar yeni yoğun istekler bekletilir.",
        "pace.high.headline": "Kapasite yüksek",
        "pace.high.guidance": "Kapasitenin büyük bölümü kullanılabilir; mevcut kullanım düzeyi sürdürülebilir.",
        "pace.balanced.headline": "Kapasite dengeli",
        "pace.balanced.guidance": "Kapasite yeterli düzeyde; planlanan kullanım sürdürülebilir.",
        "pace.declining.headline": "Kapasite azalıyor",
        "pace.declining.guidance": "Kalan alan sınırlanmaya başladı; uzun veya yoğun işleri planlı yürütmek yararlı olur.",
        "pace.critical.headline": "Kapasite kritik",
        "pace.critical.guidance": "Kapasite kritik düzeyde; kritik olmayan yoğun işleri sıfırlanma sonrasına bırakmak yararlı olur.",
        "pace.detail": "{label} limitinin %{used}'si kullanıldı; %{left} kapasite kaldı. Sıfırlanma: {reset}",
        "pace.method": "Bu değerlendirme kullanım hızını tahmin etmez; mevcut kapasiteyi ve sıfırlanma zamanını yorumlar.",
        "pace.unknownReset": "bilinmiyor",
        "pace.activeWindow": "Aktif",
        "combined.captionAll": "BİRLEŞİK TOKEN · {scope}",
        "combined.captionOne": "TOPLAM TOKEN · {scope}",
        "combined.unit": "token",
        "combined.shareTitle": "Kayıtlı geçmiş toplamı",
        "combined.noHistory": "Kayıtlı token geçmişi yok; ilk yenilemeden sonra dolar.",
        "history.title": "12 aylık token geçmişi",
        "history.monthly": "Aylık toplam",
        "history.daily": "Günlük ayrıntı",
        "history.hint": "Sütuna gel: hangi payın hangi sağlayıcıya ait olduğunu gösterir. Kayıtlar bu cihazda 365 gün tutulur.",
        "history.daysTitle": "Kayıt bulunan günler · son 365 gün",
        "history.empty": "Bu kapsam için kayıt yok.",
        "cost.dailyTitle": "Günlük maliyet · {scope}",
        "models.title": "En çok kullanılan modeller",
        "models.fallback": "Model",
        "chart.noDailyCost": "Grafik için günlük maliyet verisi yok",
        "chart.spent": "{amount} harcandı",
        "empty.scope": "Bu kapsam için sağlayıcı verisi yok.",
        "empty.costHistory": "Bu sağlayıcı için yerel maliyet geçmişi henüz bulunmuyor.",
        "empty.providers": "Gösterilecek sağlayıcı verisi yok.",
        "footer.updated": "Son güncelleme {time} · {sources}",
        "footer.cachedLoading": "Son başarılı veri gösteriliyor · Canlı veri yenileniyor…",
        "footer.cached": "Son başarılı veri gösteriliyor · {reason}",
        "footer.refreshFailed": "Yenileme başarısız",
        "tray.open": "Orbit'i aç",
        "tray.refresh": "Yenile",
        "tray.quit": "Çıkış",
        "app.alreadyRunning": "Orbit zaten arka planda çalışıyor.",
        "error.timeout": "CodexBar yanıt vermedi; yenilemeyi tekrar dene.",
        "error.launch": "CodexBar CLI çalıştırılamadı: {detail}",
        "error.json": "CodexBar geçerli JSON döndürmedi.",
        "error.fixture": "Fixture okunamadı: {detail}",
        "error.noCost": "Bu sağlayıcı için yerel maliyet verisi yok.",
        "error.noProviderList": "CLI çıktısında provider listesi bulunamadı.",
        "error.providerError": "Provider hatası",
        "error.noUsableProviders": "Kullanılabilir provider verisi bulunamadı.",
    },
    "en": {
        "app.subtitle": "AI usage and cost overview",
        "btn.refresh": "Refresh",
        "tip.refresh": "Refresh usage data",
        "tip.theme.light": "Switch to light theme",
        "tip.theme.dark": "Switch to dark theme",
        "tip.language": "Türkçe'ye geç",
        "lang.next": "TR",
        "tab.usage": "Usage",
        "tab.cost": "Cost",
        "scope.all": "All",
        "scope.caption.all": "Codex + Claude combined",
        "scope.caption.one": "{name} only",
        "provider.unknown": "Unattributed",
        "window.session": "Session",
        "window.weekly": "Weekly",
        "window.monthly": "Monthly",
        "window.generic": "Window",
        "provider.generic": "Provider",
        "usage.left": "left",
        "usage.reset": "Resets: {value}",
        "usage.resetUnknown": "Reset time unknown",
        "email.show": "Show email",
        "email.hide": "Hide email",
        "account.fallback": "Connected account",
        "stat.credit": "CREDITS",
        "stat.sessionCost": "SESSION COST",
        "stat.sessionTokens": "SESSION TOKENS",
        "stat.cost31": "COST · LAST 31 DAYS",
        "stat.tokens31": "TOKENS · LAST 31 DAYS",
        "stat.last31": "LAST 31 DAYS",
        "pace.context": "CURRENT STATE",
        "pace.contextNarrow": "CURRENT STATE · TIGHTEST WINDOW",
        "pace.remaining": "REMAINING",
        "pace.resetLabel": "RESETS",
        "pace.unknown.headline": "Pace unavailable",
        "pace.unknown.detail": "Once usage window data arrives, remaining capacity and reset time appear here.",
        "pace.unknown.guidance": "The state is interpreted automatically as soon as the provider reports limits.",
        "pace.unknown.method": "This summary reflects the current limit data only.",
        "pace.exhausted.headline": "Capacity exhausted",
        "pace.exhausted.guidance": "New heavy requests wait until this window resets.",
        "pace.high.headline": "Capacity high",
        "pace.high.guidance": "Most of the capacity is available; the current usage level is sustainable.",
        "pace.balanced.headline": "Capacity balanced",
        "pace.balanced.guidance": "Capacity is adequate; the planned usage is sustainable.",
        "pace.declining.headline": "Capacity declining",
        "pace.declining.guidance": "Headroom is tightening; plan long or heavy jobs deliberately.",
        "pace.critical.headline": "Capacity critical",
        "pace.critical.guidance": "Capacity is critical; consider deferring non-essential heavy jobs until after the reset.",
        "pace.detail": "{used}% of the {label} limit is used; {left}% capacity remains. Resets: {reset}",
        "pace.method": "This reading does not forecast a consumption rate; it interprets current capacity and reset time.",
        "pace.unknownReset": "unknown",
        "pace.activeWindow": "Active",
        "combined.captionAll": "COMBINED TOKENS · {scope}",
        "combined.captionOne": "TOTAL TOKENS · {scope}",
        "combined.unit": "tokens",
        "combined.shareTitle": "Recorded history total",
        "combined.noHistory": "No token history recorded yet; it fills after the first refresh.",
        "history.title": "12-month token history",
        "history.monthly": "Monthly total",
        "history.daily": "Daily detail",
        "history.hint": "Hover a column to see which share belongs to which provider. Records are kept on this device for 365 days.",
        "history.daysTitle": "Days with records · last 365 days",
        "history.empty": "No records for this scope.",
        "cost.dailyTitle": "Daily cost · {scope}",
        "models.title": "Most used models",
        "models.fallback": "Model",
        "chart.noDailyCost": "No daily cost data to chart",
        "chart.spent": "{amount} spent",
        "empty.scope": "No provider data for this scope.",
        "empty.costHistory": "No local cost history for this provider yet.",
        "empty.providers": "No provider data to show.",
        "footer.updated": "Updated {time} · {sources}",
        "footer.cachedLoading": "Showing last successful data · refreshing live data…",
        "footer.cached": "Showing last successful data · {reason}",
        "footer.refreshFailed": "Refresh failed",
        "tray.open": "Open Orbit",
        "tray.refresh": "Refresh",
        "tray.quit": "Quit",
        "app.alreadyRunning": "Orbit is already running in the background.",
        "error.timeout": "CodexBar did not respond; try refreshing again.",
        "error.launch": "Could not run the CodexBar CLI: {detail}",
        "error.json": "CodexBar did not return valid JSON.",
        "error.fixture": "Could not read fixture: {detail}",
        "error.noCost": "No local cost data for this provider.",
        "error.noProviderList": "No provider list found in the CLI output.",
        "error.providerError": "Provider error",
        "error.noUsableProviders": "No usable provider data found.",
    },
}

_active_language = DEFAULT_LANGUAGE


def normalize_language(code: object) -> str:
    text = str(code or "").lower()
    return text if text in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def set_language(code: object) -> str:
    global _active_language
    _active_language = normalize_language(code)
    return _active_language


def current_language() -> str:
    return _active_language


def t(key: str, **values: object) -> str:
    """Look the key up in the active language, falling back to Turkish, then to
    the key itself so a cached label from an older build still renders."""
    table = TRANSLATIONS.get(_active_language, {})
    text = table.get(key) or TRANSLATIONS[DEFAULT_LANGUAGE].get(key) or key
    return text.format(**values) if values else text


def upper(text: str) -> str:
    """str.upper() maps Turkish 'i' to a dotless 'I'; the dotted 'İ' is correct."""
    if _active_language == "tr":
        text = text.replace("i", "İ").replace("ı", "I")
    return text.upper()


def percent_text(value: float) -> str:
    """Turkish writes the sign before the number, English after it."""
    return f"%{value:.0f}" if _active_language == "tr" else f"{value:.0f}%"


def month_names() -> tuple[str, ...]:
    return MONTH_NAMES_BY_LANGUAGE.get(_active_language, MONTH_NAMES_BY_LANGUAGE[DEFAULT_LANGUAGE])
ENGLISH_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
CACHED_PROVIDERS_KEY = "cached_providers"
SCOPE_KEY = "scope"
ALL_SCOPE = "all"
# Days recorded before the provider-aware schema cannot be attributed afterwards;
# they are kept under this key instead of being dropped or silently credited.
UNKNOWN_PROVIDER = "bilinmeyen"

# Same oklch lightness and chroma, hue apart: the warm/cool split survives
# greyscale and colour-vision deficiency, so the breakdown never depends on hue alone.
PROVIDER_PALETTE = {
    "codex": {"dark": "#25c2c2", "light": "#009192"},
    "claude": {"dark": "#e99169", "light": "#b85e31"},
    UNKNOWN_PROVIDER: {"dark": "#7d8798", "light": "#98a2b3"},
}
EXTRA_PALETTE = (
    {"dark": "#8da0ff", "light": "#5b6ed6"},
    {"dark": "#b084f7", "light": "#8a4fd8"},
    {"dark": "#83e5af", "light": "#1c7f52"},
)


def cli_path() -> str:
    candidates = [DEFAULT_CLI, "/usr/bin/codexbar", "codexbar"]
    return next((path for path in candidates if os.path.isabs(path) and os.access(path, os.X_OK)), "codexbar")


def run_json(command: str, arguments: list[str]) -> tuple[object | None, str | None]:
    try:
        result = subprocess.run([command, *arguments], capture_output=True, text=True, timeout=25, check=False)
    except subprocess.TimeoutExpired:
        return None, t("error.timeout")
    except OSError as exc:
        return None, t("error.launch", detail=exc)
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError:
        return None, result.stderr.strip() or t("error.json")


def read_usage(command: str, fixture: str | None = None) -> tuple[list[dict], str | None]:
    if fixture:
        try:
            payload = json.loads(Path(fixture).read_text())
        except Exception as exc:
            return [], t("error.fixture", detail=exc)
    else:
        payload, error = run_json(command, ["usage", "--format", "json", "--json-only", "--provider", "all"])
        if error:
            return [], error
    return normalize_providers(payload)


def read_cost(command: str, provider: str) -> tuple[dict, str | None]:
    payload, error = run_json(command, ["cost", "--format", "json", "--json-only", "--provider", provider])
    if error:
        return {}, error
    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        return payload[0], None
    return {}, t("error.noCost")


def read_all_costs(command: str, provider_ids: list[str]) -> tuple[dict[str, dict], str | None]:
    """Combining totals needs every provider's cost, not just the selected one."""
    costs: dict[str, dict] = {}
    failures: list[str] = []
    for provider_id in provider_ids:
        cost, error = read_cost(command, provider_id)
        if cost:
            costs[provider_id] = cost
        elif error:
            failures.append(f"{provider_id}: {error}")
    return costs, "; ".join(failures) or None


def format_reset(value: object, local_tz: tzinfo | None = None) -> str | None:
    """Format an absolute ISO reset timestamp in the user's local timezone."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    target_tz = local_tz or datetime.now().astimezone().tzinfo
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=target_tz)
    return f"{parsed.astimezone(target_tz).day} {month_names()[parsed.astimezone(target_tz).month - 1]} {parsed.astimezone(target_tz):%H:%M}"


def localize_reset_description(value: object) -> str | None:
    """Translate common upstream English reset descriptions for the UI."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if current_language() == "tr":
        duration = text
        duration = duration.replace("days", "gün").replace("day", "gün")
        duration = duration.replace("hours", "sa.").replace("hour", "sa.")
        duration = duration.replace("minutes", "dk.").replace("minute", "dk.")
        duration = duration.replace("d", " gün").replace("h", " sa.").replace("m", " dk.")
        if duration != text and any(char.isdigit() for char in text):
            return " ".join(duration.split())

    parts = text.replace(" at ", " ").split()
    if len(parts) == 4 and parts[0] in ENGLISH_MONTHS and parts[1].isdigit():
        clock = parts[2].split(":")
        if len(clock) == 2 and clock[0].isdigit() and clock[1].isdigit() and parts[3] in {"AM", "PM"}:
            hour = int(clock[0])
            minute = int(clock[1])
            if 1 <= hour <= 12 and 0 <= minute <= 59:
                if parts[3] == "PM" and hour != 12:
                    hour += 12
                if parts[3] == "AM" and hour == 12:
                    hour = 0
                return f"{int(parts[1])} {month_names()[ENGLISH_MONTHS[parts[0]] - 1]} {hour:02d}:{minute:02d}"
    return None


def window(raw: object, label: str) -> dict | None:
    if not isinstance(raw, dict) or raw.get("usedPercent") is None:
        return None
    used = clamp_percent(raw.get("usedPercent"))
    reset_value = raw.get("resetDescription") or raw.get("resetsAt")
    return {
        "label": label,
        # Stored raw: the reset text is language-dependent, so formatting it at
        # parse time would freeze it in whatever language was active back then.
        "reset_raw": reset_value,
        "used": used,
        "left": 100 - used,
    }


def reset_text(data: dict) -> str:
    """Render a reset moment in the active language, accepting cached provider
    data from an older build that only stored the formatted string."""
    raw = data.get("reset_raw") if isinstance(data, dict) else None
    if raw is None and isinstance(data, dict):
        return str(data.get("reset") or t("usage.resetUnknown"))
    return format_reset(raw) or localize_reset_description(raw) or (str(raw) if raw else "") or t("usage.resetUnknown")


def pace_summary(windows: list[dict]) -> dict[str, str]:
    """Explain the current limit state without inventing a usage-rate forecast."""
    valid_windows = [item for item in windows if isinstance(item, dict)] if isinstance(windows, list) else []
    if not valid_windows:
        return {
            "headline": t("pace.unknown.headline"),
            "detail": t("pace.unknown.detail"),
            "guidance": t("pace.unknown.guidance"),
            "method": t("pace.unknown.method"),
            "remaining": "—",
            "reset": "—",
        }

    primary = valid_windows[0]
    used = clamp_percent(primary.get("used"))
    left = clamp_percent(primary.get("left"))
    raw_label = primary.get("label") or "pace.activeWindow"
    label = t(str(raw_label))
    reset = reset_text(primary)
    reset_sentence = reset if reset.endswith(".") else f"{reset}."
    if used >= 100 or left <= 0:
        state = "exhausted"
    elif left >= 70:
        state = "high"
    elif left >= 40:
        state = "balanced"
    elif left >= 15:
        state = "declining"
    else:
        state = "critical"
    return {
        "headline": t(f"pace.{state}.headline"),
        "detail": t("pace.detail", label=label, used=f"{used:.0f}", left=f"{left:.0f}", reset=reset_sentence),
        "guidance": t(f"pace.{state}.guidance"),
        "method": t("pace.method"),
        "remaining": f"%{left:.0f}" if current_language() == "tr" else f"{left:.0f}%",
        "reset": reset,
    }


def narrowest_window(providers: list[dict]) -> list[dict]:
    """Combined pace is governed by whichever provider window is tightest."""
    windows = []
    for provider in providers:
        for item in provider.get("windows", []):
            if isinstance(item, dict):
                windows.append(dict(item, label=f"{provider.get('name') or t('provider.generic')} · {t(item.get('label') or 'window.generic')}"))
    return sorted(windows, key=lambda item: clamp_percent(item.get("left")))


def normalize_providers(payload: object) -> tuple[list[dict], str | None]:
    if isinstance(payload, dict) and payload.get("error"):
        error = payload["error"]
        return [], error.get("message", t("error.providerError")) if isinstance(error, dict) else str(error)
    entries = payload if isinstance(payload, list) else payload.get("providers", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return [], t("error.noProviderList")

    providers: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        usage = entry.get("usage") if isinstance(entry.get("usage"), dict) else {}
        identity = usage.get("identity") if isinstance(usage.get("identity"), dict) else {}
        windows = [window(usage.get("primary"), "window.session"), window(usage.get("secondary"), "window.weekly"), window(usage.get("tertiary"), "window.monthly")]
        windows = [item for item in windows if item]
        email = usage.get("accountEmail") or identity.get("accountEmail")
        credits = entry.get("credits") if isinstance(entry.get("credits"), dict) else {}
        if not windows and not email and credits.get("remaining") is None:
            continue
        pace = entry.get("pace") if isinstance(entry.get("pace"), dict) else {}
        pace_window = pace.get("primary") or pace.get("secondary") or pace.get("tertiary") or {}
        providers.append({
            "id": str(entry.get("provider") or entry.get("name") or "provider").lower(),
            "name": str(entry.get("name") or entry.get("provider") or "Provider").title(),
            "source": entry.get("source") or "local",
            "email": email or t("account.fallback"),
            "plan": usage.get("loginMethod", "connected").replace("_", " ").title(),
            "windows": windows,
            "credits": credits.get("remaining"),
            "credit_unit": credits.get("unit") or "credits",
            # Upstream pace prose changes frequently; the UI derives its stable summary from windows.
            "pace": pace_window,
        })
    return providers, None if providers else t("error.noUsableProviders")


def load_cached_providers(settings: QSettings) -> list[dict]:
    """Read the last successful usage snapshot without trusting malformed data."""
    raw = settings.value(CACHED_PROVIDERS_KEY, "")
    try:
        cached = json.loads(str(raw)) if raw else []
    except json.JSONDecodeError:
        return []
    return cached if isinstance(cached, list) and all(isinstance(item, dict) for item in cached) else []


def save_cached_providers(settings: QSettings, providers: list[dict]) -> None:
    settings.setValue(CACHED_PROVIDERS_KEY, json.dumps(providers, ensure_ascii=False))


def migrate_legacy_settings(settings: QSettings, legacy: QSettings) -> None:
    """Copy only user preferences that Orbit has not set yet."""
    for key in (CACHED_PROVIDERS_KEY, "theme", "token_history_view"):
        if not settings.contains(key) and legacy.contains(key):
            settings.setValue(key, legacy.value(key))


def clamp_percent(value: object) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def numeric_value(value: object) -> float | None:
    """Parse CLI numbers even when a provider adds separators or a currency sign."""
    if value is None:
        return None
    try:
        return float(str(value).strip().replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None


def compact_number(value: object) -> str:
    number = numeric_value(value)
    if number is None:
        return "—"
    for amount, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs(number) >= amount:
            return f"{number / amount:.1f}{suffix}"
    return f"{number:.0f}"


def money(value: object) -> str:
    number = numeric_value(value)
    if number is None:
        return "—"
    return f"${number:,.2f}"


def token_count(value: object) -> str:
    """Keep token values visually separate from currency values."""
    formatted = compact_number(value)
    return formatted if formatted == "—" else f"{formatted} token"


def provider_label(provider_id: str) -> str:
    if provider_id == UNKNOWN_PROVIDER:
        return t("provider.unknown")
    return str(provider_id).title()


def provider_color(provider_id: str, theme: str, order: list[str] | None = None) -> str:
    key = "dark" if theme == "dark" else "light"
    known = PROVIDER_PALETTE.get(str(provider_id).lower())
    if known:
        return known[key]
    index = order.index(provider_id) if order and provider_id in order else 0
    return EXTRA_PALETTE[index % len(EXTRA_PALETTE)][key]


def app_data_path() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(location) / APP_DATA_DIRECTORY / "token-history.json"


def legacy_app_data_path() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(location) / LEGACY_APP_DATA_DIRECTORY / "token-history.json"


def normalize_history_day(value: object) -> dict[str, int]:
    """Accept the provider-keyed shape and the legacy single-number shape."""
    if isinstance(value, dict):
        entries = {}
        for provider_id, tokens in value.items():
            number = numeric_value(tokens)
            if isinstance(provider_id, str) and number is not None and number >= 0:
                entries[provider_id] = round(number)
        return entries
    number = numeric_value(value)
    # A pre-schema day cannot be attributed later, so it is preserved as unknown
    # rather than dropped or credited to whichever provider happens to be selected.
    return {UNKNOWN_PROVIDER: round(number)} if number is not None and number >= 0 else {}


def reconcile_history_day(entries: dict[str, int]) -> dict[str, int]:
    """A pre-schema day holds the last-written provider's own total, so as soon as
    any provider reports that same day the unattributed copy is a duplicate rather
    than extra consumption. Dropping it is one-way, which keeps repeated merges
    stable instead of eroding the day a little more on every refresh."""
    if UNKNOWN_PROVIDER not in entries:
        return entries
    if not any(tokens for provider_id, tokens in entries.items() if provider_id != UNKNOWN_PROVIDER):
        return entries
    return {provider_id: tokens for provider_id, tokens in entries.items() if provider_id != UNKNOWN_PROVIDER}


def read_token_history_file(path: Path) -> dict[str, dict[str, int]]:
    try:
        payload = json.loads(path.read_text())
        days = payload.get("days", {}) if isinstance(payload, dict) else {}
        history = {}
        for raw_date, value in days.items():
            entries = reconcile_history_day(normalize_history_day(value)) if isinstance(raw_date, str) else {}
            if entries:
                history[raw_date] = entries
        return history
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return {}


def load_token_history(path: Path | None = None) -> dict[str, dict[str, int]]:
    if path:
        return read_token_history_file(path)
    return read_token_history_file(app_data_path()) or read_token_history_file(legacy_app_data_path())


def save_token_history(days: dict[str, dict[str, int]], path: Path | None = None) -> None:
    target = path or app_data_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"days": days}, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    except OSError:
        # Geçmiş görünümü isteğe bağlıdır; yazma hatası ana dashboard'u durdurmamalı.
        pass


def extract_daily_tokens(cost: dict) -> dict[str, int]:
    daily = cost.get("daily") if isinstance(cost.get("daily"), list) else []
    tokens: dict[str, int] = {}
    for item in daily:
        if not isinstance(item, dict):
            continue
        value = numeric_value(item.get("totalTokens"))
        raw_date = item.get("date")
        try:
            parsed = date.fromisoformat(str(raw_date))
        except (TypeError, ValueError):
            continue
        if value is not None and value >= 0:
            tokens[parsed.isoformat()] = round(value)
    return tokens


def extract_daily_costs(cost: dict) -> list[tuple[str, float]]:
    """Accept incomplete CLI day entries and return a chronologically stable series."""
    daily = cost.get("daily") if isinstance(cost.get("daily"), list) else []
    costs: dict[str, float] = {}
    for item in daily:
        if not isinstance(item, dict):
            continue
        value = numeric_value(
            item.get("totalCost")
            if item.get("totalCost") is not None
            else item.get("totalCostUSD", item.get("costUSD", item.get("cost")))
        )
        raw_date = item.get("date")
        try:
            parsed = date.fromisoformat(str(raw_date))
        except (TypeError, ValueError):
            continue
        if value is not None and value >= 0:
            costs[parsed.isoformat()] = value
    return sorted(costs.items())


def extract_model_costs(cost: dict) -> dict[str, float]:
    """Per-model spend lives in day (or, on older CLIs, project) breakdowns; fold it into one total per model."""
    for key in ("daily", "projects"):
        buckets = cost.get(key)
        if not isinstance(buckets, list):
            continue
        totals: dict[str, float] = {}
        for bucket in buckets:
            if not isinstance(bucket, dict):
                continue
            for row in bucket.get("modelBreakdowns") or []:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("modelName") or "").strip()
                value = numeric_value(row.get("cost")) or 0.0
                if name and value >= 0:
                    totals[name] = totals.get(name, 0.0) + value
        if totals:
            return totals
    return {}


def merge_token_history(
    existing: dict[str, dict[str, int]],
    incoming: dict[str, int],
    provider: str,
    today: date | None = None,
) -> dict[str, dict[str, int]]:
    """Write one provider's days without disturbing what the others recorded."""
    cutoff = (today or date.today()) - timedelta(days=364)
    merged = {raw_date: dict(normalize_history_day(value)) for raw_date, value in existing.items()}
    for raw_date, tokens in incoming.items():
        number = numeric_value(tokens)
        if number is None or number < 0:
            continue
        merged.setdefault(raw_date, {})[provider] = round(number)
    kept: dict[str, dict[str, int]] = {}
    for raw_date, entries in merged.items():
        try:
            reconciled = reconcile_history_day(entries)
            if date.fromisoformat(raw_date) >= cutoff and reconciled:
                kept[raw_date] = dict(sorted(reconciled.items()))
        except (TypeError, ValueError):
            continue
    return dict(sorted(kept.items()))


def history_providers(days: dict[str, dict[str, int]]) -> list[str]:
    """Stable ordering so a provider keeps its colour and stack position."""
    seen: list[str] = []
    for entries in days.values():
        for provider_id in entries:
            if provider_id not in seen:
                seen.append(provider_id)
    known = [item for item in ("codex", "claude") if item in seen]
    return known + sorted(item for item in seen if item not in known)


def scoped_entries(entries: dict[str, int], scope: str) -> dict[str, int]:
    if scope == ALL_SCOPE:
        return {key: value for key, value in entries.items() if value}
    return {scope: entries[scope]} if entries.get(scope) else {}


def day_total(entries: dict[str, int], scope: str = ALL_SCOPE) -> int:
    return sum(scoped_entries(entries, scope).values())


def history_total(days: dict[str, dict[str, int]], scope: str = ALL_SCOPE) -> int:
    return sum(day_total(entries, scope) for entries in days.values())


def provider_totals(days: dict[str, dict[str, int]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for entries in days.values():
        for provider_id, tokens in entries.items():
            totals[provider_id] = totals.get(provider_id, 0) + tokens
    return {key: totals[key] for key in history_providers(days) if totals.get(key)}


def monthly_token_totals(
    days: dict[str, dict[str, int]],
    today: date | None = None,
    scope: str = ALL_SCOPE,
) -> list[tuple[str, dict[str, int]]]:
    """Twelve months back, each carrying its own provider breakdown."""
    reference = today or date.today()
    months: list[tuple[int, int]] = []
    year, month = reference.year, reference.month
    for _ in range(12):
        months.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    totals: dict[tuple[int, int], dict[str, int]] = {key: {} for key in months}
    for raw_date, entries in days.items():
        try:
            parsed = date.fromisoformat(raw_date)
        except (TypeError, ValueError):
            continue
        key = (parsed.year, parsed.month)
        if key not in totals:
            continue
        for provider_id, tokens in scoped_entries(entries, scope).items():
            totals[key][provider_id] = totals[key].get(provider_id, 0) + tokens
    return [
        (f"{month_names()[month - 1]} {str(year)[-2:]}", totals[(year, month)])
        for year, month in reversed(months)
    ]


def recent_token_days(
    days: dict[str, dict[str, int]],
    limit: int = 31,
    scope: str = ALL_SCOPE,
) -> list[tuple[str, dict[str, int]]]:
    rows = [(raw_date, scoped_entries(entries, scope)) for raw_date, entries in sorted(days.items(), reverse=True)]
    return [row for row in rows if row[1]][:limit]


def app_icon() -> QIcon:
    return QIcon(str(LOGO_PATH)) if LOGO_PATH.exists() else QIcon()


def mask_email(email: str) -> str:
    """Keep enough of an address visible to identify the active account."""
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'•' * max(3, len(local) - len(visible))}@{domain}"


def breakdown_tooltip(title: str, entries: dict[str, int], colors: dict[str, str]) -> str:
    """One tooltip shape for every surface that shows a combined number."""
    total = sum(entries.values())
    lines = [f"<b>{title}</b>", f"{token_count(total)}"]
    if len(entries) > 1:
        for provider_id, tokens in entries.items():
            share = round(tokens / total * 100) if total else 0
            swatch = f"<span style='color:{colors.get(provider_id, '#888888')}'>&#9679;</span>"
            lines.append(f"{swatch} {provider_label(provider_id)} &nbsp;{compact_number(tokens)} &nbsp;{percent_text(share)}")
    return "<br>".join(lines)


def add_depth(widget: QWidget, theme: str, blur: int = 22, alpha: int = 0) -> QWidget:
    """Cast one soft shadow so a translucent card reads as a layer above the
    ground rather than a lighter patch of it."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, 5)
    effect.setColor(QColor(0, 0, 0, alpha or (130 if theme == "dark" else 34)))
    widget.setGraphicsEffect(effect)
    return widget


class ProgressTrack(QFrame):
    def __init__(self, left: float, color: str, track: str = "#e4e9f1"):
        super().__init__()
        self.left, self.color, self.track = left, color, track
        self.setFixedHeight(6)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.track))
        painter.drawRoundedRect(self.rect(), 3, 3)
        painter.setBrush(QColor(self.color))
        painter.drawRoundedRect(0, 0, round(self.width() * self.left / 100), self.height(), 3, 3)


class ShareBar(QWidget):
    """Horizontal stacked bar: one segment per provider, hover gives the split."""

    def __init__(self, entries: dict[str, int], colors: dict[str, str], title: str):
        super().__init__()
        self.entries, self.colors, self.title = entries, colors, title
        self.setFixedHeight(10)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        total = sum(self.entries.values())
        if not total:
            return
        path_width = self.width()
        offset = 0.0
        items = list(self.entries.items())
        for index, (provider_id, tokens) in enumerate(items):
            width = path_width - offset if index == len(items) - 1 else path_width * tokens / total
            painter.setBrush(QColor(self.colors.get(provider_id, "#888888")))
            painter.drawRoundedRect(round(offset), 0, max(2, round(width) - 2), self.height(), 5, 5)
            offset += width

    def mouseMoveEvent(self, event):
        if self.entries:
            QToolTip.showText(event.globalPosition().toPoint(), breakdown_tooltip(self.title, self.entries, self.colors), self)
        event.accept()

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)


class StackedTokenChart(QWidget):
    """Columns stack the providers; hovering a column explains who spent what."""

    def __init__(self, rows: list[tuple[str, dict[str, int]]], colors: dict[str, str], order: list[str], empty_track: str):
        super().__init__()
        self.rows, self.colors, self.order, self.empty_track = rows, colors, order, empty_track
        self.setMinimumHeight(158)
        self.setMouseTracking(True)

    def chart_geometry(self) -> tuple[object, float, int]:
        chart = self.rect().adjusted(8, 8, -8, -28)
        gap = 6
        width = max(5, (chart.width() - gap * (len(self.rows) - 1)) / max(1, len(self.rows)))
        return chart, width, gap

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        chart, width, gap = self.chart_geometry()
        maximum = max((sum(entries.values()) for _, entries in self.rows), default=0) or 1
        painter.setFont(QFont("Fira Sans", 8))
        for index, (label, entries) in enumerate(self.rows):
            x = round(chart.left() + index * (width + gap))
            total = sum(entries.values())
            painter.setBrush(QColor(self.empty_track))
            painter.drawRoundedRect(x, chart.bottom() - 3, round(width), 3, 2, 2)
            bottom = chart.bottom()
            for provider_id in self.order:
                tokens = entries.get(provider_id)
                if not tokens:
                    continue
                height = max(2, round(chart.height() * tokens / maximum))
                painter.setBrush(QColor(self.colors.get(provider_id, "#888888")))
                painter.drawRoundedRect(x, bottom - height, round(width), height, 3, 3)
                bottom -= height
            painter.setPen(QColor(self.empty_track).darker(160) if total else QColor(self.empty_track))
            painter.drawText(x - 7, self.height() - 21, round(width) + 14, 14, Qt.AlignmentFlag.AlignCenter, label.split()[0])
            painter.setPen(Qt.PenStyle.NoPen)

    def mouseMoveEvent(self, event):
        chart, width, gap = self.chart_geometry()
        position = event.position()
        index = int((position.x() - chart.left()) // (width + gap))
        if chart.contains(position.toPoint()) and 0 <= index < len(self.rows):
            label, entries = self.rows[index]
            if entries:
                QToolTip.showText(event.globalPosition().toPoint(), breakdown_tooltip(label, entries, self.colors), self)
                event.accept()
                return
        QToolTip.hideText()
        event.accept()

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)


class Sparkline(QWidget):
    def __init__(self, points: list[tuple[str, float]], color: str = "#7c9cff"):
        super().__init__()
        self.points, self.color = points, color
        self.setMinimumHeight(105)
        self.setMouseTracking(True)

    def plot_rect(self):
        return self.rect().adjusted(4, 10, -4, -8)

    def point_positions(self) -> list[tuple[float, float]]:
        if not self.points:
            return []
        rect = self.plot_rect()
        maximum = max((value for _, value in self.points), default=0) or 1
        step = rect.width() / max(1, len(self.points) - 1)
        return [
            (rect.left() + index * step, rect.bottom() - (value / maximum) * rect.height())
            for index, (_, value) in enumerate(self.points)
        ]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.plot_rect()
        points = self.point_positions()
        if not points:
            painter.setPen(QColor("#718096"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, t("chart.noDailyCost"))
            return
        path = QPainterPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        fill = QPainterPath(path)
        fill.lineTo(rect.right(), rect.bottom())
        fill.lineTo(rect.left(), rect.bottom())
        fill.closeSubpath()
        tint = QColor(self.color)
        tint.setAlpha(45)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tint)
        painter.drawPath(fill)
        painter.setPen(QColor(self.color))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setBrush(QColor(self.color).lighter(120))
        for point in points:
            painter.drawEllipse(int(point[0] - 2), int(point[1] - 2), 4, 4)

    def mouseMoveEvent(self, event):
        positions = self.point_positions()
        if not positions:
            QToolTip.hideText()
            return
        nearest_index = min(range(len(positions)), key=lambda index: abs(positions[index][0] - event.position().x()))
        label, value = self.points[nearest_index]
        try:
            parsed = date.fromisoformat(label)
            label = f"{parsed.day} {month_names()[parsed.month - 1]} {parsed.year}"
        except ValueError:
            pass
        QToolTip.showText(event.globalPosition().toPoint(), f"<b>{label}</b><br>{t('chart.spent', amount=money(value))}", self)
        event.accept()

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)


class UsageWindow(QFrame):
    def __init__(self, data: dict, color: str, track: str):
        super().__init__()
        self.setObjectName("usageWindow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        header = QHBoxLayout()
        label = QLabel(t(str(data["label"])))
        label.setObjectName("windowLabel")
        percentage = QLabel(percent_text(data["left"]))
        percentage.setObjectName("percentage")
        percentage.setStyleSheet(f"color:{color};")
        suffix = QLabel(t("usage.left"))
        suffix.setObjectName("percentageSuffix")
        header.addWidget(label)
        header.addStretch()
        header.addWidget(percentage)
        header.addWidget(suffix)
        layout.addLayout(header)
        layout.addWidget(ProgressTrack(data["left"], color, track))
        reset = QLabel(t("usage.reset", value=reset_text(data)))
        reset.setObjectName("reset")
        layout.addWidget(reset)


class StatTile(QFrame):
    def __init__(self, label: str, value: str, detail: str = "", theme: str = "light"):
        super().__init__()
        self.setObjectName("statTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(4)
        caption = QLabel(label)
        caption.setObjectName("statLabel")
        caption.setWordWrap(True)
        number = QLabel(value)
        number.setObjectName("statValue")
        # The detail row is always present, even when empty: without it a tile
        # with a unit and a tile without one put their values on different
        # baselines, so a grid row never lined up.
        sub = QLabel(detail or "\u00a0")
        sub.setObjectName("statDetail")
        sub.setWordWrap(True)
        layout.addWidget(caption)
        layout.addStretch(1)
        layout.addWidget(number)
        layout.addWidget(sub)
        add_depth(self, theme, blur=16)


class LegendRow(QFrame):
    def __init__(self, provider_id: str, tokens: int, total: int, color: str):
        super().__init__()
        self.setObjectName("legendRow")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(9)
        dot = QLabel("●")
        dot.setObjectName("legendDot")
        dot.setStyleSheet(f"color:{color};")
        name = QLabel(provider_label(provider_id))
        name.setObjectName("legendName")
        value = QLabel(compact_number(tokens))
        value.setObjectName("legendValue")
        share = QLabel(percent_text(round(tokens / total * 100) if total else 0))
        share.setObjectName("legendShare")
        share.setFixedWidth(42)
        share.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(dot)
        row.addWidget(name)
        row.addStretch()
        row.addWidget(value)
        row.addWidget(share)


class TokenValueRow(QFrame):
    def __init__(self, label: str, entries: dict[str, int], colors: dict[str, str], order: list[str]):
        super().__init__()
        self.setObjectName("tokenDayRow")
        self.setToolTip(breakdown_tooltip(label, entries, colors))
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(8)
        day_label = QLabel(label)
        day_label.setObjectName("tokenDayLabel")
        row.addWidget(day_label)
        row.addStretch()
        for provider_id in order:
            tokens = entries.get(provider_id)
            if not tokens:
                continue
            dot = QLabel("●")
            dot.setObjectName("legendDot")
            dot.setStyleSheet(f"color:{colors.get(provider_id, '#888888')};")
            row.addWidget(dot)
        token_label = QLabel(token_count(sum(entries.values())))
        token_label.setObjectName("tokenDayValue")
        row.addWidget(token_label)


class TokenDayRow(TokenValueRow):
    def __init__(self, raw_date: str, entries: dict[str, int], colors: dict[str, str], order: list[str]):
        try:
            parsed = date.fromisoformat(raw_date)
            label = f"{parsed.day} {month_names()[parsed.month - 1]} {parsed.year}"
        except ValueError:
            label = raw_date
        super().__init__(label, entries, colors, order)


class Dashboard(QMainWindow):
    def __init__(self, command: str, fixture: str | None = None):
        super().__init__()
        self.command, self.fixture = command, fixture
        self.providers: list[dict] = []
        self.costs: dict[str, dict] = {}
        self.token_history = load_token_history()
        self.revealed_provider_id: str | None = None
        self.settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        migrate_legacy_settings(
            self.settings,
            QSettings(SETTINGS_ORGANIZATION, LEGACY_SETTINGS_APPLICATION),
        )
        self.providers = load_cached_providers(self.settings)
        self.language = set_language(self.settings.value(LANGUAGE_KEY, DEFAULT_LANGUAGE))
        saved_theme = str(self.settings.value("theme", "light"))
        self.theme = saved_theme if saved_theme in {"light", "dark"} else "light"
        saved_history_view = str(self.settings.value("token_history_view", "monthly"))
        self.token_history_view = saved_history_view if saved_history_view in {"monthly", "daily"} else "monthly"
        self.scope = str(self.settings.value(SCOPE_KEY, ALL_SCOPE)) or ALL_SCOPE
        self.footer_state: tuple[str | None, str | None, dict] = (None, None, {})
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.resize(500, 780)
        self.setMinimumSize(430, 620)
        self.apply_theme()
        self.build_ui()
        if self.providers:
            self.show_cached_providers()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(60_000)

    # ---- scope helpers -------------------------------------------------

    def scope_ids(self) -> list[str]:
        ids = [provider["id"] for provider in self.providers]
        return ids if self.scope == ALL_SCOPE else [item for item in ids if item == self.scope]

    def scoped_providers(self) -> list[dict]:
        allowed = set(self.scope_ids())
        return [provider for provider in self.providers if provider["id"] in allowed]

    def palette_order(self) -> list[str]:
        return history_providers(self.token_history) or [provider["id"] for provider in self.providers]

    def colors(self) -> dict[str, str]:
        order = self.palette_order()
        ids = {*order, *(provider["id"] for provider in self.providers)}
        return {provider_id: provider_color(provider_id, self.theme, order) for provider_id in ids}

    def track_color(self) -> str:
        return "#2b3341" if self.theme == "dark" else "#e6ebf3"

    def scoped_history(self) -> dict[str, dict[str, int]]:
        return {
            raw_date: scoped_entries(entries, self.scope)
            for raw_date, entries in self.token_history.items()
            if scoped_entries(entries, self.scope)
        }

    def scoped_cost_value(self, key: str) -> float | None:
        values = [numeric_value(self.costs.get(provider_id, {}).get(key)) for provider_id in self.scope_ids()]
        present = [value for value in values if value is not None]
        return sum(present) if present else None

    # ---- construction --------------------------------------------------

    def build_ui(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 18, 20, 14)
        outer.setSpacing(11)
        header = QHBoxLayout()
        brand = QHBoxLayout()
        brand.setSpacing(11)
        logo = QLabel()
        logo.setObjectName("logo")
        logo_pixmap = QPixmap(str(LOGO_PATH))
        if not logo_pixmap.isNull():
            logo.setPixmap(logo_pixmap.scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setFixedSize(34, 34)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel(t("app.subtitle"))
        subtitle.setObjectName("subtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand.addWidget(logo)
        brand.addLayout(brand_text)
        header.addLayout(brand)
        header.addStretch()
        self.language_button = QPushButton(t("lang.next"))
        self.language_button.setObjectName("languageButton")
        self.language_button.setToolTip(t("tip.language"))
        self.language_button.setAccessibleName(t("tip.language"))
        self.language_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.language_button.clicked.connect(self.toggle_language)
        header.addWidget(self.language_button)
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme_button.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_button)
        self.update_theme_button()
        self.refresh_button = QPushButton(t("btn.refresh"))
        self.refresh_button.setObjectName("refreshButton")
        self.refresh_button.setToolTip(t("tip.refresh"))
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        outer.addLayout(header)

        selector = QFrame()
        selector.setObjectName("selector")
        selector_layout = QHBoxLayout(selector)
        selector_layout.setContentsMargins(4, 4, 4, 4)
        selector_layout.setSpacing(3)
        self.scope_layout = selector_layout
        self.scope_buttons: dict[str, QPushButton] = {}
        outer.addWidget(selector)

        self.tabs = QTabWidget()
        self.usage_page = self.make_usage_page()
        self.spend_page = self.make_spend_page()
        self.tabs.addTab(self.usage_page, t("tab.usage"))
        self.tabs.addTab(self.spend_page, t("tab.cost"))
        outer.addWidget(self.tabs, 1)
        self.footer = QLabel()
        self.footer.setObjectName("footer")
        self.footer.setWordWrap(True)
        outer.addWidget(self.footer)
        self.setCentralWidget(root)

    def apply_theme(self):
        self.setStyleSheet(style_for_theme(self.theme))
        if hasattr(self, "theme_button"):
            self.update_theme_button()

    def update_theme_button(self):
        is_dark = self.theme == "dark"
        self.theme_button.setText("☀" if is_dark else "☾")
        self.theme_button.setToolTip(t("tip.theme.light") if is_dark else t("tip.theme.dark"))
        self.theme_button.setAccessibleName(self.theme_button.toolTip())

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.settings.setValue("theme", self.theme)
        self.apply_theme()
        self.render_all()

    def toggle_language(self):
        """Rebuild rather than retranslate: tab titles, tray entries and card
        captions are created once, so a full rebuild is the honest way to make
        every surface follow the switch."""
        self.language = set_language("en" if self.language == "tr" else "tr")
        self.settings.setValue(LANGUAGE_KEY, self.language)
        tab_index = self.tabs.currentIndex() if getattr(self, "tabs", None) else 0
        self.build_ui()
        self.tabs.setCurrentIndex(tab_index)
        self.build_scope_selector()
        self.render_all()
        self.render_footer()
        if getattr(self, "_tray", None):
            retranslate_tray(self._tray, self)

    def make_usage_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = QWidget()
        self.usage_layout = QVBoxLayout(panel)
        self.usage_layout.setContentsMargins(2, 8, 2, 6)
        self.usage_layout.setSpacing(11)
        scroll.setWidget(panel)
        return scroll

    def make_spend_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = QWidget()
        self.spend_layout = QVBoxLayout(panel)
        self.spend_layout.setContentsMargins(2, 10, 2, 6)
        self.spend_layout.setSpacing(11)
        scroll.setWidget(panel)
        return scroll

    @staticmethod
    def clear_layout(layout: QVBoxLayout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                Dashboard.clear_layout(item.layout())

    # ---- data ----------------------------------------------------------

    def refresh(self):
        providers, error = read_usage(self.command, self.fixture)
        # Geçici CLI hatasında son başarılı ekranı koru.
        if providers:
            self.providers = providers
            save_cached_providers(self.settings, providers)
        if not self.providers:
            self.build_scope_selector()
            self.clear_layout(self.usage_layout)
            self.clear_layout(self.spend_layout)
            self.set_footer("empty.providers") if not error else self.set_footer(None, error)
            return
        cost_error = None
        if not self.fixture:
            self.costs, cost_error = read_all_costs(self.command, [provider["id"] for provider in self.providers])
            self.update_token_history()
        if self.scope != ALL_SCOPE and self.scope not in {provider["id"] for provider in self.providers}:
            self.scope = ALL_SCOPE
        self.build_scope_selector()
        self.render_all()
        if providers:
            updated = datetime.now().strftime("%H:%M")
            sources = " + ".join(dict.fromkeys(str(provider["source"]) for provider in self.providers))
            self.set_footer("footer.updated", cost_error, time=updated, sources=sources)
        else:
            self.set_footer("footer.cached", None, reason=error or t("footer.refreshFailed"))

    def show_cached_providers(self):
        """Render cached usage immediately while the first live refresh runs."""
        self.revealed_provider_id = None
        self.costs = {}
        self.build_scope_selector()
        self.render_all()
        self.set_footer("footer.cachedLoading")

    def update_token_history(self):
        changed = False
        for provider_id, cost in self.costs.items():
            incoming = extract_daily_tokens(cost)
            if incoming:
                self.token_history = merge_token_history(self.token_history, incoming, provider_id)
                changed = True
        if changed:
            save_token_history(self.token_history)

    def select_scope(self, scope: str):
        if scope == self.scope:
            return
        self.scope = scope
        self.settings.setValue(SCOPE_KEY, scope)
        self.revealed_provider_id = None
        self.build_scope_selector()
        self.render_all()

    def toggle_email(self, provider_id: str):
        self.revealed_provider_id = None if self.revealed_provider_id == provider_id else provider_id
        self.render_usage()

    def set_token_history_view(self, index: int):
        view = "daily" if index == 1 else "monthly"
        if view == self.token_history_view:
            return
        self.token_history_view = view
        self.settings.setValue("token_history_view", view)
        self.render_spend()

    def set_footer(self, key: str | None, suffix: str | None = None, **values: object):
        """Remember what the footer says, not how it reads, so a language switch
        can render the same state again instead of freezing the old wording."""
        self.footer_state = (key, suffix, values)
        self.render_footer()

    def render_footer(self):
        key, suffix, values = getattr(self, "footer_state", (None, None, {}))
        text = t(key, **values) if key else ""
        if suffix:
            text = f"{text} · {suffix}" if text else str(suffix)
        self.footer.setText(text)

    def render_all(self):
        self.render_usage()
        self.render_spend()

    # ---- scope selector -------------------------------------------------

    def build_scope_selector(self):
        while self.scope_layout.count():
            item = self.scope_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.scope_buttons = {}
        colors = self.colors()
        options = [(ALL_SCOPE, t("scope.all"), None)]
        options += [(provider["id"], provider["name"], colors.get(provider["id"])) for provider in self.providers]
        for scope_id, name, color in options:
            button = QPushButton(("●  " if color else "") + name)
            button.setObjectName("scopeButton")
            button.setCheckable(True)
            button.setChecked(scope_id == self.scope)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if color and scope_id != self.scope:
                button.setStyleSheet(f"#scopeButton {{ color: {color}; }}")
            button.clicked.connect(lambda _checked, value=scope_id: self.select_scope(value))
            self.scope_layout.addWidget(button, 1)
            self.scope_buttons[scope_id] = button

    # ---- usage tab ------------------------------------------------------

    def render_usage(self):
        self.clear_layout(self.usage_layout)
        providers = self.scoped_providers()
        if not providers:
            empty = QLabel(t("empty.scope"))
            empty.setObjectName("empty")
            self.usage_layout.addWidget(empty)
            self.usage_layout.addStretch()
            return
        colors = self.colors()
        track = self.track_color()
        for provider in providers:
            self.usage_layout.addWidget(self.make_account_card(provider, colors, track))
        self.usage_layout.addWidget(self.make_pace_card(providers))
        grid = QGridLayout()
        grid.setSpacing(9)
        credits = [provider["credits"] for provider in providers if provider["credits"] is not None]
        credit_unit = next((provider["credit_unit"] for provider in providers if provider["credits"] is not None), "credits")
        grid.addWidget(StatTile(t("stat.credit"), compact_number(sum(credits)) if credits else "—", credit_unit, theme=self.theme), 0, 0)
        grid.addWidget(StatTile(t("stat.sessionCost"), money(self.scoped_cost_value("sessionCostUSD")), "USD", theme=self.theme), 0, 1)
        grid.addWidget(StatTile(t("stat.sessionTokens"), token_count(self.scoped_cost_value("sessionTokens")), self.scope_caption(), theme=self.theme), 1, 0)
        grid.addWidget(StatTile(t("stat.cost31"), money(self.scoped_cost_value("last30DaysCostUSD")), "USD", theme=self.theme), 1, 1)
        self.usage_layout.addLayout(grid)
        self.usage_layout.addStretch()

    def make_account_card(self, provider: dict, colors: dict[str, str], track: str) -> QFrame:
        card = QFrame()
        card.setObjectName("identity")
        add_depth(card, self.theme)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 15)
        layout.setSpacing(12)
        head = QHBoxLayout()
        head.setSpacing(10)
        dot = QLabel("●")
        dot.setObjectName("legendDot")
        dot.setStyleSheet(f"color:{colors.get(provider['id'], '#888888')};")
        identity_column = QVBoxLayout()
        identity_column.setSpacing(1)
        name = QLabel(provider["name"])
        name.setObjectName("providerName")
        shown_email = provider["email"] if self.revealed_provider_id == provider["id"] else mask_email(provider["email"])
        meta = QLabel(shown_email)
        meta.setObjectName("meta")
        identity_column.addWidget(name)
        identity_column.addWidget(meta)
        eye = QPushButton("👁")
        eye.setObjectName("eyeButton")
        eye.setFixedSize(28, 24)
        eye.setToolTip(t("email.hide") if self.revealed_provider_id == provider["id"] else t("email.show"))
        eye.clicked.connect(lambda _checked=False, value=provider["id"]: self.toggle_email(value))
        plan = QLabel(provider["plan"])
        plan.setObjectName("plan")
        head.addWidget(dot)
        head.addLayout(identity_column)
        head.addWidget(eye)
        head.addStretch()
        head.addWidget(plan)
        layout.addLayout(head)
        for window_data in provider["windows"]:
            layout.addWidget(UsageWindow(window_data, colors.get(provider["id"], "#888888"), track))
        return card

    def make_pace_card(self, providers: list[dict]) -> QFrame:
        pace = QFrame()
        pace.setObjectName("pace")
        add_depth(pace, self.theme, blur=26)
        pace_layout = QVBoxLayout(pace)
        pace_layout.setContentsMargins(17, 16, 17, 16)
        pace_layout.setSpacing(9)
        pace_data = pace_summary(narrowest_window(providers))
        pace_header = QHBoxLayout()
        pace_context = QLabel(t("pace.context") if len(providers) < 2 else t("pace.contextNarrow"))
        pace_context.setObjectName("paceContext")
        pace_status = QLabel(pace_data["headline"])
        pace_status.setObjectName("paceStatus")
        pace_header.addWidget(pace_context)
        pace_header.addStretch()
        pace_header.addWidget(pace_status)
        pace_headline = QLabel(pace_data["headline"])
        pace_headline.setObjectName("paceHeadline")
        pace_text = QLabel(pace_data["detail"])
        pace_text.setWordWrap(True)
        pace_text.setObjectName("paceText")
        pace_metrics = QFrame()
        pace_metrics.setObjectName("paceMetrics")
        metrics_layout = QHBoxLayout(pace_metrics)
        metrics_layout.setContentsMargins(13, 11, 13, 11)
        metrics_layout.setSpacing(12)
        remaining_column = QVBoxLayout()
        remaining_column.setSpacing(1)
        remaining_caption = QLabel(t("pace.remaining"))
        remaining_caption.setObjectName("paceMetricLabel")
        remaining_value = QLabel(pace_data["remaining"])
        remaining_value.setObjectName("paceMetricValue")
        remaining_column.addWidget(remaining_caption)
        remaining_column.addWidget(remaining_value)
        divider = QFrame()
        divider.setObjectName("paceDivider")
        divider.setFrameShape(QFrame.Shape.VLine)
        reset_column = QVBoxLayout()
        reset_column.setSpacing(1)
        reset_caption = QLabel(t("pace.resetLabel"))
        reset_caption.setObjectName("paceMetricLabel")
        reset_value = QLabel(pace_data["reset"])
        reset_value.setObjectName("paceMetricValue")
        reset_value.setWordWrap(True)
        reset_column.addWidget(reset_caption)
        reset_column.addWidget(reset_value)
        metrics_layout.addLayout(remaining_column, 1)
        metrics_layout.addWidget(divider)
        metrics_layout.addLayout(reset_column, 1)
        pace_guidance = QLabel(pace_data["guidance"])
        pace_guidance.setWordWrap(True)
        pace_guidance.setObjectName("paceGuidance")
        pace_method = QLabel(pace_data["method"])
        pace_method.setWordWrap(True)
        pace_method.setObjectName("paceMethod")
        pace_layout.addLayout(pace_header)
        pace_layout.addWidget(pace_headline)
        pace_layout.addWidget(pace_text)
        pace_layout.addWidget(pace_metrics)
        pace_layout.addWidget(pace_guidance)
        pace_layout.addWidget(pace_method)
        return pace

    # ---- spend tab ------------------------------------------------------

    def scope_caption(self) -> str:
        return t("scope.caption.all") if self.scope == ALL_SCOPE else t("scope.caption.one", name=provider_label(self.scope))

    def render_spend(self):
        self.clear_layout(self.spend_layout)
        if not self.providers:
            empty = QLabel(t("empty.costHistory"))
            empty.setObjectName("empty")
            self.spend_layout.addWidget(empty)
            self.spend_layout.addStretch()
            return
        self.spend_layout.addWidget(self.make_combined_card())
        grid = QGridLayout()
        grid.setSpacing(9)
        grid.addWidget(StatTile(t("stat.cost31"), money(self.scoped_cost_value("last30DaysCostUSD")), "USD", theme=self.theme), 0, 0)
        grid.addWidget(StatTile(t("stat.tokens31"), token_count(self.scoped_cost_value("last30DaysTokens")), theme=self.theme), 0, 1)
        grid.addWidget(StatTile(t("stat.sessionCost"), money(self.scoped_cost_value("sessionCostUSD")), "USD", theme=self.theme), 1, 0)
        grid.addWidget(StatTile(t("stat.sessionTokens"), token_count(self.scoped_cost_value("sessionTokens")), theme=self.theme), 1, 1)
        self.spend_layout.addLayout(grid)
        self.render_token_history()
        self.render_daily_costs()
        self.render_models()
        self.spend_layout.addStretch()

    def make_combined_card(self) -> QFrame:
        colors = self.colors()
        history = self.scoped_history()
        totals = provider_totals(history)
        total = sum(totals.values())
        card = QFrame()
        card.setObjectName("heroCard")
        add_depth(card, self.theme, blur=28)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 17, 18, 17)
        layout.setSpacing(13)
        caption = QLabel(t("combined.captionAll", scope=upper(self.scope_caption())) if self.scope == ALL_SCOPE
                         else t("combined.captionOne", scope=upper(provider_label(self.scope))))
        caption.setObjectName("cardCaption")
        layout.addWidget(caption)
        value_row = QHBoxLayout()
        value_row.setSpacing(10)
        big = QLabel(compact_number(total) if total else "—")
        big.setObjectName("heroValue")
        unit = QLabel(t("combined.unit"))
        unit.setObjectName("heroUnit")
        cost_column = QVBoxLayout()
        cost_column.setSpacing(1)
        cost_caption = QLabel(t("stat.last31"))
        cost_caption.setObjectName("statLabel")
        cost_value = QLabel(money(self.scoped_cost_value("last30DaysCostUSD")))
        cost_value.setObjectName("heroCost")
        cost_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        cost_caption.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        cost_column.addWidget(cost_caption)
        cost_column.addWidget(cost_value)
        value_row.addWidget(big)
        value_row.addWidget(unit)
        value_row.addStretch()
        value_row.addLayout(cost_column)
        layout.addLayout(value_row)
        if totals:
            layout.addWidget(ShareBar(totals, colors, t("combined.shareTitle")))
            for provider_id, tokens in totals.items():
                layout.addWidget(LegendRow(provider_id, tokens, total, colors.get(provider_id, "#888888")))
        else:
            hint = QLabel(t("combined.noHistory"))
            hint.setObjectName("sectionHint")
            hint.setWordWrap(True)
            layout.addWidget(hint)
        return card

    def render_token_history(self):
        history = QFrame()
        history.setObjectName("chart")
        add_depth(history, self.theme)
        layout = QVBoxLayout(history)
        layout.setContentsMargins(17, 15, 17, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        heading = QLabel(t("history.title"))
        heading.setObjectName("historyTitle")
        header.addWidget(heading)
        header.addStretch()
        view_picker = QComboBox()
        view_picker.setObjectName("historyPicker")
        view_picker.addItem(t("history.monthly"), "monthly")
        view_picker.addItem(t("history.daily"), "daily")
        view_picker.setCurrentIndex(0 if self.token_history_view == "monthly" else 1)
        view_picker.currentIndexChanged.connect(self.set_token_history_view)
        header.addWidget(view_picker)
        layout.addLayout(header)
        summary = QLabel(t("history.hint"))
        summary.setObjectName("historyHint")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        colors = self.colors()
        order = self.palette_order()
        scoped = self.scoped_history()
        if self.token_history_view == "monthly":
            months = monthly_token_totals(self.token_history, scope=self.scope)
            layout.addWidget(StackedTokenChart(months, colors, order, self.track_color()))
            for label, entries in reversed(months):
                layout.addWidget(TokenValueRow(label, entries, colors, order))
        else:
            title = QLabel(t("history.daysTitle"))
            title.setObjectName("historyHint")
            layout.addWidget(title)
            rows = recent_token_days(self.token_history, 365, self.scope)
            layout.addWidget(StackedTokenChart(list(reversed(rows[:31])), colors, order, self.track_color()))
            for raw_date, entries in rows:
                layout.addWidget(TokenDayRow(raw_date, entries, colors, order))
        if not scoped:
            empty = QLabel(t("history.empty"))
            empty.setObjectName("historyHint")
            layout.addWidget(empty)
        self.spend_layout.addWidget(history)

    def render_daily_costs(self):
        series: dict[str, float] = {}
        for provider_id in self.scope_ids():
            for raw_date, value in extract_daily_costs(self.costs.get(provider_id, {})):
                series[raw_date] = series.get(raw_date, 0.0) + value
        if not series:
            return
        chart = QFrame()
        chart.setObjectName("chart")
        add_depth(chart, self.theme)
        chart_layout = QVBoxLayout(chart)
        chart_layout.setContentsMargins(17, 15, 17, 14)
        chart_layout.setSpacing(9)
        heading = QLabel(t("cost.dailyTitle", scope=self.scope_caption()))
        heading.setObjectName("historyTitle")
        chart_layout.addWidget(heading)
        accent = "#8da0ff" if self.theme == "dark" else "#5b6ed6"
        chart_layout.addWidget(Sparkline(sorted(series.items()), accent))
        self.spend_layout.addWidget(chart)

    def render_models(self):
        rows: list[tuple[str, str, float]] = []
        for provider_id in self.scope_ids():
            for name, cost in extract_model_costs(self.costs.get(provider_id, {})).items():
                rows.append((provider_id, name or t("models.fallback"), cost))
        if not rows:
            return
        colors = self.colors()
        panel = QFrame()
        panel.setObjectName("chart")
        add_depth(panel, self.theme)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(17, 15, 17, 14)
        layout.setSpacing(9)
        heading = QLabel(t("models.title"))
        heading.setObjectName("historyTitle")
        layout.addWidget(heading)
        for provider_id, name, cost in sorted(rows, key=lambda item: item[2], reverse=True)[:5]:
            line = QHBoxLayout()
            line.setSpacing(9)
            dot = QLabel("●")
            dot.setObjectName("legendDot")
            dot.setStyleSheet(f"color:{colors.get(provider_id, '#888888')};")
            model = QLabel(name)
            model.setObjectName("legendName")
            model.setToolTip(provider_label(provider_id))
            amount = QLabel(money(cost))
            amount.setObjectName("legendValue")
            line.addWidget(dot)
            line.addWidget(model)
            line.addStretch()
            line.addWidget(amount)
            layout.addLayout(line)
        self.spend_layout.addWidget(panel)


# Depth comes from layered translucency, not from flat fills: a gradient ground,
# hairline-lit card surfaces over it, and a soft cast shadow per card.
SHARED_STYLE = """
QWidget { background:transparent; font-family:'Fira Sans', 'Noto Sans', sans-serif; }
QLabel { background:transparent; }
QScrollArea { border:0; background:transparent; }
QTabWidget::pane { border:0; background:transparent; }
QTabBar::tab { padding:8px 15px; margin-right:6px; border-radius:10px; font-weight:600; font-size:12.5px; }
#title { font-size:25px; font-weight:700; letter-spacing:-.5px; }
#subtitle { font-size:12px; }
#footer { font-size:11px; padding:3px 2px; }
#scopeButton { background:transparent; border:0; border-radius:9px; padding:7px 8px; font-size:12px; font-weight:600; }
#sectionHint, #historyHint { font-size:11px; }
#meta { font-size:11.5px; }
#providerName { font-size:16px; font-weight:600; letter-spacing:-.2px; }
#plan { font-size:10.5px; font-weight:600; border-radius:8px; padding:4px 10px; }
#eyeButton { background:transparent; border:0; padding:0; font-size:13px; }
#windowLabel { font-size:12.5px; font-weight:500; }
#percentage { font-family:'Noto Sans Mono', monospace; font-size:12.5px; font-weight:600; }
#percentageSuffix { font-size:11px; }
#reset { font-size:11px; }
#legendDot { font-size:11px; }
#legendName { font-size:12.5px; font-weight:500; }
#legendValue { font-family:'Noto Sans Mono', monospace; font-size:12.5px; }
#legendShare { font-family:'Noto Sans Mono', monospace; font-size:12px; }
/* Small all-caps captions lose their Turkish diacritics below ~10px, so the
   caption scale starts at 10.5px and leans on tracking instead of size. */
#cardCaption, #statLabel, #paceContext, #paceMetricLabel { font-size:10.5px; font-weight:700; letter-spacing:.9px; }
#heroValue { font-family:'Noto Sans Mono', monospace; font-size:38px; font-weight:700; letter-spacing:-1.4px; }
#heroUnit { font-size:11px; }
#heroCost { font-family:'Noto Sans Mono', monospace; font-size:17px; font-weight:600; }
#paceStatus { border-radius:9px; padding:4px 10px; font-size:10.5px; font-weight:600; }
#paceHeadline { font-size:20px; font-weight:700; letter-spacing:-.4px; }
#paceText, #paceGuidance { font-size:12px; }
#paceMethod, #statDetail { font-size:10.5px; }
#paceMetricValue { font-family:'Noto Sans Mono', monospace; font-size:17px; font-weight:600; }
#statValue { font-family:'Noto Sans Mono', monospace; font-size:18px; font-weight:600; letter-spacing:-.4px; }
#historyTitle { font-size:13px; font-weight:600; }
#historyPicker { min-width:130px; font-size:11px; font-weight:600; }
#tokenDayLabel { font-size:12px; }
#tokenDayValue { font-family:'Noto Sans Mono', monospace; font-size:12px; font-weight:600; }
#empty { padding:24px 8px; }
#themeButton, #languageButton { min-width:20px; padding:7px 10px; }
#themeButton { font-size:15px; }
#languageButton { font-family:'Noto Sans Mono', monospace; font-size:11.5px; font-weight:700; letter-spacing:.6px; }
QComboBox::drop-down { border:0; width:24px; }
QScrollBar:vertical { background:transparent; width:9px; margin:2px 0; }
QScrollBar::handle:vertical { border-radius:4px; min-height:30px; }
/* Unstyled arrow buttons and the scroll-area corner render as bright squares
   over a translucent ground, so they are removed rather than recoloured. */
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; width:0; background:transparent; border:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QAbstractScrollArea::corner { background:transparent; border:0; }
QToolTip { border-radius:10px; padding:8px 11px; font-size:12px; }
"""


LIGHT_STYLE = SHARED_STYLE + """
QMainWindow { background:qlineargradient(x1:0, y1:0, x2:0.4, y2:1,
    stop:0 #eef2fa, stop:0.55 #f4f6fc, stop:1 #eceff8); }
QWidget { color:#172236; }
#title { color:#142033; }
#subtitle, #meta, #reset, #statLabel, #statDetail, #cardCaption, #sectionHint,
#historyHint, #percentageSuffix, #heroUnit, #legendShare { color:#69768c; }
#footer { color:#8793a5; }
#selector { background:rgba(20, 32, 51, 0.05); border:1px solid rgba(20, 32, 51, 0.05); border-radius:12px; }
#scopeButton { color:#69768c; }
#scopeButton:hover { background:rgba(255, 255, 255, 0.65); }
#scopeButton:checked { background:#ffffff; color:#142033; }
#identity, #chart, #statTile {
    background:qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.92), stop:1 rgba(255, 255, 255, 0.66));
    border:1px solid rgba(20, 32, 51, 0.075); border-radius:17px; }
#heroCard {
    background:qlineargradient(x1:0, y1:0, x2:0.6, y2:1,
        stop:0 rgba(91, 110, 214, 0.16), stop:0.6 rgba(255, 255, 255, 0.86), stop:1 rgba(255, 255, 255, 0.7));
    border:1px solid rgba(91, 110, 214, 0.22); border-radius:19px; }
#pace {
    background:qlineargradient(x1:0, y1:0, x2:0.6, y2:1,
        stop:0 rgba(28, 127, 82, 0.13), stop:0.65 rgba(255, 255, 255, 0.88), stop:1 rgba(255, 255, 255, 0.72));
    border:1px solid rgba(28, 127, 82, 0.2); border-radius:19px; }
#paceContext, #paceMetricLabel { color:#4d7b64; }
#paceStatus { background:rgba(28, 127, 82, 0.14); color:#146042; }
#paceHeadline { color:#123c2b; }
#paceText, #paceGuidance { color:#2f5b46; }
#paceMethod { color:#6f9182; }
#paceMetrics { background:rgba(255, 255, 255, 0.72); border:1px solid rgba(28, 127, 82, 0.16); border-radius:12px; }
#paceMetricValue { color:#12452f; }
#paceDivider { color:rgba(28, 127, 82, 0.18); background:rgba(28, 127, 82, 0.18); max-width:1px; }
#heroValue, #heroCost, #statValue, #providerName, #historyTitle, #tokenDayValue, #legendName { color:#142033; }
#plan { color:#5c6a80; background:rgba(20, 32, 51, 0.06); }
#legendValue { color:#5c6a80; }
#tokenDayRow { background:rgba(255, 255, 255, 0.6); border:1px solid rgba(20, 32, 51, 0.055); border-radius:10px; }
#tokenDayLabel { color:#5c6a80; }
#empty { color:#5c6a80; }
QComboBox { background:rgba(255, 255, 255, 0.85); border:1px solid rgba(20, 32, 51, 0.1); border-radius:9px; padding:6px 10px; min-width:150px; color:#172236; }
QComboBox QAbstractItemView { background:#ffffff; color:#172236; selection-background-color:#e4eaff; selection-color:#263b8f; border:1px solid rgba(20, 32, 51, 0.1); }
QPushButton { background:rgba(255, 255, 255, 0.9); border:1px solid rgba(20, 32, 51, 0.1); border-radius:10px; padding:7px 12px; color:#27364d; font-size:13px; font-weight:600; }
QPushButton:hover { background:#ffffff; border-color:rgba(20, 32, 51, 0.18); }
#refreshButton { background:#5b6ed6; border-color:#5b6ed6; color:#ffffff; }
#refreshButton:hover { background:#4d60c4; border-color:#4d60c4; }
#eyeButton { color:#8793a5; }
#eyeButton:hover { color:#263b8f; background:rgba(91, 110, 214, 0.1); border-radius:7px; }
QTabBar::tab { background:transparent; color:#8793a5; }
QTabBar::tab:hover { background:rgba(255, 255, 255, 0.6); color:#40506a; }
QTabBar::tab:selected { background:#ffffff; color:#142033; }
QScrollBar::handle:vertical { background:rgba(20, 32, 51, 0.18); }
QScrollBar::handle:vertical:hover { background:rgba(20, 32, 51, 0.3); }
QToolTip { background:#ffffff; color:#172236; border:1px solid rgba(20, 32, 51, 0.12); }
"""


DARK_STYLE = SHARED_STYLE + """
QMainWindow { background:qlineargradient(x1:0, y1:0, x2:0.4, y2:1,
    stop:0 #141926, stop:0.55 #0d1119, stop:1 #0a0d13); }
QWidget { color:#f3f5f8; }
#title { color:#ffffff; }
#subtitle, #meta, #reset, #statLabel, #statDetail, #cardCaption, #sectionHint,
#historyHint, #percentageSuffix, #heroUnit, #legendShare { color:#8a95a8; }
#footer { color:#78849a; }
#selector { background:rgba(255, 255, 255, 0.04); border:1px solid rgba(255, 255, 255, 0.05); border-radius:12px; }
#scopeButton { color:#8a95a8; }
#scopeButton:hover { background:rgba(255, 255, 255, 0.06); }
#scopeButton:checked { background:rgba(255, 255, 255, 0.11); color:#ffffff; }
#identity, #chart, #statTile {
    background:qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(255, 255, 255, 0.062), stop:1 rgba(255, 255, 255, 0.022));
    border:1px solid rgba(255, 255, 255, 0.08); border-radius:17px; }
#heroCard {
    background:qlineargradient(x1:0, y1:0, x2:0.6, y2:1,
        stop:0 rgba(120, 145, 255, 0.2), stop:0.6 rgba(255, 255, 255, 0.05), stop:1 rgba(255, 255, 255, 0.02));
    border:1px solid rgba(140, 164, 255, 0.24); border-radius:19px; }
#pace {
    background:qlineargradient(x1:0, y1:0, x2:0.6, y2:1,
        stop:0 rgba(88, 214, 150, 0.17), stop:0.65 rgba(255, 255, 255, 0.045), stop:1 rgba(255, 255, 255, 0.02));
    border:1px solid rgba(88, 214, 150, 0.22); border-radius:19px; }
#paceContext, #paceMetricLabel { color:#8fc0a7; }
#paceStatus { background:rgba(88, 214, 150, 0.16); color:#8ff0bb; }
#paceHeadline { color:#e6faef; }
#paceText, #paceGuidance { color:#b6d8c6; }
#paceMethod { color:#7e9c8b; }
#paceMetrics { background:rgba(255, 255, 255, 0.045); border:1px solid rgba(88, 214, 150, 0.18); border-radius:12px; }
#paceMetricValue { color:#ddf6e6; }
#paceDivider { color:rgba(88, 214, 150, 0.2); background:rgba(88, 214, 150, 0.2); max-width:1px; }
#heroValue, #heroCost, #statValue, #providerName, #historyTitle, #tokenDayValue, #legendName { color:#ffffff; }
#plan { color:#aeb8c8; background:rgba(255, 255, 255, 0.07); }
#legendValue { color:#aeb8c8; }
#tokenDayRow { background:rgba(255, 255, 255, 0.035); border:1px solid rgba(255, 255, 255, 0.055); border-radius:10px; }
#tokenDayLabel { color:#aeb8c8; }
#empty { color:#aeb8c8; }
QComboBox { background:rgba(255, 255, 255, 0.07); border:1px solid rgba(255, 255, 255, 0.1); border-radius:9px; padding:6px 10px; min-width:150px; color:#f3f5f8; }
QComboBox QAbstractItemView { background:#161b23; color:#f3f5f8; selection-background-color:#2a3550; selection-color:#ffffff; border:1px solid rgba(255, 255, 255, 0.1); }
QPushButton { background:rgba(255, 255, 255, 0.07); border:1px solid rgba(255, 255, 255, 0.1); border-radius:10px; padding:7px 12px; color:#e8ecf3; font-size:13px; font-weight:600; }
QPushButton:hover { background:rgba(255, 255, 255, 0.12); border-color:rgba(255, 255, 255, 0.18); }
#refreshButton { background:#5f6fe0; border-color:#6b7ae8; color:#ffffff; }
#refreshButton:hover { background:#6f7dea; border-color:#8290f2; }
#eyeButton { color:#8a95a8; }
#eyeButton:hover { color:#c9d4ff; background:rgba(140, 164, 255, 0.14); border-radius:7px; }
QTabBar::tab { background:transparent; color:#8a95a8; }
QTabBar::tab:hover { background:rgba(255, 255, 255, 0.05); color:#d3dae6; }
QTabBar::tab:selected { background:rgba(255, 255, 255, 0.11); color:#ffffff; }
QScrollBar::handle:vertical { background:rgba(255, 255, 255, 0.16); }
QScrollBar::handle:vertical:hover { background:rgba(255, 255, 255, 0.26); }
QToolTip { background:#10141c; color:#f3f5f8; border:1px solid rgba(255, 255, 255, 0.14); }
"""


def style_for_theme(theme: str) -> str:
    return DARK_STYLE if theme == "dark" else LIGHT_STYLE


def acquire_single_instance() -> QSharedMemory | None:
    """Return a process-held guard, or None if Orbit is already running."""
    guard = QSharedMemory(APP_INSTANCE_NAME)
    return guard if guard.create(1) else None


def make_tray(window: Dashboard) -> QSystemTrayIcon:
    icon = app_icon()
    if icon.isNull():
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#849dff"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(3, 3, 26, 26)
        painter.end()
        icon = QIcon(pixmap)
    tray = QSystemTrayIcon(icon, window)
    retranslate_tray(tray, window)
    tray.activated.connect(lambda reason: window.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()
    return tray


def retranslate_tray(tray: QSystemTrayIcon, window: Dashboard) -> None:
    menu = QMenu()
    show = QAction(t("tray.open"), menu)
    show.triggered.connect(lambda: (window.show(), window.raise_(), window.activateWindow()))
    menu.addAction(show)
    menu.addAction(t("tray.refresh"), window.refresh)
    menu.addSeparator()
    menu.addAction(t("tray.quit"), QApplication.instance().quit)
    previous = tray.contextMenu()
    tray.setContextMenu(menu)
    tray.setToolTip(f"{APP_NAME} · {t('app.subtitle')}")
    if previous is not None:
        previous.deleteLater()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", default=cli_path())
    parser.add_argument("--fixture")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    # This message is printed before the window exists, so the stored language
    # has to be read here rather than inherited from the Dashboard.
    set_language(QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION).value(LANGUAGE_KEY, DEFAULT_LANGUAGE))
    instance_guard = acquire_single_instance()
    if instance_guard is None:
        print(t("app.alreadyRunning"))
        return
    window = Dashboard(args.cli, args.fixture)
    window._tray = make_tray(window)
    window.show()
    window._instance_guard = instance_guard
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
