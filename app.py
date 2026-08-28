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
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QPushButton, QScrollArea, QSystemTrayIcon, QTabWidget, QToolTip, QVBoxLayout, QWidget,
)


DEFAULT_CLI = "/home/utkucan/.local/bin/codexbar-0540"
APP_INSTANCE_NAME = "codexbar-linux-single-instance-v1"
LOGO_PATH = Path(__file__).parent / "assets" / "codexbar-linux-logo.png"
MONTH_NAMES = ("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara")
ENGLISH_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}
CACHED_PROVIDERS_KEY = "cached_providers"


def cli_path() -> str:
    candidates = [DEFAULT_CLI, "/usr/bin/codexbar", "codexbar"]
    return next((path for path in candidates if os.path.isabs(path) and os.access(path, os.X_OK)), "codexbar")


def run_json(command: str, arguments: list[str]) -> tuple[object | None, str | None]:
    try:
        result = subprocess.run([command, *arguments], capture_output=True, text=True, timeout=25, check=False)
    except subprocess.TimeoutExpired:
        return None, "CodexBar yanıt vermedi; yenilemeyi tekrar dene."
    except OSError as exc:
        return None, f"CodexBar CLI çalıştırılamadı: {exc}"
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError:
        return None, result.stderr.strip() or "CodexBar geçerli JSON döndürmedi."


def read_usage(command: str, fixture: str | None = None) -> tuple[list[dict], str | None]:
    if fixture:
        try:
            payload = json.loads(Path(fixture).read_text())
        except Exception as exc:
            return [], f"Fixture okunamadı: {exc}"
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
    return {}, "Bu sağlayıcı için yerel maliyet verisi yok."


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
    return f"{parsed.astimezone(target_tz).day} {MONTH_NAMES[parsed.astimezone(target_tz).month - 1]} {parsed.astimezone(target_tz):%H:%M}"


def localize_reset_description(value: object) -> str | None:
    """Translate common upstream English reset descriptions for the UI."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
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
                return f"{int(parts[1])} {MONTH_NAMES[ENGLISH_MONTHS[parts[0]] - 1]} {hour:02d}:{minute:02d}"
    return None


def window(raw: object, label: str) -> dict | None:
    if not isinstance(raw, dict) or raw.get("usedPercent") is None:
        return None
    used = clamp_percent(raw.get("usedPercent"))
    reset_value = raw.get("resetDescription") or raw.get("resetsAt")
    reset = format_reset(reset_value) or localize_reset_description(reset_value) or reset_value or "Reset zamanı bilinmiyor"
    return {
        "label": label,
        "used": used,
        "left": 100 - used,
        "reset": reset,
    }


def pace_summary(windows: list[dict]) -> dict[str, str]:
    """Explain the current limit state without inventing a usage-rate forecast."""
    valid_windows = [item for item in windows if isinstance(item, dict)] if isinstance(windows, list) else []
    if not valid_windows:
        return {
            "headline": "Tempo hesaplanamadı",
            "detail": "Kullanım penceresi verisi geldiğinde kalan kapasiteyi ve sıfırlanma zamanını burada göreceksin.",
            "guidance": "Sağlayıcı limit bilgisini yenilediğinde durum otomatik yorumlanır.",
            "method": "Bu özet, mevcut limit verisine dayanır.",
            "remaining": "—",
            "reset": "—",
        }

    primary = valid_windows[0]
    used = clamp_percent(primary.get("used"))
    left = clamp_percent(primary.get("left"))
    label = str(primary.get("label", "Aktif"))
    reset = str(primary.get("reset", "bilinmiyor"))
    reset_sentence = reset if reset.endswith(".") else f"{reset}."
    if used >= 100 or left <= 0:
        headline = "Kapasite tükendi"
        guidance = "Bu pencere sıfırlanana kadar yeni yoğun istekler bekletilir."
    elif left >= 70:
        headline = "Kapasite yüksek"
        guidance = "Kapasitenin büyük bölümü kullanılabilir; mevcut kullanım düzeyi sürdürülebilir."
    elif left >= 40:
        headline = "Kapasite dengeli"
        guidance = "Kapasite yeterli düzeyde; planlanan kullanım sürdürülebilir."
    elif left >= 15:
        headline = "Kapasite azalıyor"
        guidance = "Kalan alan sınırlanmaya başladı; uzun veya yoğun işleri planlı yürütmek yararlı olur."
    else:
        headline = "Kapasite kritik"
        guidance = "Kapasite kritik düzeyde; kritik olmayan yoğun işleri sıfırlanma sonrasına bırakmak yararlı olur."
    return {
        "headline": headline,
        "detail": f"{label} limitinin %{used:.0f}'si kullanıldı; %{left:.0f} kapasite kaldı. Sıfırlanma: {reset_sentence}",
        "guidance": guidance,
        "method": "Bu değerlendirme kullanım hızını tahmin etmez; mevcut kapasiteyi ve sıfırlanma zamanını yorumlar.",
        "remaining": f"%{left:.0f}",
        "reset": reset,
    }


def normalize_providers(payload: object) -> tuple[list[dict], str | None]:
    if isinstance(payload, dict) and payload.get("error"):
        error = payload["error"]
        return [], error.get("message", "Provider hatası") if isinstance(error, dict) else str(error)
    entries = payload if isinstance(payload, list) else payload.get("providers", []) if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return [], "CLI çıktısında provider listesi bulunamadı."

    providers: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        usage = entry.get("usage") if isinstance(entry.get("usage"), dict) else {}
        identity = usage.get("identity") if isinstance(usage.get("identity"), dict) else {}
        windows = [window(usage.get("primary"), "Oturum"), window(usage.get("secondary"), "Haftalık"), window(usage.get("tertiary"), "Aylık")]
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
            "email": email or "Bağlı hesap",
            "plan": usage.get("loginMethod", "connected").replace("_", " ").title(),
            "windows": windows,
            "credits": credits.get("remaining"),
            "credit_unit": credits.get("unit") or "credits",
            # Upstream pace prose changes frequently; the UI derives its stable summary from windows.
            "pace": pace_window,
        })
    return providers, None if providers else "Kullanılabilir provider verisi bulunamadı."


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


def app_data_path() -> Path:
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    return Path(location) / "CodexBarLinux" / "token-history.json"


def load_token_history(path: Path | None = None) -> dict[str, int]:
    try:
        payload = json.loads((path or app_data_path()).read_text())
        days = payload.get("days", {}) if isinstance(payload, dict) else {}
        return {key: int(value) for key, value in days.items() if isinstance(key, str) and numeric_value(value) is not None}
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return {}


def save_token_history(days: dict[str, int], path: Path | None = None) -> None:
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


def merge_token_history(existing: dict[str, int], incoming: dict[str, int], today: date | None = None) -> dict[str, int]:
    cutoff = (today or date.today()) - timedelta(days=364)
    merged = dict(existing)
    merged.update(incoming)
    kept: dict[str, int] = {}
    for raw_date, value in merged.items():
        try:
            if date.fromisoformat(raw_date) >= cutoff and value >= 0:
                kept[raw_date] = int(value)
        except (TypeError, ValueError):
            continue
    return dict(sorted(kept.items()))


def monthly_token_totals(days: dict[str, int], today: date | None = None) -> list[tuple[str, int]]:
    reference = today or date.today()
    months: list[tuple[int, int]] = []
    year, month = reference.year, reference.month
    for _ in range(12):
        months.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    totals = {(year, month): 0 for year, month in months}
    for raw_date, tokens in days.items():
        try:
            parsed = date.fromisoformat(raw_date)
        except (TypeError, ValueError):
            continue
        key = (parsed.year, parsed.month)
        if key in totals:
            totals[key] += tokens
    return [(f"{MONTH_NAMES[month - 1]} {str(year)[-2:]}", totals[(year, month)]) for year, month in reversed(months)]


def recent_token_days(days: dict[str, int], limit: int = 31) -> list[tuple[str, int]]:
    return sorted(days.items(), reverse=True)[:limit]


def app_icon() -> QIcon:
    return QIcon(str(LOGO_PATH)) if LOGO_PATH.exists() else QIcon()


def mask_email(email: str) -> str:
    """Keep enough of an address visible to identify the active account."""
    if "@" not in email:
        return email
    local, domain = email.split("@", 1)
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}{'•' * max(3, len(local) - len(visible))}@{domain}"


class ProgressTrack(QFrame):
    def __init__(self, left: float, color: str):
        super().__init__()
        self.left, self.color = left, color
        self.setFixedHeight(8)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#e4e9f1"))
        painter.drawRoundedRect(self.rect(), 4, 4)
        painter.setBrush(QColor(self.color))
        painter.drawRoundedRect(0, 0, round(self.width() * self.left / 100), self.height(), 4, 4)


class UsageWindow(QFrame):
    def __init__(self, data: dict, color: str):
        super().__init__()
        self.setObjectName("usageWindow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 13, 15, 14)
        header = QHBoxLayout()
        label = QLabel(data["label"])
        label.setObjectName("windowLabel")
        percentage = QLabel(f"%{data['left']:.0f} kaldı")
        percentage.setObjectName("percentage")
        header.addWidget(label)
        header.addStretch()
        header.addWidget(percentage)
        layout.addLayout(header)
        layout.addWidget(ProgressTrack(data["left"], color))
        reset = QLabel(f"Sıfırlanma: {data['reset']}")
        reset.setObjectName("reset")
        layout.addWidget(reset)


class StatTile(QFrame):
    def __init__(self, label: str, value: str, detail: str = ""):
        super().__init__()
        self.setObjectName("statTile")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 12, 13, 12)
        caption = QLabel(label)
        caption.setObjectName("statLabel")
        number = QLabel(value)
        number.setObjectName("statValue")
        layout.addWidget(caption)
        layout.addWidget(number)
        if detail:
            sub = QLabel(detail)
            sub.setObjectName("statDetail")
            layout.addWidget(sub)


class Sparkline(QWidget):
    def __init__(self, points: list[tuple[str, float]]):
        super().__init__()
        self.points = points
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
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Grafik için günlük maliyet verisi yok")
            return
        path = QPainterPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        fill = QPainterPath(path)
        fill.lineTo(rect.right(), rect.bottom())
        fill.lineTo(rect.left(), rect.bottom())
        fill.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(90, 119, 237, 45))
        painter.drawPath(fill)
        painter.setPen(QColor("#7c9cff"))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setBrush(QColor("#a6b8ff"))
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
            label = f"{parsed.day} {MONTH_NAMES[parsed.month - 1]} {parsed.year}"
        except ValueError:
            pass
        QToolTip.showText(event.globalPosition().toPoint(), f"<b>{label}</b><br>{money(value)} harcandı", self)
        event.accept()

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)


class MonthlyTokenChart(QWidget):
    def __init__(self, months: list[tuple[str, int]]):
        super().__init__()
        self.months = months
        self.setMinimumHeight(150)
        self.setMouseTracking(True)

    def chart_geometry(self) -> tuple[object, float, int]:
        chart = self.rect().adjusted(8, 8, -8, -28)
        gap = 6
        width = max(5, (chart.width() - gap * (len(self.months) - 1)) / max(1, len(self.months)))
        return chart, width, gap

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        chart, width, gap = self.chart_geometry()
        maximum = max((value for _, value in self.months), default=0) or 1
        painter.setFont(QFont("Sans", 8))
        for index, (label, value) in enumerate(self.months):
            height = round(chart.height() * value / maximum)
            x = round(chart.left() + index * (width + gap))
            painter.setBrush(QColor("#dce3ef"))
            painter.drawRoundedRect(x, chart.bottom() - height, round(width), height, 4, 4)
            if value:
                painter.setBrush(QColor("#6176e7"))
                painter.drawRoundedRect(x, chart.bottom() - height, round(width), height, 4, 4)
            painter.setPen(QColor("#718096"))
            painter.drawText(x - 7, self.height() - 21, round(width) + 14, 14, Qt.AlignmentFlag.AlignCenter, label.split()[0])
            painter.setPen(Qt.PenStyle.NoPen)

    def mouseMoveEvent(self, event):
        chart, width, gap = self.chart_geometry()
        position = event.position()
        index = int((position.x() - chart.left()) // (width + gap))
        within_chart = chart.contains(position.toPoint())
        if within_chart and 0 <= index < len(self.months):
            label, value = self.months[index]
            QToolTip.showText(
                event.globalPosition().toPoint(),
                f"<b>{label}</b><br>{token_count(value)} harcandı",
                self,
            )
        else:
            QToolTip.hideText()
        event.accept()

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)


class TokenValueRow(QFrame):
    def __init__(self, label: str, tokens: int):
        super().__init__()
        self.setObjectName("tokenDayRow")
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 9, 12, 9)
        day_label = QLabel(label)
        day_label.setObjectName("tokenDayLabel")
        token_label = QLabel(token_count(tokens))
        token_label.setObjectName("tokenDayValue")
        row.addWidget(day_label)
        row.addStretch()
        row.addWidget(token_label)


class TokenDayRow(TokenValueRow):
    def __init__(self, raw_date: str, tokens: int):
        try:
            parsed = date.fromisoformat(raw_date)
            label = f"{parsed.day} {MONTH_NAMES[parsed.month - 1]} {parsed.year}"
        except ValueError:
            label = raw_date
        super().__init__(label, tokens)


class Dashboard(QMainWindow):
    def __init__(self, command: str, fixture: str | None = None):
        super().__init__()
        self.command, self.fixture = command, fixture
        self.providers: list[dict] = []
        self.cost: dict = {}
        self.token_history = load_token_history()
        self.revealed_provider_id: str | None = None
        self.settings = QSettings("Utku", "CodexBarLinux")
        self.providers = load_cached_providers(self.settings)
        saved_theme = str(self.settings.value("theme", "light"))
        self.theme = saved_theme if saved_theme in {"light", "dark"} else "light"
        saved_history_view = str(self.settings.value("token_history_view", "monthly"))
        self.token_history_view = saved_history_view if saved_history_view in {"monthly", "daily"} else "monthly"
        self.setWindowTitle("CodexBar Linux")
        self.setWindowIcon(app_icon())
        self.resize(500, 760)
        self.setMinimumSize(430, 620)
        self.apply_theme()
        self.build_ui()
        if self.providers:
            self.show_cached_providers()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(60_000)

    def build_ui(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(10)
        header = QHBoxLayout()
        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setObjectName("logo")
        logo_pixmap = QPixmap(str(LOGO_PATH))
        if not logo_pixmap.isNull():
            logo.setPixmap(logo_pixmap.scaled(34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setFixedSize(34, 34)
        brand_text = QVBoxLayout()
        title = QLabel("CodexBar")
        title.setObjectName("title")
        subtitle = QLabel("AI kullanım ve maliyet özeti")
        subtitle.setObjectName("subtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand.addWidget(logo)
        brand.addLayout(brand_text)
        header.addLayout(brand)
        header.addStretch()
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("themeButton")
        self.theme_button.clicked.connect(self.toggle_theme)
        header.addWidget(self.theme_button)
        self.update_theme_button()
        self.refresh_button = QPushButton("Yenile")
        self.refresh_button.setObjectName("refreshButton")
        self.refresh_button.setToolTip("Kullanım verisini yenile")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        outer.addLayout(header)
        selector = QFrame()
        selector.setObjectName("selector")
        selector_layout = QHBoxLayout(selector)
        selector_layout.setContentsMargins(12, 8, 12, 8)
        provider_label = QLabel("Sağlayıcı")
        provider_label.setObjectName("sectionLabel")
        selector_layout.addWidget(provider_label)
        self.provider_picker = QComboBox()
        self.provider_picker.currentIndexChanged.connect(self.select_provider)
        selector_layout.addWidget(self.provider_picker, 1)
        outer.addWidget(selector)
        self.tabs = QTabWidget()
        self.usage_page = self.make_usage_page()
        self.spend_page = self.make_spend_page()
        self.tabs.addTab(self.usage_page, "Kullanım")
        self.tabs.addTab(self.spend_page, "Maliyet")
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
        self.theme_button.setToolTip("Açık temaya geç" if is_dark else "Koyu temaya geç")
        self.theme_button.setAccessibleName(self.theme_button.toolTip())

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self.settings.setValue("theme", self.theme)
        self.apply_theme()

    def make_usage_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = QWidget()
        self.usage_layout = QVBoxLayout(panel)
        self.usage_layout.setContentsMargins(2, 6, 2, 6)
        self.usage_layout.setSpacing(8)
        scroll.setWidget(panel)
        return scroll

    def make_spend_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        panel = QWidget()
        self.spend_layout = QVBoxLayout(panel)
        self.spend_layout.setContentsMargins(2, 10, 2, 6)
        self.spend_layout.setSpacing(10)
        scroll.setWidget(panel)
        return scroll

    @staticmethod
    def clear_layout(layout: QVBoxLayout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def refresh(self):
        current_id = self.current_provider_id()
        providers, error = read_usage(self.command, self.fixture)
        # Geçici CLI hatasında son başarılı ekranı koru.
        if providers:
            self.providers = providers
            save_cached_providers(self.settings, providers)
        self.populate_provider_picker(current_id)
        if self.providers:
            index = next((i for i, item in enumerate(self.providers) if item["id"] == current_id), 0)
            self.provider_picker.blockSignals(True)
            self.provider_picker.setCurrentIndex(index)
            self.provider_picker.blockSignals(False)
            if providers:
                self.select_provider(index)
            else:
                self.footer.setText(f"Son başarılı veri gösteriliyor · {error or 'Yenileme başarısız'}")
        else:
            self.clear_layout(self.usage_layout)
            self.clear_layout(self.spend_layout)
            self.footer.setText(error or "Gösterilecek sağlayıcı verisi yok.")

    def populate_provider_picker(self, current_id: str = ""):
        self.provider_picker.blockSignals(True)
        self.provider_picker.clear()
        for provider in self.providers:
            self.provider_picker.addItem(provider["name"], provider["id"])
        self.provider_picker.blockSignals(False)

    def show_cached_providers(self):
        """Render cached usage immediately while the first live refresh runs."""
        current_id = self.current_provider_id()
        self.populate_provider_picker(current_id)
        index = next((i for i, item in enumerate(self.providers) if item["id"] == current_id), 0)
        self.provider_picker.blockSignals(True)
        self.provider_picker.setCurrentIndex(index)
        self.provider_picker.blockSignals(False)
        provider = self.providers[index]
        self.revealed_provider_id = None
        self.cost = {}
        self.render_usage(provider)
        self.render_spend(provider)
        self.footer.setText("Son başarılı veri gösteriliyor · Canlı veri yenileniyor…")

    def current_provider_id(self) -> str:
        return str(self.provider_picker.currentData() or "")

    def select_provider(self, index: int):
        if index < 0 or index >= len(self.providers):
            return
        provider = self.providers[index]
        self.revealed_provider_id = None
        self.cost, cost_error = read_cost(self.command, provider["id"]) if not self.fixture else ({}, None)
        self.update_token_history()
        self.render_usage(provider)
        self.render_spend(provider)
        updated = datetime.now().strftime("%H:%M")
        self.footer.setText(f"Son güncelleme {updated} · {provider['source']}" + (f" · {cost_error}" if cost_error else ""))

    def update_token_history(self):
        incoming = extract_daily_tokens(self.cost)
        if incoming:
            self.token_history = merge_token_history(self.token_history, incoming)
            save_token_history(self.token_history)

    def render_usage(self, provider: dict):
        self.clear_layout(self.usage_layout)
        identity = QFrame()
        identity.setObjectName("identity")
        layout = QVBoxLayout(identity)
        layout.setContentsMargins(16, 15, 16, 15)
        name = QLabel(provider["name"])
        name.setObjectName("providerName")
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)
        shown_email = provider["email"] if self.revealed_provider_id == provider["id"] else mask_email(provider["email"])
        meta = QLabel(f"●  {shown_email}")
        meta.setObjectName("meta")
        eye = QPushButton("👁")
        eye.setObjectName("eyeButton")
        eye.setFixedSize(28, 24)
        eye.setToolTip("E-postayı gizle" if self.revealed_provider_id == provider["id"] else "E-postayı göster")
        eye.clicked.connect(lambda: self.toggle_email(provider["id"]))
        plan = QLabel(provider["plan"])
        plan.setObjectName("plan")
        meta_row.addWidget(meta)
        meta_row.addWidget(eye)
        meta_row.addStretch()
        meta_row.addWidget(plan)
        layout.addWidget(name)
        layout.addLayout(meta_row)
        self.usage_layout.addWidget(identity)
        usage_heading = QLabel("Kullanım limitleri")
        usage_heading.setObjectName("sectionTitle")
        usage_hint = QLabel("Her pencere için kalan kapasite ve sıfırlanma zamanı")
        usage_hint.setObjectName("sectionHint")
        self.usage_layout.addWidget(usage_heading)
        self.usage_layout.addWidget(usage_hint)
        for window_data, color in zip(provider["windows"], ("#7c9cff", "#b084f7", "#58d1bb")):
            self.usage_layout.addWidget(UsageWindow(window_data, color))
        pace = QFrame()
        pace.setObjectName("pace")
        pace_layout = QVBoxLayout(pace)
        pace_layout.setContentsMargins(18, 17, 18, 17)
        pace_layout.setSpacing(8)
        pace_label = QLabel("Kullanım temposu")
        pace_label.setObjectName("paceLabel")
        pace_data = pace_summary(provider.get("windows", []))
        pace_header = QHBoxLayout()
        pace_header.setSpacing(8)
        pace_context = QLabel("ANLIK DURUM")
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
        remaining_caption = QLabel("KALAN KAPASİTE")
        remaining_caption.setObjectName("paceMetricLabel")
        remaining_value = QLabel(pace_data["remaining"])
        remaining_value.setObjectName("paceMetricValue")
        remaining_column = QVBoxLayout()
        remaining_column.setSpacing(1)
        remaining_column.addWidget(remaining_caption)
        remaining_column.addWidget(remaining_value)
        divider = QFrame()
        divider.setObjectName("paceDivider")
        divider.setFrameShape(QFrame.Shape.VLine)
        reset_caption = QLabel("SIFIRLANMA")
        reset_caption.setObjectName("paceMetricLabel")
        reset_value = QLabel(pace_data["reset"])
        reset_value.setObjectName("paceMetricValue")
        reset_value.setWordWrap(True)
        reset_column = QVBoxLayout()
        reset_column.setSpacing(1)
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
        pace_layout.addWidget(pace_label)
        pace_layout.addLayout(pace_header)
        pace_layout.addWidget(pace_headline)
        pace_layout.addWidget(pace_text)
        pace_layout.addWidget(pace_metrics)
        pace_layout.addWidget(pace_guidance)
        pace_layout.addWidget(pace_method)
        self.usage_layout.addWidget(pace)
        grid = QGridLayout()
        credit = "—" if provider["credits"] is None else compact_number(provider["credits"])
        grid.addWidget(StatTile("Kredi", credit, provider["credit_unit"]), 0, 0)
        grid.addWidget(StatTile("Bu oturum maliyeti", money(self.cost.get("sessionCostUSD")), "USD"), 0, 1)
        grid.addWidget(StatTile("Bu oturum tokenleri", token_count(self.cost.get("sessionTokens"))), 1, 0)
        grid.addWidget(StatTile("Son 31 gün maliyeti", money(self.cost.get("last30DaysCostUSD")), "USD"), 1, 1)
        self.usage_layout.addLayout(grid)
        self.usage_layout.addStretch()

    def toggle_email(self, provider_id: str):
        self.revealed_provider_id = None if self.revealed_provider_id == provider_id else provider_id
        index = self.provider_picker.currentIndex()
        if 0 <= index < len(self.providers):
            self.render_usage(self.providers[index])

    def render_spend(self, provider: dict):
        self.clear_layout(self.spend_layout)
        self.render_token_history()
        if not self.cost:
            empty = QLabel("Bu sağlayıcı için yerel maliyet geçmişi henüz bulunmuyor.")
            empty.setObjectName("empty")
            self.spend_layout.addWidget(empty)
            self.spend_layout.addStretch()
            return
        grid = QGridLayout()
        grid.addWidget(StatTile("Son 31 gün maliyeti", money(self.cost.get("last30DaysCostUSD")), "USD"), 0, 0)
        grid.addWidget(StatTile("Son 31 gün tokenleri", token_count(self.cost.get("last30DaysTokens"))), 0, 1)
        grid.addWidget(StatTile("Bu oturum maliyeti", money(self.cost.get("sessionCostUSD")), "USD"), 1, 0)
        grid.addWidget(StatTile("Bu oturum tokenleri", token_count(self.cost.get("sessionTokens"))), 1, 1)
        self.spend_layout.addLayout(grid)
        chart = QFrame()
        chart.setObjectName("chart")
        chart_layout = QVBoxLayout(chart)
        chart_layout.setContentsMargins(15, 13, 15, 13)
        chart_layout.addWidget(QLabel("Günlük maliyet · yerel Codex kayıtları"))
        chart_layout.addWidget(Sparkline(extract_daily_costs(self.cost)))
        self.spend_layout.addWidget(chart)
        projects = self.cost.get("projects", [])
        breakdowns = projects[0].get("modelBreakdowns", []) if projects and isinstance(projects[0], dict) else []
        if breakdowns:
            models_panel = QFrame()
            models_panel.setObjectName("chart")
            models_layout = QVBoxLayout(models_panel)
            models_layout.setContentsMargins(15, 13, 15, 13)
            models_layout.addWidget(QLabel("En çok kullanılan modeller"))
            for row in sorted(breakdowns, key=lambda item: item.get("cost", 0), reverse=True)[:4]:
                line = QHBoxLayout()
                line.addWidget(QLabel(str(row.get("modelName", "Model"))))
                line.addStretch()
                line.addWidget(QLabel(money(row.get("cost"))))
                models_layout.addLayout(line)
            self.spend_layout.addWidget(models_panel)
        self.spend_layout.addStretch()

    def render_token_history(self):
        history = QFrame()
        history.setObjectName("chart")
        layout = QVBoxLayout(history)
        layout.setContentsMargins(15, 13, 15, 13)
        header = QHBoxLayout()
        heading = QLabel("12 aylık token geçmişi")
        heading.setObjectName("historyTitle")
        header.addWidget(heading)
        header.addStretch()
        view_picker = QComboBox()
        view_picker.setObjectName("historyPicker")
        view_picker.addItem("Aylık toplam", "monthly")
        view_picker.addItem("Günlük ayrıntı", "daily")
        view_picker.setCurrentIndex(0 if self.token_history_view == "monthly" else 1)
        view_picker.currentIndexChanged.connect(self.set_token_history_view)
        header.addWidget(view_picker)
        summary = QLabel("Günlük kayıtlar bu cihazda saklanır; en eski kayıtlar 365 gün sonra temizlenir.")
        summary.setObjectName("historyHint")
        summary.setWordWrap(True)
        layout.addLayout(header)
        layout.addWidget(summary)
        if self.token_history_view == "monthly":
            months = monthly_token_totals(self.token_history)
            layout.addWidget(MonthlyTokenChart(months))
            for label, tokens in reversed(months):
                layout.addWidget(TokenValueRow(label, tokens))
        else:
            title = QLabel("Kayıt bulunan günler · son 365 gün")
            title.setObjectName("historyHint")
            layout.addWidget(title)
            for raw_date, tokens in recent_token_days(self.token_history, 365):
                layout.addWidget(TokenDayRow(raw_date, tokens))
        self.spend_layout.addWidget(history)

    def set_token_history_view(self, index: int):
        view = "daily" if index == 1 else "monthly"
        if view == self.token_history_view:
            return
        self.token_history_view = view
        self.settings.setValue("token_history_view", view)
        provider_index = self.provider_picker.currentIndex()
        if 0 <= provider_index < len(self.providers):
            self.render_spend(self.providers[provider_index])


LIGHT_STYLE = """
QMainWindow, QWidget { background:#f5f7fb; color:#172236; font-family:Inter, Noto Sans, sans-serif; }
QLabel { background:transparent; }
#title { font-size:26px; font-weight:800; letter-spacing:-.6px; color:#142033; }
#subtitle, #footer, #meta, #reset, #statLabel, #statDetail { color:#68758a; }
#subtitle { font-size:12px; color:#68758a; }
#footer { font-size:11px; padding:3px 2px; color:#718096; }
#selector { background:#ffffff; border:1px solid #dfe5ee; border-radius:12px; }
#sectionLabel { color:#536176; font-size:11px; font-weight:800; }
#sectionTitle { color:#172236; font-size:16px; font-weight:800; margin-top:6px; }
#sectionHint { color:#718096; font-size:11px; margin-bottom:1px; }
#identity { background:#ffffff; border:1px solid #dfe5ee; border-radius:14px; }
#pace { background:qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #effbf5, stop:1 #e4f5ee); border:1px solid #c4e7d5; border-radius:18px; }
#chart { background:#ffffff; border:1px solid #dfe5ee; border-radius:12px; }
#statTile { background:#ffffff; border:1px solid #dfe5ee; border-radius:12px; }
QComboBox { background:#f8faff; border:1px solid #cfd8e6; border-radius:8px; padding:7px 10px; min-width:190px; color:#172236; }
QComboBox::drop-down { border:0; width:24px; }
QComboBox QAbstractItemView { background:#ffffff; color:#172236; selection-background-color:#e4eaff; selection-color:#263b8f; border:1px solid #cfd8e6; }
QPushButton { background:#ffffff; border:1px solid #cfd8e6; border-radius:9px; padding:7px 12px; color:#27364d; font-size:13px; font-weight:700; }
QPushButton:hover { background:#f0f3fa; }
#refreshButton { background:#5b6ed6; border-color:#5b6ed6; color:#ffffff; }
#refreshButton:hover { background:#4d60c4; border-color:#4d60c4; }
#themeButton { min-width:18px; padding:7px 10px; font-size:15px; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:transparent; color:#718096; padding:10px 16px; margin-right:3px; font-weight:800; }
QTabBar::tab:selected { color:#263b8f; border-bottom:2px solid #5b6ed6; }
QScrollArea { border:0; background:#f5f7fb; }
#providerName { font-size:21px; font-weight:800; color:#142033; }
#meta { color:#208353; font-size:12px; margin-top:3px; }
#plan { color:#526176; font-size:12px; font-weight:700; }
#eyeButton { background:transparent; border:0; padding:0; color:#68758a; font-size:14px; }
#eyeButton:hover { color:#263b8f; background:#edf0ff; border-radius:6px; }
#usageWindow { background:#ffffff; border:1px solid #dfe5ee; border-radius:12px; }
#windowLabel { font-size:15px; color:#1b2a40; font-weight:800; }
#percentage { background:#e8edff; color:#3449a4; border-radius:7px; padding:4px 8px; font-size:13px; font-weight:800; }
#reset { color:#68758a; font-size:12px; margin-top:7px; }
#paceLabel { color:#187a4b; font-size:13px; font-weight:800; }
#paceContext, #paceMetricLabel { color:#5c8170; font-size:10px; font-weight:800; letter-spacing:.7px; }
#paceStatus { background:#d2f1df; color:#176d42; border-radius:10px; padding:5px 9px; font-size:11px; font-weight:800; }
#paceHeadline { color:#163f2d; font-size:21px; font-weight:800; letter-spacing:-.3px; }
#paceText { color:#416b58; font-size:12px; }
#paceMetrics { background:rgba(255,255,255,.66); border:1px solid #c9e5d5; border-radius:12px; }
#paceMetricValue { color:#174934; font-size:18px; font-weight:800; }
#paceDivider { color:#b9ddc8; background:#b9ddc8; max-width:1px; }
#paceGuidance { color:#245a3f; font-size:12px; font-weight:700; margin-top:2px; }
#paceMethod { color:#668575; font-size:10px; margin-top:1px; }
#statValue { color:#142033; font-size:19px; font-weight:800; }
#statLabel { color:#526176; font-size:11px; font-weight:700; }
#statDetail { color:#8793a5; font-size:10px; }
#chart QLabel { color:#394960; font-size:12px; font-weight:700; }
#historyTitle { color:#172236; font-size:15px; font-weight:800; }
#historyHint { color:#718096; font-size:11px; margin-bottom:3px; }
#historyPicker { min-width:130px; font-size:11px; font-weight:700; }
#tokenDayRow { background:#f8faff; border:1px solid #e1e7f0; border-radius:8px; }
#tokenDayLabel { color:#526176; font-size:12px; font-weight:700; }
#tokenDayValue { color:#263b8f; font-size:12px; font-weight:800; }
#empty { color:#68758a; padding:24px 8px; }
QScrollBar:vertical { background:#edf1f6; width:9px; margin:2px 0; }
QScrollBar::handle:vertical { background:#c4cedd; border-radius:4px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:#aab8cc; }
QToolTip { background:#172236; color:#ffffff; border:1px solid #3449a4; border-radius:7px; padding:7px 9px; font-size:12px; }
"""


DARK_STYLE = """
QMainWindow, QWidget { background:#12151b; color:#f3f5f8; font-family:Inter, Noto Sans, sans-serif; }
QLabel { background:transparent; }
#title { font-size:26px; font-weight:800; letter-spacing:-.6px; color:#ffffff; }
#subtitle { font-size:12px; color:#aeb8c8; }
#footer { font-size:11px; padding:3px 2px; color:#9da9ba; }
#selector { background:#1b2029; border:1px solid #303846; border-radius:12px; }
#sectionLabel { color:#c5cedb; font-size:11px; font-weight:800; }
#sectionTitle { color:#f6f8fb; font-size:16px; font-weight:800; margin-top:6px; }
#sectionHint { color:#aeb8c8; font-size:11px; margin-bottom:1px; }
#identity { background:#1b2029; border:1px solid #303846; border-radius:14px; }
#pace { background:qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #172f24, stop:1 #13271f); border:1px solid #32684f; border-radius:18px; }
#chart { background:#1b2029; border:1px solid #303846; border-radius:12px; }
#statTile { background:#1b2029; border:1px solid #303846; border-radius:12px; }
QComboBox { background:#232a35; border:1px solid #3b4657; border-radius:8px; padding:7px 10px; min-width:190px; color:#f3f5f8; }
QComboBox::drop-down { border:0; width:24px; }
QComboBox QAbstractItemView { background:#232a35; color:#f3f5f8; selection-background-color:#354a93; selection-color:#ffffff; border:1px solid #3b4657; }
QPushButton { background:#232a35; border:1px solid #3b4657; border-radius:9px; padding:7px 12px; color:#f3f5f8; font-size:13px; font-weight:700; }
QPushButton:hover { background:#2b3442; }
#themeButton { min-width:18px; padding:7px 10px; font-size:15px; }
#refreshButton { background:#7185f6; border-color:#7185f6; color:#111521; }
#refreshButton:hover { background:#8b9bff; border-color:#8b9bff; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:transparent; color:#aeb8c8; padding:10px 16px; margin-right:3px; font-weight:800; }
QTabBar::tab:selected { color:#bac7ff; border-bottom:2px solid #8da0ff; }
QScrollArea { border:0; background:#12151b; }
#providerName { font-size:21px; font-weight:800; color:#ffffff; }
#meta { color:#72d9a0; font-size:12px; margin-top:3px; }
#plan { color:#d7dee8; font-size:12px; font-weight:700; }
#eyeButton { background:transparent; border:0; padding:0; color:#aeb8c8; font-size:14px; }
#eyeButton:hover { color:#c7d0ff; background:#293149; border-radius:6px; }
#usageWindow { background:#1b2029; border:1px solid #303846; border-radius:12px; }
#windowLabel { font-size:15px; color:#f5f7fb; font-weight:800; }
#percentage { background:#293657; color:#cbd5ff; border-radius:7px; padding:4px 8px; font-size:13px; font-weight:800; }
#reset { color:#b5c0d0; font-size:12px; margin-top:7px; }
#paceLabel { color:#83e5af; font-size:13px; font-weight:800; }
#paceContext, #paceMetricLabel { color:#9bcbae; font-size:10px; font-weight:800; letter-spacing:.7px; }
#paceStatus { background:#24583f; color:#c5f7d9; border-radius:10px; padding:5px 9px; font-size:11px; font-weight:800; }
#paceHeadline { color:#e1f8ea; font-size:21px; font-weight:800; letter-spacing:-.3px; }
#paceText { color:#bddbc9; font-size:12px; }
#paceMetrics { background:rgba(11,30,21,.52); border:1px solid #34684f; border-radius:12px; }
#paceMetricValue { color:#ddf6e6; font-size:18px; font-weight:800; }
#paceDivider { color:#397458; background:#397458; max-width:1px; }
#paceGuidance { color:#d3f1df; font-size:12px; font-weight:700; margin-top:2px; }
#paceMethod { color:#9fc4ad; font-size:10px; margin-top:1px; }
#statValue { color:#ffffff; font-size:19px; font-weight:800; }
#statLabel { color:#bdc7d5; font-size:11px; font-weight:700; }
#statDetail { color:#9da9ba; font-size:10px; }
#chart QLabel { color:#d7dee8; font-size:12px; font-weight:700; }
#historyTitle { color:#f3f5f8; font-size:15px; font-weight:800; }
#historyHint { color:#aeb8c8; font-size:11px; margin-bottom:3px; }
#historyPicker { min-width:130px; font-size:11px; font-weight:700; }
#tokenDayRow { background:#222832; border:1px solid #343f4f; border-radius:8px; }
#tokenDayLabel { color:#c8d0dc; font-size:12px; font-weight:700; }
#tokenDayValue { color:#cbd5ff; font-size:12px; font-weight:800; }
#empty { color:#b5c0d0; padding:24px 8px; }
QScrollBar:vertical { background:#12151b; width:9px; margin:2px 0; }
QScrollBar::handle:vertical { background:#3b4657; border-radius:4px; min-height:30px; }
QScrollBar::handle:vertical:hover { background:#536176; }
QToolTip { background:#f3f5f8; color:#172236; border:1px solid #7185f6; border-radius:7px; padding:7px 9px; font-size:12px; }
"""


def style_for_theme(theme: str) -> str:
    return DARK_STYLE if theme == "dark" else LIGHT_STYLE


def acquire_single_instance() -> QSharedMemory | None:
    """Return a process-held guard, or None if CodexBar is already running."""
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
    menu = QMenu()
    show = QAction("CodexBar Linux'ı aç", menu)
    show.triggered.connect(lambda: (window.show(), window.raise_(), window.activateWindow()))
    menu.addAction(show)
    menu.addAction("Yenile", window.refresh)
    menu.addSeparator()
    menu.addAction("Çıkış", QApplication.instance().quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: window.show() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray.show()
    return tray


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cli", default=cli_path())
    parser.add_argument("--fixture")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    instance_guard = acquire_single_instance()
    if instance_guard is None:
        print("CodexBar zaten arka planda çalışıyor.")
        return
    window = Dashboard(args.cli, args.fixture)
    tray = make_tray(window)
    window.show()
    window._tray = tray
    window._instance_guard = instance_guard
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
