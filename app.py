from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
    QMenu, QPushButton, QScrollArea, QSystemTrayIcon, QTabWidget, QVBoxLayout, QWidget,
)


DEFAULT_CLI = "/home/utkucan/.local/bin/codexbar-0540"


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


def window(raw: object, label: str) -> dict | None:
    if not isinstance(raw, dict) or raw.get("usedPercent") is None:
        return None
    used = clamp_percent(raw.get("usedPercent"))
    return {
        "label": label,
        "used": used,
        "left": 100 - used,
        "reset": raw.get("resetDescription") or raw.get("resetsAt") or "Reset zamanı bilinmiyor",
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
        windows = [window(usage.get("primary"), "Session"), window(usage.get("secondary"), "Weekly"), window(usage.get("tertiary"), "Monthly")]
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
            "pace": pace_window.get("summary") or "Usage pace will appear when enough data is available.",
        })
    return providers, None if providers else "Kullanılabilir provider verisi bulunamadı."


def clamp_percent(value: object) -> float:
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def compact_number(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    for amount, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if abs(number) >= amount:
            return f"{number / amount:.1f}{suffix}"
    return f"{number:.0f}"


def money(value: object) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "—"


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
        painter.setBrush(QColor("#2a303b"))
        painter.drawRoundedRect(self.rect(), 4, 4)
        painter.setBrush(QColor(self.color))
        painter.drawRoundedRect(0, 0, round(self.width() * self.left / 100), self.height(), 4, 4)


class UsageWindow(QFrame):
    def __init__(self, data: dict, color: str):
        super().__init__()
        self.setObjectName("usageWindow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 14, 0, 12)
        header = QHBoxLayout()
        label = QLabel(data["label"])
        label.setObjectName("windowLabel")
        percentage = QLabel(f"{data['left']:.0f}% left")
        percentage.setObjectName("percentage")
        header.addWidget(label)
        header.addStretch()
        header.addWidget(percentage)
        layout.addLayout(header)
        layout.addWidget(ProgressTrack(data["left"], color))
        reset = QLabel(f"Resets in {data['reset']}")
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
    def __init__(self, values: list[float]):
        super().__init__()
        self.values = values or [0]
        self.setMinimumHeight(105)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(4, 10, -4, -8)
        maximum = max(self.values) or 1
        step = rect.width() / max(1, len(self.values) - 1)
        points = [(rect.left() + index * step, rect.bottom() - (value / maximum) * rect.height()) for index, value in enumerate(self.values)]
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


class Dashboard(QMainWindow):
    def __init__(self, command: str, fixture: str | None = None):
        super().__init__()
        self.command, self.fixture = command, fixture
        self.providers: list[dict] = []
        self.cost: dict = {}
        self.revealed_provider_id: str | None = None
        self.setWindowTitle("CodexBar Linux")
        self.resize(500, 760)
        self.setMinimumSize(430, 620)
        self.setStyleSheet(STYLE)
        self.build_ui()
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
        brand = QVBoxLayout()
        title = QLabel("CodexBar")
        title.setObjectName("title")
        subtitle = QLabel("AI usage limits")
        subtitle.setObjectName("subtitle")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        header.addLayout(brand)
        header.addStretch()
        self.refresh_button = QPushButton("↻")
        self.refresh_button.setToolTip("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        outer.addLayout(header)
        selector = QFrame()
        selector.setObjectName("selector")
        selector_layout = QHBoxLayout(selector)
        selector_layout.setContentsMargins(12, 8, 12, 8)
        selector_layout.addWidget(QLabel("Provider"))
        self.provider_picker = QComboBox()
        self.provider_picker.currentIndexChanged.connect(self.select_provider)
        selector_layout.addWidget(self.provider_picker, 1)
        outer.addWidget(selector)
        self.tabs = QTabWidget()
        self.usage_page = self.make_usage_page()
        self.spend_page = self.make_spend_page()
        self.tabs.addTab(self.usage_page, "Usage")
        self.tabs.addTab(self.spend_page, "Spend")
        outer.addWidget(self.tabs, 1)
        self.footer = QLabel()
        self.footer.setObjectName("footer")
        self.footer.setWordWrap(True)
        outer.addWidget(self.footer)
        self.setCentralWidget(root)

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
        self.providers, error = read_usage(self.command, self.fixture)
        self.provider_picker.blockSignals(True)
        self.provider_picker.clear()
        for provider in self.providers:
            self.provider_picker.addItem(provider["name"], provider["id"])
        self.provider_picker.blockSignals(False)
        if self.providers:
            index = next((i for i, item in enumerate(self.providers) if item["id"] == current_id), 0)
            self.provider_picker.setCurrentIndex(index)
            self.select_provider(index)
        else:
            self.clear_layout(self.usage_layout)
            self.clear_layout(self.spend_layout)
            self.footer.setText(error or "No provider data.")

    def current_provider_id(self) -> str:
        return str(self.provider_picker.currentData() or "")

    def select_provider(self, index: int):
        if index < 0 or index >= len(self.providers):
            return
        provider = self.providers[index]
        self.revealed_provider_id = None
        self.cost, cost_error = read_cost(self.command, provider["id"]) if not self.fixture else ({}, None)
        self.render_usage(provider)
        self.render_spend(provider)
        updated = datetime.now().strftime("%H:%M")
        self.footer.setText(f"Updated {updated} · {provider['source']}" + (f" · {cost_error}" if cost_error else ""))

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
        for window_data, color in zip(provider["windows"], ("#7c9cff", "#b084f7", "#58d1bb")):
            self.usage_layout.addWidget(UsageWindow(window_data, color))
        pace = QFrame()
        pace.setObjectName("pace")
        pace_layout = QVBoxLayout(pace)
        pace_layout.setContentsMargins(15, 13, 15, 13)
        pace_label = QLabel("Pace")
        pace_label.setObjectName("paceLabel")
        pace_text = QLabel(provider["pace"])
        pace_text.setWordWrap(True)
        pace_text.setObjectName("paceText")
        pace_layout.addWidget(pace_label)
        pace_layout.addWidget(pace_text)
        self.usage_layout.addWidget(pace)
        grid = QGridLayout()
        credit = "—" if provider["credits"] is None else compact_number(provider["credits"])
        grid.addWidget(StatTile("Credits", credit, provider["credit_unit"]), 0, 0)
        grid.addWidget(StatTile("Today", money(self.cost.get("sessionCostUSD"))), 0, 1)
        grid.addWidget(StatTile("Latest tokens", compact_number(self.cost.get("sessionTokens"))), 1, 0)
        grid.addWidget(StatTile("Last 31 days", money(self.cost.get("last30DaysCostUSD"))), 1, 1)
        self.usage_layout.addLayout(grid)
        self.usage_layout.addStretch()

    def toggle_email(self, provider_id: str):
        self.revealed_provider_id = None if self.revealed_provider_id == provider_id else provider_id
        index = self.provider_picker.currentIndex()
        if 0 <= index < len(self.providers):
            self.render_usage(self.providers[index])

    def render_spend(self, provider: dict):
        self.clear_layout(self.spend_layout)
        if not self.cost:
            empty = QLabel("Local cost history is not available for this provider yet.")
            empty.setObjectName("empty")
            self.spend_layout.addWidget(empty)
            self.spend_layout.addStretch()
            return
        grid = QGridLayout()
        grid.addWidget(StatTile("Last 31 days cost", money(self.cost.get("last30DaysCostUSD"))), 0, 0)
        grid.addWidget(StatTile("Last 31 days tokens", compact_number(self.cost.get("last30DaysTokens"))), 0, 1)
        grid.addWidget(StatTile("This session", money(self.cost.get("sessionCostUSD"))), 1, 0)
        grid.addWidget(StatTile("Session tokens", compact_number(self.cost.get("sessionTokens"))), 1, 1)
        self.spend_layout.addLayout(grid)
        chart = QFrame()
        chart.setObjectName("chart")
        chart_layout = QVBoxLayout(chart)
        chart_layout.setContentsMargins(15, 13, 15, 13)
        chart_layout.addWidget(QLabel("Daily cost · local Codex logs"))
        daily = self.cost.get("daily") if isinstance(self.cost.get("daily"), list) else []
        values = [float(day.get("totalCost", 0)) for day in daily if isinstance(day, dict)]
        chart_layout.addWidget(Sparkline(values))
        self.spend_layout.addWidget(chart)
        projects = self.cost.get("projects", [])
        breakdowns = projects[0].get("modelBreakdowns", []) if projects and isinstance(projects[0], dict) else []
        if breakdowns:
            models_panel = QFrame()
            models_panel.setObjectName("chart")
            models_layout = QVBoxLayout(models_panel)
            models_layout.setContentsMargins(15, 13, 15, 13)
            models_layout.addWidget(QLabel("Top models"))
            for row in sorted(breakdowns, key=lambda item: item.get("cost", 0), reverse=True)[:4]:
                line = QHBoxLayout()
                line.addWidget(QLabel(str(row.get("modelName", "Model"))))
                line.addStretch()
                line.addWidget(QLabel(money(row.get("cost"))))
                models_layout.addLayout(line)
            self.spend_layout.addWidget(models_panel)
        self.spend_layout.addStretch()


STYLE = """
QMainWindow, QWidget { background:#101216; color:#f2f3f5; font-family:Inter, Noto Sans, sans-serif; }
#title { font-size:25px; font-weight:700; letter-spacing:-.4px; }
#subtitle, #footer, #meta, #reset, #statLabel, #statDetail { color:#9299a8; }
#subtitle { font-size:12px; }
#footer { font-size:11px; padding:3px 2px; }
#selector { background:transparent; border:0; }
#identity { background:#171a20; border:0; border-radius:14px; }
#pace { background:#14201e; border:0; border-radius:12px; }
#chart { background:#171a20; border:0; border-radius:12px; }
#statTile { background:transparent; border:0; border-radius:0; }
QComboBox { background:#1c2027; border:0; border-radius:8px; padding:7px 10px; min-width:190px; }
QComboBox::drop-down { border:0; width:24px; }
QPushButton { background:#1c2027; border:0; border-radius:9px; padding:7px 12px; color:#eef1f8; font-size:16px; }
QPushButton:hover { background:#262c35; }
QTabWidget::pane { border:0; }
QTabBar::tab { background:transparent; color:#8f97a7; padding:10px 16px; margin-right:3px; }
QTabBar::tab:selected { color:#f4f6fb; border-bottom:2px solid #8aa2ff; }
QScrollArea { border:0; background:transparent; }
#providerName { font-size:20px; font-weight:650; color:#f6f7fb; }
#meta { color:#6fd79a; font-size:12px; margin-top:3px; }
#plan { color:#b6bfce; font-size:12px; }
#eyeButton { background:transparent; border:0; padding:0; color:#aab3c4; font-size:14px; }
#eyeButton:hover { color:#f3f5fb; background:#262d38; border-radius:6px; }
#usageWindow { border-bottom:1px solid #222730; }
#windowLabel { font-size:15px; color:#f0f2f7; font-weight:600; }
#percentage { color:#f0f2f7; font-size:14px; font-weight:600; }
#reset { font-size:12px; margin-top:7px; }
#paceLabel { color:#75dda5; font-weight:600; }
#paceText { color:#b9c7c0; font-size:12px; margin-top:4px; }
#statValue { color:#f6f7fb; font-size:17px; font-weight:650; }
#statDetail { font-size:10px; }
#chart QLabel { color:#c5cbd7; font-size:12px; }
#empty { color:#9299a8; padding:24px 8px; }
"""


def make_tray(window: Dashboard) -> QSystemTrayIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#849dff"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(3, 3, 26, 26)
    painter.setPen(QColor("#151821"))
    painter.setFont(QFont("Sans", 15, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "C")
    painter.end()
    tray = QSystemTrayIcon(QIcon(pixmap), window)
    menu = QMenu()
    show = QAction("Open CodexBar Linux", menu)
    show.triggered.connect(lambda: (window.show(), window.raise_(), window.activateWindow()))
    menu.addAction(show)
    menu.addAction("Refresh", window.refresh)
    menu.addSeparator()
    menu.addAction("Quit", QApplication.instance().quit)
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
    window = Dashboard(args.cli, args.fixture)
    tray = make_tray(window)
    window.show()
    window._tray = tray
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
