"""
Stats Dashboard for Pokemon TCG Live Monitor v2.1
Modern, sleek UI with transparent glass-morphism design
"""

VERSION = "2.1"

import sys
import os
import re
import threading
import subprocess
import textwrap
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QFrame, QPushButton, QScrollArea, QGridLayout, QGraphicsOpacityEffect,
    QTabWidget, QMessageBox, QLineEdit, QToolButton, QStyle, QDialog,
    QDialogButtonBox, QComboBox, QCompleter, QSlider, QCheckBox, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, QThread, Signal, QSize, QObject, QPoint, QEvent
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QLinearGradient, QFont, QIcon
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QSizePolicy
from PySide6.QtTest import QTest
from BattleDatabase import BattleDatabase
from deck_analytics import (
    bayesian_binomial_summary,
    match_meta_row,
    rank_weighted_winrate,
    wilson_interval,
)
import japan_data
from app_settings import (
    clear_api_key,
    load_api_key,
    load_app_settings,
    save_api_key,
    save_app_settings,
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtCore import QUrl
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage, QWebEngineSettings
    WEBENGINE_AVAILABLE = True
except ImportError:
    WEBENGINE_AVAILABLE = False
    print("Warning: PySide6 WebEngine not available, web-based tabs will use link buttons")

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    from bs4 import BeautifulSoup
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    HTTPAdapter = None
    Retry = None
    print("Warning: requests/beautifulsoup4 not available, meta scraping disabled")

import json
import shutil
import time
import startup_utils
import weakref
from urllib.parse import quote_plus, urljoin

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class PageScrollArea(QScrollArea):
    """A QScrollArea that keeps the wheel scroll on the page.

    By default, when the cursor is over a child QTableWidget, the table's own
    scrollbar captures the wheel event and scrolls the table instead of the
    page — which feels clunky. This subclass intercepts wheel events anywhere
    inside the page and scrolls the page's vertical scrollbar instead, so the
    whole page scrolls smoothly like a normal webpage. (Tables are still
    scrollable via their own scrollbars when the page itself can't scroll.)
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setObjectName("scrollArea")
        try:
            self.verticalScrollBar().setSingleStep(24)
            self.verticalScrollBar().setPageStep(160)
        except Exception:
            pass

    def wheelEvent(self, event):
        # Always scroll the page's vertical scrollbar, regardless of which
        # child widget the cursor is over. This prevents inner tables from
        # hijacking the wheel.
        vbar = self.verticalScrollBar()
        if vbar is None:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        # If the page can still scroll, consume the event and scroll the page.
        if vbar.maximum() > 0:
            vbar.setValue(vbar.value() - delta)
            event.accept()
        else:
            # Page is at top/bottom — let the event propagate (e.g. to a
            # parent scroll area) so nested pages still feel natural.
            super().wheelEvent(event)


# Japanese deck name → English translation map (City League Season 4)
JP_DECK_TRANSLATION = {
    "ドラパルト": "Dragapult",
    "メガルカリオ": "Mega Lucario",
    "タケルライコ": "Raging Bolt",
    "ゲッコウガ": "Greninja",
    "ゾロアーク": "N's Zoroark",
    "フーディン": "Alakazam",
    "ピッピ": "Clefairy",
    "ガブリアス": "Cynthia's Garchomp",
    "ミュウツー": "Rocket's Mewtwo",
    "リザードン": "Charizard",
    "カビゴン": "Snorlax",
    "ルギア": "Lugia",
    "アルセウス": "Arceus",
    "パオジアン": "Chien-Pao",
    "テツノカイナ": "Iron Hands",
    "サーナイト": "Gardevoir",
    "ロストバレット": "Lost Box",
    "ロストギラティナ": "Lost Giratina",
    "ミライドン": "Miraidon",
    "コライドン": "Koraidon",
    "イダイナキバ": "Great Tusk",
    "ハピナス": "Blissey",
    "バシャドラパ": "Blaziken Dragapult",
    "ミュウ": "Mew VMAX",
    "ディンルー": "Ting-Lu",
    "カイリュー": "Dragonite",
    "バンギラス": "Tyranitar",
    "ハバタクカミ": "Flutter Mane",
    "テツノブジン": "Iron Valiant",
}

try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not available, graphs will not display")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
META_ICON_CACHE_DIR = os.path.join(BASE_DIR, ".meta_icon_cache")
POKESPRITE_BASE_URL = "https://raw.githubusercontent.com/bradley-erickson/pokesprite/master/pokemon/regular"
POKEAPI_POKEMON_URL = "https://pokeapi.co/api/v2/pokemon/{name}"
TRAINERHILL_BASE_URL = "https://www.trainerhill.com"
STATS_WINDOW_STATE_FILE = os.path.join(BASE_DIR, ".stats_window_geometry.json")
LIMITLESS_DASHBOARD_URL = "https://play.limitlesstcg.com/dashboard"
LIMITLESS_LOGIN_URL = "https://play.limitlesstcg.com/login"
LIMITLESS_PROFILE_DIR = os.path.join(BASE_DIR, ".limitless_web_profile")
LIMITLESS_DASHBOARD_STATE_FILE = os.path.join(BASE_DIR, ".limitless_dashboard_state.json")
# Shared flag file written by the Limitless dashboard manager and read by
# AIParseBattleLog.py so battles played while enrolled in a tournament get
# tagged and weighted as tournament games.
LIMITLESS_TOURNAMENT_FLAG_FILE = os.path.join(BASE_DIR, ".in_tournament")
LIMITLESS_SOUND_FILE = os.path.join(BASE_DIR, "ding.mp3")
LIMITLESS_CHECK_INTERVAL_MS = 60000
LIMITLESS_CHECK_DELAY_MS = 12000
LIMITLESS_CHAT_POLL_INTERVAL_MS = 3000
DECK_ICON_OVERRIDE_FILE = os.path.join(BASE_DIR, ".deck_icon_overrides.json")
PTCGL_REPLAY_URL = "https://www.ptcglreplay.com/"
SPRITE_NAME_ALIASES = {
    "ogerpon": ["ogerpon-teal-mask"],
    "ogerpon-wellspring": ["ogerpon-wellspring-mask", "ogerpon-teal-mask"],
    "ogerpon-hearthflame": ["ogerpon-hearthflame-mask", "ogerpon-teal-mask"],
    "ogerpon-cornerstone": ["ogerpon-cornerstone-mask", "ogerpon-teal-mask"],
    "ogerpon-teal": ["ogerpon-teal-mask"],
    "charizard-mega-x": ["charizard"],
    "charizard-mega-y": ["charizard"],
}


def _normalize_sprite_name(sprite_name):
    return (sprite_name or "").strip().lower().replace(" ", "-")


def _looks_japanese(text):
    """Return True if the text contains Japanese characters (untranslated)."""
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", text or ""))


def _sprite_cache_path(sprite_name):
    normalized = _normalize_sprite_name(sprite_name)
    if not normalized:
        return None
    return os.path.join(META_ICON_CACHE_DIR, f"{normalized.replace('/', '_')}.png")


def _sprite_name_candidates(sprite_name):
    normalized = _normalize_sprite_name(sprite_name)
    if not normalized:
        return []

    candidates = []
    seen = set()

    def add(name):
        normalized_name = _normalize_sprite_name(name)
        if normalized_name and normalized_name not in seen:
            seen.add(normalized_name)
            candidates.append(normalized_name)

    add(normalized)
    for alias in SPRITE_NAME_ALIASES.get(normalized, []):
        add(alias)

    parts = normalized.split("-")
    while len(parts) > 1:
        parts = parts[:-1]
        fallback = "-".join(parts)
        add(fallback)
        for alias in SPRITE_NAME_ALIASES.get(fallback, []):
            add(alias)

    return candidates


def _promote_cached_sprite(sprite_name, cached_path):
    requested_path = _sprite_cache_path(sprite_name)
    if not requested_path or not cached_path or not os.path.exists(cached_path):
        return None
    if requested_path == cached_path:
        return requested_path
    try:
        os.makedirs(META_ICON_CACHE_DIR, exist_ok=True)
        if not os.path.exists(requested_path):
            shutil.copyfile(cached_path, requested_path)
        return requested_path if os.path.exists(requested_path) else cached_path
    except Exception:
        return cached_path


def _find_cached_sprite_path(sprite_name):
    requested_path = _sprite_cache_path(sprite_name)
    if requested_path and os.path.exists(requested_path):
        return requested_path
    for candidate in _sprite_name_candidates(sprite_name):
        candidate_path = _sprite_cache_path(candidate)
        if candidate_path and os.path.exists(candidate_path):
            return _promote_cached_sprite(sprite_name, candidate_path)
    return None


def _fetch_sprite_to_cache(sprite_name, session=None):
    existing_path = _find_cached_sprite_path(sprite_name)
    if existing_path:
        return existing_path
    if not REQUESTS_AVAILABLE:
        return None

    requested_name = _normalize_sprite_name(sprite_name)
    if not requested_name:
        return None

    owns_session = session is None
    active_session = session or _build_retry_session()
    try:
        os.makedirs(META_ICON_CACHE_DIR, exist_ok=True)
        requested_path = _sprite_cache_path(requested_name)
        for candidate in _sprite_name_candidates(requested_name):
            response = active_session.get(f"{POKESPRITE_BASE_URL}/{candidate}.png", timeout=15)
            if response.status_code == 200 and response.content:
                with open(requested_path, "wb") as handle:
                    handle.write(response.content)
                candidate_path = _sprite_cache_path(candidate)
                if candidate_path and candidate_path != requested_path and not os.path.exists(candidate_path):
                    with open(candidate_path, "wb") as handle:
                        handle.write(response.content)
                return requested_path
            try:
                pokeapi_response = active_session.get(POKEAPI_POKEMON_URL.format(name=candidate), timeout=15)
                if pokeapi_response.status_code != 200:
                    continue
                payload = pokeapi_response.json()
                sprites = payload.get("sprites") or {}
                other = sprites.get("other") or {}
                sprite_url = (
                    (((other.get("home") or {}).get("front_default")))
                    or (((other.get("official-artwork") or {}).get("front_default")))
                    or sprites.get("front_default")
                )
                if not sprite_url:
                    continue
                image_response = active_session.get(sprite_url, timeout=20)
                if image_response.status_code == 200 and image_response.content:
                    with open(requested_path, "wb") as handle:
                        handle.write(image_response.content)
                    candidate_path = _sprite_cache_path(candidate)
                    if candidate_path and candidate_path != requested_path and not os.path.exists(candidate_path):
                        with open(candidate_path, "wb") as handle:
                            handle.write(image_response.content)
                    return requested_path
            except Exception:
                continue
    except Exception:
        return None
    finally:
        if owns_session:
            try:
                active_session.close()
            except Exception:
                pass
    return None


def _build_retry_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "TCGLiveMonitor/2.3 (+https://github.com/lavahawk)",
        "Accept": "application/json, text/plain, */*",
    })
    if Retry and HTTPAdapter:
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.4,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "POST"),
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    return session


def _dash_text(node):
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, (int, float)):
        return str(node)
    if isinstance(node, list):
        return "".join(_dash_text(child) for child in node)
    if isinstance(node, dict):
        return _dash_text(node.get("props", {}).get("children"))
    return ""


def _dash_find_first(node, *, type_name=None, class_contains=None):
    if isinstance(node, dict):
        node_type = node.get("type")
        class_name = node.get("props", {}).get("className", "")
        if (type_name is None or node_type == type_name) and (
            class_contains is None or class_contains in class_name
        ):
            return node
        for value in node.values():
            match = _dash_find_first(value, type_name=type_name, class_contains=class_contains)
            if match is not None:
                return match
    elif isinstance(node, list):
        for child in node:
            match = _dash_find_first(child, type_name=type_name, class_contains=class_contains)
            if match is not None:
                return match
    return None


def _dash_find_all(node, *, type_name=None, class_contains=None):
    matches = []
    if isinstance(node, dict):
        node_type = node.get("type")
        class_name = node.get("props", {}).get("className", "")
        if (type_name is None or node_type == type_name) and (
            class_contains is None or class_contains in class_name
        ):
            matches.append(node)
        for value in node.values():
            matches.extend(_dash_find_all(value, type_name=type_name, class_contains=class_contains))
    elif isinstance(node, list):
        for child in node:
            matches.extend(_dash_find_all(child, type_name=type_name, class_contains=class_contains))
    return matches


def _play_limitless_notification_sound():
    try:
        if PYGAME_AVAILABLE and os.path.exists(LIMITLESS_SOUND_FILE):
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            sound = pygame.mixer.Sound(LIMITLESS_SOUND_FILE)
            sound.play()
            return
    except Exception:
        pass

    try:
        QApplication.beep()
    except Exception:
        pass


class LimitlessCheckInAlert(QWidget):
    """Small topmost alert banner for Limitless tournament check-ins."""

    check_in_requested = Signal()
    dismissed = Signal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(360)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("limitlessCheckinAlert")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        title = QLabel("Limitless Check-In Ready")
        title.setObjectName("limitlessCheckinTitle")
        title_row.addWidget(title)
        title_row.addStretch()

        close_btn = QPushButton("×")
        close_btn.setObjectName("limitlessCheckinCloseBtn")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self._dismiss)
        title_row.addWidget(close_btn)
        card_layout.addLayout(title_row)

        self.body_label = QLabel("A tournament on your dashboard needs a check-in.")
        self.body_label.setObjectName("limitlessCheckinBody")
        self.body_label.setWordWrap(True)
        card_layout.addWidget(self.body_label)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        self.action_btn = QPushButton("Open Check-In")
        self.action_btn.setObjectName("limitlessCheckinActionBtn")
        self.action_btn.setFixedHeight(32)
        self.action_btn.clicked.connect(self.check_in_requested.emit)
        action_row.addWidget(self.action_btn)

        dismiss_btn = QPushButton("Dismiss")
        dismiss_btn.setObjectName("limitlessCheckinSecondaryBtn")
        dismiss_btn.setFixedHeight(32)
        dismiss_btn.clicked.connect(self._dismiss)
        action_row.addWidget(dismiss_btn)
        card_layout.addLayout(action_row)

        outer.addWidget(card)

        self.setStyleSheet("""
            QFrame#limitlessCheckinAlert {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(13, 20, 31, 0.97),
                    stop:1 rgba(9, 14, 22, 0.97));
                border: 1px solid rgba(249, 168, 37, 0.45);
                border-radius: 12px;
            }
            QLabel#limitlessCheckinTitle {
                color: rgba(255, 240, 200, 0.97);
                font-size: 13px;
                font-weight: 700;
            }
            QLabel#limitlessCheckinBody {
                color: rgba(233, 240, 250, 0.88);
                font-size: 11px;
                line-height: 1.3;
            }
            QPushButton#limitlessCheckinActionBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(249,168,37,0.42),
                    stop:1 rgba(230,126,34,0.42));
                border: 1px solid rgba(249,168,37,0.5);
                border-radius: 8px;
                color: rgba(255,255,255,0.96);
                font-size: 11px;
                font-weight: 700;
                padding: 6px 12px;
            }
            QPushButton#limitlessCheckinActionBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(249,168,37,0.56),
                    stop:1 rgba(230,126,34,0.56));
            }
            QPushButton#limitlessCheckinSecondaryBtn, QPushButton#limitlessCheckinCloseBtn {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 8px;
                color: rgba(233, 240, 250, 0.82);
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#limitlessCheckinSecondaryBtn:hover, QPushButton#limitlessCheckinCloseBtn:hover {
                background: rgba(255,255,255,0.10);
            }
        """)

    def _dismiss(self):
        self.hide()
        self.dismissed.emit()

    def show_message(self, text):
        self.body_label.setText(text)
        self.adjustSize()
        self.show()
        self.raise_()
        self.activateWindow()

    def position_near_overlay(self, overlay):
        try:
            if overlay and hasattr(overlay, "find_game_window"):
                hwnd = overlay.find_game_window()
                if hwnd:
                    import win32gui
                    left, top, right, _ = win32gui.GetWindowRect(hwnd)
                    x = max(20, right - self.width() - 20)
                    y = max(20, top + 20)
                    self.move(x, y)
                    return
        except Exception:
            pass

        screen = QApplication.primaryScreen()
        if screen:
            geometry = screen.availableGeometry()
            self.move(geometry.right() - self.width() - 20, geometry.top() + 20)


class WindowResizeHandle(QFrame):
    """Simple bottom-right resize handle that works reliably with frameless windows."""

    resize_started = Signal(object)
    resize_delta = Signal(object)
    resize_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragging = False
        self.setObjectName("windowSizeHandle")
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.resize_started.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.resize_delta.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.resize_finished.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(174, 196, 220, 190), 1.5)
        painter.setPen(pen)
        w = self.width()
        h = self.height()
        for offset in (5, 9, 13):
            painter.drawLine(w - offset, h - 2, w - 2, h - offset)
        painter.end()


class ClickableFrame(QFrame):
    """Lightweight frame with a clicked signal for row-style interactions."""

    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class ReplayWebPage(QWebEnginePage if WEBENGINE_AVAILABLE else QObject):
    """WebEngine page that can auto-answer the replay site's file picker."""

    upload_requested = Signal(str)

    def __init__(self, profile=None, parent=None):
        if WEBENGINE_AVAILABLE:
            super().__init__(profile, parent)
        else:
            super().__init__(parent)
        self.pending_upload_path = None

    def queue_upload(self, file_path):
        self.pending_upload_path = file_path

    if WEBENGINE_AVAILABLE:
        def chooseFiles(self, mode, old_files, accepted_mime_types):
            if self.pending_upload_path and os.path.exists(self.pending_upload_path):
                chosen = self.pending_upload_path
                self.pending_upload_path = None
                self.upload_requested.emit(chosen)
                return [chosen]
            self.upload_requested.emit("")
            return super().chooseFiles(mode, old_files, accepted_mime_types)


class LimitlessDashboardManager(QObject):
    """Persistent Limitless dashboard/profile manager with background check-in polling."""

    auth_state_changed = Signal(bool)
    status_changed = Signal(str)
    checkin_state_changed = Signal(dict)
    chat_state_changed = Signal(dict)

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.profile = None
        self.background_view = None
        self.background_page = None
        self.background_enabled = True
        self.auto_checkin_enabled = True
        self.authenticated = False
        self.in_tournament = False
        self.last_status = "Limitless dashboard idle."
        self.last_checkin = None
        self.last_chat_state = {}
        self.pending_visible_checkin = False
        self.visible_view = None
        self.visible_status_label = None
        self.chat_view = None
        self.chat_page = None
        self.chat_target_url = ""
        self.overlay_ref = None
        self.alert = LimitlessCheckInAlert()
        self.alert.check_in_requested.connect(self.handle_checkin_requested)
        self.alert.dismissed.connect(self._handle_alert_dismissed)

        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(LIMITLESS_CHECK_INTERVAL_MS)
        self.poll_timer.timeout.connect(self.poll_for_checkin)

        self.delayed_poll_timer = QTimer(self)
        self.delayed_poll_timer.setSingleShot(True)
        self.delayed_poll_timer.timeout.connect(self.poll_for_checkin)

        self.chat_poll_timer = QTimer(self)
        self.chat_poll_timer.setInterval(LIMITLESS_CHAT_POLL_INTERVAL_MS)
        self.chat_poll_timer.timeout.connect(self.poll_for_chat)

        self._load_state()
        if WEBENGINE_AVAILABLE:
            self._ensure_profile()

    def _load_state(self):
        try:
            if os.path.exists(LIMITLESS_DASHBOARD_STATE_FILE):
                with open(LIMITLESS_DASHBOARD_STATE_FILE, "r", encoding="utf-8") as handle:
                    state = json.load(handle)
                legacy_enabled = bool(state.get("background_enabled", True))
                self.auto_checkin_enabled = bool(state.get("auto_checkin_enabled", legacy_enabled))
        except Exception:
            self.auto_checkin_enabled = True
        self.background_enabled = True

    def _save_state(self):
        try:
            with open(LIMITLESS_DASHBOARD_STATE_FILE, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "background_enabled": True,
                        "auto_checkin_enabled": self.auto_checkin_enabled,
                    },
                    handle,
                )
        except Exception:
            pass

    def _update_tournament_flag(self, in_tournament, opponent=None):
        """Persist the current tournament-match state to a shared flag file.

        AIParseBattleLog.py reads this file so battles played while the player
        is actively in a Limitless tournament match get tagged and weighted as
        tournament games.

        The flag stores the opponent's username (when known) so a battle is
        only tagged as a tournament game if the battle-log opponent matches
        the opponent in the tournament chat. This avoids false positives from
        simply being enrolled in a tournament days in advance.
        """
        self.in_tournament = bool(in_tournament)
        try:
            if self.in_tournament:
                payload = {"in_tournament": True, "opponent": (opponent or "").strip()}
                with open(LIMITLESS_TOURNAMENT_FLAG_FILE, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle)
            else:
                if os.path.exists(LIMITLESS_TOURNAMENT_FLAG_FILE):
                    os.remove(LIMITLESS_TOURNAMENT_FLAG_FILE)
        except Exception:
            pass

    def _ensure_profile(self):
        if self.profile is not None:
            return
        os.makedirs(LIMITLESS_PROFILE_DIR, exist_ok=True)
        self.profile = QWebEngineProfile("limitless-dashboard", self)
        self.profile.setPersistentStoragePath(LIMITLESS_PROFILE_DIR)
        self.profile.setCachePath(os.path.join(LIMITLESS_PROFILE_DIR, "cache"))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.setHttpUserAgent("TCGLiveMonitor/2.3 Limitless Dashboard")

        page = QWebEnginePage(self.profile, self)
        try:
            page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        except Exception:
            pass
        page.urlChanged.connect(self._on_background_url_changed)
        page.loadFinished.connect(self._on_background_load_finished)
        self.background_page = page
        self.background_view = QWebEngineView()
        self.background_view.setPage(page)
        self.background_view.hide()

        chat_page = QWebEnginePage(self.profile, self)
        try:
            chat_page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            chat_page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        except Exception:
            pass
        chat_page.loadFinished.connect(self._on_chat_page_load_finished)
        self.chat_page = chat_page
        self.chat_view = QWebEngineView()
        self.chat_view.setPage(chat_page)
        self.chat_view.hide()

        if self.background_enabled:
            self.ensure_background_loaded()

    def set_overlay(self, overlay):
        self.overlay_ref = weakref.ref(overlay) if overlay else None

    def get_overlay(self):
        return self.overlay_ref() if self.overlay_ref else None

    def register_view(self, view, status_label=None):
        if not WEBENGINE_AVAILABLE:
            return
        self._ensure_profile()
        page = QWebEnginePage(self.profile, view)
        try:
            page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        except Exception:
            pass
        page.urlChanged.connect(lambda url: self._update_view_status(url.toString()))
        page.urlChanged.connect(lambda url: self._on_visible_url_changed(url.toString(), view))
        page.loadFinished.connect(lambda ok: self._on_visible_load_finished(ok, view))
        view.setPage(page)
        self.visible_view = view
        self.visible_status_label = status_label
        self._update_view_status(page.url().toString())

    def _update_view_status(self, url_text):
        if self.visible_status_label is None:
            return
        if not url_text:
            self.visible_status_label.setText(self.last_status)
        elif "/login" in url_text:
            self.visible_status_label.setText("Login required. Sign in here and your session will be remembered.")
        else:
            self.visible_status_label.setText(self.last_status)

    def enable_background_mode(self):
        self.background_enabled = True
        self.ensure_background_loaded()

    def ensure_background_loaded(self):
        if not WEBENGINE_AVAILABLE:
            return
        self._ensure_profile()
        current = self.background_page.url().toString()
        if not current or "/login" in current or "play.limitlesstcg.com" not in current:
            self.background_page.load(QUrl(LIMITLESS_DASHBOARD_URL))

    def ensure_visible_dashboard_loaded(self, force_login=False):
        if not WEBENGINE_AVAILABLE or self.visible_view is None:
            return
        page = self.visible_view.page()
        target = LIMITLESS_LOGIN_URL if force_login else LIMITLESS_DASHBOARD_URL
        if page.url().toString() != target:
            page.load(QUrl(target))

    def _on_background_url_changed(self, url):
        url_text = url.toString()
        if "/login" in url_text:
            self.authenticated = False
            self.auth_state_changed.emit(False)
            self.last_status = "Limitless dashboard is waiting for login."
            self.status_changed.emit(self.last_status)
        elif url_text:
            self.last_status = "Limitless dashboard is loading in the background."
            self.status_changed.emit(self.last_status)
        self._update_view_status(url_text)

    def _on_background_load_finished(self, ok):
        current_url = self.background_page.url().toString() if self.background_page else ""
        if not ok and not current_url:
            self.last_status = "Limitless dashboard failed to load."
            self.status_changed.emit(self.last_status)
            self._update_view_status("")
            return
        self.delayed_poll_timer.start(LIMITLESS_CHECK_DELAY_MS)
        if self.background_enabled and not self.poll_timer.isActive():
            self.poll_timer.start()
        self._update_view_status(self.background_page.url().toString())

    def _on_visible_load_finished(self, ok, view):
        if not ok:
            return
        try:
            current_url = view.page().url().toString()
            if current_url and "play.limitlesstcg.com" in current_url and self.background_page is not None:
                QTimer.singleShot(400, lambda: self.background_page.load(QUrl(LIMITLESS_DASHBOARD_URL)))
        except Exception:
            pass
        try:
            view.page().runJavaScript(
                self._chat_extract_js(),
                lambda result, source="visible": self._handle_chat_probe_result(result, source),
            )
        except Exception:
            pass
        if self.pending_visible_checkin and view is self.visible_view:
            QTimer.singleShot(1200, self.perform_checkin_click)

    def _on_visible_url_changed(self, url_text, view):
        try:
            if view is self.visible_view and url_text and "play.limitlesstcg.com" in url_text:
                QTimer.singleShot(800, lambda: view.page().runJavaScript(
                    self._chat_extract_js(),
                    lambda result, source="visible": self._handle_chat_probe_result(result, source),
                ))
        except Exception:
            pass

    def _checkin_scan_js(self):
        return """
            (() => {
                const visible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                const clickables = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"], div[role="button"]'));
                const authText = clickables.map(el => ((el.innerText || el.value || el.getAttribute('aria-label') || '') + '').trim()).join(' ');
                const loginForm = !!document.querySelector('input[type="password"]');
                const candidates = [];
                clickables.forEach((el, index) => {
                    const text = ((el.innerText || el.value || el.getAttribute('aria-label') || '') + '').replace(/\\s+/g, ' ').trim();
                    const href = el.href || el.getAttribute('href') || '';
                    if (!visible(el)) return;
                    if (!/check[\\s-]?in/i.test(text) && !/check[\\s-]?in/i.test(href)) return;
                    el.setAttribute('data-tcglive-checkin-id', String(index));
                    let context = '';
                    const container = el.closest('article, section, .card, .event, .tournament, [class*="event"], [class*="tournament"], li, tr, .dashboard-card');
                    if (container && container.innerText) {
                        context = container.innerText.replace(/\\s+/g, ' ').trim();
                    } else if (document.title) {
                        context = document.title;
                    }
                    if (context.length > 220) context = context.slice(0, 220) + '...';
                    candidates.push({
                        id: String(index),
                        text,
                        href,
                        context,
                        url: window.location.href
                    });
                });

                // Detect whether the player is enrolled in / checked into a
                // Limitless tournament. We look for tournament cards on the
                // dashboard that mention check-in, "enrolled", "registered",
                // "round", or a tournament/event heading.
                const bodyText = (document.body ? document.body.innerText : '').replace(/\\s+/g, ' ').trim();
                const tournamentHints = /check[\\s-]?in|enrolled|registered|tournament|round \\d+|\\brounds?\\b|\\bstandings\\b|\\bdecklist\\b/i;
                const inTournament = tournamentHints.test(bodyText) && !/\\/login(?:[?#]|$)/i.test(window.location.pathname + window.location.search);

                return JSON.stringify({
                    url: window.location.href,
                    title: document.title || '',
                    loggedIn: !/\\/login(?:[?#]|$)/i.test(window.location.pathname + window.location.search) && !loginForm && !/\\blog\\s*in\\b|\\bsign\\s*in\\b/i.test(authText),
                    inTournament,
                    candidates
                });
            })();
        """

    def poll_for_checkin(self):
        if not WEBENGINE_AVAILABLE or self.background_page is None:
            return
        url_text = self.background_page.url().toString()
        if not url_text:
            self.ensure_background_loaded()
            return
        self.background_page.runJavaScript(self._checkin_scan_js(), self._handle_checkin_scan_result)

    def _handle_checkin_scan_result(self, result):
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                result = None
        if not isinstance(result, dict):
            return
        self.authenticated = bool(result.get("loggedIn"))
        self.auth_state_changed.emit(self.authenticated)
        # Persist tournament-enrollment state for AIParseBattleLog to read.
        self._update_tournament_flag(bool(result.get("inTournament")))
        if not self.authenticated:
            self.last_checkin = None
            self.last_status = "Limitless dashboard is waiting for login."
            self.status_changed.emit(self.last_status)
            self._update_view_status(LIMITLESS_LOGIN_URL)
            if self.alert.isVisible():
                self.alert.hide()
            self.checkin_state_changed.emit({})
            return

        candidates = result.get("candidates") or []
        if not candidates:
            self.last_checkin = None
            self.last_status = "Limitless dashboard is loaded. No active check-in is currently required."
            self.status_changed.emit(self.last_status)
            self._update_view_status(result.get("url", ""))
            if self.alert.isVisible():
                self.alert.hide()
            self.checkin_state_changed.emit({})
            return

        candidate = candidates[0]
        key = "|".join(filter(None, [candidate.get("id"), candidate.get("text"), candidate.get("href"), candidate.get("context")]))
        is_new = not self.last_checkin or self.last_checkin.get("key") != key
        self.last_checkin = {
            "key": key,
            "candidate": candidate,
        }
        self.last_status = "Tournament check-in found on the Limitless dashboard."
        self.status_changed.emit(self.last_status)
        self._update_view_status(result.get("url", ""))
        self.checkin_state_changed.emit(candidate)
        if is_new:
            context = candidate.get("context") or candidate.get("text") or "A tournament on your Limitless dashboard is ready for check-in."
            if self.auto_checkin_enabled:
                self._attempt_auto_checkin(candidate, context)
            else:
                _play_limitless_notification_sound()
                overlay = self.get_overlay()
                self.alert.position_near_overlay(overlay)
                self.alert.show_message(context)

    def _handle_alert_dismissed(self):
        pass

    def _on_chat_page_load_finished(self, ok):
        if ok and not self.chat_poll_timer.isActive():
            self.chat_poll_timer.start()

    def _chat_extract_js(self):
        return r"""
            (() => {
                const clean = (text) => (text || '').replace(/\s+/g, ' ').trim();
                const drop = new Set(['chat', 'match chat', 'call judge', 'send', 'message', 'type a message']);
                const unique = (values) => {
                    const out = [];
                    const seen = new Set();
                    for (const value of values) {
                        const key = clean(value);
                        if (!key || seen.has(key)) continue;
                        seen.add(key);
                        out.push(key);
                    }
                    return out;
                };

                const containers = Array.from(document.querySelectorAll(
                    '[class*="chat"], [id*="chat"], [data-testid*="chat"], [data-cy*="chat"], section, article, div'
                ));

                let best = null;
                for (const node of containers) {
                    const text = clean(node.innerText);
                    if (!text) continue;
                    const lower = text.toLowerCase();
                    const score =
                        ((node.className || '').toString().toLowerCase().includes('chat') ? 6 : 0) +
                        ((node.id || '').toString().toLowerCase().includes('chat') ? 6 : 0) +
                        (lower.includes('call judge') ? 5 : 0) +
                        (lower.includes('match chat') ? 4 : 0) +
                        (node.querySelector('textarea, input[type="text"]') ? 2 : 0);
                    if (score < 4) continue;
                    if (!best || score > best.score || text.length > best.text.length) {
                        best = { node, score, text };
                    }
                }

                const pageText = clean(document.body ? document.body.innerText : '');
                const hasChat = !!best;
                let messages = [];
                let header = '';
                let subtitle = '';
                let opponent = '';

                if (best) {
                    const headerNode = best.node.closest('main, article, section, div')?.querySelector('h1, h2, h3');
                    header = clean(headerNode ? headerNode.innerText : document.title || 'Limitless Match');

                    const siblingText = clean((best.node.closest('main, article, section, div') || best.node).innerText);
                    const lines = siblingText.split(/\n+/).map(clean).filter(Boolean);
                    const filtered = [];
                    for (const line of lines) {
                        const lower = line.toLowerCase();
                        if (drop.has(lower)) continue;
                        if (lower === header.toLowerCase()) continue;
                        if (line.length < 2) continue;
                        if (/^round\b/i.test(line) || /\bvs\b/i.test(line) || /\btable\b/i.test(line)) {
                            if (!subtitle) subtitle = line;
                            // Extract the opponent username from "Round 1 vs OpponentName"
                            // or "vs OpponentName" patterns.
                            const vsMatch = line.match(/\bvs\.?\s+([A-Za-z0-9_\- ]+)/i);
                            if (vsMatch && vsMatch[1]) {
                                opponent = clean(vsMatch[1]);
                            }
                            continue;
                        }
                        filtered.push(line);
                    }
                    messages = unique(filtered).slice(-8);
                }

                return JSON.stringify({
                    url: window.location.href,
                    title: clean(document.title || ''),
                    hasChat,
                    header,
                    subtitle,
                    opponent,
                    messages,
                    pageTextSnippet: pageText.slice(0, 400)
                });
            })();
        """

    def _handle_chat_probe_result(self, result, source):
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                result = None
        if not isinstance(result, dict):
            return

        url_text = result.get("url") or ""
        has_chat = bool(result.get("hasChat"))

        if source == "visible" and has_chat and url_text and "play.limitlesstcg.com" in url_text:
            if url_text != self.chat_target_url:
                self.chat_target_url = url_text
                try:
                    if self.chat_page is not None and self.chat_page.url().toString() != url_text:
                        self.chat_page.load(QUrl(url_text))
                except Exception:
                    pass
            self._publish_chat_state(result)
            return

        if source == "chat" and has_chat:
            self._publish_chat_state(result)
            return

        if source == "visible" and not has_chat and self.visible_view is not None:
            current_url = ""
            try:
                current_url = self.visible_view.page().url().toString()
            except Exception:
                current_url = ""
            if current_url == self.chat_target_url and self.chat_target_url:
                self.chat_target_url = ""
                self._publish_chat_state({})

    def poll_for_chat(self):
        if not WEBENGINE_AVAILABLE:
            return

        page = None
        try:
            if self.visible_view is not None:
                visible_page = self.visible_view.page()
                visible_url = visible_page.url().toString() if visible_page is not None else ""
                if self.chat_target_url and visible_url == self.chat_target_url:
                    page = visible_page
            if page is None and self.chat_page is not None and self.chat_target_url:
                current_url = self.chat_page.url().toString()
                if current_url != self.chat_target_url:
                    self.chat_page.load(QUrl(self.chat_target_url))
                    return
                page = self.chat_page
        except Exception:
            page = None

        if page is None:
            if self.last_chat_state:
                self._publish_chat_state({})
            return

        try:
            source = "chat" if page is self.chat_page else "visible"
            page.runJavaScript(
                self._chat_extract_js(),
                lambda result, source=source: self._handle_chat_probe_result(result, source),
            )
        except Exception:
            pass

    def _publish_chat_state(self, payload):
        state = payload if isinstance(payload, dict) else {}
        normalized_messages = [str(msg).strip() for msg in (state.get("messages") or []) if str(msg).strip()]
        normalized = {
            "url": state.get("url") or "",
            "title": state.get("title") or "",
            "header": state.get("header") or "Limitless Match",
            "subtitle": state.get("subtitle") or "",
            "opponent": str(state.get("opponent") or "").strip(),
            "messages": normalized_messages[-8:],
            "visible": bool(normalized_messages),
        }
        if normalized == self.last_chat_state:
            return
        self.last_chat_state = normalized
        self.chat_state_changed.emit(normalized)
        # If we have a tournament match with a known opponent, persist it so
        # AIParseBattleLog can match the battle-log opponent against it.
        # If the match chat is gone (no opponent), clear the tournament flag.
        if normalized.get("opponent"):
            self._update_tournament_flag(True, opponent=normalized["opponent"])
        elif self.in_tournament:
            self._update_tournament_flag(False)

    def handle_checkin_requested(self):
        overlay = self.get_overlay()
        if overlay and hasattr(overlay, "open_stats_dashboard"):
            overlay.open_stats_dashboard()
            if overlay.stats_window:
                overlay.stats_window.open_limitless_dashboard_tab()
        self.pending_visible_checkin = True
        if self.visible_view is not None:
            self.perform_checkin_click()

    def _build_checkin_click_js(self, candidate):
        return f"""
            (() => {{
                const byId = document.querySelector('[data-tcglive-checkin-id="{candidate.get("id", "")}"]');
                const visible = (el) => {{
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                }};
                let target = byId;
                if (!visible(target)) {{
                    target = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"], div[role="button"]'))
                        .find(el => /check[\\s-]?in/i.test((el.innerText || el.value || el.getAttribute('aria-label') || '') + ''));
                }}
                if (target) {{
                    target.click();
                    return true;
                }}
                return false;
            }})();
        """

    def _attempt_auto_checkin(self, candidate, context):
        if self.background_page is None:
            return
        self.last_status = "Auto Check-In is attempting to confirm your tournament seat."
        self.status_changed.emit(self.last_status)
        _play_limitless_notification_sound()
        self.background_page.runJavaScript(
            self._build_checkin_click_js(candidate),
            lambda clicked, context=context: self._handle_auto_checkin_result(bool(clicked), context),
        )

    def _handle_auto_checkin_result(self, clicked, context):
        if clicked:
            self.last_status = "Auto Check-In clicked the Limitless dashboard."
            self.status_changed.emit(self.last_status)
            self.delayed_poll_timer.start(3500)
            return
        self.last_status = "Auto Check-In found a tournament but needs you to confirm manually."
        self.status_changed.emit(self.last_status)
        overlay = self.get_overlay()
        self.alert.position_near_overlay(overlay)
        self.alert.show_message(context)

    def perform_checkin_click(self):
        self.pending_visible_checkin = False
        candidate = (self.last_checkin or {}).get("candidate")
        if not candidate:
            return

        if self.visible_view is not None:
            page = self.visible_view.page()
            current_url = page.url().toString()
            if not current_url or "/login" in current_url:
                self.ensure_visible_dashboard_loaded(force_login=not self.authenticated)
                QTimer.singleShot(1500, self.perform_checkin_click)
                return
            page.runJavaScript(self._build_checkin_click_js(candidate))
        elif self.background_page is not None:
            self.background_page.runJavaScript(self._build_checkin_click_js(candidate))


_limitless_dashboard_manager = None


def get_limitless_dashboard_manager():
    global _limitless_dashboard_manager
    app = QApplication.instance()
    if _limitless_dashboard_manager is None and app is not None:
        _limitless_dashboard_manager = LimitlessDashboardManager(app)
    return _limitless_dashboard_manager


class MplCanvas(FigureCanvasQTAgg):
    """Matplotlib canvas with modern dark theme"""
    def __init__(self, parent=None, width=5, height=3, dpi=100):
        self.figure = Figure(figsize=(width, height), dpi=dpi)
        self.figure.patch.set_facecolor('none')
        self.figure.patch.set_alpha(0.0)
        
        self.axes = self.figure.add_subplot(111)
        
        # Modern dark styling
        self.axes.set_facecolor('#0a0a0a')
        self.axes.patch.set_alpha(0.3)
        
        # Remove top and right spines for cleaner look
        self.axes.spines['top'].set_visible(False)
        self.axes.spines['right'].set_visible(False)
        self.axes.spines['bottom'].set_color('#2a2a2a')
        self.axes.spines['left'].set_color('#2a2a2a')
        self.axes.spines['bottom'].set_linewidth(0.5)
        self.axes.spines['left'].set_linewidth(0.5)
        
        super(MplCanvas, self).__init__(self.figure)
        self.setStyleSheet("background-color: transparent;")
        self.setMinimumSize(300, 200)

    def wheelEvent(self, event):
        """Forward wheel events to the enclosing page scroll area.

        Matplotlib canvases normally capture the wheel for zooming, which
        stops the page from scrolling when the cursor is over a graph. We
        instead let the wheel scroll the page (like a normal webpage). The
        graph's own zoom is disabled in favor of smooth page scrolling.
        """
        # Find the nearest PageScrollArea ancestor and scroll it.
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, PageScrollArea):
                vbar = parent.verticalScrollBar()
                if vbar is not None and vbar.maximum() > 0:
                    vbar.setValue(vbar.value() - event.angleDelta().y())
                    event.accept()
                    return
            parent = parent.parent()
        # No page scroll area found — fall back to default behavior.
        super().wheelEvent(event)


class DeckIconPickerDialog(QDialog):
    """Themed icon picker that supports up to three icons per deck."""

    def __init__(self, owner, deck_name, choices, current_icons=None, default_icons=None):
        super().__init__(owner)
        self.owner = owner
        self.deck_name = deck_name
        self.choices = choices
        self.current_icons = list(current_icons or [])
        self.default_icons = list(default_icons or [])
        self.reset_requested = False
        self.combos = []
        self.slot_previews = []
        self.slot_clear_buttons = []
        self.active_slot_index = 0
        self.normalized_choices = []

        self.setObjectName("deckIconPickerDialog")
        self.setWindowTitle(f"{deck_name} Icons")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel(f"{deck_name} Icons")
        title.setObjectName("deckIconPickerTitle")
        layout.addWidget(title)

        subtitle = QLabel("Choose up to three Pokemon icons for this deck.")
        subtitle.setObjectName("deckIconPickerBody")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.selection_summary = QLabel("")
        self.selection_summary.setObjectName("deckIconPickerHint")
        self.selection_summary.setWordWrap(True)
        layout.addWidget(self.selection_summary)

        self.preview = QWidget()
        self.preview_layout = QHBoxLayout(self.preview)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_layout.setSpacing(6)
        layout.addWidget(self.preview, alignment=Qt.AlignmentFlag.AlignLeft)

        defaults_row = QHBoxLayout()
        defaults_row.setContentsMargins(0, 0, 0, 0)
        defaults_row.setSpacing(8)

        defaults_label = QLabel("Defaults")
        defaults_label.setObjectName("metaStatTitle")
        defaults_label.setFixedWidth(44)
        defaults_row.addWidget(defaults_label)

        self.default_preview = QWidget()
        self.default_preview_layout = QHBoxLayout(self.default_preview)
        self.default_preview_layout.setContentsMargins(0, 0, 0, 0)
        self.default_preview_layout.setSpacing(4)
        defaults_row.addWidget(self.default_preview, stretch=1)
        layout.addLayout(defaults_row)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(8)

        search_label = QLabel("Search")
        search_label.setObjectName("metaStatTitle")
        search_label.setFixedWidth(44)
        search_row.addWidget(search_label)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("deckIconSearch")
        self.search_input.setPlaceholderText("Search pokemon icons and click a result to fill the active slot")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._refresh_suggestions)
        search_row.addWidget(self.search_input, stretch=1)
        layout.addLayout(search_row)

        self.suggestion_list = QListWidget()
        self.suggestion_list.setObjectName("deckIconSuggestionList")
        self.suggestion_list.setMinimumHeight(160)
        self.suggestion_list.itemClicked.connect(self._apply_suggestion)
        layout.addWidget(self.suggestion_list)

        normalized_choices = list(choices)
        for sprite_name in list(self.current_icons) + list(self.default_icons):
            if sprite_name and sprite_name not in normalized_choices:
                normalized_choices.append(sprite_name)
        self.normalized_choices = normalized_choices
        options = ["None"] + normalized_choices
        current = list(self.current_icons[:3]) + ["None"] * max(0, 3 - len(self.current_icons[:3]))
        for index in range(3):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)

            label = QLabel(f"Icon {index + 1}")
            label.setObjectName("metaStatTitle")
            label.setFixedWidth(44)
            row.addWidget(label)

            slot_preview = QLabel()
            slot_preview.setObjectName("deckIconSlotPreview")
            slot_preview.setFixedSize(30, 30)
            row.addWidget(slot_preview)
            self.slot_previews.append(slot_preview)

            combo = QComboBox()
            combo.setObjectName("deckIconCombo")
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.setMaxVisibleItems(12)
            combo.addItems(options)
            combo.setCurrentText(current[index] if current[index] in options else "None")
            combo.lineEdit().setPlaceholderText("Type to search")
            combo.lineEdit().setClearButtonEnabled(True)
            combo.lineEdit().setStyleSheet("color: rgba(245,249,255,0.92); background: transparent;")
            combo.lineEdit().textEdited.connect(lambda _text, c=combo: c.showPopup())
            completer = combo.completer()
            if completer is not None:
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            combo.currentTextChanged.connect(self._refresh_preview)
            combo.activated.connect(lambda _idx, slot=index: self._set_active_slot(slot))
            combo.lineEdit().selectionChanged.connect(lambda slot=index: self._set_active_slot(slot))
            combo.lineEdit().cursorPositionChanged.connect(lambda _old, _new, slot=index: self._set_active_slot(slot))
            row.addWidget(combo, stretch=1)
            self.combos.append(combo)

            clear_btn = QToolButton()
            clear_btn.setObjectName("deckIconSlotClearBtn")
            clear_btn.setText("×")
            clear_btn.setToolTip("Clear this icon slot")
            clear_btn.clicked.connect(lambda checked=False, slot=index: self._clear_slot(slot))
            row.addWidget(clear_btn)
            self.slot_clear_buttons.append(clear_btn)
            layout.addLayout(row)

        buttons = QDialogButtonBox()
        save_btn = buttons.addButton("Save", QDialogButtonBox.ButtonRole.AcceptRole)
        reset_btn = buttons.addButton("Use Default", QDialogButtonBox.ButtonRole.ResetRole)
        cancel_btn = buttons.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        save_btn.clicked.connect(self.accept)
        reset_btn.clicked.connect(self._reset_to_default)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet("""
            QDialog#deckIconPickerDialog {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(10, 16, 25, 0.98),
                    stop:1 rgba(8, 12, 20, 0.98));
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 12px;
            }
            QLabel#deckIconPickerTitle {
                color: rgba(245,249,255,0.96);
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#deckIconPickerBody {
                color: rgba(168,182,204,0.82);
                font-size: 10px;
            }
            QLabel#deckIconPickerHint {
                color: rgba(201,218,238,0.76);
                font-size: 10px;
            }
            QLineEdit#deckIconSearch {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px;
                color: rgba(245,249,255,0.92);
                font-size: 11px;
                padding: 6px 10px;
                min-height: 28px;
            }
            QLineEdit#deckIconSearch:focus {
                border-color: rgba(74,159,216,0.45);
                background: rgba(255,255,255,0.08);
            }
            QListWidget#deckIconSuggestionList {
                background: rgba(255,255,255,0.045);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 8px;
                color: rgba(245,249,255,0.92);
                font-size: 11px;
                outline: none;
                padding: 4px;
            }
            QListWidget#deckIconSuggestionList::item {
                padding: 7px 8px;
                border-radius: 6px;
            }
            QListWidget#deckIconSuggestionList::item:selected {
                background: rgba(74,159,216,0.28);
                color: rgba(255,255,255,0.96);
            }
            QListWidget#deckIconSuggestionList::item:hover {
                background: rgba(255,255,255,0.07);
            }
            QComboBox#deckIconCombo {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px;
                color: rgba(245,249,255,0.92);
                font-size: 11px;
                padding: 4px 8px;
                min-height: 28px;
            }
            QComboBox#deckIconCombo:focus {
                border-color: rgba(74,159,216,0.45);
                background: rgba(255,255,255,0.08);
            }
            QComboBox#deckIconCombo::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox#deckIconCombo QAbstractItemView {
                background: rgb(20,20,20);
                color: rgba(255,255,255,0.88);
                selection-background-color: rgba(74,159,216,0.30);
                border: 1px solid rgba(255,255,255,0.10);
            }
            QComboBox#deckIconCombo QLineEdit {
                background: transparent;
                border: none;
                color: rgba(245,249,255,0.92);
                selection-background-color: rgba(74,159,216,0.30);
                padding: 0px;
            }
            QLabel#deckIconSlotPreview {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 6px;
            }
            QToolButton#deckIconSlotClearBtn {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 6px;
                color: rgba(255,255,255,0.78);
                font-size: 12px;
                font-weight: 700;
                min-width: 22px;
                min-height: 22px;
            }
            QToolButton#deckIconSlotClearBtn:hover {
                background: rgba(239,83,80,0.18);
                border-color: rgba(239,83,80,0.35);
                color: rgba(255,255,255,0.95);
            }
            QDialogButtonBox QPushButton {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px;
                color: rgba(255,255,255,0.88);
                font-size: 11px;
                font-weight: 600;
                min-height: 30px;
                padding: 4px 12px;
            }
            QDialogButtonBox QPushButton:hover {
                background: rgba(74,159,216,0.22);
                border-color: rgba(74,159,216,0.42);
            }
        """)

        self._refresh_default_preview()
        self._refresh_suggestions()
        self._refresh_preview()

    def _selected_icons(self):
        selected = []
        seen = set()
        for combo in self.combos:
            value = _normalize_sprite_name(combo.currentText())
            if not value or value == "none" or value in seen:
                continue
            selected.append(value)
            seen.add(value)
        return selected

    def _refresh_default_preview(self):
        while self.default_preview_layout.count():
            child = self.default_preview_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        defaults = []
        seen = set()
        for sprite_name in self.default_icons[:3]:
            if sprite_name and sprite_name not in seen:
                defaults.append(sprite_name)
                seen.add(sprite_name)
        if not defaults:
            text = QLabel("No Limitless defaults")
            text.setObjectName("deckIconPickerBody")
            self.default_preview_layout.addWidget(text)
            return
        for sprite_name in defaults:
            label = QLabel()
            pixmap = self.owner._load_sprite_pixmap(sprite_name, 30)
            if pixmap is None:
                pixmap = self.owner._build_placeholder_sprite(sprite_name[:1] or self.deck_name[:1], 30)
            label.setPixmap(pixmap)
            label.setFixedSize(32, 32)
            self.default_preview_layout.addWidget(label)

    def _set_active_slot(self, slot_index):
        self.active_slot_index = max(0, min(2, int(slot_index)))
        self._refresh_selection_summary()

    def _target_slot_for_suggestion(self):
        current_value = self.combos[self.active_slot_index].currentText().strip()
        if not current_value or current_value == "None":
            return self.active_slot_index
        for idx, combo in enumerate(self.combos):
            value = combo.currentText().strip()
            if not value or value == "None":
                return idx
        return self.active_slot_index

    def _clear_slot(self, slot_index):
        if 0 <= slot_index < len(self.combos):
            self.combos[slot_index].setCurrentText("None")
            self._set_active_slot(slot_index)
            self._refresh_preview()

    def _refresh_suggestions(self):
        if not hasattr(self, "suggestion_list"):
            return
        query = self.search_input.text().strip().lower() if hasattr(self, "search_input") else ""
        selected = set(self._selected_icons())
        self.suggestion_list.clear()
        ranked = []
        exact_present = False
        for sprite_name in self.normalized_choices:
            label = str(sprite_name)
            lower = label.lower()
            if query:
                if lower.startswith(query):
                    rank = 0
                elif query in lower:
                    rank = 1
                else:
                    continue
            else:
                rank = 0 if label in self.default_icons else 1
            ranked.append((rank, label))
            if query and lower == query:
                exact_present = True
        ranked.sort(key=lambda item: (item[0], item[1]))
        if query and query != "none" and not exact_present:
            custom_item = QListWidgetItem(f'Use online sprite "{query}"')
            custom_item.setData(Qt.ItemDataRole.UserRole, _normalize_sprite_name(query))
            self.suggestion_list.addItem(custom_item)
        for _, sprite_name in ranked[:80]:
            item = QListWidgetItem(sprite_name)
            if sprite_name in selected:
                item.setText(f"{sprite_name}  • already selected")
                item.setData(Qt.ItemDataRole.UserRole, sprite_name)
            else:
                item.setData(Qt.ItemDataRole.UserRole, sprite_name)
            self.suggestion_list.addItem(item)

    def _apply_suggestion(self, item):
        if item is None:
            return
        sprite_name = item.data(Qt.ItemDataRole.UserRole) or item.text().split("  •", 1)[0].strip()
        if not sprite_name:
            return
        slot_index = self._target_slot_for_suggestion()
        if 0 <= slot_index < len(self.combos):
            self.combos[slot_index].setCurrentText(sprite_name)
            self._set_active_slot(slot_index)
            self._refresh_preview()
            if hasattr(self, "search_input"):
                self.search_input.setFocus()
                self.search_input.selectAll()

    def _refresh_selection_summary(self):
        selected = self._selected_icons()
        active_slot = self.active_slot_index + 1
        default_text = ", ".join(self.default_icons[:3]) if self.default_icons else "none"
        self.selection_summary.setText(
            f"{len(selected)}/3 selected. Active slot: {active_slot}. "
            f"Click a search result to fill the active or next empty slot. "
            f"You can also search any Pokemon name online. Defaults: {default_text}."
        )

    def _refresh_preview(self):
        while self.preview_layout.count():
            child = self.preview_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

        selected = self._selected_icons()
        if not selected:
            placeholder = QLabel()
            placeholder.setPixmap(self.owner._build_placeholder_sprite(self.deck_name[:1], 36))
            placeholder.setFixedSize(38, 38)
            self.preview_layout.addWidget(placeholder)
            return

        for sprite_name in selected[:3]:
            label = QLabel()
            pixmap = self.owner._load_sprite_pixmap(sprite_name, 36)
            if pixmap is None:
                pixmap = self.owner._build_placeholder_sprite(sprite_name[:1] or self.deck_name[:1], 36)
            label.setPixmap(pixmap)
            label.setFixedSize(38, 38)
            self.preview_layout.addWidget(label)

        for idx, preview in enumerate(self.slot_previews):
            value = _normalize_sprite_name(self.combos[idx].currentText()) if idx < len(self.combos) else ""
            pixmap = None
            if value and value != "none":
                pixmap = self.owner._load_sprite_pixmap(value, 28)
                if pixmap is None:
                    pixmap = self.owner._build_placeholder_sprite(value[:1] or self.deck_name[:1], 28)
            else:
                pixmap = self.owner._build_placeholder_sprite(self.deck_name[:1], 28, accent="#2E445A")
            preview.setPixmap(pixmap)
            preview.setStyleSheet(
                "background: rgba(74,159,216,0.14); border: 1px solid rgba(74,159,216,0.38); border-radius: 6px;"
                if idx == self.active_slot_index
                else "background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.10); border-radius: 6px;"
            )

        self._refresh_selection_summary()
        self._refresh_suggestions()

    def _reset_to_default(self):
        self.reset_requested = True
        self.reject()

    def chosen_icons(self):
        normalized = []
        seen = set()
        for combo in self.combos:
            value = _normalize_sprite_name(combo.currentText())
            if not value or value == "none" or value in seen:
                continue
            normalized.append(value)
            seen.add(value)
        return normalized


class MetaTableItem(QTableWidgetItem):
    """QTableWidgetItem that sorts using an optional numeric/text payload."""

    def __lt__(self, other):
        if isinstance(other, QTableWidgetItem):
            left = self.data(Qt.ItemDataRole.UserRole)
            right = other.data(Qt.ItemDataRole.UserRole)
            if left is not None and right is not None:
                try:
                    return left < right
                except Exception:
                    return str(left) < str(right)
        return super().__lt__(other)


class MetaFetcher(QThread):
    """Background thread for fetching meta data from web sources.
    Caches results to disk for 1 hour to avoid hammering APIs."""
    data_ready = Signal(str, object)  # (source_name, data)
    error = Signal(str, str)           # (source_name, error_message)

    CACHE_TTL = 3600  # 1 hour
    CACHE_SCHEMA_VERSION = 2

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.source = source  # 'limitless_standard', 'limitless_pocket', 'trainerhill'
        self.session = _build_retry_session() if REQUESTS_AVAILABLE else None

    def run(self):
        try:
            cache_file = os.path.join(BASE_DIR, f".meta_cache_{self.source}.json")
            # Use cache if fresh enough
            if os.path.exists(cache_file):
                age = time.time() - os.path.getmtime(cache_file)
                if age < self.CACHE_TTL:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if self._is_cache_usable(data):
                        self.data_ready.emit(self.source, data)
                        return

            if self.source in ('limitless_standard', 'limitless_pocket'):
                data = self._fetch_limitless()
            elif self.source == 'trainerhill':
                data = self._fetch_trainerhill()
            else:
                self.error.emit(self.source, f"Unknown source: {self.source}")
                return

            # Cache result
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)

            self.data_ready.emit(self.source, data)

        except Exception as e:
            self.error.emit(self.source, str(e))

    def _is_cache_usable(self, data):
        rows = data.get("rows", [])
        if self.source in ("limitless_standard", "limitless_pocket"):
            if int(data.get("schema_version", 0) or 0) < self.CACHE_SCHEMA_VERSION:
                return False
        if self.source == "trainerhill" and not rows:
            return False
        return isinstance(rows, list)

    def _get_json(self, url, *, params=None, timeout=20):
        response = self.session.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def _post_json(self, url, payload, *, timeout=30):
        response = self.session.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def _prefetch_sprite_icons(self, rows):
        os.makedirs(META_ICON_CACHE_DIR, exist_ok=True)
        seen = set()
        for row in rows:
            for sprite_name in row.get("icons", [])[:3]:
                if not sprite_name or sprite_name in seen:
                    continue
                seen.add(sprite_name)
                self._ensure_sprite_cached(sprite_name)

    def _ensure_sprite_cached(self, sprite_name):
        return _fetch_sprite_to_cache(sprite_name, self.session)

    def _parse_limitless_record_text(self, text):
        if not text:
            return None
        match = re.search(
            r"([\d,]+)\s+wins\s+\(([\d.]+)%\)\s*-\s*([\d,]+)\s+losses(?:\s*-\s*([\d,]+)\s+ties)?",
            text,
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        wins = int(match.group(1).replace(",", ""))
        raw_pct = float(match.group(2))
        losses = int(match.group(3).replace(",", ""))
        ties = int((match.group(4) or "0").replace(",", ""))
        return {
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "raw_page_win_pct": raw_pct,
        }

    def _fetch_limitless_deck_record(self, deck_url):
        if not deck_url:
            return None
        try:
            response = self.session.get(deck_url, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser") if BeautifulSoup else None
            score_text = ""
            if soup is not None:
                score_node = soup.select_one(".score")
                if score_node is not None:
                    score_text = score_node.get_text(" ", strip=True)
            if not score_text:
                match = re.search(r'<div class="score">([^<]+)</div>', response.text, flags=re.IGNORECASE)
                if match:
                    score_text = match.group(1).strip()
            return self._parse_limitless_record_text(score_text)
        except Exception:
            return None

    def _enrich_limitless_rows_with_deck_records(self, rows):
        targets = [(index, row) for index, row in enumerate(rows) if row.get("deck_url")]
        if not targets:
            return
        max_workers = max(1, min(8, len(targets)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(self._fetch_limitless_deck_record, row.get("deck_url")): (index, row)
                for index, row in targets
            }
            for future in as_completed(future_map):
                index, row = future_map[future]
                try:
                    record = future.result()
                except Exception:
                    record = None
                if not record:
                    continue
                summary = bayesian_binomial_summary(
                    record.get("wins", 0),
                    record.get("losses", 0),
                    record.get("ties", 0),
                )
                rows[index].update({
                    "wins": record.get("wins", 0),
                    "losses": record.get("losses", 0),
                    "ties": record.get("ties", 0),
                    "win_pct": round(summary.get("observed", 0.0) * 100.0, 1),
                    "raw_page_win_pct": record.get("raw_page_win_pct", 0.0),
                    "bayes_win_pct": round(summary.get("bayes_mean", 0.0) * 100.0, 1),
                    "ci_low_pct": round(summary.get("ci_low", 0.0) * 100.0, 1),
                    "ci_high_pct": round(summary.get("ci_high", 0.0) * 100.0, 1),
                    "prob_above_even_pct": round(summary.get("probability_above_even", 0.0) * 100.0, 1),
                    "confidence_label": summary.get("confidence_label"),
                    "record_source": "deck_page",
                })

    def _fetch_limitless(self):
        """Aggregate deck stats from Limitless tournament standings with icon support."""
        game = "PTCG" if self.source == "limitless_standard" else "PTCGP"
        params = {"game": game, "limit": 30}
        if game == "PTCG":
            params["format"] = "Standard"
        tournaments = self._get_json("https://play.limitlesstcg.com/api/tournaments", params=params, timeout=20)

        deck_stats = {}
        processed = 0
        total_entries = 0
        for t in tournaments[:15]:  # top 15 most recent
            tid = t.get('id')
            if not tid:
                continue
            try:
                standings = self._get_json(f"https://play.limitlesstcg.com/api/tournaments/{tid}/standings", timeout=20)
                total_entries += len(standings)
                for player in standings:
                    deck = player.get('deck', {})
                    deck_name = None
                    deck_id = None
                    deck_icons = []
                    if isinstance(deck, dict):
                        deck_name = deck.get('name') or deck.get('id')
                        deck_id = deck.get("id") or deck_name
                        deck_icons = deck.get("icons") or []
                    elif isinstance(deck, str):
                        deck_name = deck
                        deck_id = deck
                    if not deck_name:
                        continue
                    record = player.get('record', {})
                    w = int(record.get('wins', 0) if isinstance(record, dict) else 0)
                    l = int(record.get('losses', 0) if isinstance(record, dict) else 0)
                    t_draw = 0
                    if isinstance(record, dict):
                        t_draw = int(
                            record.get('ties', 0)
                            or record.get('draws', 0)
                            or record.get('tie', 0)
                        )
                    key = deck_id or deck_name
                    if key not in deck_stats:
                        deck_stats[key] = {
                            "id": deck_id,
                            "deck": deck_name,
                            "icons": deck_icons,
                            "count": 0,
                            "wins": 0,
                            "losses": 0,
                            "ties": 0,
                            "deck_url": f"https://play.limitlesstcg.com/decks/{deck_id}?game={game}" if deck_id else None,
                        }
                    deck_stats[key]["count"] += 1
                    deck_stats[key]["wins"] += w
                    deck_stats[key]["losses"] += l
                    deck_stats[key]["ties"] += t_draw
                processed += 1
            except Exception:
                continue

        total = sum(d['count'] for d in deck_stats.values()) or 1
        rows = []
        for stats in deck_stats.values():
            c = stats['count']
            w = stats['wins']
            l = stats['losses']
            t = stats.get("ties", 0)
            summary = bayesian_binomial_summary(w, l, t)
            win_pct = round(summary.get("observed", 0.0) * 100, 1)
            rows.append({
                'id': stats.get("id"),
                'deck': stats['deck'],
                'icons': stats.get("icons") or [],
                'count': c,
                'share': round(c / total * 100, 1),
                'wins': w,
                'losses': l,
                'ties': t,
                'win_pct': win_pct,
                'bayes_win_pct': round(summary.get("bayes_mean", 0.0) * 100.0, 1),
                'ci_low_pct': round(summary.get("ci_low", 0.0) * 100.0, 1),
                'ci_high_pct': round(summary.get("ci_high", 0.0) * 100.0, 1),
                'prob_above_even_pct': round(summary.get("probability_above_even", 0.0) * 100.0, 1),
                'confidence_label': summary.get("confidence_label"),
                'deck_url': stats.get("deck_url"),
                'record_source': 'recent_tournaments',
            })
        rows.sort(key=lambda x: x['count'], reverse=True)
        self._enrich_limitless_rows_with_deck_records(rows)
        self._prefetch_sprite_icons(rows[:25])
        return {
            'schema_version': self.CACHE_SCHEMA_VERSION,
            'rows': rows,
            'tournaments_processed': processed,
            'total_entries': total_entries,
            'fetched_at': time.time(),
        }

    def _trainerhill_fetch_page_state(self):
        payload = {
            "output": ".._pages_content.children..._pages_store.data..",
            "outputs": [
                {"id": "_pages_content", "property": "children"},
                {"id": "_pages_store", "property": "data"},
            ],
            "inputs": [
                {"id": "_pages_location", "property": "pathname", "value": "/meta"},
                {"id": "_pages_location", "property": "search", "value": "?game=PTCG"},
            ],
            "state": [],
            "changedPropIds": ["_pages_location.pathname", "_pages_location.search"],
        }
        response = self._post_json(f"{TRAINERHILL_BASE_URL}/_dash-update-component", payload)
        page_tree = response["response"]["_pages_content"]["children"]
        for store in _dash_find_all(page_tree, type_name="Store"):
            if store.get("props", {}).get("id") == "meta-tour-store":
                return store.get("props", {}).get("data")
        raise RuntimeError("TrainerHill meta store was not found")

    def _trainerhill_fetch_archetypes(self, meta_store):
        payload = {
            "output": "..meta-archetype-select.options...meta-archetype-store.data..",
            "outputs": [
                {"id": "meta-archetype-select", "property": "options"},
                {"id": "meta-archetype-store", "property": "data"},
            ],
            "inputs": [{"id": "meta-tour-store", "property": "data", "value": meta_store}],
            "state": [],
            "changedPropIds": ["meta-tour-store.data"],
        }
        response = self._post_json(f"{TRAINERHILL_BASE_URL}/_dash-update-component", payload)
        return (
            response["response"]["meta-archetype-select"]["options"],
            response["response"]["meta-archetype-store"]["data"],
        )

    def _trainerhill_fetch_breakdown(self, meta_store, options):
        payload = {
            "output": "meta-breakdown-overall.children",
            "outputs": {"id": "meta-breakdown-overall", "property": "children"},
            "inputs": [
                {"id": "meta-tour-store", "property": "data", "value": meta_store},
                {"id": "meta-archetype-select", "property": "options", "value": options},
                {"id": "meta-breakdown-show-more", "property": "value", "value": True},
            ],
            "state": [],
            "changedPropIds": ["meta-tour-store.data"],
        }
        response = self._post_json(f"{TRAINERHILL_BASE_URL}/_dash-update-component", payload)
        return response["response"]["meta-breakdown-overall"]["children"]

    def _parse_trainerhill_breakdown_rows(self, breakdown_tree):
        rows = []
        for tr in _dash_find_all(breakdown_tree, type_name="Tr", class_contains="deck-row"):
            cells = tr.get("props", {}).get("children", [])
            if not isinstance(cells, list) or len(cells) < 4:
                continue

            trend_node = _dash_find_first(cells[1], type_name="I")
            trend_class = (trend_node or {}).get("props", {}).get("className", "")
            trend = "flat"
            if "trend-up" in trend_class:
                trend = "up"
            elif "trend-down" in trend_class:
                trend = "down"

            link_node = _dash_find_first(cells[2], type_name="Link")
            href = (link_node or {}).get("props", {}).get("href")
            deck_id = None
            if href and "/decklist/" in href:
                deck_id = href.split("/decklist/", 1)[1].split("?", 1)[0]

            share_text = _dash_text(cells[3]).replace("%", "").strip()
            try:
                share = float(share_text)
            except ValueError:
                share = 0.0

            rows.append({
                "id": deck_id,
                "share": share,
                "trend": trend,
                "deck_url": f"{TRAINERHILL_BASE_URL}{href}" if href else None,
            })
        return rows

    def _fetch_trainerhill(self):
        """Fetch TrainerHill data through its structured Dash callbacks."""
        meta_store = self._trainerhill_fetch_page_state()
        options, archetypes = self._trainerhill_fetch_archetypes(meta_store)
        breakdown_tree = self._trainerhill_fetch_breakdown(meta_store, options)
        breakdown_rows = self._parse_trainerhill_breakdown_rows(breakdown_tree)

        archetype_lookup = {row.get("id"): row for row in archetypes}
        rows = []
        for row in breakdown_rows:
            archetype = archetype_lookup.get(row.get("id"), {})
            rows.append({
                "id": row.get("id"),
                "deck": archetype.get("name") or row.get("id", "Unknown"),
                "icons": archetype.get("icons") or [],
                "count": archetype.get("count", 0),
                "share": row.get("share", 0.0),
                "trend": row.get("trend", "flat"),
                "deck_url": row.get("deck_url"),
            })

        rows.sort(key=lambda item: item.get("share", 0.0), reverse=True)
        self._prefetch_sprite_icons(rows[:25])
        return {
            "rows": rows,
            "filters": meta_store,
            "total_archetypes": len(archetypes),
            "fetched_at": time.time(),
        }


class JapanFetcher(QThread):
    """Background thread for fetching Japan meta data from pokekameshi.com."""
    data_ready = Signal(str, object)  # (source_name, data)
    error = Signal(str, str)          # (source_name, error_message)

    def __init__(self, ai_enabled=False, api_key=None, force=False, parent=None):
        super().__init__(parent)
        self.ai_enabled = ai_enabled
        self.api_key = api_key
        self.force = force

    def run(self):
        try:
            data = japan_data.fetch_japan_data(
                ai_enabled=self.ai_enabled,
                api_key=self.api_key,
                force=self.force,
                use_cache=not self.force,
            )
            self.data_ready.emit("japan", data)
        except Exception as e:
            self.error.emit("japan", str(e))


class StatsWindow(QWidget):
    """Modern sleek stats dashboard - minimizes to mini overlay"""
    
    def __init__(self, parent_overlay=None):
        super().__init__()
        self.db = BattleDatabase()
        self.parent_overlay = parent_overlay
        self.limitless_manager = get_limitless_dashboard_manager()
        self.is_minimized = False
        self.console_hidden = False  # Track console visibility state
        self.monitor_console_hwnd = None  # Handle to monitor's console window
        
        # For dragging and all-edge resizing
        self.dragging = False
        self.drag_position = None
        self.resizing = False
        self.resize_start_global = None
        self.resize_start_size = None
        self.resize_start_geometry = None
        self._resize_edges = (False, False, False, False)
        self._pre_fullscreen_geometry = None
        self.limitless_row_links = []
        self.trainerhill_row_links = []
        self.deck_tab_lookup = {}
        self.deck_analyses = []
        self.deck_icon_overrides = self._load_deck_icon_overrides()
        self.limitless_standard_meta = self._load_meta_cache("limitless_standard")
        self._japan_rows = []
        # In-memory pixmap cache keyed by (sprite_name, size) to avoid re-reading
        # and re-scaling sprite PNGs from disk on every UI refresh.
        self._sprite_pixmap_cache = {}
        self._deck_icon_choices_cache = None
        self.surface_opacity_scale = 0.80
        self._protected_interaction_depth = 0
        self._deck_dashboards_dirty = True
        self._stats_scroll_restore_pending = None
        self.app_settings = load_app_settings()
        self.replay_pending_log_path = None
        self._replay_request_token = 0
        self._window_focus_protection_active = False
        self._replay_tab_visible = False
        self.elo_time_scale = "all"
        self.elo_time_scale_days = {
            "1w": 7,
            "1m": 30,
            "3m": 90,
            "1y": 365,
        }
        
        self.init_ui()
        self.load_stats()
        
        # Auto-refresh every 15 seconds
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.load_stats)
        self.refresh_timer.start(15000)
    
    def init_ui(self):
        """Initialize modern UI with glass-morphism design"""
        # Window properties - transparent, frameless, always on top
        self.setWindowTitle("TCG Stats")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        
        # Main container with glass effect
        self.container = QFrame()
        self.container.setObjectName("glassContainer")
        
        # Layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)
        
        # Container layout
        layout = QVBoxLayout(self.container)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        
        # Title bar
        title_bar = self.create_title_bar()
        layout.addWidget(title_bar)
        
        # Tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("mainTabs")
        
        # Stats Tab
        stats_tab = self.create_stats_tab()
        self.tab_widget.addTab(stats_tab, "Stats")

        # Deck Dashboards Tab
        decks_tab = self.create_decks_tab()
        self.decks_tab_index = self.tab_widget.addTab(decks_tab, "Decks")
        
        # Limitless Meta Tab
        limitless_meta_tab = self.create_limitless_tab()
        self.limitless_meta_tab_index = self.tab_widget.addTab(limitless_meta_tab, "Limitless TCG Live Meta")

        # Limitless Dashboard Tab
        limitless_dashboard_tab = self.create_limitless_dashboard_tab()
        self.limitless_dashboard_tab_index = self.tab_widget.addTab(limitless_dashboard_tab, "Limitless Dashboard")

        # Replay Tab
        replay_tab = self.create_replay_tab()
        self.replay_tab_index = self.tab_widget.addTab(replay_tab, "Replay")
        self._set_replay_tab_visible(False)
        
        # TrainerHill Tab
        trainerhill_tab = self.create_trainerhill_tab()
        self.tab_widget.addTab(trainerhill_tab, "TrainerHill")
        
        # Japan City League Tab
        japan_tab = self.create_japan_tab()
        self.tab_widget.addTab(japan_tab, "Japan Data")
        
        # PokeData Tab
        pokedata_tab = self.create_pokedata_tab()
        self.tab_widget.addTab(pokedata_tab, "PokeData")
        
        # Settings Tab
        settings_tab = self.create_settings_tab()
        self.tab_widget.addTab(settings_tab, "Advanced")
        
        # Donate Tab
        support_tab = self.create_support_tab()
        self.tab_widget.addTab(support_tab, "Donate")
        
        layout.addWidget(self.tab_widget)
        layout.addWidget(self.create_footer_bar())
        
        # Apply modern styling
        self.apply_modern_style()
        
        self.tab_widget.currentChanged.connect(self.handle_tab_changed)

        # Start resizable and restore the user's preferred popup size if available
        self.setMinimumSize(900, 520)
        self.resize(1100, 760)
        self.restore_window_geometry()
        self._apply_window_opacity(self.surface_opacity_scale)

        if self.limitless_manager:
            self.limitless_manager.set_overlay(self.parent_overlay)
            self.limitless_manager.status_changed.connect(self._update_limitless_dashboard_status)
            self.limitless_manager.auth_state_changed.connect(self._update_limitless_dashboard_auth)
            self.limitless_manager.checkin_state_changed.connect(self._update_limitless_checkin_summary)
            self._update_limitless_dashboard_status(self.limitless_manager.last_status)
            self._update_limitless_dashboard_auth(self.limitless_manager.authenticated)

        if REQUESTS_AVAILABLE:
            QTimer.singleShot(1200, self._refresh_decks_meta)

        app = QApplication.instance()
        if app is not None:
            try:
                app.focusChanged.connect(self._on_app_focus_changed)
            except Exception:
                pass
    
    def create_title_bar(self):
        """Create modern title bar with fullscreen/minimize buttons"""
        title_bar = QFrame()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(32)  # Smaller title bar
        
        layout = QHBoxLayout(title_bar)
        layout.setContentsMargins(16, 0, 12, 0)
        layout.setSpacing(12)
        
        # Empty title area - clean minimal design
        layout.addStretch()
        
        # Fullscreen button
        self.fullscreen_btn = QPushButton("⛶")
        self.fullscreen_btn.setObjectName("minBtn")
        self.fullscreen_btn.setFixedSize(22, 22)
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self.fullscreen_btn.setToolTip("Toggle fullscreen")
        layout.addWidget(self.fullscreen_btn)
        
        # Minimize button (down arrow) - only button needed
        min_btn = QPushButton("▼")
        min_btn.setObjectName("minBtn")
        min_btn.setFixedSize(22, 22)  # Slightly smaller
        min_btn.clicked.connect(self.minimize_to_overlay)
        min_btn.setToolTip("Minimize to overlay")
        layout.addWidget(min_btn)
        
        return title_bar

    def toggle_fullscreen(self):
        """Toggle between fullscreen and the saved window geometry."""
        if self.isFullScreen():
            self.showNormal()
            # Restore the saved geometry after leaving fullscreen.
            self._restore_saved_geometry()
        else:
            self._pre_fullscreen_geometry = (self.x(), self.y(), self.width(), self.height())
            self.showFullScreen()
        self.fullscreen_btn.setText("🗗" if self.isFullScreen() else "⛶")

    def _restore_saved_geometry(self):
        try:
            if os.path.exists(STATS_WINDOW_STATE_FILE):
                with open(STATS_WINDOW_STATE_FILE, "r", encoding="utf-8") as handle:
                    state = json.load(handle)
                x = int(state.get("x", 100))
                y = int(state.get("y", 100))
                w = int(state.get("width", 900))
                h = int(state.get("height", 600))
                self.setGeometry(x, y, w, h)
                return
        except Exception:
            pass
        # Fallback to the geometry captured before entering fullscreen.
        if getattr(self, "_pre_fullscreen_geometry", None):
            x, y, w, h = self._pre_fullscreen_geometry
            self.setGeometry(x, y, w, h)

    def create_footer_bar(self):
        """Create a minimal footer that only exposes a resize grip."""
        footer = QFrame()
        footer.setObjectName("footerBar")
        footer.setFixedHeight(26)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(10, 0, 10, 4)
        layout.setSpacing(8)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setObjectName("opacitySlider")
        self.opacity_slider.setRange(70, 125)
        self.opacity_slider.setValue(int(round(self.surface_opacity_scale * 100)))
        self.opacity_slider.setFixedWidth(96)
        self.opacity_slider.setFixedHeight(14)
        self.opacity_slider.setToolTip("Adjust surface transparency")
        self.opacity_slider.valueChanged.connect(self._on_opacity_slider_changed)
        layout.addWidget(self.opacity_slider, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addStretch()

        self.resize_handle = WindowResizeHandle(footer)
        self.resize_handle.setToolTip("Drag to resize")
        self.resize_handle.resize_started.connect(self._begin_manual_resize)
        self.resize_handle.resize_delta.connect(self._update_manual_resize)
        self.resize_handle.resize_finished.connect(self._finish_manual_resize)
        layout.addWidget(self.resize_handle, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        return footer

    def _create_standard_scroll_area(self):
        return PageScrollArea()

    def _restore_scroll_value(self, scroll, value):
        if scroll is None or value is None:
            return
        try:
            scroll.verticalScrollBar().setValue(int(value))
        except Exception:
            pass

    def _apply_window_opacity(self, opacity_value):
        self.surface_opacity_scale = max(0.70, min(1.25, float(opacity_value)))
        self.apply_modern_style()

    def _on_opacity_slider_changed(self, value):
        self._apply_window_opacity(value / 100.0)
        self.save_window_geometry()

    def _begin_manual_resize(self, global_pos):
        self.resizing = True
        self.resize_start_global = global_pos
        self.resize_start_size = self.size()

    def _update_manual_resize(self, global_pos):
        if not self.resizing or self.resize_start_global is None or self.resize_start_size is None:
            return
        delta = global_pos - self.resize_start_global
        self.resize(
            max(self.minimumWidth(), self.resize_start_size.width() + delta.x()),
            max(self.minimumHeight(), self.resize_start_size.height() + delta.y()),
        )

    def _finish_manual_resize(self):
        self.resizing = False
        self.resize_start_global = None
        self.resize_start_size = None
        self.save_window_geometry()

    def save_window_geometry(self):
        try:
            payload = {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height(),
                "surface_opacity": round(self.surface_opacity_scale, 3),
            }
            with open(STATS_WINDOW_STATE_FILE, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
        except Exception:
            pass

    def restore_window_geometry(self):
        try:
            if not os.path.exists(STATS_WINDOW_STATE_FILE):
                return
            with open(STATS_WINDOW_STATE_FILE, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.resize(
                max(self.minimumWidth(), int(payload.get("width", self.width()))),
                max(self.minimumHeight(), int(payload.get("height", self.height()))),
            )
            self.move(int(payload.get("x", self.x())), int(payload.get("y", self.y())))
            self.surface_opacity_scale = max(0.70, min(1.25, float(payload.get("surface_opacity", self.surface_opacity_scale))))
            if hasattr(self, "opacity_slider"):
                self.opacity_slider.setValue(int(round(self.surface_opacity_scale * 100)))
        except Exception:
            pass
    
    def _resize_edge_at(self, pos):
        """Return which edge(s) the cursor is over for all-edge resizing.

        Returns a tuple of flags: (left, right, top, bottom). Uses a small
        hit zone (RESIZE_MARGIN px) around each edge.
        """
        margin = 6
        w = self.width()
        h = self.height()
        x = pos.x()
        y = pos.y()
        left = x <= margin
        right = x >= w - margin
        top = y <= margin
        bottom = y >= h - margin
        return left, right, top, bottom

    def _resize_cursor_for_edges(self, left, right, top, bottom):
        if (left and top) or (right and bottom):
            return Qt.CursorShape.SizeFDiagCursor
        if (right and top) or (left and bottom):
            return Qt.CursorShape.SizeBDiagCursor
        if left or right:
            return Qt.CursorShape.SizeHorCursor
        if top or bottom:
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def mousePressEvent(self, event):
        """Handle mouse press for dragging and all-edge resizing"""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            left, right, top, bottom = self._resize_edge_at(pos)
            if left or right or top or bottom:
                # Start an edge resize.
                self.resizing = True
                self._resize_edges = (left, right, top, bottom)
                self.resize_start_global = event.globalPosition().toPoint()
                self.resize_start_geometry = self.geometry()
                event.accept()
                return
            # Check if clicking on title bar area (top 32px) to drag.
            if pos.y() < 32:
                self.dragging = True
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                event.accept()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for dragging and all-edge resizing"""
        if self.resizing:
            self._update_edge_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if self.dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
            return
        # Update the resize cursor when hovering over an edge (no button held).
        if not event.buttons():
            left, right, top, bottom = self._resize_edge_at(event.position())
            if left or right or top or bottom:
                self.setCursor(self._resize_cursor_for_edges(left, right, top, bottom))
            else:
                self.unsetCursor()
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release to stop dragging/resizing"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.resizing = False
            self._resize_edges = (False, False, False, False)
            self.unsetCursor()
            self.save_window_geometry()
            event.accept()

    def _update_edge_resize(self, global_pos):
        """Resize the window from any edge based on the drag delta."""
        if not self.resizing or self.resize_start_global is None or self.resize_start_geometry is None:
            return
        left, right, top, bottom = self._resize_edges
        start_geo = self.resize_start_geometry
        delta = global_pos - self.resize_start_global

        new_left = start_geo.left()
        new_top = start_geo.top()
        new_right = start_geo.right()
        new_bottom = start_geo.bottom()

        if left:
            new_left = start_geo.left() + delta.x()
        if right:
            new_right = start_geo.right() + delta.x()
        if top:
            new_top = start_geo.top() + delta.y()
        if bottom:
            new_bottom = start_geo.bottom() + delta.y()

        min_w = self.minimumWidth()
        min_h = self.minimumHeight()
        if new_right - new_left < min_w:
            if left:
                new_left = new_right - min_w
            else:
                new_right = new_left + min_w
        if new_bottom - new_top < min_h:
            if top:
                new_top = new_bottom - min_h
            else:
                new_bottom = new_top + min_h

        self.setGeometry(new_left, new_top, new_right - new_left, new_bottom - new_top)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.save_window_geometry()

    def moveEvent(self, event):
        super().moveEvent(event)
        self.save_window_geometry()

    def closeEvent(self, event):
        try:
            app = QApplication.instance()
            if app is not None:
                try:
                    app.focusChanged.disconnect(self._on_app_focus_changed)
                except Exception:
                    pass
            self._update_window_interaction_state(force_release=True)
            while self.is_protected_interaction_active():
                self.end_protected_interaction()
            if self.parent_overlay and getattr(self.parent_overlay, "stats_window", None) is self:
                self.parent_overlay.stats_window = None
                self.parent_overlay.arrow_label.setText("▲")
            if self.limitless_manager:
                try:
                    self.limitless_manager.status_changed.disconnect(self._update_limitless_dashboard_status)
                except Exception:
                    pass
                try:
                    self.limitless_manager.auth_state_changed.disconnect(self._update_limitless_dashboard_auth)
                except Exception:
                    pass
                try:
                    self.limitless_manager.checkin_state_changed.disconnect(self._update_limitless_checkin_summary)
                except Exception:
                    pass
        finally:
            super().closeEvent(event)

    def event(self, event):
        if event.type() in (QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate, QEvent.Type.Show, QEvent.Type.Hide):
            QTimer.singleShot(0, self._update_window_interaction_state)
        return super().event(event)

    def _owns_widget(self, widget):
        current = widget
        while current is not None:
            if current is self:
                return True
            current = current.parentWidget() if hasattr(current, "parentWidget") else None
        return False

    def _on_app_focus_changed(self, _old, _new):
        QTimer.singleShot(0, self._update_window_interaction_state)

    def _update_window_interaction_state(self, force_release=False):
        should_protect = False
        if not force_release and self.isVisible():
            app = QApplication.instance()
            if app is not None:
                focus_widget = app.focusWidget()
                active_popup = app.activePopupWidget()
                active_modal = app.activeModalWidget()
                should_protect = (
                    self.isActiveWindow()
                    or self._owns_widget(focus_widget)
                    or self._owns_widget(active_popup)
                    or self._owns_widget(active_modal)
                )

        if should_protect and not self._window_focus_protection_active:
            self._window_focus_protection_active = True
            self.begin_protected_interaction()
        elif not should_protect and self._window_focus_protection_active:
            self._window_focus_protection_active = False
            self.end_protected_interaction()
    
    def minimize_to_overlay(self):
        """Minimize stats window back to mini overlay"""
        self.is_minimized = True
        self.hide()
        if self.parent_overlay:
            self.parent_overlay.arrow_label.setText("▲")  # Flip arrow back up
    
    def create_stats_tab(self):
        """Create stats tab with all statistics"""
        scroll = self._create_standard_scroll_area()
        self.stats_scroll = scroll
        
        content_widget = QWidget()
        content_widget.setObjectName("contentWidget")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(8)
        content_layout.setContentsMargins(12, 8, 12, 20)  # Added bottom padding
        
        # Stats cards
        self.stats_summary = self.create_stats_cards()
        content_layout.addWidget(self.stats_summary)
        
        # Graphs section
        if MATPLOTLIB_AVAILABLE:
            graphs_container = self.create_graphs_section()
            content_layout.addWidget(graphs_container)
        
        # Deck usage section
        self.deck_usage_widget = self.create_deck_section()
        content_layout.addWidget(self.deck_usage_widget)
        
        # Recent battles
        self.recent_battles_widget = self.create_battles_section()
        content_layout.addWidget(self.recent_battles_widget)
        
        # Limitless integration
        limitless_section = self.create_limitless_section()
        content_layout.addWidget(limitless_section)
        
        content_layout.addStretch()
        
        scroll.setWidget(content_widget)
        return scroll

    def create_decks_tab(self):
        """Create per-deck dashboards with streamlined navigation."""
        outer = QWidget()
        outer.setObjectName("contentWidget")
        vlayout = QVBoxLayout(outer)
        vlayout.setContentsMargins(12, 8, 12, 12)
        vlayout.setSpacing(0)

        self.deck_tabs = QTabWidget()
        self.deck_tabs.setObjectName("deckTabs")
        self.deck_tabs.setDocumentMode(True)
        self.deck_tabs.setMovable(True)
        self.deck_tabs.setUsesScrollButtons(True)
        self.deck_tabs.setCornerWidget(self._create_deck_search_widget(), Qt.Corner.TopRightCorner)
        vlayout.addWidget(self.deck_tabs, stretch=1)

        return outer

    def _create_deck_search_widget(self):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.deck_search_input = QLineEdit()
        self.deck_search_input.setObjectName("deckSearchInput")
        self.deck_search_input.setPlaceholderText("Find deck")
        self.deck_search_input.setFixedWidth(150)
        self.deck_search_input.hide()
        self.deck_search_input.textChanged.connect(self._filter_deck_tabs)
        self.deck_search_input.returnPressed.connect(self._focus_current_deck_match)
        layout.addWidget(self.deck_search_input)

        self.deck_search_btn = QToolButton()
        self.deck_search_btn.setObjectName("deckSearchBtn")
        self.deck_search_btn.setText("⌕")
        self.deck_search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.deck_search_btn.setToolTip("Find a deck tab")
        self.deck_search_btn.clicked.connect(self._toggle_deck_search)
        layout.addWidget(self.deck_search_btn)

        return container

    def _toggle_deck_search(self):
        if not hasattr(self, "deck_search_input"):
            return
        visible = self.deck_search_input.isVisible()
        self.deck_search_input.setVisible(not visible)
        if visible:
            self.deck_search_input.clear()
        else:
            self.deck_search_input.setFocus()
            self.deck_search_input.selectAll()

    def _filter_deck_tabs(self, text):
        text = (text or "").strip().lower()
        if not text:
            return
        for idx in range(self.deck_tabs.count()):
            full_name = self.deck_tabs.tabBar().tabToolTip(idx) or self.deck_tabs.tabText(idx)
            if text in full_name.lower():
                self.deck_tabs.setCurrentIndex(idx)
                break

    def _focus_current_deck_match(self):
        if hasattr(self, "deck_search_input"):
            self._filter_deck_tabs(self.deck_search_input.text())

    def _choose_deck_icon(self, deck_name):
        choices = self._deck_icon_choices()

        matched_meta = self._match_limitless_row(deck_name)
        default_icons = []
        if matched_meta:
            default_icons = list((matched_meta.get("row") or {}).get("icons", [])[:3])
        current_icons = self.deck_icon_overrides.get(deck_name) or self._resolved_deck_icons(deck_name, default_icons)

        dialog = DeckIconPickerDialog(
            self,
            deck_name,
            choices,
            current_icons=current_icons,
            default_icons=default_icons,
        )
        self.begin_protected_interaction()
        try:
            result = dialog.exec()
        finally:
            self.end_protected_interaction()
        if dialog.reset_requested:
            self.deck_icon_overrides.pop(deck_name, None)
            self._save_deck_icon_overrides()
            self._refresh_deck_dashboards()
            self.update_deck_usage(self.deck_analyses)
            return
        if result != QDialog.DialogCode.Accepted:
            return

        chosen = dialog.chosen_icons()[:3]
        for sprite_name in chosen:
            if self._ensure_sprite_cached_local(sprite_name) is None:
                QMessageBox.warning(
                    self,
                    "Icon Not Found",
                    f"Couldn't load a sprite for '{sprite_name}'. Try another Pokemon name.",
                )
                return

        normalized_default = list(default_icons[:3])
        if not chosen or chosen == normalized_default:
            self.deck_icon_overrides.pop(deck_name, None)
        else:
            self.deck_icon_overrides[deck_name] = chosen
        self._save_deck_icon_overrides()
        self._refresh_deck_dashboards()
        self.update_deck_usage(self.deck_analyses)

    def _create_dashboard_card(self, title):
        card = QFrame()
        card.setObjectName("deckDashboardCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("sectionHeader")
        layout.addWidget(title_label)
        return card, layout

    def _set_mouse_passthrough(self, widget):
        if widget is None:
            return
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        for child in widget.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def begin_protected_interaction(self):
        self._protected_interaction_depth += 1
        if self._protected_interaction_depth == 1:
            if hasattr(self, "refresh_timer") and self.refresh_timer.isActive():
                self._protected_refresh_was_active = True
                self.refresh_timer.stop()
            else:
                self._protected_refresh_was_active = False
            if self.parent_overlay and hasattr(self.parent_overlay, "suspend_stats_window_tracking"):
                self.parent_overlay.suspend_stats_window_tracking()

    def end_protected_interaction(self):
        if self._protected_interaction_depth <= 0:
            return
        self._protected_interaction_depth -= 1
        if self._protected_interaction_depth == 0:
            if getattr(self, "_protected_refresh_was_active", False) and hasattr(self, "refresh_timer"):
                self.refresh_timer.start(15000)
            if self.parent_overlay and hasattr(self.parent_overlay, "resume_stats_window_tracking"):
                self.parent_overlay.resume_stats_window_tracking()

    def is_protected_interaction_active(self):
        return self._protected_interaction_depth > 0

    def _create_metric_grid(self, metrics, columns=4):
        container = QWidget()
        layout = QGridLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        for index, metric in enumerate(metrics):
            title = metric.get("title", "")
            value = metric.get("value", "--")
            accent = metric.get("accent", "#EEF4FF")
            tooltip = metric.get("tooltip")

            card = QFrame()
            card.setObjectName("metaStatCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(2)

            value_label = QLabel(value)
            value_label.setObjectName("metaStatValue")
            value_label.setStyleSheet(f"color: {accent}; font-size: 15px; font-weight: 700;")
            title_label = QLabel(title)
            title_label.setObjectName("metaStatTitle")

            if tooltip:
                card.setToolTip(tooltip)
                value_label.setToolTip(tooltip)
                title_label.setToolTip(tooltip)

            card_layout.addWidget(value_label)
            card_layout.addWidget(title_label)
            layout.addWidget(card, index // columns, index % columns)

        return container

    def _create_scale_metric_card(self, title, value_text, fill_ratio, accent, subtitle=None):
        card = QFrame()
        card.setObjectName("deckMetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QLabel(title)
        header.setObjectName("metaStatTitle")
        layout.addWidget(header)

        value = QLabel(value_text)
        value.setObjectName("deckScaleValue")
        value.setStyleSheet(f"color: {accent};")
        layout.addWidget(value)

        track = QFrame()
        track.setObjectName("deckScaleTrack")
        track_layout = QHBoxLayout(track)
        track_layout.setContentsMargins(0, 0, 0, 0)
        track_layout.setSpacing(0)

        fill = QFrame()
        fill.setObjectName("deckScaleFill")
        fill.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 rgba(255,255,255,0.92)); border-radius: 4px;"
        )

        ratio = max(0, min(100, int(round(fill_ratio * 100.0))))
        track_layout.addWidget(fill, ratio)
        track_layout.addStretch(max(0, 100 - ratio))
        layout.addWidget(track)

        if subtitle:
            note = QLabel(subtitle)
            note.setObjectName("deckMetricNote")
            note.setWordWrap(True)
            layout.addWidget(note)

        return card

    def _create_interval_metric_card(self, title, low_pct, mid_pct, high_pct, accent, subtitle=None):
        card = QFrame()
        card.setObjectName("deckMetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QLabel(title)
        header.setObjectName("metaStatTitle")
        layout.addWidget(header)

        value = QLabel(f"{mid_pct:.1f}%")
        value.setObjectName("deckScaleValue")
        value.setStyleSheet(f"color: {accent};")
        layout.addWidget(value)

        meter = QWidget()
        meter.setMinimumHeight(18)
        meter.setStyleSheet("background: transparent;")
        meter_layout = QVBoxLayout(meter)
        meter_layout.setContentsMargins(0, 0, 0, 0)
        meter_layout.setSpacing(2)

        bar = QFrame()
        bar.setObjectName("deckIntervalBar")
        bar.setFixedHeight(8)
        bar.setStyleSheet("background-color: rgba(255,255,255,0.06); border-radius: 4px;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(0)

        left_spacer = max(0, min(100, int(round(low_pct))))
        interval_width = max(2, min(100 - left_spacer, int(round(high_pct - low_pct))))
        right_spacer = max(0, 100 - left_spacer - interval_width)

        bar_layout.addStretch(left_spacer)
        interval = QFrame()
        interval.setStyleSheet(f"background-color: {accent}; border-radius: 4px;")
        bar_layout.addWidget(interval, interval_width)
        bar_layout.addStretch(right_spacer)
        meter_layout.addWidget(bar)

        marker_row = QLabel(f"{low_pct:.0f}% - {high_pct:.0f}%")
        marker_row.setObjectName("deckMetricNote")
        meter_layout.addWidget(marker_row)
        layout.addWidget(meter)

        if subtitle:
            note = QLabel(subtitle)
            note.setObjectName("deckMetricNote")
            note.setWordWrap(True)
            layout.addWidget(note)

        return card

    def _create_deck_visual_metrics(self, analysis):
        summary = analysis.get("summary", {})
        rank_summary = analysis.get("rank_summary", {})
        bayes_pct = summary.get("bayes_mean", 0) * 100.0
        prob_even = summary.get("probability_above_even", 0) * 100.0
        ci_low = summary.get("ci_low", 0) * 100.0
        ci_high = summary.get("ci_high", 0) * 100.0
        delta_vs_meta = analysis.get("delta_vs_meta")
        confidence_label = summary.get("confidence_label", "Low")
        confidence_note = summary.get("confidence_note", "")

        # Rank-weighted Elo win rate metrics.
        rw_pct = rank_summary.get("weighted_winrate", 0.0) * 100.0
        rw_low = rank_summary.get("ci_low", 0.0) * 100.0
        rw_high = rank_summary.get("ci_high", 0.0) * 100.0
        rw_eff_n = rank_summary.get("effective_n", 0.0)
        rw_avg_rank = rank_summary.get("avg_rank")
        rw_conf = rank_summary.get("confidence_label", "Low")
        rw_note = rank_summary.get("confidence_note", "")
        rw_tourney_games = rank_summary.get("tournament_games", 0)
        if rw_avg_rank is not None:
            rw_note = f"Avg Elo {rw_avg_rank:.0f} • {rw_note}"
        else:
            rw_note = f"No rank data recorded • {rw_note}"
        if rw_tourney_games:
            rw_note = f"{rw_tourney_games} tournament game(s) • {rw_note}"

        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)

        cards = [
            self._create_scale_metric_card(
                "Rank-Weighted Win Rate",
                f"{rw_pct:.1f}%",
                rw_pct / 100.0,
                self._percent_accent(rw_pct),
                f"Elo-adjusted (eff. n={rw_eff_n:.1f}). {rw_note}",
            ),
            self._create_interval_metric_card(
                "Rank-Weighted 95% CI",
                rw_low,
                rw_pct,
                rw_high,
                "#6BB6E8",
                "Confidence interval on the Elo-weighted win rate.",
            ),
            self._create_scale_metric_card(
                "Bayesian Win Rate",
                f"{bayes_pct:.1f}%",
                bayes_pct / 100.0,
                self._percent_accent(bayes_pct),
                "Smoothed estimate of true deck strength.",
            ),
            self._create_interval_metric_card(
                "Confidence Interval",
                ci_low,
                bayes_pct,
                ci_high,
                "#6BB6E8",
                "Observed range that still fits the sample.",
            ),
            self._create_scale_metric_card(
                "P(True WR > 50%)",
                f"{prob_even:.0f}%",
                prob_even / 100.0,
                self._probability_accent(prob_even),
                "How likely the deck is actually above even.",
            ),
            self._create_scale_metric_card(
                "Sample Strength",
                confidence_label,
                min(1.0, analysis.get("games", 0) / 30.0),
                "#F9A825" if confidence_label == "Medium" else "#66BB6A" if confidence_label == "High" else "#EF5350",
                confidence_note,
            ),
        ]

        if delta_vs_meta is not None:
            cards.append(
                self._create_scale_metric_card(
                    "Edge vs Meta" if analysis.get("matched_meta") else "Edge vs Field",
                    f"{delta_vs_meta:+.1f} pts",
                    (max(-15.0, min(15.0, delta_vs_meta)) + 15.0) / 30.0,
                    self._delta_accent(delta_vs_meta),
                    "Positive means your sample is running ahead of the benchmark.",
                )
            )
        cards.append(
            self._create_scale_metric_card(
                "Meta Exposure",
                f"{analysis.get('meta_exposure', 0):.0f}%",
                analysis.get("meta_exposure", 0) / 100.0,
                "#6BB6E8",
                "Share of logged games played into top current archetypes.",
            )
        )

        for index, card in enumerate(cards):
            grid.addWidget(card, index // 3, index % 3)

        return container

    def _smart_time_format(self, timestamps):
        if len(timestamps) < 2:
            return "%m/%d"
        time_range = (timestamps[-1] - timestamps[0]).total_seconds()
        if time_range < 86400:
            return "%H:%M"
        if time_range < 86400 * 14:
            return "%m/%d"
        if time_range < 86400 * 90:
            return "%m/%d"
        return "%m/%d/%y"

    def _build_deck_trend_series(self, deck_name):
        history = self.db.get_deck_battle_history(deck_name)
        times = []
        observed = []
        bayes = []
        lows = []
        highs = []
        wins = 0
        losses = 0
        ties = 0

        for timestamp, result in history:
            try:
                dt = datetime.fromisoformat(timestamp)
            except Exception:
                continue
            normalized_result = str(result).lower()
            if normalized_result == "win":
                wins += 1
            elif normalized_result in ("tie", "draw"):
                ties += 1
            else:
                losses += 1
            summary = bayesian_binomial_summary(wins, losses, ties)
            total = wins + losses + ties
            times.append(dt)
            observed.append(summary.get("observed", 0.0) * 100.0)
            bayes.append(summary["bayes_mean"] * 100.0)
            lows.append(summary["ci_low"] * 100.0)
            highs.append(summary["ci_high"] * 100.0)

        return times, observed, bayes, lows, highs

    def _create_deck_trend_card(self, analysis):
        card, layout = self._create_dashboard_card("WIN RATE OVER TIME")
        if not MATPLOTLIB_AVAILABLE:
            fallback = QLabel("Matplotlib is not available, so deck trend charts are disabled.")
            fallback.setObjectName("deckMetricNote")
            fallback.setWordWrap(True)
            layout.addWidget(fallback)
            return card

        times, observed, bayes, lows, highs = self._build_deck_trend_series(analysis.get("deck_name", ""))
        if not times:
            empty = QLabel("No battle history is available for this deck yet.")
            empty.setObjectName("deckMetricNote")
            layout.addWidget(empty)
            return card

        canvas = MplCanvas(self, width=7.0, height=3.1, dpi=90)
        canvas.setMinimumHeight(250)
        axes = canvas.axes
        axes.cla()
        axes.set_facecolor((0.04, 0.04, 0.04, 0.32))
        canvas.figure.patch.set_facecolor("none")
        canvas.figure.patch.set_alpha(0)

        axes.fill_between(times, lows, highs, alpha=0.12, color="#6BB6E8")
        axes.plot(times, bayes, color="#6BB6E8", linewidth=2.6, marker="o", markersize=4)
        axes.plot(times, observed, color="#9CC344", linewidth=1.6, linestyle="--", alpha=0.9)
        axes.axhline(y=50, color="#666666", linestyle="--", linewidth=1, alpha=0.35)
        axes.set_ylim(0, 100)
        axes.tick_params(colors="#8797AB", labelsize=8)
        axes.grid(True, alpha=0.08, color="#444444", linewidth=0.5)
        axes.spines["top"].set_visible(False)
        axes.spines["right"].set_visible(False)
        axes.spines["bottom"].set_color("#2a2a2a")
        axes.spines["left"].set_color("#2a2a2a")
        axes.spines["bottom"].set_linewidth(0.5)
        axes.spines["left"].set_linewidth(0.5)

        date_format = self._smart_time_format(times)
        if len(times) <= 5:
            tick_indices = list(range(len(times)))
        else:
            step = max(1, len(times) // 4)
            tick_indices = list(range(0, len(times), step))
            if tick_indices[-1] != len(times) - 1:
                tick_indices.append(len(times) - 1)

        tick_positions = [times[i] for i in tick_indices]
        tick_labels = [times[i].strftime(date_format) for i in tick_indices]
        axes.set_xticks(tick_positions)
        axes.set_xticklabels(tick_labels, rotation=35, ha="right")
        axes.set_yticks([0, 25, 50, 75, 100])
        axes.set_yticklabels(["0", "25", "50", "75", "100"])
        canvas.figure.subplots_adjust(left=0.08, right=0.98, top=0.96, bottom=0.22)
        canvas.draw()

        legend = QLabel("Blue = Bayesian trend  •  Green = observed cumulative win rate  •  Band = confidence interval")
        legend.setObjectName("deckMetricNote")
        legend.setWordWrap(True)
        layout.addWidget(canvas)
        layout.addWidget(legend)
        return card

    def _load_meta_cache(self, source):
        cache_file = os.path.join(BASE_DIR, f".meta_cache_{source}.json")
        if not os.path.exists(cache_file):
            return None
        try:
            with open(cache_file, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return None

    def _load_deck_icon_overrides(self):
        if not os.path.exists(DECK_ICON_OVERRIDE_FILE):
            return {}
        try:
            with open(DECK_ICON_OVERRIDE_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_deck_icon_overrides(self):
        try:
            with open(DECK_ICON_OVERRIDE_FILE, "w", encoding="utf-8") as handle:
                json.dump(self.deck_icon_overrides, handle, ensure_ascii=False, indent=2)
        except Exception:
            pass
        # Invalidate the cached icon choices since overrides changed.
        self._deck_icon_choices_cache = None

    def _deck_icon_choices(self):
        # Cache the computed choices so opening the icon picker repeatedly
        # doesn't re-scan the cache directory and re-iterate meta rows each time.
        if getattr(self, "_deck_icon_choices_cache", None) is not None:
            return self._deck_icon_choices_cache
        choices = set()
        for row in self._top_limitless_rows():
            for sprite_name in row.get("icons", []) or []:
                if sprite_name:
                    choices.add(sprite_name)
        if os.path.isdir(META_ICON_CACHE_DIR):
            for file_name in os.listdir(META_ICON_CACHE_DIR):
                if file_name.lower().endswith(".png"):
                    choices.add(file_name[:-4].replace("_", "/"))
        for icons in self.deck_icon_overrides.values():
            for sprite_name in icons or []:
                if sprite_name:
                    choices.add(sprite_name)
        self._deck_icon_choices_cache = sorted(choices)
        return self._deck_icon_choices_cache

    def _ensure_sprite_cached_local(self, sprite_name):
        return _fetch_sprite_to_cache(sprite_name)

    def _resolved_deck_icons(self, deck_name, matched_icons=None):
        override_icons = list((self.deck_icon_overrides.get(deck_name) or [])[:3])
        if override_icons:
            return override_icons
        icons = []
        seen = set()
        for sprite_name in (matched_icons or [])[:3]:
            if sprite_name and sprite_name not in seen:
                icons.append(sprite_name)
                seen.add(sprite_name)
        return icons

    def _top_limitless_rows(self, limit=None):
        rows = []
        if self.limitless_standard_meta:
            rows = list(self.limitless_standard_meta.get("rows", []))
        return rows[:limit] if limit else rows

    def _match_limitless_row(self, deck_name):
        return match_meta_row(deck_name, self._top_limitless_rows())

    def _field_benchmark_winrate(self, limit=10):
        rows = self._top_limitless_rows(limit)
        weight_total = sum(max(1, int(row.get("count", 0) or 0)) for row in rows)
        if not rows or weight_total <= 0:
            return None
        weighted = sum((float(row.get("win_pct", 0) or 0) / 100.0) * max(1, int(row.get("count", 0) or 0)) for row in rows)
        return (weighted / weight_total) * 100.0

    def _format_record_text(self, wins=0, losses=0, ties=0):
        wins = int(wins or 0)
        losses = int(losses or 0)
        ties = int(ties or 0)
        if ties > 0:
            return f"{wins}-{losses}-{ties}"
        return f"{wins}-{losses}"

    def _summarize_meta_record(self, row):
        wins = float(row.get("wins", 0) or 0)
        losses = float(row.get("losses", 0) or 0)
        ties = float(row.get("ties", 0) or 0)
        return bayesian_binomial_summary(wins, losses, ties)

    def _percent_accent(self, pct):
        if pct >= 55:
            return "#66BB6A"
        if pct >= 50:
            return "#4A9FD8"
        return "#EF5350"

    def _probability_accent(self, probability_pct):
        if probability_pct >= 65:
            return "#66BB6A"
        if probability_pct >= 45:
            return "#F9A825"
        return "#EF5350"

    def _delta_accent(self, delta):
        if delta is None:
            return "#AAB7CB"
        if delta >= 2:
            return "#66BB6A"
        if delta <= -2:
            return "#EF5350"
        return "#F9A825"

    def _deck_tab_label(self, deck_name):
        return deck_name if len(deck_name) <= 22 else f"{deck_name[:19]}..."

    def _icon_for_deck(self, deck_name, icons=None, size=20):
        for sprite_name in (icons or [])[:2]:
            pixmap = self._load_sprite_pixmap(sprite_name, size)
            if pixmap is not None:
                return QIcon(pixmap)
        return QIcon(self._build_placeholder_sprite(deck_name[:1] or "?", size))

    def _build_top_meta_matrix(self, matchup_entries, limit=8):
        aggregate = {}
        for entry in matchup_entries:
            meta_match = entry.get("matched_meta")
            if not meta_match or meta_match.get("rank", 999) > limit:
                continue
            meta_row = meta_match.get("row", {})
            key = meta_row.get("id") or meta_row.get("deck")
            if key not in aggregate:
                aggregate[key] = {
                    "games": 0,
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                }
            aggregate[key]["games"] += entry.get("games", 0)
            aggregate[key]["wins"] += entry.get("wins", 0)
            aggregate[key]["losses"] += entry.get("losses", 0)
            aggregate[key]["ties"] += entry.get("ties", 0)

        rows = []
        for meta_row in self._top_limitless_rows(limit):
            key = meta_row.get("id") or meta_row.get("deck")
            local = aggregate.get(key, {"games": 0, "wins": 0, "losses": 0, "ties": 0})
            summary = bayesian_binomial_summary(local["wins"], local["losses"], local["ties"])
            rows.append({
                "meta_row": meta_row,
                "games": local["games"],
                "wins": local["wins"],
                "losses": local["losses"],
                "ties": local["ties"],
                "summary": summary,
            })
        return rows

    def _build_deck_analysis(self, deck_name, games, wins, losses, ties=0):
        summary = bayesian_binomial_summary(wins, losses, ties)
        # Rank-weighted Elo win rate: weights each battle by the rank it was
        # played at, so high-rank results count more and sub-Masterball games
        # are heavily discounted.
        rank_battles = self.db.get_deck_battles_with_rank(deck_name)
        rank_summary = rank_weighted_winrate(rank_battles)
        matched_meta = self._match_limitless_row(deck_name)
        opponent_rows = self.db.get_deck_matchups(deck_name)
        matchup_entries = []
        for opponent_name, opp_games, opp_wins, opp_losses, opp_ties in opponent_rows:
            opp_summary = bayesian_binomial_summary(opp_wins, opp_losses, opp_ties)
            opp_meta = self._match_limitless_row(opponent_name)
            matchup_entries.append({
                "deck": opponent_name,
                "games": opp_games,
                "wins": opp_wins,
                "losses": opp_losses,
                "ties": opp_ties,
                "summary": opp_summary,
                "matched_meta": opp_meta,
            })

        top_meta_games = sum(
            entry["games"]
            for entry in matchup_entries
            if entry.get("matched_meta") and entry["matched_meta"].get("rank", 999) <= 10
        )
        field_benchmark = self._field_benchmark_winrate()
        matched_row = matched_meta.get("row") if matched_meta else None
        bayes_pct = summary["bayes_mean"] * 100.0
        delta_vs_meta = None
        if matched_row:
            delta_vs_meta = bayes_pct - float(matched_row.get("win_pct", 0) or 0)
        elif field_benchmark is not None:
            delta_vs_meta = bayes_pct - field_benchmark

        recent_battles = self.db.get_deck_recent_battles(deck_name, limit=6)
        deck_icons = self._resolved_deck_icons(deck_name, (matched_row or {}).get("icons", []))

        return {
            "deck_name": deck_name,
            "games": games,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "record": self._format_record_text(wins, losses, ties),
            "summary": summary,
            "rank_summary": rank_summary,
            "matchups": matchup_entries,
            "matched_meta": matched_meta,
            "deck_icons": deck_icons,
            "top_meta_matrix": self._build_top_meta_matrix(matchup_entries),
            "recent_battles": recent_battles,
            "field_benchmark": field_benchmark,
            "meta_exposure": (top_meta_games / games * 100.0) if games else 0.0,
            "delta_vs_meta": delta_vs_meta,
        }

    def _create_top_meta_table(self, analysis):
        table = self._make_meta_table(
            ["#", "Top Deck", "Meta Share", "Limitless WR", "Your Record", "Bayes WR"],
            [42, None, 88, 88, 86, 90],
        )
        row_links = []
        rows = analysis.get("top_meta_matrix", [])
        table.setRowCount(0)
        for row_index, entry in enumerate(rows):
            meta_row = entry.get("meta_row", {})
            summary = entry.get("summary", {})
            games = entry.get("games", 0)
            wins = entry.get("wins", 0)
            losses = entry.get("losses", 0)
            table.insertRow(row_index)
            table.setRowHeight(row_index, 42)
            self._set_meta_item(table, row_index, 0, str(row_index + 1))
            table.setCellWidget(
                row_index,
                1,
                self._create_deck_cell_widget(
                    meta_row.get("deck", ""),
                    meta_row.get("icons", []),
                    subtitle=f"{int(meta_row.get('count', 0) or 0)} finishes",
                ),
            )
            self._set_meta_item(table, row_index, 2, f"{float(meta_row.get('share', 0) or 0):.1f}%")
            meta_wr = float(meta_row.get("win_pct", 0) or 0)
            self._set_meta_item(table, row_index, 3, f"{meta_wr:.1f}%", accent=self._percent_accent(meta_wr))
            record_text = self._format_record_text(wins, losses, entry.get("ties", 0)) if games else "--"
            self._set_meta_item(table, row_index, 4, record_text, muted=games == 0)
            if games:
                local_wr = summary.get("bayes_mean", 0) * 100.0
                self._set_meta_item(table, row_index, 5, f"{local_wr:.1f}%", accent=self._percent_accent(local_wr))
            else:
                self._set_meta_item(table, row_index, 5, "--", muted=True)
            row_links.append(meta_row.get("deck_url"))

        table.cellDoubleClicked.connect(lambda row, col, links=row_links: self._open_row_link(links, row))
        return table

    def _create_matchup_table(self, analysis):
        table = self._make_meta_table(
            ["Opponent", "Games", "Record", "Bayes WR", "95% CI", "Current Meta"],
            [None, 64, 80, 86, 118, 120],
        )
        table.setRowCount(0)
        row_links = []

        rows = analysis.get("matchups", [])
        for row_index, entry in enumerate(rows[:14]):
            summary = entry.get("summary", {})
            bayes_pct = summary.get("bayes_mean", 0) * 100.0
            ci_low = summary.get("ci_low", 0) * 100.0
            ci_high = summary.get("ci_high", 0) * 100.0
            meta_match = entry.get("matched_meta")
            meta_row = meta_match.get("row", {}) if meta_match else {}
            meta_text = "Unmatched"
            if meta_match:
                meta_text = f"#{meta_match.get('rank')} • {float(meta_row.get('share', 0) or 0):.1f}%"

            table.insertRow(row_index)
            table.setRowHeight(row_index, 42)
            table.setCellWidget(
                row_index,
                0,
                self._create_deck_cell_widget(
                    entry.get("deck", ""),
                    meta_row.get("icons", []),
                    subtitle=self._format_record_text(
                        entry.get("wins", 0),
                        entry.get("losses", 0),
                        entry.get("ties", 0),
                    ),
                ),
            )
            self._set_meta_item(table, row_index, 1, str(entry.get("games", 0)))
            self._set_meta_item(
                table,
                row_index,
                2,
                self._format_record_text(entry.get("wins", 0), entry.get("losses", 0), entry.get("ties", 0)),
            )
            self._set_meta_item(table, row_index, 3, f"{bayes_pct:.1f}%", accent=self._percent_accent(bayes_pct))
            self._set_meta_item(table, row_index, 4, f"{ci_low:.0f}% - {ci_high:.0f}%")
            self._set_meta_item(table, row_index, 5, meta_text, muted=not meta_match)
            row_links.append(meta_row.get("deck_url"))

        table.cellDoubleClicked.connect(lambda row, col, links=row_links: self._open_row_link(links, row))
        return table

    def _create_recent_deck_battles_card(self, analysis):
        card, layout = self._create_dashboard_card("RECENT WITH THIS DECK")
        recent = analysis.get("recent_battles", [])
        if not recent:
            empty = QLabel("No recent battles logged with this deck yet.")
            empty.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 10px; font-style: italic;")
            layout.addWidget(empty)
            return card

        for timestamp, my_deck, opp_deck, result, my_rank, log_file, is_tournament in recent:
            row = ClickableFrame() if log_file else QFrame()
            row.setObjectName("deckRecentBattleRow")
            if log_file:
                row.setCursor(Qt.CursorShape.PointingHandCursor)
                row.setToolTip(
                    f"Open this battle in PTCGL Replay: {os.path.basename(log_file) if log_file else 'N/A'}"
                )
                row.clicked.connect(lambda lf=log_file: self.open_battle_replay(lf))
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 6, 10, 6)
            row_layout.setSpacing(10)

            indicator = QFrame()
            indicator.setFixedSize(5, 20)
            color = "#66BB6A" if result == "Win" else "#EF5350"
            indicator.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
            row_layout.addWidget(indicator)

            info = QVBoxLayout()
            info.setContentsMargins(0, 0, 0, 0)
            info.setSpacing(1)

            title = QLabel(f"vs {opp_deck}")
            title.setStyleSheet("color: rgba(255,255,255,0.92); font-size: 11px; font-weight: 600;")
            info.addWidget(title)

            stamp = QLabel(f"{timestamp} • {result}")
            stamp.setStyleSheet("color: rgba(168,182,204,0.78); font-size: 9px;")
            info.addWidget(stamp)

            row_layout.addLayout(info)
            if is_tournament:
                tourney_tag = QLabel("Limitless Tournament")
                tourney_tag.setStyleSheet("""
                    QLabel {
                        color: #FFD54F;
                        background-color: rgba(255, 213, 79, 0.12);
                        border: 1px solid rgba(255, 213, 79, 0.45);
                        border-radius: 3px;
                        font-size: 8px;
                        font-weight: 600;
                        padding: 1px 5px;
                    }
                """)
                row_layout.addWidget(tourney_tag)
            row_layout.addStretch()
            layout.addWidget(row)

        return card

    def _create_deck_dashboard_page(self, analysis):
        scroll = PageScrollArea()

        content = QWidget()
        content.setObjectName("contentWidget")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 10)
        layout.setSpacing(8)

        matched_meta = analysis.get("matched_meta")
        matched_row = matched_meta.get("row") if matched_meta else {}
        deck_icons = analysis.get("deck_icons", [])
        summary = analysis.get("summary", {})
        bayes_pct = summary.get("bayes_mean", 0) * 100.0
        delta_vs_meta = analysis.get("delta_vs_meta")
        field_benchmark = analysis.get("field_benchmark")

        hero_card, hero_layout = self._create_dashboard_card("DECK SNAPSHOT")
        hero_top = QHBoxLayout()
        hero_top.setContentsMargins(0, 0, 0, 0)
        hero_top.setSpacing(10)
        title_wrap = QWidget()
        title_layout = QHBoxLayout(title_wrap)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(10)

        icon_column = QWidget()
        icon_column_layout = QVBoxLayout(icon_column)
        icon_column_layout.setContentsMargins(0, 0, 0, 0)
        icon_column_layout.setSpacing(2)

        icon_row_wrap = QWidget()
        icon_row_layout = QHBoxLayout(icon_row_wrap)
        icon_row_layout.setContentsMargins(0, 0, 0, 0)
        icon_row_layout.setSpacing(3)
        for sprite_name in deck_icons[:3]:
            icon_label = QLabel()
            icon_pixmap = self._load_sprite_pixmap(sprite_name, 38)
            if icon_pixmap is None:
                icon_pixmap = self._build_placeholder_sprite(sprite_name[:1] or analysis.get("deck_name", "")[:1], 38)
            icon_label.setPixmap(icon_pixmap)
            icon_label.setFixedSize(40, 40)
            icon_row_layout.addWidget(icon_label)
        if icon_row_layout.count() == 0:
            fallback = QLabel()
            fallback.setPixmap(self._build_placeholder_sprite(analysis.get("deck_name", "")[:1], 38))
            fallback.setFixedSize(40, 40)
            icon_row_layout.addWidget(fallback)
        icon_column_layout.addWidget(icon_row_wrap, alignment=Qt.AlignmentFlag.AlignLeft)

        icon_btn = QToolButton()
        icon_btn.setObjectName("deckIconArrowBtn")
        icon_btn.setText("▾")
        icon_btn.setToolTip("Choose deck icons")
        icon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        icon_btn.clicked.connect(lambda checked=False, deck_name=analysis.get("deck_name", ""): self._choose_deck_icon(deck_name))
        icon_column_layout.addWidget(icon_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        title_layout.addWidget(icon_column)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        deck_title = QLabel(analysis.get("deck_name", ""))
        deck_title.setObjectName("deckPageTitle")
        text_col.addWidget(deck_title)

        record_label = QLabel(f"{analysis.get('record')} across {analysis.get('games')} games")
        record_label.setObjectName("deckPageSubtitle")
        text_col.addWidget(record_label)
        title_layout.addLayout(text_col)
        hero_top.addWidget(title_wrap)
        hero_top.addStretch()
        if matched_row.get("deck_url"):
            open_btn = QPushButton("Limitless ↗")
            open_btn.setObjectName("limitlessBtn")
            open_btn.setFixedHeight(30)
            open_btn.clicked.connect(lambda checked=False, url=matched_row.get("deck_url"): webbrowser.open(url))
            hero_top.addWidget(open_btn)
        hero_layout.addLayout(hero_top)

        if matched_meta:
            comparison_text = (
                f"Matched to Limitless archetype #{matched_meta.get('rank')} by current share. "
                f"Limitless shows {float(matched_row.get('win_pct', 0) or 0):.1f}% adjusted WR "
                f"from {self._format_record_text(matched_row.get('wins', 0), matched_row.get('losses', 0), matched_row.get('ties', 0))} "
                f"with {float(matched_row.get('share', 0) or 0):.1f}% meta share. "
                f"Your Bayesian estimate is {bayes_pct:.1f}% ({delta_vs_meta:+.1f} pts). "
                f"{summary.get('confidence_note')}"
            )
        else:
            field_note = f"{field_benchmark:.1f}%" if field_benchmark is not None else "N/A"
            comparison_text = f"No direct Limitless archetype match was found for this deck name. "
            if delta_vs_meta is not None:
                comparison_text += (
                    f"Using the current top-field benchmark of {field_note}, "
                    f"your Bayesian estimate is {bayes_pct:.1f}% ({delta_vs_meta:+.1f} pts vs field). "
                )
            comparison_text += summary.get("confidence_note")

        insight = QLabel(comparison_text)
        insight.setObjectName("deckInsightText")
        insight.setWordWrap(True)
        hero_layout.addWidget(insight)
        hero_layout.addWidget(self._create_deck_visual_metrics(analysis))
        layout.addWidget(hero_card)

        layout.addWidget(self._create_deck_trend_card(analysis))

        benchmark_card, benchmark_layout = self._create_dashboard_card("TOP META BENCHMARK")
        benchmark_layout.addWidget(self._create_top_meta_table(analysis))
        layout.addWidget(benchmark_card)

        matchup_card, matchup_layout = self._create_dashboard_card("OBSERVED MATCHUPS")
        matchup_layout.addWidget(self._create_matchup_table(analysis))
        layout.addWidget(matchup_card)

        layout.addWidget(self._create_recent_deck_battles_card(analysis))
        layout.addStretch()

        scroll.setWidget(content)
        return scroll

    def _refresh_deck_dashboards(self, deck_analyses=None):
        if not hasattr(self, "deck_tabs"):
            return

        deck_analyses = deck_analyses if deck_analyses is not None else self.deck_analyses
        current_name = None
        prior_scrolls = {}
        if self.deck_tabs.count() and self.deck_tabs.currentIndex() >= 0:
            current_name = self.deck_tabs.tabBar().tabToolTip(self.deck_tabs.currentIndex()) or self.deck_tabs.tabText(self.deck_tabs.currentIndex())
            for index in range(self.deck_tabs.count()):
                deck_name = self.deck_tabs.tabBar().tabToolTip(index) or self.deck_tabs.tabText(index)
                widget = self.deck_tabs.widget(index)
                if deck_name and widget is not None and hasattr(widget, "verticalScrollBar"):
                    try:
                        prior_scrolls[deck_name] = widget.verticalScrollBar().value()
                    except Exception:
                        pass

        while self.deck_tabs.count():
            widget = self.deck_tabs.widget(0)
            self.deck_tabs.removeTab(0)
            if widget is not None:
                widget.deleteLater()

        self.deck_tab_lookup = {}

        if not deck_analyses:
            placeholder = QWidget()
            placeholder_layout = QVBoxLayout(placeholder)
            placeholder_layout.setContentsMargins(16, 16, 16, 16)
            label = QLabel("No deck data yet. Play a few matches and each deck will get its own dashboard here.")
            label.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 11px; font-style: italic;")
            label.setWordWrap(True)
            placeholder_layout.addWidget(label)
            placeholder_layout.addStretch()
            self.deck_tabs.addTab(placeholder, "No Data")
            return

        for analysis in deck_analyses:
            page = self._create_deck_dashboard_page(analysis)
            icon = self._icon_for_deck(analysis.get("deck_name", ""), analysis.get("deck_icons", []), size=18)
            idx = self.deck_tabs.addTab(page, icon, self._deck_tab_label(analysis.get("deck_name", "")))
            full_name = analysis.get("deck_name", "")
            self.deck_tabs.tabBar().setTabToolTip(idx, full_name)
            self.deck_tab_lookup[full_name] = idx

        if current_name in self.deck_tab_lookup:
            self.deck_tabs.setCurrentIndex(self.deck_tab_lookup[current_name])
        for deck_name, scroll_value in prior_scrolls.items():
            idx = self.deck_tab_lookup.get(deck_name)
            if idx is None:
                continue
            widget = self.deck_tabs.widget(idx)
            if widget is not None and hasattr(widget, "verticalScrollBar"):
                QTimer.singleShot(0, lambda w=widget, v=scroll_value: self._restore_scroll_value(w, v))

        self._deck_dashboards_dirty = False

    def _refresh_decks_meta(self, force=False):
        if not REQUESTS_AVAILABLE:
            return
        if hasattr(self, "_decks_meta_fetcher") and self._decks_meta_fetcher.isRunning():
            return

        self._decks_meta_fetcher = MetaFetcher("limitless_standard")
        self._decks_meta_fetcher.data_ready.connect(self._on_decks_meta_data)
        self._decks_meta_fetcher.error.connect(self._on_decks_meta_error)
        self._decks_meta_fetcher.start()

    def _on_decks_meta_data(self, source, data):
        self.limitless_standard_meta = data
        self._deck_dashboards_dirty = True
        if hasattr(self, "tab_widget") and self.tab_widget.currentIndex() == getattr(self, "decks_tab_index", -1):
            self._refresh_deck_dashboards()

    def _on_decks_meta_error(self, source, message):
        print(f"Deck meta refresh failed: {message}")

    def open_deck_dashboard(self, deck_name):
        if not hasattr(self, "deck_tabs"):
            return
        if deck_name not in self.deck_tab_lookup:
            return
        if hasattr(self, "decks_tab_index"):
            self.tab_widget.setCurrentIndex(self.decks_tab_index)
        self.deck_tabs.setCurrentIndex(self.deck_tab_lookup[deck_name])

    def create_replay_tab(self):
        outer = QWidget()
        outer.setObjectName("contentWidget")
        vlayout = QVBoxLayout(outer)
        vlayout.setContentsMargins(12, 12, 12, 12)
        vlayout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        title = QLabel("PTCGL REPLAY")
        title.setObjectName("sectionHeader")
        header_row.addWidget(title)

        header_row.addStretch()

        self.replay_status_label = QLabel("Click any battle row to load its log here.")
        self.replay_status_label.setStyleSheet("color: rgba(255,255,255,0.42); font-size: 10px;")
        header_row.addWidget(self.replay_status_label)

        open_browser_btn = QPushButton("Replay ↗")
        open_browser_btn.setObjectName("limitlessBtn")
        open_browser_btn.setFixedHeight(30)
        open_browser_btn.clicked.connect(self.open_replay_in_browser)
        header_row.addWidget(open_browser_btn)

        vlayout.addLayout(header_row)

        if WEBENGINE_AVAILABLE:
            self.replay_view = QWebEngineView()
            self.replay_view.setMinimumHeight(420)
            self.replay_profile = None
            self.replay_page = None
            self._rebuild_replay_page()
            self.replay_view.load(QUrl(PTCGL_REPLAY_URL))
            vlayout.addWidget(self.replay_view, stretch=1)
        else:
            self.replay_view = None
            self.replay_profile = None
            self.replay_page = None
            fallback = QLabel("Qt WebEngine is not available. Replay loading will fall back to your browser.")
            fallback.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 11px; font-style: italic;")
            fallback.setWordWrap(True)
            vlayout.addWidget(fallback)
            vlayout.addStretch()

        return outer

    def _create_replay_profile(self):
        profile = QWebEngineProfile(self)
        try:
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        except Exception:
            pass
        try:
            profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
            )
        except Exception:
            pass
        try:
            profile.setHttpUserAgent("TCGLiveMonitor/2.3 Replay")
        except Exception:
            pass
        return profile

    def _rebuild_replay_page(self):
        if not WEBENGINE_AVAILABLE or getattr(self, "replay_view", None) is None:
            return

        old_page = getattr(self, "replay_page", None)
        old_profile = getattr(self, "replay_profile", None)

        try:
            self.replay_view.stop()
        except Exception:
            pass

        if old_page is not None:
            try:
                old_page.loadFinished.disconnect(self._on_replay_page_load_finished)
            except Exception:
                pass
            try:
                old_page.upload_requested.disconnect(self._on_replay_upload_requested)
            except Exception:
                pass

        self.replay_profile = self._create_replay_profile()
        self.replay_page = ReplayWebPage(self.replay_profile, self.replay_view)
        try:
            self.replay_page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            self.replay_page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        except Exception:
            pass
        self.replay_page.loadFinished.connect(self._on_replay_page_load_finished)
        self.replay_page.upload_requested.connect(self._on_replay_upload_requested)
        self.replay_view.setPage(self.replay_page)

        if old_page is not None:
            try:
                old_page.deleteLater()
            except Exception:
                pass
        if old_profile is not None:
            try:
                old_profile.deleteLater()
            except Exception:
                pass

    def _on_replay_upload_requested(self, chosen_path):
        if chosen_path:
            self.replay_status_label.setText(f"Supplying {os.path.basename(chosen_path)} to replay…")
        else:
            self.replay_status_label.setText("Replay requested a file chooser, but no queued battle log was available.")

    def _on_replay_page_load_finished(self, ok):
        if self.sender() is not self.replay_page:
            return
        if not ok or not self.replay_pending_log_path or not self.replay_page:
            return
        current_url = self.replay_page.url().toString()
        if "ptcglreplay.com" not in current_url:
            return
        self.replay_page.queue_upload(self.replay_pending_log_path)
        self._inject_replay_log_via_dom(self.replay_pending_log_path, self._replay_request_token)

    def _inject_replay_log_via_dom(self, log_file_path, request_token=None):
        if not self.replay_page or not log_file_path:
            return
        if request_token is not None and request_token != self._replay_request_token:
            return
        try:
            with open(log_file_path, "r", encoding="utf-8", errors="replace") as handle:
                log_text = handle.read()
        except Exception as e:
            self.replay_status_label.setText(f"Could not read battle log: {e}")
            return

        payload_json = json.dumps(
            {
                "fileName": os.path.basename(log_file_path),
                "fileContent": log_text,
            },
            ensure_ascii=False,
        )
        self.replay_status_label.setText(f"Injecting {os.path.basename(log_file_path)} into replay…")
        js = f"""
            (() => {{
                const payload = {payload_json};
                const input = document.querySelector('input[type="file"][accept=".txt"]');
                if (!input) {{
                    return JSON.stringify({{ status: "missing-input" }});
                }}
                const zone = input.parentElement?.closest('[class*="cursor-pointer"]') || input.parentElement;
                try {{
                    const file = new File([payload.fileContent], payload.fileName, {{ type: "text/plain" }});
                    const dt = new DataTransfer();
                    dt.items.add(file);
                    let assigned = false;
                    try {{
                        input.files = dt.files;
                        assigned = !!(input.files && input.files.length);
                    }} catch (assignError) {{}}
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    if (zone) {{
                        try {{
                            zone.dispatchEvent(new DragEvent('drop', {{
                                bubbles: true,
                                cancelable: true,
                                dataTransfer: dt
                            }}));
                        }} catch (dropError) {{}}
                    }}
                    return JSON.stringify({{
                        status: "injected",
                        assigned,
                        fileCount: input.files ? input.files.length : -1,
                        fileSize: file.size
                    }});
                }} catch (error) {{
                    return JSON.stringify({{
                        status: "error",
                        message: String(error)
                    }});
                }}
            }})();
        """
        self.replay_page.runJavaScript(
            js,
            lambda result, token=request_token: self._handle_replay_dom_injection_result(result, token),
        )

    def _handle_replay_dom_injection_result(self, result, request_token=None):
        if request_token is not None and request_token != self._replay_request_token:
            return
        payload = None
        if isinstance(result, str):
            try:
                payload = json.loads(result)
            except Exception:
                payload = {"status": "raw", "value": result}
        elif isinstance(result, dict):
            payload = result
        else:
            payload = {"status": "invalid", "value": str(result)}

        status = payload.get("status")
        if status == "missing-input":
            self.replay_status_label.setText("Replay page loaded, but its upload input was not found.")
            return
        if status == "error":
            self.replay_status_label.setText(f"Replay import injection failed: {payload.get('message', 'unknown error')}")
            return
        if status != "injected":
            self.replay_status_label.setText(f"Replay import did not complete ({payload.get('value', status)}).")
            return

        file_name = os.path.basename(self.replay_pending_log_path) if self.replay_pending_log_path else "battle log"
        assigned = bool(payload.get("assigned"))
        self.replay_status_label.setText(
            f"Injected {file_name} into replay{' (input populated)' if assigned else ''}."
        )
        QTimer.singleShot(1200, lambda token=request_token: self._verify_replay_loaded(token))

    def _verify_replay_loaded(self, request_token=None):
        if request_token is not None and request_token != self._replay_request_token:
            return
        if not self.replay_page:
            return
        js = """
            (() => JSON.stringify({
                hasActionLog: document.body.innerText.includes("ACTION LOG"),
                hasUploadPrompt: document.body.innerText.includes("drag and drop your battle log")
            }))();
        """
        self.replay_page.runJavaScript(
            js,
            lambda result, token=request_token: self._handle_replay_loaded_check(result, token),
        )

    def _handle_replay_loaded_check(self, result, request_token=None):
        if request_token is not None and request_token != self._replay_request_token:
            return
        payload = {}
        if isinstance(result, str):
            try:
                payload = json.loads(result)
            except Exception:
                payload = {}
        elif isinstance(result, dict):
            payload = result
        if payload.get("hasActionLog"):
            file_name = os.path.basename(self.replay_pending_log_path) if self.replay_pending_log_path else "battle log"
            self.replay_status_label.setText(f"Replay loaded successfully for {file_name}.")
        elif payload.get("hasUploadPrompt"):
            self.replay_status_label.setText("Replay import was attempted, but the site still shows the upload prompt.")

    def open_replay_in_browser(self):
        current_log_path = self.replay_pending_log_path
        if not current_log_path or not os.path.exists(current_log_path):
            webbrowser.open(PTCGL_REPLAY_URL)
            return

        if self.replay_page:
            js = """
                (() => JSON.stringify((() => {
                    const text = document.body.innerText || "";
                    const match = text.match(/ACTION\\s+(\\d+)/);
                    return {
                        actionIndex: match ? Number(match[1]) : 0,
                        hasActionLog: text.includes("ACTION LOG")
                    };
                })()))();
            """
            self.replay_page.runJavaScript(
                js,
                lambda result, path=current_log_path: self._open_replay_in_browser_with_state(path, result),
            )
            return

        self._open_replay_in_browser_with_state(current_log_path, None)

    def _open_replay_in_browser_with_state(self, log_file_path, state_result):
        action_index = 0
        if isinstance(state_result, str):
            try:
                payload = json.loads(state_result)
            except Exception:
                payload = {}
        elif isinstance(state_result, dict):
            payload = state_result
        else:
            payload = {}

        try:
            action_index = max(0, int(payload.get("actionIndex", 0) or 0))
        except Exception:
            action_index = 0

        self.replay_status_label.setText(
            f"Opening browser replay from {os.path.basename(log_file_path)} at action {action_index}."
        )

        def worker():
            try:
                self._launch_ptcgl_replay_browser(log_file_path, headless=False, action_index=action_index)
            except Exception as e:
                print(f"Error opening browser replay with preserved state: {e}")
                try:
                    self._launch_ptcgl_replay_helper(log_file_path, headless=False, action_index=action_index)
                except Exception as helper_error:
                    print(f"Replay browser helper fallback failed: {helper_error}")
                    try:
                        webbrowser.open(PTCGL_REPLAY_URL)
                    except Exception:
                        pass

        threading.Thread(target=worker, daemon=True).start()
    
    def create_settings_tab(self):
        """Create settings/advanced tab with debug controls"""
        scroll = self._create_standard_scroll_area()
        self.settings_scroll = scroll
        
        content = QWidget()
        content.setObjectName("contentWidget")
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Debugging Section
        debug_card = self.create_card("Debugging & Development")
        debug_layout = QVBoxLayout()
        debug_layout.setSpacing(8)
        debug_layout.setContentsMargins(12, 8, 12, 12)
        
        # Hide/Show Console button
        self.console_btn = QPushButton("Hide Console Window")
        self.console_btn.setObjectName("settingsBtn")
        self.console_btn.setFixedHeight(40)
        self.console_btn.clicked.connect(self.toggle_console)
        debug_layout.addWidget(self.console_btn)

        refresh_console_btn = QPushButton("Re-scan Monitor Console")
        refresh_console_btn.setObjectName("settingsBtn")
        refresh_console_btn.setFixedHeight(36)
        refresh_console_btn.clicked.connect(self.check_console_availability)
        debug_layout.addWidget(refresh_console_btn)
        
        # OCR Test Window button
        ocr_test_btn = QPushButton("Open OCR Test Window")
        ocr_test_btn.setObjectName("settingsBtn")
        ocr_test_btn.setFixedHeight(40)
        ocr_test_btn.clicked.connect(self.launch_ocr_test)
        debug_layout.addWidget(ocr_test_btn)
        
        # Run AI Parse button
        ai_parse_btn = QPushButton("Run AI Battle Log Parser")
        ai_parse_btn.setObjectName("settingsBtn")
        ai_parse_btn.setFixedHeight(40)
        ai_parse_btn.clicked.connect(self.launch_ai_parser)
        debug_layout.addWidget(ai_parse_btn)

        open_logs_btn = QPushButton("Open Logs Folder")
        open_logs_btn.setObjectName("settingsBtn")
        open_logs_btn.setFixedHeight(36)
        open_logs_btn.clicked.connect(self.open_logs_folder)
        debug_layout.addWidget(open_logs_btn)

        self.debug_status_label = QLabel("")
        self.debug_status_label.setObjectName("settingsDesc")
        self.debug_status_label.setWordWrap(True)
        debug_layout.addWidget(self.debug_status_label)

        # Check console availability on startup
        self.check_console_availability()
        
        desc = QLabel("Quick access to development tools and debugging features")
        desc.setObjectName("settingsDesc")
        desc.setWordWrap(True)
        debug_layout.addWidget(desc)
        
        debug_card.layout().addLayout(debug_layout)
        layout.addWidget(debug_card)

        # AI / Local Parsing Section
        parser_card = self.create_card("AI Parsing Mode")
        parser_layout = QVBoxLayout()
        parser_layout.setSpacing(8)
        parser_layout.setContentsMargins(12, 8, 12, 12)

        self.api_key_input = QLineEdit()
        self.api_key_input.setObjectName("metaSearch")
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("OpenAI API key")
        self.api_key_input.setText(load_api_key() or "")
        parser_layout.addWidget(self.api_key_input)

        self.show_api_key_toggle = QCheckBox("Show API key")
        self.show_api_key_toggle.setObjectName("settingsCheck")
        self.show_api_key_toggle.toggled.connect(
            lambda checked: self.api_key_input.setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )
        )
        parser_layout.addWidget(self.show_api_key_toggle)

        self.local_only_checkbox = QCheckBox("Enable local-only parsing fallback")
        self.local_only_checkbox.setObjectName("settingsCheck")
        self.local_only_checkbox.setChecked(bool(self.app_settings.get("local_only_mode", False)))
        self.local_only_checkbox.toggled.connect(lambda checked: self.refresh_parser_mode_status())
        parser_layout.addWidget(self.local_only_checkbox)

        parser_btn_row = QHBoxLayout()
        parser_btn_row.setSpacing(8)

        save_parser_btn = QPushButton("Save Parser Settings")
        save_parser_btn.setObjectName("settingsBtn")
        save_parser_btn.setFixedHeight(38)
        save_parser_btn.clicked.connect(self.save_parser_settings)
        parser_btn_row.addWidget(save_parser_btn)

        clear_key_btn = QPushButton("Clear API Key")
        clear_key_btn.setObjectName("settingsBtn")
        clear_key_btn.setFixedHeight(38)
        clear_key_btn.clicked.connect(self.clear_parser_api_key)
        parser_btn_row.addWidget(clear_key_btn)

        parser_layout.addLayout(parser_btn_row)

        self.parser_mode_status_label = QLabel("")
        self.parser_mode_status_label.setObjectName("settingsDesc")
        self.parser_mode_status_label.setWordWrap(True)
        parser_layout.addWidget(self.parser_mode_status_label)

        parser_desc = QLabel(
            "When local-only mode is enabled, or no API key is available, battle parsing falls back to OCR/manual flow. "
            "The parser will use your last OCR-detected deck and ask for the opponent deck name."
        )
        parser_desc.setObjectName("settingsDesc")
        parser_desc.setWordWrap(True)
        parser_layout.addWidget(parser_desc)

        parser_card.layout().addLayout(parser_layout)
        layout.addWidget(parser_card)
        self.refresh_parser_mode_status()
        
        # AutoRun Section
        autorun_card = self.create_card("AutoRun Configuration")
        autorun_layout = QVBoxLayout()
        autorun_layout.setSpacing(8)
        autorun_layout.setContentsMargins(12, 8, 12, 12)
        
        add_autorun_btn = QPushButton("Add to Windows Startup")
        add_autorun_btn.setObjectName("settingsBtn")
        add_autorun_btn.setFixedHeight(40)
        add_autorun_btn.clicked.connect(self.add_autorun)
        autorun_layout.addWidget(add_autorun_btn)
        
        remove_autorun_btn = QPushButton("Remove from Windows Startup")
        remove_autorun_btn.setObjectName("settingsBtn")
        remove_autorun_btn.setFixedHeight(40)
        remove_autorun_btn.clicked.connect(self.remove_autorun)
        autorun_layout.addWidget(remove_autorun_btn)
        
        autorun_desc = QLabel("Configure one-click Windows startup in headless mode (no console window)")
        autorun_desc.setObjectName("settingsDesc")
        autorun_desc.setWordWrap(True)
        autorun_layout.addWidget(autorun_desc)
        
        autorun_card.layout().addLayout(autorun_layout)
        layout.addWidget(autorun_card)
        
        # Battle Management Section
        battle_mgmt_card = self.create_card("Battle Database Management")
        battle_mgmt_layout = QVBoxLayout()
        battle_mgmt_layout.setSpacing(8)
        battle_mgmt_layout.setContentsMargins(12, 8, 12, 12)
        
        # Recent battles list
        battles_label = QLabel("Recent Battles (Last 20)")
        battles_label.setStyleSheet("color: rgba(255, 255, 255, 0.8); font-size: 11px; font-weight: 600; margin-top: 4px;")
        battle_mgmt_layout.addWidget(battles_label)
        
        self.battle_mgmt_table = self._make_meta_table(
            ["Time", "My Deck", "Opponent", "Result", "Rank", "Confidence", "Source", "Log", "Tournament", "", ""],
            [150, 120, 150, 74, 60, 80, 70, 80, 80, 100, 100],
            sortable=False,
            stretch_last=False,
        )
        self.battle_mgmt_table.setFixedHeight(320)
        self.battle_mgmt_table.setEditTriggers(
            QTableWidget.EditTrigger.CurrentChanged
            | QTableWidget.EditTrigger.SelectedClicked
            | QTableWidget.EditTrigger.EditKeyPressed
        )
        self.battle_mgmt_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.battle_mgmt_table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Use fixed widths for every column so the action buttons (Replay /
        # Delete) always have enough room and are never squeezed by stretch
        # columns. Only the "My Deck" and "Opponent" columns stretch to fill
        # leftover space.
        header = self.battle_mgmt_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.battle_mgmt_table.verticalHeader().setDefaultSectionSize(36)
        self.battle_mgmt_table.cellClicked.connect(self._handle_battle_mgmt_cell_clicked)
        self.battle_mgmt_table.itemChanged.connect(self._handle_battle_mgmt_item_changed)
        battle_mgmt_layout.addWidget(self.battle_mgmt_table)
        
        # Refresh button
        refresh_battles_btn = QPushButton("Refresh Battle List")
        refresh_battles_btn.setObjectName("settingsBtn")
        refresh_battles_btn.setFixedHeight(35)
        refresh_battles_btn.clicked.connect(self.refresh_battle_management)
        battle_mgmt_layout.addWidget(refresh_battles_btn)
        
        self.battle_mgmt_status_label = QLabel("Click a field to edit it. Changes save automatically.")
        self.battle_mgmt_status_label.setObjectName("settingsDesc")
        self.battle_mgmt_status_label.setWordWrap(True)
        battle_mgmt_layout.addWidget(self.battle_mgmt_status_label)
        
        battle_mgmt_card.layout().addLayout(battle_mgmt_layout)
        layout.addWidget(battle_mgmt_card)
        
        # Load initial battles
        self.refresh_battle_management()
        
        # Application Control Section
        app_control_card = self.create_card("Application Control")
        app_control_layout = QVBoxLayout()
        app_control_layout.setSpacing(8)
        app_control_layout.setContentsMargins(12, 8, 12, 12)
        
        # Close Application button
        close_app_btn = QPushButton("Close Application")
        close_app_btn.setObjectName("closeAppBtn")
        close_app_btn.setFixedHeight(45)
        close_app_btn.setStyleSheet("""
            QPushButton#closeAppBtn {
                background-color: rgba(239, 83, 80, 0.15);
                color: #EF5350;
                border: 1px solid rgba(239, 83, 80, 0.3);
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#closeAppBtn:hover {
                background-color: rgba(239, 83, 80, 0.25);
                border: 1px solid rgba(239, 83, 80, 0.5);
            }
            QPushButton#closeAppBtn:pressed {
                background-color: rgba(239, 83, 80, 0.35);
            }
        """)
        close_app_btn.clicked.connect(self.close_application)
        app_control_layout.addWidget(close_app_btn)
        
        app_control_desc = QLabel("Completely close the Stats Dashboard and Overlay")
        app_control_desc.setObjectName("settingsDesc")
        app_control_desc.setWordWrap(True)
        app_control_layout.addWidget(app_control_desc)
        
        app_control_card.layout().addLayout(app_control_layout)
        layout.addWidget(app_control_card)
        
        layout.addStretch()
        
        scroll.setWidget(content)
        return scroll
    
    def create_support_tab(self):
        """Create support tab with Buy Me a Coffee"""
        content = QWidget()
        content.setObjectName("contentWidget")
        layout = QVBoxLayout(content)
        layout.setSpacing(16)
        layout.setContentsMargins(12, 12, 12, 12)
        
        layout.addStretch()
        
        # Support header
        header = QLabel("Support Development")
        header.setStyleSheet("color: rgba(255, 255, 255, 0.95); font-size: 24px; font-weight: 600;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)
        
        # Description
        desc = QLabel("If you enjoy using this tool and want to support its development,\nconsider buying me a coffee!")
        desc.setStyleSheet("color: rgba(255, 255, 255, 0.7); font-size: 13px; line-height: 1.5;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        # Buy Me a Coffee button
        coffee_btn = QPushButton("Buy Me a Coffee")
        coffee_btn.setObjectName("coffeeBtn")
        coffee_btn.setFixedHeight(50)
        coffee_btn.setFixedWidth(250)
        coffee_btn.clicked.connect(lambda: webbrowser.open("https://www.buymeacoffee.com/lavahawk"))
        layout.addWidget(coffee_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Thank you message
        thanks = QLabel("Thank you for your support! 💙")
        thanks.setStyleSheet("color: rgba(255, 255, 255, 0.5); font-size: 12px; font-style: italic;")
        thanks.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(thanks)
        
        layout.addStretch()
        
        return content
    
    # ─── META ANALYSIS TABS ─────────────────────────────────────────────────

    def _make_meta_table(self, columns, col_widths=None, *, sortable=False, stretch_last=True):
        """Helper: build a styled QTableWidget for meta data."""
        table = QTableWidget()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.setShowGrid(False)
        table.setAlternatingRowColors(False)
        table.horizontalHeader().setStretchLastSection(stretch_last)
        # Center the column headings for a cleaner look.
        table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
        # Default: fit every column to its content so names are never cut off.
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setWordWrap(False)
        table.setSortingEnabled(sortable)
        if col_widths:
            for i, w in enumerate(col_widths):
                if w:
                    table.setColumnWidth(i, w)
        table.setStyleSheet("""
            QTableWidget {
                background-color: rgba(7, 11, 18, 0.88);
                alternate-background-color: rgba(9, 14, 22, 0.88);
                color: rgba(236,242,252,0.92);
                font-size: 11px;
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 8px;
                gridline-color: transparent;
                selection-background-color: rgba(74,159,216,0.18);
            }
            QTableWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid rgba(255,255,255,0.04);
                background-color: transparent;
            }
            QTableWidget::item:selected {
                background-color: rgba(74,159,216,0.18);
                color: white;
            }
            QHeaderView::section {
                background-color: rgba(16, 24, 36, 0.98);
                color: rgba(214,225,240,0.76);
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1px;
                padding: 8px 10px;
                border: none;
                border-bottom: 1px solid rgba(255,255,255,0.08);
            }
        """)
        return table

    def _create_meta_stats_bar(self, metrics):
        bar = QFrame()
        bar.setObjectName("metaStatsBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        value_labels = {}
        for key, title in metrics:
            card = QFrame()
            card.setObjectName("metaStatCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(2)

            value = QLabel("--")
            value.setObjectName("metaStatValue")
            label = QLabel(title)
            label.setObjectName("metaStatTitle")

            card_layout.addWidget(value)
            card_layout.addWidget(label)
            layout.addWidget(card)
            value_labels[key] = value

        return bar, value_labels

    def _load_sprite_pixmap(self, sprite_name, size=24):
        if not sprite_name:
            return None
        cache_key = (sprite_name, size)
        cached = self._sprite_pixmap_cache.get(cache_key)
        if cached is not None:
            return cached
        cache_path = _find_cached_sprite_path(sprite_name)
        if cache_path is None:
            cache_path = self._ensure_sprite_cached_local(sprite_name)
        if not cache_path or not os.path.exists(cache_path):
            return None
        pixmap = QPixmap(cache_path)
        if pixmap.isNull():
            return None
        scaled = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
        # Bound the cache so it can't grow unboundedly across many decks/sizes.
        if len(self._sprite_pixmap_cache) > 512:
            self._sprite_pixmap_cache.clear()
        self._sprite_pixmap_cache[cache_key] = scaled
        return scaled

    def _build_placeholder_sprite(self, label_text, size=24, accent="#4A9FD8"):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(accent))
        painter.drawRoundedRect(0, 0, size, size, 6, 6)
        painter.setPen(QColor("#F4F7FB"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(max(8, size // 2 - 2))
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, (label_text or "?")[:1].upper())
        painter.end()
        return pixmap

    def _create_deck_cell_widget(self, deck_name, icons=None, subtitle=None, icon_size=24):
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        icon_wrap = QWidget()
        icon_wrap.setStyleSheet("background: transparent;")
        icon_row = QHBoxLayout(icon_wrap)
        icon_row.setContentsMargins(0, 0, 0, 0)
        icon_row.setSpacing(2)

        for sprite_name in (icons or [])[:3]:
            icon_label = QLabel()
            pixmap = self._load_sprite_pixmap(sprite_name, icon_size)
            if pixmap is None:
                pixmap = self._build_placeholder_sprite(sprite_name[:1] or deck_name[:1], icon_size)
            icon_label.setPixmap(pixmap)
            icon_label.setFixedSize(icon_size + 2, icon_size + 2)
            icon_row.addWidget(icon_label)

        if icon_row.count() == 0:
            fallback = QLabel()
            fallback.setPixmap(self._build_placeholder_sprite(deck_name[:1], icon_size))
            fallback.setFixedSize(icon_size + 2, icon_size + 2)
            icon_row.addWidget(fallback)

        layout.addWidget(icon_wrap)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        title = QLabel(deck_name)
        title.setStyleSheet("color: rgba(242,247,255,0.96); font-size: 11px; font-weight: 600; background: transparent;")
        # Ensure the label reports its full text width so the column is wide
        # enough to show the whole deck name (never cut off).
        title.setMinimumWidth(title.fontMetrics().horizontalAdvance(deck_name) + 4)
        text_col.addWidget(title)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setStyleSheet("color: rgba(168,182,204,0.78); font-size: 9px; background: transparent;")
            text_col.addWidget(sub)

        layout.addLayout(text_col)
        layout.addStretch()
        return container

    def _set_meta_item(self, table, row, col, value, *, accent=None, muted=False, align=Qt.AlignmentFlag.AlignCenter, sort_value=None, link=None):
        item = MetaTableItem(value)
        item.setTextAlignment(align)
        if sort_value is not None:
            item.setData(Qt.ItemDataRole.UserRole, sort_value)
        if link:
            item.setData(Qt.ItemDataRole.UserRole + 1, link)
        fg = QColor(accent or "#EEF4FF")
        if muted:
            fg = QColor("#9BA8BC")
        item.setForeground(fg)
        bg = QColor(18, 25, 36, 225) if row % 2 == 0 else QColor(12, 18, 28, 225)
        item.setBackground(bg)
        table.setItem(row, col, item)

    def _set_meta_deck_cell(self, table, row, col, deck_name, icons=None, subtitle=None, *, sort_value=None, link=None):
        self._set_meta_item(
            table,
            row,
            col,
            "",
            align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            sort_value=sort_value if sort_value is not None else deck_name.lower(),
            link=link,
        )
        table.setCellWidget(
            row,
            col,
            self._create_deck_cell_widget(deck_name, icons, subtitle=subtitle),
        )

    def _open_table_row_link(self, table, row):
        if row < 0:
            return
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item is None:
                continue
            link = item.data(Qt.ItemDataRole.UserRole + 1)
            if link:
                webbrowser.open(link)
                return

    def _trend_display(self, trend):
        if trend == "up":
            return "UP", "#66BB6A"
        if trend == "down":
            return "DOWN", "#EF5350"
        return "EVEN", "#F9A825"

    def _open_row_link(self, links, row):
        if 0 <= row < len(links) and links[row]:
            webbrowser.open(links[row])

    def handle_tab_changed(self, index):
        tab_name = self.tab_widget.tabText(index)
        if tab_name == "Limitless TCG Live Meta" and self.limitless_table.rowCount() == 0 and self.limitless_refresh_btn.isEnabled():
            self._fetch_limitless_data()
        elif tab_name == "Decks":
            if not self._top_limitless_rows():
                self._refresh_decks_meta()
            if self._deck_dashboards_dirty:
                self._refresh_deck_dashboards()
        elif tab_name == "Limitless Dashboard":
            if self.limitless_manager:
                self.limitless_manager.enable_background_mode()
                self.limitless_manager.ensure_visible_dashboard_loaded()
        elif tab_name == "TrainerHill" and self.trainerhill_table.rowCount() == 0 and self.trainerhill_refresh_btn.isEnabled():
            self._fetch_trainerhill_data()
        elif tab_name == "Japan Data" and self.japan_table.rowCount() == 0 and self.japan_refresh_btn.isEnabled():
            self._fetch_japan_data()

    def _meta_header_bar(self, title_text, last_updated_label, refresh_btn, browser_url=None, browser_label="Open in Browser"):
        """Build the top bar used by all meta tabs: title | last updated | refresh | browser btn."""
        bar = QFrame()
        bar.setObjectName("metaHeaderBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 8)
        row.setSpacing(10)

        title = QLabel(title_text)
        title.setObjectName("sectionHeader")
        row.addWidget(title)

        row.addStretch()

        last_updated_label.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 10px;")
        row.addWidget(last_updated_label)

        refresh_btn.setObjectName("metaRefreshBtn")
        refresh_btn.setFixedHeight(28)
        refresh_btn.setFixedWidth(70)
        row.addWidget(refresh_btn)

        if browser_url:
            open_btn = QPushButton(browser_label)
            open_btn.setObjectName("limitlessBtn")
            open_btn.setFixedHeight(28)
            open_btn.clicked.connect(lambda: webbrowser.open(browser_url))
            row.addWidget(open_btn)

        return bar

    def create_limitless_tab(self):
        """Limitless Standard + Pocket meta from public API."""
        outer = QWidget()
        outer.setObjectName("contentWidget")
        vlayout = QVBoxLayout(outer)
        vlayout.setContentsMargins(12, 10, 12, 12)
        vlayout.setSpacing(8)

        # Game/format switcher
        switcher_row = QHBoxLayout()
        switcher_row.setSpacing(8)
        game_label = QLabel("Format:")
        game_label.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        switcher_row.addWidget(game_label)

        self.limitless_format_combo = QComboBox()
        self.limitless_format_combo.addItems(["PTCG Standard", "PTCG Pocket"])
        self.limitless_format_combo.setObjectName("metaCombo")
        self.limitless_format_combo.setFixedWidth(140)
        self.limitless_format_combo.setFixedHeight(28)
        self.limitless_format_combo.currentIndexChanged.connect(self._on_limitless_format_changed)
        switcher_row.addWidget(self.limitless_format_combo)
        switcher_row.addStretch()
        vlayout.addLayout(switcher_row)

        # Header bar
        self.limitless_updated_label = QLabel("Not loaded")
        self.limitless_refresh_btn = QPushButton("↻ Load")
        self.limitless_refresh_btn.clicked.connect(self._fetch_limitless_data)
        header = self._meta_header_bar(
            "STANDARD META", self.limitless_updated_label, self.limitless_refresh_btn,
            "https://play.limitlesstcg.com/decks?game=PTCG", "Limitless ↗"
        )
        vlayout.addWidget(header)

        # Status label
        self.limitless_status = QLabel("Click ↻ Load to fetch latest meta data from Limitless TCG API.")
        self.limitless_status.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10px; font-style: italic;")
        self.limitless_status.setWordWrap(True)
        vlayout.addWidget(self.limitless_status)

        metrics_bar, self.limitless_metric_labels = self._create_meta_stats_bar((
            ("tournaments", "Tournaments"),
            ("entries", "Entries"),
            ("decks", "Decks"),
        ))
        vlayout.addWidget(metrics_bar)

        # Table
        cols = ["#", "Deck", "Finishes", "Share", "Wins", "Losses", "Ties", "Raw WR", "Bayes WR", "95% CI", "P>50"]
        widths = [34, None, 68, 64, 58, 62, 52, 72, 78, 98, 56]
        self.limitless_table = self._make_meta_table(cols, widths, sortable=True, stretch_last=False)
        self.limitless_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.limitless_table.cellDoubleClicked.connect(lambda row, col: self._open_table_row_link(self.limitless_table, row))
        vlayout.addWidget(self.limitless_table)

        # Info label
        info = QLabel("Data comes from the Limitless API, uses real deck icons, aggregates recent tournament standings, and now includes Bayesian win-rate estimates. Click column headers to sort. Double-click a row to open that archetype on Limitless.")
        info.setStyleSheet("color: rgba(255,255,255,0.25); font-size: 9px;")
        info.setWordWrap(True)
        vlayout.addWidget(info)

        return outer

    def create_limitless_dashboard_tab(self):
        """Embedded Limitless tournament dashboard with persistent login."""
        outer = QWidget()
        outer.setObjectName("contentWidget")
        vlayout = QVBoxLayout(outer)
        vlayout.setContentsMargins(12, 12, 12, 12)
        vlayout.setSpacing(10)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.setContentsMargins(0, 0, 0, 0)

        refresh_btn = QPushButton("Reload Dashboard")
        refresh_btn.setObjectName("settingsBtn")
        refresh_btn.setFixedHeight(34)
        refresh_btn.clicked.connect(lambda: self.limitless_dashboard_view.load(QUrl(LIMITLESS_DASHBOARD_URL)) if WEBENGINE_AVAILABLE else webbrowser.open(LIMITLESS_DASHBOARD_URL))
        action_row.addWidget(refresh_btn)

        self.limitless_dashboard_autocheck_btn = QPushButton()
        self.limitless_dashboard_autocheck_btn.setObjectName("settingsBtn")
        self.limitless_dashboard_autocheck_btn.setFixedHeight(34)
        self.limitless_dashboard_autocheck_btn.setCheckable(True)
        self.limitless_dashboard_autocheck_btn.clicked.connect(self.toggle_limitless_auto_checkin)
        action_row.addWidget(self.limitless_dashboard_autocheck_btn)

        action_row.addStretch()
        vlayout.addLayout(action_row)

        if WEBENGINE_AVAILABLE:
            self.limitless_dashboard_view = QWebEngineView()
            self.limitless_dashboard_view.setMinimumHeight(360)
            self.limitless_dashboard_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            if self.limitless_manager:
                self.limitless_manager.register_view(self.limitless_dashboard_view, None)
            self.limitless_dashboard_view.load(QUrl(LIMITLESS_DASHBOARD_URL))
            vlayout.addWidget(self.limitless_dashboard_view, stretch=1)
        else:
            self.limitless_dashboard_view = None
            fallback = QLabel(
                "Qt WebEngine is not available. Open Limitless in your browser to manage your dashboard."
            )
            fallback.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 11px; font-style: italic;")
            fallback.setWordWrap(True)
            vlayout.addWidget(fallback)
            vlayout.addStretch()

        self._sync_limitless_autocheck_button()
        return outer

    def _sync_limitless_autocheck_button(self):
        if hasattr(self, "limitless_dashboard_autocheck_btn"):
            enabled = bool(self.limitless_manager and self.limitless_manager.auto_checkin_enabled)
            self.limitless_dashboard_autocheck_btn.setChecked(enabled)
            self.limitless_dashboard_autocheck_btn.setText(
                "Auto Check-In: ON" if enabled else "Auto Check-In: OFF"
            )

    def enable_limitless_background_watch(self):
        if not self.limitless_manager:
            return
        self.limitless_manager.enable_background_mode()
        self.limitless_manager.ensure_visible_dashboard_loaded()
        self._sync_limitless_autocheck_button()

    def toggle_limitless_auto_checkin(self):
        if not self.limitless_manager:
            return
        self.limitless_manager.auto_checkin_enabled = not self.limitless_manager.auto_checkin_enabled
        self.limitless_manager._save_state()
        self.limitless_manager.ensure_background_loaded()
        self._sync_limitless_autocheck_button()

    def open_limitless_dashboard_tab(self):
        if hasattr(self, "limitless_dashboard_tab_index"):
            self.show()
            self.raise_()
            self.activateWindow()
            self.tab_widget.setCurrentIndex(self.limitless_dashboard_tab_index)
            if self.limitless_manager:
                self.limitless_manager.ensure_visible_dashboard_loaded()

    def _update_limitless_dashboard_status(self, text):
        self._sync_limitless_autocheck_button()

    def _update_limitless_dashboard_auth(self, authenticated):
        if authenticated and self.limitless_manager:
            self.limitless_manager.ensure_background_loaded()

    def _update_limitless_checkin_summary(self, candidate):
        self._sync_limitless_autocheck_button()

    def _on_limitless_format_changed(self, idx):
        """Clear table and update header title when format is switched."""
        self.limitless_table.setRowCount(0)
        self.limitless_updated_label.setText("Not loaded")
        self.limitless_status.setText("Click ↻ Load to fetch latest meta data.")
        self.limitless_row_links = []
        for label in self.limitless_metric_labels.values():
            label.setText("--")

    def _fetch_limitless_data(self):
        if not REQUESTS_AVAILABLE:
            self.limitless_status.setText("Error: requests support is not installed.")
            return
        idx = self.limitless_format_combo.currentIndex()
        source = 'limitless_standard' if idx == 0 else 'limitless_pocket'
        self.limitless_status.setText("Fetching data from Limitless API…")
        self.limitless_refresh_btn.setEnabled(False)
        self._limitless_fetcher = MetaFetcher(source)
        self._limitless_fetcher.data_ready.connect(self._on_limitless_data)
        self._limitless_fetcher.error.connect(self._on_limitless_error)
        self._limitless_fetcher.start()

    def _on_limitless_data(self, source, data):
        self.limitless_refresh_btn.setEnabled(True)
        if source == "limitless_standard":
            self.limitless_standard_meta = data
            self._deck_dashboards_dirty = True
            if hasattr(self, "tab_widget") and self.tab_widget.currentIndex() == getattr(self, "decks_tab_index", -1):
                self._refresh_deck_dashboards()
        rows = data.get('rows', [])
        processed = data.get('tournaments_processed', 0)
        total_entries = data.get("total_entries", 0)
        fetched = data.get('fetched_at', 0)
        
        ft = datetime.fromtimestamp(fetched).strftime('%H:%M:%S') if fetched else 'unknown'
        self.limitless_updated_label.setText(f"Last: {ft}")
        if rows:
            self.limitless_status.setText(
                f"Loaded {len(rows)} archetypes from {processed} recent tournaments with deck-page W/L/T records."
            )
        else:
            self.limitless_status.setText("No recent data was returned by the Limitless API for this format.")
        self.limitless_metric_labels["tournaments"].setText(str(processed))
        self.limitless_metric_labels["entries"].setText(str(total_entries))
        self.limitless_metric_labels["decks"].setText(str(len(rows)))

        sorting_enabled = self.limitless_table.isSortingEnabled()
        if sorting_enabled:
            self.limitless_table.setSortingEnabled(False)
        self.limitless_table.setRowCount(0)
        for i, row in enumerate(rows[:50]):
            summary = self._summarize_meta_record(row)
            link = row.get("deck_url")
            wins = float(row.get("wins", 0) or 0)
            losses = float(row.get("losses", 0) or 0)
            ties = float(row.get("ties", 0) or 0)
            raw_pct = summary.get("observed", 0.0) * 100.0
            bayes_pct = summary.get("bayes_mean", 0.0) * 100.0
            ci_low = summary.get("ci_low", 0.0) * 100.0
            ci_high = summary.get("ci_high", 0.0) * 100.0
            prob_even = summary.get("probability_above_even", 0.0) * 100.0
            row["win_pct"] = round(raw_pct, 1)
            row["bayes_win_pct"] = round(bayes_pct, 1)
            row["ci_low_pct"] = round(ci_low, 1)
            row["ci_high_pct"] = round(ci_high, 1)
            row["prob_above_even_pct"] = round(prob_even, 1)
            row["confidence_label"] = summary.get("confidence_label")
            self.limitless_table.insertRow(i)
            self.limitless_table.setRowHeight(i, 46)
            self._set_meta_item(self.limitless_table, i, 0, str(i + 1), sort_value=i + 1, link=link)
            self._set_meta_deck_cell(
                self.limitless_table,
                i,
                1,
                row.get("deck", ""),
                row.get("icons", []),
                subtitle=f"{int(row.get('count', 0) or 0)} finishes • {summary.get('confidence_label', 'n/a')} confidence",
                sort_value=(row.get("deck", "") or "").lower(),
                link=link,
            )
            self._set_meta_item(self.limitless_table, i, 2, str(row.get('count', 0)), sort_value=int(row.get('count', 0) or 0), link=link)
            self._set_meta_item(self.limitless_table, i, 3, f"{row.get('share', 0):.1f}%", sort_value=float(row.get('share', 0) or 0), link=link)
            self._set_meta_item(self.limitless_table, i, 4, str(int(wins)), accent="#66BB6A", sort_value=wins, link=link)
            self._set_meta_item(self.limitless_table, i, 5, str(int(losses)), accent="#EF5350", sort_value=losses, link=link)
            self._set_meta_item(self.limitless_table, i, 6, str(int(ties)), accent="#F9A825", sort_value=ties, link=link)
            pct_color = "#66BB6A" if raw_pct >= 55 else "#EF5350" if raw_pct < 45 else "#F9A825"
            self._set_meta_item(self.limitless_table, i, 7, f"{raw_pct:.1f}%", accent=pct_color, sort_value=raw_pct, link=link)
            bayes_color = "#66BB6A" if bayes_pct >= 55 else "#EF5350" if bayes_pct < 45 else "#F9A825"
            self._set_meta_item(self.limitless_table, i, 8, f"{bayes_pct:.1f}%", accent=bayes_color, sort_value=bayes_pct, link=link)
            self._set_meta_item(self.limitless_table, i, 9, f"{ci_low:.0f}% - {ci_high:.0f}%", sort_value=(ci_high - ci_low), link=link)
            prob_color = "#66BB6A" if prob_even >= 65 else "#EF5350" if prob_even < 45 else "#F9A825"
            self._set_meta_item(self.limitless_table, i, 10, f"{prob_even:.0f}%", accent=prob_color, sort_value=prob_even, link=link)
        if sorting_enabled:
            self.limitless_table.setSortingEnabled(True)

    def _on_limitless_error(self, source, msg):
        self.limitless_refresh_btn.setEnabled(True)
        self.limitless_status.setText(f"Error: {msg}")

    def create_trainerhill_tab(self):
        """TrainerHill meta breakdown through its Dash callbacks."""
        outer = QWidget()
        outer.setObjectName("contentWidget")
        vlayout = QVBoxLayout(outer)
        vlayout.setContentsMargins(12, 10, 12, 12)
        vlayout.setSpacing(8)

        self.trainerhill_updated_label = QLabel("Not loaded")
        self.trainerhill_refresh_btn = QPushButton("↻ Load")
        self.trainerhill_refresh_btn.clicked.connect(self._fetch_trainerhill_data)
        header = self._meta_header_bar(
            "TRAINERHILL META", self.trainerhill_updated_label, self.trainerhill_refresh_btn,
            "https://trainerhill.com/meta?game=PTCG", "TrainerHill ↗"
        )
        vlayout.addWidget(header)

        self.trainerhill_status = QLabel("Click ↻ Load to fetch meta breakdown from TrainerHill.")
        self.trainerhill_status.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10px; font-style: italic;")
        self.trainerhill_status.setWordWrap(True)
        vlayout.addWidget(self.trainerhill_status)

        metrics_bar, self.trainerhill_metric_labels = self._create_meta_stats_bar((
            ("players", "Min Players"),
            ("range", "Date Range"),
            ("decks", "Archetypes"),
        ))
        vlayout.addWidget(metrics_bar)

        cols = ["#", "Trend", "Deck", "Share", "Count"]
        widths = [34, 62, None, 72, 72]
        self.trainerhill_table = self._make_meta_table(cols, widths)
        self.trainerhill_table.cellDoubleClicked.connect(lambda row, col: self._open_row_link(self.trainerhill_row_links, row))
        vlayout.addWidget(self.trainerhill_table)

        note = QLabel(
            "TrainerHill is read through its structured Dash callbacks instead of scraping the rendered page. Double-click a row to open the archetype page in your browser."
        )
        note.setStyleSheet("color: rgba(255,255,255,0.25); font-size: 9px;")
        note.setWordWrap(True)
        vlayout.addWidget(note)

        return outer

    def _fetch_trainerhill_data(self):
        if not REQUESTS_AVAILABLE:
            self.trainerhill_status.setText("Error: requests support is not installed.")
            return
        self.trainerhill_status.setText("Fetching data from TrainerHill…")
        self.trainerhill_refresh_btn.setEnabled(False)
        self._trainerhill_fetcher = MetaFetcher('trainerhill')
        self._trainerhill_fetcher.data_ready.connect(self._on_trainerhill_data)
        self._trainerhill_fetcher.error.connect(self._on_trainerhill_error)
        self._trainerhill_fetcher.start()

    def _on_trainerhill_data(self, source, data):
        self.trainerhill_refresh_btn.setEnabled(True)
        rows = data.get('rows', [])
        filters = data.get("filters", {})
        total_archetypes = data.get("total_archetypes", len(rows))
        fetched = data.get('fetched_at', 0)
        ft = datetime.fromtimestamp(fetched).strftime('%H:%M:%S') if fetched else 'unknown'
        self.trainerhill_updated_label.setText(f"Last: {ft}")
        self.trainerhill_metric_labels["players"].setText(str(filters.get("players", "--")))
        if filters.get("start_date") and filters.get("end_date"):
            self.trainerhill_metric_labels["range"].setText(f"{filters['start_date'][5:]} - {filters['end_date'][5:]}")
        else:
            self.trainerhill_metric_labels["range"].setText("--")
        self.trainerhill_metric_labels["decks"].setText(str(total_archetypes))

        if not rows:
            self.trainerhill_status.setText("TrainerHill returned no archetype rows for the active filter set.")
            self.trainerhill_table.setRowCount(0)
            self.trainerhill_row_links = []
            return

        self.trainerhill_status.setText(f"Loaded {len(rows)} archetypes from TrainerHill.")
        self.trainerhill_table.setRowCount(0)
        self.trainerhill_row_links = []
        for i, row in enumerate(rows):
            self.trainerhill_table.insertRow(i)
            self.trainerhill_table.setRowHeight(i, 42)
            self._set_meta_item(self.trainerhill_table, i, 0, str(i + 1))
            trend_text, trend_color = self._trend_display(row.get("trend"))
            self._set_meta_item(self.trainerhill_table, i, 1, trend_text, accent=trend_color)
            self.trainerhill_table.setCellWidget(
                i,
                2,
                self._create_deck_cell_widget(
                    row.get("deck", ""),
                    row.get("icons", []),
                    subtitle=f"{row.get('count', 0)} results in current sample",
                ),
            )
            self._set_meta_item(self.trainerhill_table, i, 3, f"{row.get('share', 0):.1f}%")
            self._set_meta_item(self.trainerhill_table, i, 4, str(row.get("count", 0)))
            self.trainerhill_row_links.append(row.get("deck_url"))

    def _on_trainerhill_error(self, source, msg):
        self.trainerhill_refresh_btn.setEnabled(True)
        self.trainerhill_status.setText(f"Error: {msg}")

    def create_japan_tab(self):
        """Japan Data: consolidated, translated, sortable-by-timeframe meta.

        Pulls from pokekameshi.com, translates deck names to English (aligned
        with Limitless names via optional AI), and renders in a format
        comparable to the US/Limitless meta table. Includes a timeframe filter,
        an AI-translation toggle, a hard-refresh button, and an important-sites
        showcase.
        """
        outer = QWidget()
        outer.setObjectName("contentWidget")
        vlayout = QVBoxLayout(outer)
        vlayout.setContentsMargins(12, 10, 12, 12)
        vlayout.setSpacing(8)

        # --- Header row: title + timeframe filter + AI toggle + refresh ---
        header_row = QHBoxLayout()
        header_row.setSpacing(10)
        title = QLabel("JAPAN DATA")
        title.setObjectName("sectionHeader")
        header_row.addWidget(title)
        header_row.addStretch()

        # Timeframe filter (sortable by timeframe)
        tf_label = QLabel("Timeframe:")
        tf_label.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        header_row.addWidget(tf_label)
        self.japan_timeframe_combo = QComboBox()
        self.japan_timeframe_combo.addItems(["Recent", "1 Week", "1 Month", "3 Months", "All Time"])
        self.japan_timeframe_combo.setObjectName("metaCombo")
        self.japan_timeframe_combo.setFixedWidth(120)
        self.japan_timeframe_combo.setFixedHeight(28)
        self.japan_timeframe_combo.currentIndexChanged.connect(self._on_japan_timeframe_changed)
        header_row.addWidget(self.japan_timeframe_combo)

        # AI translation toggle (recommended)
        self.japan_ai_toggle = QCheckBox("AI Translate")
        self.japan_ai_toggle.setObjectName("metaCombo")
        self.japan_ai_toggle.setToolTip(
            "Use the OpenAI API key to translate Japanese deck names, aligned "
            "with the top Limitless deck names. Runs once and caches permanently."
        )
        self.japan_ai_toggle.setChecked(True)
        header_row.addWidget(self.japan_ai_toggle)

        # Hard refresh button (re-runs AI translation)
        self.japan_hard_refresh_btn = QPushButton("↻ Hard Refresh")
        self.japan_hard_refresh_btn.setObjectName("metaRefreshBtn")
        self.japan_hard_refresh_btn.setFixedHeight(28)
        self.japan_hard_refresh_btn.setToolTip(
            "Force a full re-fetch AND re-run the AI translation of deck names. "
            "This uses API tokens, so only use it when you want fresh translations."
        )
        self.japan_hard_refresh_btn.clicked.connect(self._japan_hard_refresh)
        header_row.addWidget(self.japan_hard_refresh_btn)

        # Normal refresh button
        self.japan_refresh_btn = QPushButton("↻ Load")
        self.japan_refresh_btn.setObjectName("metaRefreshBtn")
        self.japan_refresh_btn.setFixedHeight(28)
        self.japan_refresh_btn.setFixedWidth(70)
        self.japan_refresh_btn.clicked.connect(self._fetch_japan_data)
        header_row.addWidget(self.japan_refresh_btn)

        open_btn = QPushButton("pokekameshi ↗")
        open_btn.setObjectName("limitlessBtn")
        open_btn.setFixedHeight(28)
        open_btn.clicked.connect(lambda: webbrowser.open(japan_data.TIER_LIST_URL))
        header_row.addWidget(open_btn)
        vlayout.addLayout(header_row)

        # --- Status label ---
        self.japan_status = QLabel(
            "Click ↻ Load to fetch consolidated Japanese meta from pokekameshi.com. "
            "Deck names are translated to English and aligned with Limitless names."
        )
        self.japan_status.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10px; font-style: italic;")
        self.japan_status.setWordWrap(True)
        vlayout.addWidget(self.japan_status)

        # --- Metrics bar ---
        metrics_bar, self.japan_metric_labels = self._create_meta_stats_bar((
            ("decks", "Decks"),
            ("entries", "Entries"),
            ("translated", "Translated"),
        ))
        vlayout.addWidget(metrics_bar)

        # --- Comparable meta table ---
        cols = ["#", "Deck", "Finishes", "Share", "Wins", "Losses", "Raw WR", "Bayes WR", "95% CI", "P>50"]
        widths = [34, None, 68, 64, 58, 62, 72, 78, 98, 56]
        self.japan_table = self._make_meta_table(cols, widths, sortable=True, stretch_last=False)
        self.japan_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        vlayout.addWidget(self.japan_table)

        # --- Important sites showcase ---
        sites_label = QLabel("IMPORTANT JAPANESE SITES")
        sites_label.setObjectName("sectionHeader")
        sites_label.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 10px; font-weight: 700; letter-spacing: 1px; margin-top: 8px;")
        vlayout.addWidget(sites_label)

        sites = [
            ("Pokeka Meshi (ポケカ飯)", japan_data.POKEKAMESHI_BASE,
             "Tier list, deck recipes, data lab reports, tournament results"),
            ("Pokeka Data Lab", "https://pokekameshi.com/datalab-voluntarycompetition/",
             "Methodology + weekly independent-tournament aggregation"),
            ("Pokemon Card Official (JP)", "https://www.pokemon-card.com/",
             "Official deck-code viewer, card search, rules"),
            ("ポケカデータラボ", "https://pokekameshi.com/taikairesult-m6-3w/",
             "Weekly independent-tournament data aggregation"),
            ("ポケカ情報局", "https://pokecabook.com/",
             "Japanese deck recipes, tier lists, tournament results"),
            ("ポケカ速報", "https://pokeka-sokuhou.com/",
             "Japanese Pokemon card news and meta updates"),
            ("ポケカデッキ研究所", "https://pokeca-deck.com/",
             "Japanese deck analysis and meta reports"),
            ("ポケモンカード公式 デッキ検索", "https://www.pokemon-card.com/deck/",
             "Official deck-code search and deck building"),
        ]
        sites_grid = QGridLayout()
        sites_grid.setSpacing(6)
        for i, (name, url, desc) in enumerate(sites):
            row = i // 2
            col = (i % 2) * 2
            btn = QPushButton(name)
            btn.setObjectName("limitlessBtn")
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda checked=False, u=url: webbrowser.open(u))
            sites_grid.addWidget(btn, row, col)
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 9px;")
            desc_lbl.setWordWrap(True)
            sites_grid.addWidget(desc_lbl, row, col + 1)
        vlayout.addLayout(sites_grid)

        # --- Info note ---
        info = QLabel(
            "Japan data is consolidated from pokekameshi.com and translated to English "
            "aligned with Limitless deck names, so it can be compared directly with the "
            "US meta and eventually merged by set list. Click column headers to sort. "
            "Enable 'AI Translate' and use 'Hard Refresh' to re-run the AI translation "
            "(uses API tokens, cached permanently)."
        )
        info.setStyleSheet("color: rgba(255,255,255,0.25); font-size: 9px;")
        info.setWordWrap(True)
        vlayout.addWidget(info)

        return outer

    def _on_japan_timeframe_changed(self, idx):
        """Re-render the Japan table when the timeframe filter changes."""
        self._render_japan_table()

    def _fetch_japan_data(self):
        """Fetch Japan data in the background (uses cache unless hard refresh)."""
        if not REQUESTS_AVAILABLE:
            self.japan_status.setText("Error: requests support is not installed.")
            return
        api_key = load_api_key()
        ai_enabled = self.japan_ai_toggle.isChecked() and bool(api_key)
        self.japan_status.setText("Fetching Japan data from pokekameshi.com…")
        self.japan_refresh_btn.setEnabled(False)
        self.japan_hard_refresh_btn.setEnabled(False)
        self._japan_fetcher = JapanFetcher(ai_enabled=ai_enabled, api_key=api_key, force=False)
        self._japan_fetcher.data_ready.connect(self._on_japan_data)
        self._japan_fetcher.error.connect(self._on_japan_error)
        self._japan_fetcher.start()

    def _japan_hard_refresh(self):
        """Force a full re-fetch AND re-run the AI translation."""
        if not REQUESTS_AVAILABLE:
            self.japan_status.setText("Error: requests support is not installed.")
            return
        api_key = load_api_key()
        if not api_key:
            self.japan_status.setText(
                "Hard Refresh needs an OpenAI API key to re-run AI translation. "
                "Add a key in Advanced, or use ↻ Load for cached translations."
            )
            return
        ai_enabled = self.japan_ai_toggle.isChecked()
        self.japan_status.setText("Hard refresh: re-fetching and re-translating deck names (uses API tokens)…")
        self.japan_refresh_btn.setEnabled(False)
        self.japan_hard_refresh_btn.setEnabled(False)
        self._japan_fetcher = JapanFetcher(ai_enabled=ai_enabled, api_key=api_key, force=True)
        self._japan_fetcher.data_ready.connect(self._on_japan_data)
        self._japan_fetcher.error.connect(self._on_japan_error)
        self._japan_fetcher.start()

    def _on_japan_data(self, source, data):
        self.japan_refresh_btn.setEnabled(True)
        self.japan_hard_refresh_btn.setEnabled(True)
        rows = data.get("rows", [])
        self._japan_rows = rows
        fetched = data.get("fetched_at", 0)
        ft = datetime.fromtimestamp(fetched).strftime('%H:%M:%S') if fetched else 'unknown'
        self.japan_status.setText(
            f"Loaded {len(rows)} archetypes from pokekameshi.com (last: {ft}). "
            f"Deck names translated to English and aligned with Limitless."
        )
        self.japan_metric_labels["decks"].setText(str(len(rows)))
        self.japan_metric_labels["entries"].setText(str(data.get("total_entries", 0)))
        translated = sum(1 for r in rows if r.get("deck") and not _looks_japanese(r.get("deck", "")))
        self.japan_metric_labels["translated"].setText(str(translated))
        self._render_japan_table()

    def _on_japan_error(self, source, msg):
        self.japan_refresh_btn.setEnabled(True)
        self.japan_hard_refresh_btn.setEnabled(True)
        self.japan_status.setText(f"Error: {msg}")

    def _render_japan_table(self):
        """Render the Japan meta table, applying the timeframe filter."""
        rows = []
        if hasattr(self, "japan_table"):
            rows = list(getattr(self, "_japan_rows", []) or [])
        # Map the combo label to a timeframe key for filtering.
        tf_label = self.japan_timeframe_combo.currentText() if hasattr(self, "japan_timeframe_combo") else "Recent"
        tf_map = {
            "Recent": "recent",
            "1 Week": "1w",
            "1 Month": "1m",
            "3 Months": "3m",
            "All Time": "all",
        }
        tf = tf_map.get(tf_label, "recent")
        rows = japan_data.filter_by_timeframe({"rows": rows}, tf)

        sorting_enabled = self.japan_table.isSortingEnabled()
        if sorting_enabled:
            self.japan_table.setSortingEnabled(False)
        self.japan_table.setRowCount(0)
        for i, row in enumerate(rows[:50]):
            summary = self._summarize_meta_record(row)
            wins = float(row.get("wins", 0) or 0)
            losses = float(row.get("losses", 0) or 0)
            ties = float(row.get("ties", 0) or 0)
            raw_pct = summary.get("observed", 0.0) * 100.0
            bayes_pct = summary.get("bayes_mean", 0.0) * 100.0
            ci_low = summary.get("ci_low", 0.0) * 100.0
            ci_high = summary.get("ci_high", 0.0) * 100.0
            prob_even = summary.get("probability_above_even", 0.0) * 100.0
            self.japan_table.insertRow(i)
            self.japan_table.setRowHeight(i, 46)
            self._set_meta_item(self.japan_table, i, 0, str(i + 1), sort_value=i + 1)
            self._set_meta_deck_cell(
                self.japan_table,
                i,
                1,
                row.get("deck", ""),
                row.get("icons", []),
                subtitle=f"{int(row.get('count', 0) or 0)} finishes • {summary.get('confidence_label', 'n/a')}",
                sort_value=(row.get("deck", "") or "").lower(),
            )
            self._set_meta_item(self.japan_table, i, 2, str(row.get('count', 0)), sort_value=int(row.get('count', 0) or 0))
            self._set_meta_item(self.japan_table, i, 3, f"{row.get('share', 0):.1f}%", sort_value=float(row.get('share', 0) or 0))
            self._set_meta_item(self.japan_table, i, 4, str(int(wins)), accent="#66BB6A", sort_value=wins)
            self._set_meta_item(self.japan_table, i, 5, str(int(losses)), accent="#EF5350", sort_value=losses)
            pct_color = "#66BB6A" if raw_pct >= 55 else "#EF5350" if raw_pct < 45 else "#F9A825"
            self._set_meta_item(self.japan_table, i, 6, f"{raw_pct:.1f}%", accent=pct_color, sort_value=raw_pct)
            bayes_color = "#66BB6A" if bayes_pct >= 55 else "#EF5350" if bayes_pct < 45 else "#F9A825"
            self._set_meta_item(self.japan_table, i, 7, f"{bayes_pct:.1f}%", accent=bayes_color, sort_value=bayes_pct)
            self._set_meta_item(self.japan_table, i, 8, f"{ci_low:.0f}% - {ci_high:.0f}%", sort_value=(ci_high - ci_low))
            prob_color = "#66BB6A" if prob_even >= 65 else "#EF5350" if prob_even < 45 else "#F9A825"
            self._set_meta_item(self.japan_table, i, 9, f"{prob_even:.0f}%", accent=prob_color, sort_value=prob_even)
        if sorting_enabled:
            self.japan_table.setSortingEnabled(True)

    def create_pokedata_tab(self):
        """PokeData.ovh – embedded interactive tool with nav buttons."""
        POKEDATA_BASE = "https://www.pokedata.ovh"
        POKEDATA_PAGES = [
            ("Events",         POKEDATA_BASE + "/"),
            ("Standings",      POKEDATA_BASE + "/standings"),
            ("Champ Points",   POKEDATA_BASE + "/championship-points"),
            ("Hand Sim",       POKEDATA_BASE + "/hand-simulator"),
            ("Compare Lists",  POKEDATA_BASE + "/compare"),
        ]

        outer = QWidget()
        outer.setObjectName("contentWidget")
        vlayout = QVBoxLayout(outer)
        vlayout.setContentsMargins(12, 10, 12, 12)
        vlayout.setSpacing(8)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("POKEDATA.OVH TOOLS")
        title.setObjectName("sectionHeader")
        header_row.addWidget(title)
        header_row.addStretch()
        open_btn = QPushButton("Open in Browser ↗")
        open_btn.setObjectName("limitlessBtn")
        open_btn.setFixedHeight(28)
        open_btn.clicked.connect(lambda: webbrowser.open(POKEDATA_BASE))
        header_row.addWidget(open_btn)
        vlayout.addLayout(header_row)

        note = QLabel("A useful site for events, standings, championship points, hand simulation and decklist comparison.")
        note.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 10px;")
        note.setWordWrap(True)
        vlayout.addWidget(note)

        # Navigation button bar
        nav_bar = QFrame()
        nav_bar.setObjectName("metaHeaderBar")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setSpacing(6)
        nav_layout.setContentsMargins(0, 0, 0, 4)

        if WEBENGINE_AVAILABLE:
            self._pokedata_webview = QWebEngineView()
            self._pokedata_webview.setMinimumHeight(450)
            self._pokedata_webview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            # Zoom out so the tools fit better (was too zoomed in).
            self._pokedata_webview.setZoomFactor(0.50)
            self._pokedata_webview.load(QUrl(POKEDATA_PAGES[0][1]))

            for label, url in POKEDATA_PAGES:
                btn = QPushButton(label)
                btn.setObjectName("metaNavBtn")
                btn.setFixedHeight(28)
                btn.clicked.connect(lambda checked=False, u=url: self._pokedata_webview.load(QUrl(u)))
                nav_layout.addWidget(btn)
            nav_layout.addStretch()
            vlayout.addWidget(nav_bar)
            vlayout.addWidget(self._pokedata_webview, stretch=1)
        else:
            # Fallback: grid of link buttons
            for label, url in POKEDATA_PAGES:
                btn = QPushButton(f"  {label}  ↗")
                btn.setObjectName("limitlessBtn")
                btn.setFixedHeight(38)
                btn.clicked.connect(lambda checked=False, u=url: webbrowser.open(u))
                nav_layout.addWidget(btn)
            nav_layout.addStretch()
            vlayout.addWidget(nav_bar)
            fallback = QLabel("WebEngine not available. Use buttons above to open pages in your browser.")
            fallback.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10px; font-style: italic;")
            vlayout.addWidget(fallback)
            vlayout.addStretch()

        return outer

    # ─── END META ANALYSIS TABS ─────────────────────────────────────────────

    def create_card(self, title):
        """Create a styled card container"""
        card = QFrame()
        card.setObjectName("settingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(0)
        card_layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header = QLabel(title)
        header.setStyleSheet("color: rgba(255, 255, 255, 0.9); font-size: 14px; font-weight: 600; padding: 12px;")
        card_layout.addWidget(header)
        
        return card
    
    def check_console_availability(self):
        """Check if console window is available and set button state"""
        try:
            import ctypes
            import win32gui
            import win32process
            import psutil
            
            print("\n[Console Detection] Starting...")
            print(f"[Console Detection] Current process PID: {os.getpid()}")
            
            console_found = False
            monitor_pid = None
            
            # Method 1: Try PID file first
            pid_file = os.path.join(BASE_DIR, ".monitor_pid")
            print(f"[Console Detection] Checking PID file: {pid_file}")
            
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        file_pid = int(f.read().strip())
                    
                    print(f"[Console Detection] PID from file: {file_pid}")
                    
                    # Verify process is still running
                    try:
                        process = psutil.Process(file_pid)
                        # Check if it's actually TCGLiveMonitor (not Stats UI or other script)
                        if 'python' in process.name().lower():
                            cmdline = ' '.join(process.cmdline())
                            if 'TCGLiveMonitor.py' in cmdline and file_pid != os.getpid():
                                monitor_pid = file_pid
                                print(f"[Console Detection] ✓ Valid monitor PID from file: {monitor_pid}")
                            else:
                                print(f"[Console Detection] PID {file_pid} is not TCGLiveMonitor (cmdline: {cmdline})")
                    except psutil.NoSuchProcess:
                        print(f"[Console Detection] PID {file_pid} from file is stale")
                except Exception as e:
                    print(f"[Console Detection] Error reading PID file: {e}")
            
            # Method 2: Search all Python processes for TCGLiveMonitor
            if monitor_pid is None:
                print("[Console Detection] Searching for TCGLiveMonitor process...")
                for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                    try:
                        # Skip our own process
                        if proc.info['pid'] == os.getpid():
                            continue
                            
                        if 'python' in proc.info['name'].lower():
                            cmdline = ' '.join(proc.info['cmdline']) if proc.info['cmdline'] else ''
                            if 'TCGLiveMonitor.py' in cmdline:
                                monitor_pid = proc.info['pid']
                                print(f"[Console Detection] ✓ Found TCGLiveMonitor: PID {monitor_pid}")
                                print(f"[Console Detection]   Command: {cmdline}")
                                # Update PID file with correct PID
                                try:
                                    with open(pid_file, 'w') as f:
                                        f.write(str(monitor_pid))
                                    print(f"[Console Detection] Updated PID file")
                                except:
                                    pass
                                break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            
            # Method 3: Find console window for the monitor process (NOT our own)
            if monitor_pid:
                print(f"[Console Detection] Looking for console window (Monitor PID: {monitor_pid}, Our PID: {os.getpid()})...")
                
                def find_console_callback(hwnd, lParam):
                    try:
                        if win32gui.IsWindowVisible(hwnd):
                            _, pid = win32process.GetWindowThreadProcessId(hwnd)
                            # ONLY match the monitor's console, not ours
                            if pid == monitor_pid:
                                class_name = win32gui.GetClassName(hwnd)
                                title = win32gui.GetWindowText(hwnd)
                                if class_name == "ConsoleWindowClass":
                                    self.monitor_console_hwnd = hwnd
                                    print(f"[Console Detection] ✓ FOUND MONITOR CONSOLE")
                                    print(f"[Console Detection]   PID: {pid}, HWND: {hwnd}, Title: '{title}'")
                                    return False
                    except:
                        pass
                    return True
                
                self.monitor_console_hwnd = None
                win32gui.EnumWindows(find_console_callback, None)
                
                if self.monitor_console_hwnd:
                    console_found = True
                    print(f"[Console Detection] ✓ Console ready for control")
                else:
                    print(f"[Console Detection] ✗ No console window found for monitor PID {monitor_pid}")
            else:
                print("[Console Detection] ✗ TCGLiveMonitor process not found")
            
            # Do NOT use fallback to own console - we only want the monitor's console
            if not console_found:
                self.console_btn.setText("No Console Available")
                self.console_btn.setEnabled(False)
                self.console_hidden = False
                self.monitor_console_hwnd = None
                if hasattr(self, "debug_status_label"):
                    self.debug_status_label.setText("Monitor console was not found. Run the monitor in console mode to enable live toggling.")
                print("[Console Detection] ✗ Monitor console not found")
            else:
                # Check saved preference and apply it
                self.load_console_preference()
                if hasattr(self, "debug_status_label"):
                    self.debug_status_label.setText("Monitor console detected and ready for visibility control.")
                
        except Exception as e:
            print(f"[Console Detection] Error: {e}")
            import traceback
            traceback.print_exc()
            if hasattr(self, "debug_status_label"):
                self.debug_status_label.setText(f"Console detection hit an error: {e}")
    
    def load_console_preference(self):
        """Load and apply saved console visibility preference"""
        try:
            pref_file = os.path.join(BASE_DIR, ".console_pref")
            if os.path.exists(pref_file):
                with open(pref_file, 'r') as f:
                    pref = f.read().strip()
                
                if pref == "hidden":
                    print("[Console Pref] Applying saved preference: hidden")
                    # Hide console immediately
                    import ctypes
                    if self.monitor_console_hwnd:
                        ctypes.windll.user32.ShowWindow(self.monitor_console_hwnd, 0)
                        self.console_hidden = True
                        self.console_btn.setText("Show Console Window")
                        print("✓ Console auto-hidden on startup")
                else:
                    print("[Console Pref] Applying saved preference: visible")
                    self.console_hidden = False
                    self.console_btn.setText("Hide Console Window")
            else:
                print("[Console Pref] No saved preference, defaulting to visible")
                self.console_btn.setText("Hide Console Window")
        except Exception as e:
            print(f"[Console Pref] Error loading preference: {e}")
    
    def save_console_preference(self):
        """Save console visibility preference"""
        try:
            pref_file = os.path.join(BASE_DIR, ".console_pref")
            with open(pref_file, 'w') as f:
                f.write("hidden" if self.console_hidden else "visible")
            print(f"[Console Pref] Saved: {'hidden' if self.console_hidden else 'visible'}")
        except Exception as e:
            print(f"[Console Pref] Error saving preference: {e}")
    
    def toggle_console(self):
        """Toggle console window visibility"""
        try:
            import ctypes
            
            # Check if we have a console window handle
            if not hasattr(self, 'monitor_console_hwnd') or self.monitor_console_hwnd is None:
                print("No console window available to toggle")
                return
            
            hwnd = self.monitor_console_hwnd
            
            # Toggle based on current state
            if self.console_hidden:
                # Show console
                ctypes.windll.user32.ShowWindow(hwnd, 1)  # SW_SHOWNORMAL
                self.console_hidden = False
                self.console_btn.setText("Hide Console Window")
                print("✓ Monitor console window shown")
            else:
                # Hide console
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
                self.console_hidden = True
                self.console_btn.setText("Show Console Window")
                print("✓ Monitor console window hidden (running headless)")
            
            # Save preference
            self.save_console_preference()
                
        except Exception as e:
            print(f"Error toggling console: {e}")
            import traceback
            traceback.print_exc()
    
    def launch_ocr_test(self):
        """Launch OCR test window"""
        import subprocess
        try:
            # Run the main script which will show the OCR test window
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "TCGLiveMonitor.py"), "--ocr-test"], **kwargs)
        except Exception as e:
            print(f"Error launching OCR test: {e}")
    
    def launch_ai_parser(self):
        """Launch AI battle log parser"""
        import subprocess
        try:
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "AIParseBattleLog.py")], **kwargs)
        except Exception as e:
            print(f"Error launching AI parser: {e}")

    def open_logs_folder(self):
        log_dir = os.path.join(BASE_DIR, "Logs")
        os.makedirs(log_dir, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(log_dir)
            elif sys.platform == "darwin":
                subprocess.run(["open", log_dir], check=False)
            else:
                subprocess.run(["xdg-open", log_dir], check=False)
        except Exception as e:
            print(f"Error opening logs folder: {e}")

    def refresh_parser_mode_status(self):
        local_only = bool(self.app_settings.get("local_only_mode", False))
        has_key = bool(load_api_key())
        if local_only:
            text = "Local-only mode is active. The parser will not call GPT and will ask for the opponent deck name."
        elif has_key:
            text = "GPT parsing is active. If an API call fails, the parser will fall back to local-only flow."
        else:
            text = "No API key is saved. The parser will automatically fall back to local-only mode."
        if hasattr(self, "parser_mode_status_label"):
            self.parser_mode_status_label.setText(text)

    def save_parser_settings(self):
        key_value = (self.api_key_input.text() if hasattr(self, "api_key_input") else "").strip()
        self.app_settings["local_only_mode"] = bool(
            self.local_only_checkbox.isChecked() if hasattr(self, "local_only_checkbox") else False
        )
        save_app_settings(self.app_settings)
        if key_value:
            save_api_key(key_value)
        else:
            clear_api_key()
        self.refresh_parser_mode_status()
        QMessageBox.information(self, "Parser Settings Saved", "Parser settings were updated successfully.")

    def clear_parser_api_key(self):
        clear_api_key()
        if hasattr(self, "api_key_input"):
            self.api_key_input.clear()
        self.refresh_parser_mode_status()
    
    def add_autorun(self):
        """Add to Windows startup"""
        print("\n" + "="*50)
        print("Adding TCG Live Monitor to Windows startup (headless mode)...")
        print("="*50)
        report = startup_utils.enable_startup(BASE_DIR)
        methods = []
        if report["registry_ok"]:
            methods.append("Registry Run key")
        if report["task_ok"]:
            methods.append("Scheduled Task (elevated)")

        if methods:
            print("\nSuccessfully added to Windows startup!")
            print("   The monitor will now start automatically when you log in.")
            print("   Startup mode: Headless (no console window)")
            print(f"   Methods: {', '.join(methods)}")
            print("="*50 + "\n")
            QMessageBox.information(
                self,
                "Startup Enabled",
                "Windows startup is enabled.\n\n"
                f"Mode: Headless (no console)\n"
                f"Methods: {', '.join(methods)}"
            )
            return

        errors = [msg for msg in (report["registry_error"], report["task_error"]) if msg]
        error_text = "\n".join(errors) if errors else "Unknown startup registration error."
        print(f"\n❌ Error adding to startup:\n   {error_text}")
        print("="*50 + "\n")
        QMessageBox.warning(self, "Startup Failed", error_text)
    
    def remove_autorun(self):
        """Remove from Windows startup"""
        print("\n" + "="*50)
        print("Removing TCG Live Monitor from Windows Startup...")
        print("="*50)
        report = startup_utils.disable_startup()
        if report["registry_ok"] and report["task_ok"]:
            removed = ", ".join(report["removed_tasks"]) if report["removed_tasks"] else "no scheduled tasks were present"
            print("\nSuccessfully removed Windows startup!")
            print("   The monitor will no longer start automatically.")
            print(f"   Removed tasks: {removed}")
            print("="*50 + "\n")
            QMessageBox.information(
                self,
                "Startup Disabled",
                "Windows startup has been removed.\n\n"
                f"Removed tasks: {removed}"
            )
            return

        errors = []
        if report["registry_error"]:
            errors.append(report["registry_error"])
        errors.extend(report["task_errors"])
        error_text = "\n".join(errors) if errors else "Unknown startup removal error."
        print(f"\n❌ Error removing from startup:\n   {error_text}")
        print("="*50 + "\n")
        QMessageBox.warning(self, "Startup Removal Failed", error_text)
    
    def close_application(self):
        """Close the entire application including overlay and monitor process"""
        try:
            # Confirm closure
            reply = QMessageBox.question(
                self, 
                'Close Application',
                'Are you sure you want to close the entire TCG Live Monitor?\n\nThis will stop all monitoring and close all windows.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                print("\n" + "="*50)
                print("Closing TCG Live Monitor...")
                print("="*50 + "\n")
                
                # Try to terminate the monitor process
                try:
                    import psutil
                    pid_file = os.path.join(BASE_DIR, ".monitor_pid")
                    if os.path.exists(pid_file):
                        with open(pid_file, 'r') as f:
                            monitor_pid = int(f.read().strip())
                        
                        # Kill the monitor process
                        try:
                            process = psutil.Process(monitor_pid)
                            process.terminate()
                            process.wait(timeout=3)
                            print(f"✓ Terminated monitor process (PID: {monitor_pid})")
                        except psutil.NoSuchProcess:
                            print("Monitor process already terminated")
                        except psutil.TimeoutExpired:
                            process.kill()
                            print(f"✓ Force killed monitor process (PID: {monitor_pid})")
                        
                        # Clean up PID file
                        os.remove(pid_file)
                except Exception as e:
                    print(f"Warning: Could not terminate monitor process: {e}")
                
                # Close overlay if it exists
                if hasattr(self, 'parent_overlay') and self.parent_overlay:
                    self.parent_overlay.close()
                
                # Close this window
                self.close()
                
                # Quit the application
                QApplication.quit()
                
        except Exception as e:
            print(f"Error closing application: {e}")
            import traceback
            traceback.print_exc()
    
    def create_stats_cards(self):
        """Create modern stat cards grid"""
        container = QFrame()
        container.setObjectName("statsGrid")
        
        layout = QGridLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Stat cards data
        self.total_games_label = QLabel("--")
        self.win_rate_label = QLabel("--%")
        self.current_elo_label = QLabel("--")
        self.best_elo_label = QLabel("--")
        self.total_wins_label = QLabel("--")
        self.total_losses_label = QLabel("--")
        
        cards = [
            ("TOTAL GAMES", self.total_games_label, "#4A9FD8"),
            ("WIN RATE", self.win_rate_label, "#9CC344"),
            ("CURRENT ELO", self.current_elo_label, "#F9A825"),
            ("BEST ELO", self.best_elo_label, "#7B1FA2"),
            ("WINS", self.total_wins_label, "#66BB6A"),
            ("LOSSES", self.total_losses_label, "#EF5350"),
        ]
        
        row, col = 0, 0
        for label_text, value_label, color in cards:
            card = self.create_stat_card(label_text, value_label, color)
            layout.addWidget(card, row, col)
            
            col += 1
            if col >= 3:
                col = 0
                row += 1
        
        return container
    
    def create_stat_card(self, title, value_label, accent_color):
        """Create individual modern stat card"""
        card = QFrame()
        card.setObjectName("statCard")
        card.setStyleSheet(f"""
            QFrame#statCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 255, 255, 0.03),
                    stop:1 rgba(255, 255, 255, 0.01));
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                border-left: 3px solid {accent_color};
            }}
        """)
        card.setFixedHeight(85)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        
        # Title
        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        title_label.setStyleSheet(f"color: {accent_color}; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(title_label)
        
        # Value
        value_label.setObjectName("cardValue")
        value_label.setStyleSheet("color: rgba(255, 255, 255, 0.95); font-size: 28px; font-weight: 700;")
        layout.addWidget(value_label)
        
        layout.addStretch()
        
        return card
    
    def create_graphs_section(self):
        """Create modern graphs section"""
        container = QFrame()
        container.setObjectName("graphsContainer")
        
        layout = QHBoxLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Elo graph
        self.elo_canvas = MplCanvas(self, width=4.5, height=2.8, dpi=90)
        elo_frame = self.create_graph_card("ELO PROGRESSION", self.elo_canvas, header_widget=self._create_elo_scale_selector())
        layout.addWidget(elo_frame)
        
        # Win rate graph
        self.winrate_canvas = MplCanvas(self, width=4.5, height=2.8, dpi=90)
        winrate_frame = self.create_graph_card("WIN RATE TREND", self.winrate_canvas)
        layout.addWidget(winrate_frame)
        
        return container
    
    def _create_elo_scale_selector(self):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.elo_scale_buttons = {}
        for key, label in (("all", "All"), ("1y", "1Y"), ("3m", "3M"), ("1m", "1M"), ("1w", "1W")):
            btn = QPushButton(label)
            btn.setObjectName("eloScaleBtn")
            btn.setCheckable(True)
            btn.setChecked(key == self.elo_time_scale)
            btn.setFixedHeight(22)
            btn.setMinimumWidth(28)
            btn.clicked.connect(lambda checked=False, scale_key=key: self._set_elo_time_scale(scale_key))
            layout.addWidget(btn)
            self.elo_scale_buttons[key] = btn

        return container

    def _set_replay_tab_visible(self, visible):
        self._replay_tab_visible = bool(visible)
        if not hasattr(self, "tab_widget") or not hasattr(self, "replay_tab_index"):
            return
        try:
            self.tab_widget.setTabVisible(self.replay_tab_index, self._replay_tab_visible)
            return
        except Exception:
            pass
        try:
            self.tab_widget.tabBar().setTabVisible(self.replay_tab_index, self._replay_tab_visible)
        except Exception:
            pass

    def _set_elo_time_scale(self, scale_key):
        if scale_key == self.elo_time_scale:
            return
        self.elo_time_scale = scale_key
        for key, button in getattr(self, "elo_scale_buttons", {}).items():
            button.setChecked(key == scale_key)
        self.update_elo_graph()

    def _update_elo_scale_visibility(self, times):
        buttons = getattr(self, "elo_scale_buttons", {})
        if not buttons:
            return

        available = {"all"}
        if times:
            latest = times[-1]
            earliest = times[0]
            for key, days in self.elo_time_scale_days.items():
                cutoff = latest - timedelta(days=days)
                if earliest <= cutoff:
                    available.add(key)

        for key, button in buttons.items():
            button.setVisible(key in available)

        if self.elo_time_scale not in available:
            fallback_order = ["all", "1y", "3m", "1m", "1w"]
            self.elo_time_scale = next((key for key in fallback_order if key in available), "all")

        for key, button in buttons.items():
            button.setChecked(key == self.elo_time_scale)

    def create_graph_card(self, title, canvas, header_widget=None):
        """Create modern graph card"""
        card = QFrame()
        card.setObjectName("graphCard")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        title_label = QLabel(title)
        title_label.setObjectName("graphTitle")
        header_row.addWidget(title_label)
        header_row.addStretch()
        if header_widget is not None:
            header_row.addWidget(header_widget, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(header_row)
        
        # Canvas
        layout.addWidget(canvas)
        
        return card
    
    def create_deck_section(self):
        """Create modern deck usage section"""
        card = QFrame()
        card.setObjectName("deckCard")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # Header
        header = QLabel("DECK PERFORMANCE")
        header.setObjectName("sectionHeader")
        layout.addWidget(header)
        
        # Deck list
        self.deck_list_layout = QVBoxLayout()
        self.deck_list_layout.setSpacing(6)
        layout.addLayout(self.deck_list_layout)
        
        return card
    
    def create_battles_section(self):
        """Create modern battles section"""
        card = QFrame()
        card.setObjectName("battlesCard")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # Header
        header = QLabel("RECENT BATTLES")
        header.setObjectName("sectionHeader")
        layout.addWidget(header)
        
        # Battles list
        self.battles_list_layout = QVBoxLayout()
        self.battles_list_layout.setSpacing(4)
        layout.addLayout(self.battles_list_layout)
        
        return card
    
    def create_limitless_section(self):
        """Create Limitless integration section"""
        card = QFrame()
        card.setObjectName("limitlessCard")
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # Header
        header = QLabel("LIMITLESS TCG")
        header.setObjectName("sectionHeader")
        layout.addWidget(header)
        
        # Button
        btn = QPushButton("Open Limitless TCG")
        btn.setObjectName("limitlessBtn")
        btn.setFixedHeight(36)
        btn.clicked.connect(self.open_limitless)
        layout.addWidget(btn)
        
        # Placeholder
        placeholder = QLabel("Chat relay feature coming soon")
        placeholder.setObjectName("placeholder")
        layout.addWidget(placeholder)
        
        return card
    
    def open_limitless(self):
        """Open Limitless TCG website"""
        webbrowser.open("https://play.limitlesstcg.com/")
    
    def load_stats(self):
        """Load and display all statistics"""
        try:
            stats_scroll_value = None
            if hasattr(self, "stats_scroll"):
                try:
                    stats_scroll_value = self.stats_scroll.verticalScrollBar().value()
                except Exception:
                    stats_scroll_value = None

            # Get overall stats
            total, wins, losses, best_elo, worst_elo = self.db.get_all_time_stats()
            current_elo = self.db.get_current_rank()
            
            self.total_games_label.setText(str(total))
            self.total_wins_label.setText(str(wins))
            self.total_losses_label.setText(str(losses))
            
            if total > 0:
                win_rate = (wins / total) * 100
                self.win_rate_label.setText(f"{win_rate:.1f}%")
            else:
                self.win_rate_label.setText("0%")
            
            self.current_elo_label.setText(str(current_elo) if current_elo else "--")
            self.best_elo_label.setText(str(best_elo) if best_elo else "--")
            
            # Load graphs
            if MATPLOTLIB_AVAILABLE:
                try:
                    self.update_elo_graph()
                    self.update_winrate_graph()
                except Exception as graph_error:
                    print(f"Graph error: {graph_error}")
                    import traceback
                    traceback.print_exc()
            else:
                print("Warning: matplotlib not available - graphs disabled")
            
            deck_rows = self.db.get_deck_usage_stats(limit=None)
            self.deck_analyses = [
                self._build_deck_analysis(deck_name, games, wins, losses, ties)
                for deck_name, games, wins, losses, ties in deck_rows
            ]
            
            # Load deck usage
            self.update_deck_usage(self.deck_analyses)
            self._deck_dashboards_dirty = True
            if hasattr(self, "tab_widget") and self.tab_widget.currentIndex() == getattr(self, "decks_tab_index", -1):
                self._refresh_deck_dashboards(self.deck_analyses)
            
            # Load recent battles
            self.update_recent_battles()

            if stats_scroll_value is not None and hasattr(self, "stats_scroll"):
                QTimer.singleShot(0, lambda v=stats_scroll_value: self._restore_scroll_value(self.stats_scroll, v))
            
        except Exception as e:
            print(f"Error loading stats: {e}")
            import traceback
            traceback.print_exc()
    
    def update_elo_graph(self):
        """Update Elo progression graph"""
        try:
            data = self.db.get_elo_history(limit=None)
            if not data:
                return
            
            # Parse timestamps and elos
            times = []
            elos = []
            for row in data:
                try:
                    times.append(datetime.fromisoformat(row[0]))
                    elos.append(int(row[1]))
                except:
                    continue
            
            if not times or not elos:
                return

            self._update_elo_scale_visibility(times)

            if self.elo_time_scale != "all":
                days = self.elo_time_scale_days.get(self.elo_time_scale)
                if days:
                    cutoff = times[-1] - timedelta(days=days)
                    filtered = [(time_value, elo_value) for time_value, elo_value in zip(times, elos) if time_value >= cutoff]
                    if filtered:
                        times = [time_value for time_value, _ in filtered]
                        elos = [elo_value for _, elo_value in filtered]
            
            # Clear previous plot
            self.elo_canvas.axes.cla()
            
            # Set dark transparent background  
            self.elo_canvas.axes.set_facecolor((0.04, 0.04, 0.04, 0.3))
            self.elo_canvas.figure.patch.set_facecolor('none')
            self.elo_canvas.figure.patch.set_alpha(0)
            
            # Plot the main line
            self.elo_canvas.axes.plot(times, elos, 
                                     color='#4A9FD8', 
                                     linewidth=2.5,
                                     marker='o',
                                     markersize=5,
                                     markerfacecolor='#6BB6E8',
                                     markeredgecolor='#4A9FD8',
                                     markeredgewidth=1.5)
            
            # Fill area under curve
            self.elo_canvas.axes.fill_between(times, elos, 
                                             min(elos) - 10,
                                             alpha=0.2,
                                             color='#4A9FD8')
            
            # Set y limits with padding
            y_range = max(elos) - min(elos)
            padding = max(10, y_range * 0.15)
            self.elo_canvas.axes.set_ylim(min(elos) - padding, max(elos) + padding)
            
            # Style the axes
            self.elo_canvas.axes.tick_params(colors='#666666', labelsize=8)
            self.elo_canvas.axes.grid(True, alpha=0.1, color='#444444', linewidth=0.5)
            
            # Remove spines
            self.elo_canvas.axes.spines['top'].set_visible(False)
            self.elo_canvas.axes.spines['right'].set_visible(False)
            self.elo_canvas.axes.spines['bottom'].set_color('#2a2a2a')
            self.elo_canvas.axes.spines['left'].set_color('#2a2a2a')
            self.elo_canvas.axes.spines['bottom'].set_linewidth(0.5)
            self.elo_canvas.axes.spines['left'].set_linewidth(0.5)
            
            # Smart date formatting based on time range
            time_range = (times[-1] - times[0]).total_seconds()
            if time_range < 3600:  # Less than 1 hour
                date_format = '%H:%M'
            elif time_range < 86400:  # Less than 1 day
                date_format = '%H:%M'
            elif time_range < 604800:  # Less than 1 week
                date_format = '%m/%d %H:%M'
            else:  # 1 week or more
                date_format = '%m/%d'
            
            # Select evenly spaced tick positions (max 4-5 ticks for better spacing)
            num_points = len(times)
            if num_points <= 4:
                tick_indices = range(num_points)
            else:
                # Always include first and last, space out the rest
                step = max(1, num_points // 4)
                tick_indices = list(range(0, num_points, step))
                # Always include the last point
                if tick_indices[-1] != num_points - 1:
                    tick_indices.append(num_points - 1)
            
            # Format x-axis labels for selected ticks only
            tick_positions = [times[i] for i in tick_indices]
            tick_labels = [times[i].strftime(date_format) for i in tick_indices]
            
            self.elo_canvas.axes.set_xticks(tick_positions)
            self.elo_canvas.axes.set_xticklabels(tick_labels, rotation=35, ha='right', fontsize=8)
            
            # Manual positioning with more bottom space for rotated labels
            self.elo_canvas.figure.subplots_adjust(left=0.15, right=0.95, top=0.95, bottom=0.25)
            
            # Redraw
            self.elo_canvas.draw()
            
        except Exception as e:
            print(f"Error in Elo graph: {e}")
            import traceback
            traceback.print_exc()
    
    def update_winrate_graph(self):
        """Update win rate graph"""
        try:
            data = self.db.get_win_rate_over_time(days=30)
            if not data:
                return
            
            # Parse dates and win rates
            dates = []
            win_rates = []
            ci_lows = []
            ci_highs = []
            for row in data:
                try:
                    dates.append(datetime.strptime(row[0], '%Y-%m-%d'))
                    wr = (row[1] / row[3]) * 100 if row[3] > 0 else 0
                    win_rates.append(wr)
                    low, high = wilson_interval(int(row[1] or 0), int(row[3] or 0))
                    ci_lows.append(low * 100)
                    ci_highs.append(high * 100)
                except:
                    continue
            
            if not dates or not win_rates:
                return
            
            # Clear previous plot
            self.winrate_canvas.axes.cla()
            
            # Set dark transparent background
            self.winrate_canvas.axes.set_facecolor((0.04, 0.04, 0.04, 0.3))
            self.winrate_canvas.figure.patch.set_facecolor('none')
            self.winrate_canvas.figure.patch.set_alpha(0)
            
            # Confidence band for daily estimates
            self.winrate_canvas.axes.fill_between(
                dates,
                ci_lows,
                ci_highs,
                alpha=0.14,
                color="#9CC344",
            )

            # Plot the main line
            self.winrate_canvas.axes.plot(dates, win_rates,
                                         color='#9CC344',
                                         linewidth=2.5,
                                         marker='s',
                                         markersize=5,
                                         markerfacecolor='#B4D96A',
                                         markeredgecolor='#9CC344',
                                         markeredgewidth=1.5)
            
            # Fill area under curve
            self.winrate_canvas.axes.fill_between(dates, win_rates, 0,
                                                  alpha=0.08,
                                                  color='#9CC344')
            
            # Add 50% reference line
            self.winrate_canvas.axes.axhline(y=50,
                                            color='#666666',
                                            linestyle='--',
                                            linewidth=1,
                                            alpha=0.4)
            
            # Set y limits
            self.winrate_canvas.axes.set_ylim(0, 105)
            
            # Style the axes
            self.winrate_canvas.axes.tick_params(colors='#666666', labelsize=8)
            self.winrate_canvas.axes.grid(True, alpha=0.1, color='#444444', linewidth=0.5)
            
            # Remove spines
            self.winrate_canvas.axes.spines['top'].set_visible(False)
            self.winrate_canvas.axes.spines['right'].set_visible(False)
            self.winrate_canvas.axes.spines['bottom'].set_color('#2a2a2a')
            self.winrate_canvas.axes.spines['left'].set_color('#2a2a2a')
            self.winrate_canvas.axes.spines['bottom'].set_linewidth(0.5)
            self.winrate_canvas.axes.spines['left'].set_linewidth(0.5)
            
            # Smart date formatting based on date range
            date_range = (dates[-1] - dates[0]).days
            if date_range <= 7:  # 1 week or less
                date_format = '%m/%d'
            elif date_range <= 30:  # 1 month or less
                date_format = '%m/%d'
            else:  # More than 1 month
                date_format = '%m/%d'
            
            # Format x-axis labels
            formatted_labels = []
            for d in dates:
                formatted_labels.append(d.strftime(date_format))
            
            self.winrate_canvas.axes.set_xticks(dates)
            self.winrate_canvas.axes.set_xticklabels(formatted_labels, rotation=45, ha='right')
            
            # Manual positioning
            self.winrate_canvas.figure.subplots_adjust(left=0.15, right=0.95, top=0.95, bottom=0.2)
            
            # Redraw
            self.winrate_canvas.draw()
            
        except Exception as e:
            print(f"Error in win rate graph: {e}")
            import traceback
            traceback.print_exc()
    
    def update_deck_usage(self, deck_analyses=None):
        """Update the dashboard deck summary with richer, clickable deck stats."""
        try:
            # Clear existing
            while self.deck_list_layout.count():
                child = self.deck_list_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            deck_analyses = deck_analyses if deck_analyses is not None else self.deck_analyses
            
            if not deck_analyses:
                no_data = QLabel("No deck data yet")
                no_data.setObjectName("noData")
                no_data.setStyleSheet("color: rgba(255, 255, 255, 0.3); font-size: 11px; font-style: italic;")
                self.deck_list_layout.addWidget(no_data)
                return
            
            for analysis in deck_analyses[:8]:
                summary = analysis.get("summary", {})
                bayes_pct = summary.get("bayes_mean", 0) * 100.0
                ci_low = summary.get("ci_low", 0) * 100.0
                ci_high = summary.get("ci_high", 0) * 100.0
                matched_meta = analysis.get("matched_meta")
                deck_icons = analysis.get("deck_icons", [])

                row_button = QPushButton()
                row_button.setCursor(Qt.CursorShape.PointingHandCursor)
                row_button.setMinimumHeight(58)
                row_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                row_button.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(255, 255, 255, 0.025);
                        border-radius: 8px;
                        border: 1px solid rgba(255,255,255,0.04);
                        text-align: left;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background-color: rgba(255, 255, 255, 0.06);
                        border-color: rgba(74,159,216,0.25);
                    }
                """)
                row_button.clicked.connect(lambda checked=False, deck_name=analysis.get("deck_name", ""): self.open_deck_dashboard(deck_name))

                row_layout = QVBoxLayout(row_button)
                row_layout.setContentsMargins(10, 8, 10, 8)
                row_layout.setSpacing(6)

                top_row = QHBoxLayout()
                top_row.setContentsMargins(0, 0, 0, 0)
                top_row.setSpacing(8)
                deck_cell = self._create_deck_cell_widget(
                    analysis.get("deck_name", ""),
                    deck_icons,
                    subtitle=f"{analysis.get('record')} • {analysis.get('games')} game{'s' if analysis.get('games', 0) != 1 else ''}",
                )
                self._set_mouse_passthrough(deck_cell)
                top_row.addWidget(deck_cell)
                top_row.addStretch()

                right_col = QVBoxLayout()
                right_col.setContentsMargins(0, 0, 0, 0)
                right_col.setSpacing(1)

                wr_label = QLabel(f"{bayes_pct:.1f}% Bayesian WR")
                wr_label.setStyleSheet(f"color: {self._percent_accent(bayes_pct)}; font-size: 11px; font-weight: 700;")
                wr_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                wr_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                right_col.addWidget(wr_label)

                meta_text = f"95% CI {ci_low:.0f}% - {ci_high:.0f}%"
                if matched_meta:
                    meta_text += f" • Meta #{matched_meta.get('rank')}"
                else:
                    meta_text += " • Local sample"
                meta_label = QLabel(meta_text)
                meta_label.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 9px;")
                meta_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                meta_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                right_col.addWidget(meta_label)
                top_row.addLayout(right_col)
                row_layout.addLayout(top_row)

                bar_container = QFrame()
                bar_container.setFixedHeight(6)
                bar_container.setStyleSheet("""
                    QFrame {
                        background-color: rgba(255, 255, 255, 0.05);
                        border-radius: 3px;
                    }
                """)

                bar_layout = QHBoxLayout(bar_container)
                bar_layout.setContentsMargins(0, 0, 0, 0)
                bar_layout.setSpacing(0)
                fill_bar = QFrame()
                fill_bar.setFixedHeight(6)
                gradient_color = (
                    "stop:0 #66BB6A, stop:1 #81C784" if bayes_pct >= 55 else
                    "stop:0 #4A9FD8, stop:1 #6BB6E8" if bayes_pct >= 50 else
                    "stop:0 #EF5350, stop:1 #E57373"
                )
                fill_bar.setStyleSheet(f"""
                    QFrame {{
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {gradient_color});
                        border-radius: 3px;
                    }}
                """)
                bar_container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                fill_bar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                fill = max(0, min(100, int(round(bayes_pct))))
                bar_layout.addWidget(fill_bar, fill)
                bar_layout.addStretch(max(0, 100 - fill))
                row_layout.addWidget(bar_container)

                self.deck_list_layout.addWidget(row_button)
        
        except Exception as e:
            print(f"Error updating deck usage: {e}")
    
    def update_recent_battles(self):
        """Update recent battles with modern styling"""
        try:
            # Clear existing
            while self.battles_list_layout.count():
                child = self.battles_list_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            battles = self.db.get_recent_battles(limit=10)
            
            if not battles:
                no_data = QLabel("No battles yet")
                no_data.setStyleSheet("color: rgba(255, 255, 255, 0.3); font-size: 11px; font-style: italic;")
                self.battles_list_layout.addWidget(no_data)
                return
            
            for battle in battles:
                timestamp, my_deck, opp_deck, result, my_rank, log_file, is_tournament = battle
                
                battle_row = QPushButton()  # Changed to QPushButton for clickability
                battle_row.setFixedHeight(32)
                battle_row.setCursor(Qt.CursorShape.PointingHandCursor)
                battle_row.setStyleSheet("""
                    QPushButton {
                        background-color: rgba(255, 255, 255, 0.02);
                        border-radius: 4px;
                        border: none;
                        text-align: left;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background-color: rgba(255, 255, 255, 0.06);
                    }
                    QPushButton:pressed {
                        background-color: rgba(255, 255, 255, 0.08);
                    }
                """)
                
                # Connect click event
                if log_file:
                    battle_row.clicked.connect(lambda checked=False, lf=log_file: self.open_battle_replay(lf))
                    battle_row.setToolTip(
                        f"Click to open this battle in PTCGL Replay: {os.path.basename(log_file) if log_file else 'N/A'}"
                    )
                
                layout = QHBoxLayout(battle_row)
                layout.setContentsMargins(10, 4, 10, 4)
                layout.setSpacing(10)
                
                # Result indicator
                result_indicator = QFrame()
                result_indicator.setFixedSize(4, 20)
                color = "#66BB6A" if result == "Win" else "#EF5350"
                result_indicator.setStyleSheet(f"""
                    QFrame {{
                        background-color: {color};
                        border-radius: 2px;
                    }}
                """)
                layout.addWidget(result_indicator)
                
                # Decks
                decks_text = f"{my_deck[:18]} vs {opp_deck[:18]}"
                decks_label = QLabel(decks_text)
                decks_label.setStyleSheet("color: rgba(255, 255, 255, 0.8); font-size: 10px;")
                layout.addWidget(decks_label)

                # Yellow "Limitless Tournament" tag for tournament games
                if is_tournament:
                    tourney_tag = QLabel("Limitless Tournament")
                    tourney_tag.setStyleSheet("""
                        QLabel {
                            color: #FFD54F;
                            background-color: rgba(255, 213, 79, 0.12);
                            border: 1px solid rgba(255, 213, 79, 0.45);
                            border-radius: 3px;
                            font-size: 8px;
                            font-weight: 600;
                            padding: 1px 5px;
                        }
                    """)
                    layout.addWidget(tourney_tag)
                
                layout.addStretch()
                
                # Time
                try:
                    time_obj = datetime.fromisoformat(timestamp)
                    time_str = time_obj.strftime("%m/%d %H:%M")
                except:
                    time_str = "Unknown"
                
                time_label = QLabel(time_str)
                time_label.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-size: 9px;")
                time_label.setFixedWidth(65)
                layout.addWidget(time_label)
                
                self.battles_list_layout.addWidget(battle_row)
        
        except Exception as e:
            print(f"Error updating recent battles: {e}")
    
    def _resolve_log_file_path(self, log_file_path):
        if not log_file_path:
            return None
        resolved_path = log_file_path
        if not os.path.isabs(resolved_path):
            resolved_path = os.path.join(BASE_DIR, "Logs", resolved_path)
        return os.path.abspath(resolved_path)

    def _launch_ptcgl_replay_browser(self, log_file_path, *, headless=False, action_index=0):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            raise RuntimeError(f"Playwright is not available: {e}") from e

        with sync_playwright() as playwright:
            browser = None
            context = None
            launch_kwargs = {
                "headless": headless,
                "args": ["--new-window", "--start-maximized"],
            }
            launch_attempts = [
                ("msedge", lambda: playwright.chromium.launch(channel="msedge", **launch_kwargs)),
                ("chrome", lambda: playwright.chromium.launch(channel="chrome", **launch_kwargs)),
                ("chromium", lambda: playwright.chromium.launch(**launch_kwargs)),
            ]

            last_error = None
            for browser_name, launcher in launch_attempts:
                try:
                    browser = launcher()
                    context_kwargs = {}
                    if not headless:
                        context_kwargs["no_viewport"] = True
                    context = browser.new_context(**context_kwargs)
                    print(f"Opened PTCGL Replay using {browser_name}")
                    break
                except Exception as e:
                    last_error = e
                    browser = None
                    context = None

            if context is None:
                raise RuntimeError(f"Unable to launch a supported browser for PTCGL Replay: {last_error}")

            try:
                page = context.new_page()
                page.goto(PTCGL_REPLAY_URL, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_selector('input[type="file"][accept=".txt"]', state="attached", timeout=60000)
                page.locator('input[type="file"][accept=".txt"]').set_input_files(log_file_path)
                page.wait_for_timeout(1500)
                page.wait_for_load_state("networkidle", timeout=60000)
                page.wait_for_selector("text=ACTION LOG", timeout=15000)
                try:
                    action_index = max(0, int(action_index or 0))
                except Exception:
                    action_index = 0
                if action_index > 0:
                    next_action = page.locator('button[title="Next action"]')
                    for _ in range(action_index):
                        next_action.click(timeout=5000)
                        page.wait_for_timeout(35)
                page.bring_to_front()
                if headless:
                    return
                while any(not open_page.is_closed() for open_page in context.pages):
                    time.sleep(1.0)
            finally:
                try:
                    context.close()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass

    def _build_ptcgl_replay_helper_script(self):
        return textwrap.dedent(
            f"""
            import sys
            import time

            PTCGL_REPLAY_URL = {PTCGL_REPLAY_URL!r}

            def main():
                if len(sys.argv) < 2:
                    raise RuntimeError("Missing battle log path")
                log_file_path = sys.argv[1]
                headless = "--headless" in sys.argv[2:]
                action_index = 0
                for arg in sys.argv[2:]:
                    if arg.startswith("--action-index="):
                        try:
                            action_index = max(0, int(arg.split("=", 1)[1]))
                        except Exception:
                            action_index = 0
                from playwright.sync_api import sync_playwright

                with sync_playwright() as playwright:
                    browser = None
                    context = None
                    launch_kwargs = {{
                        "headless": headless,
                        "args": ["--new-window", "--start-maximized"],
                    }}
                    launch_attempts = [
                        ("msedge", lambda: playwright.chromium.launch(channel="msedge", **launch_kwargs)),
                        ("chrome", lambda: playwright.chromium.launch(channel="chrome", **launch_kwargs)),
                        ("chromium", lambda: playwright.chromium.launch(**launch_kwargs)),
                    ]
                    last_error = None
                    for browser_name, launcher in launch_attempts:
                        try:
                            browser = launcher()
                            context_kwargs = {{}}
                            if not headless:
                                context_kwargs["no_viewport"] = True
                            context = browser.new_context(**context_kwargs)
                            print(f"Opened PTCGL Replay using {{browser_name}}")
                            break
                        except Exception as exc:
                            last_error = exc
                            browser = None
                            context = None

                    if context is None:
                        raise RuntimeError(f"Unable to launch a supported browser for PTCGL Replay: {{last_error}}")

                    try:
                        page = context.new_page()
                        page.goto(PTCGL_REPLAY_URL, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_selector('input[type="file"][accept=".txt"]', state="attached", timeout=60000)
                        page.locator('input[type="file"][accept=".txt"]').set_input_files(log_file_path)
                        page.wait_for_timeout(1500)
                        page.wait_for_load_state("networkidle", timeout=60000)
                        page.wait_for_selector("text=ACTION LOG", timeout=15000)
                        if action_index > 0:
                            next_action = page.locator('button[title="Next action"]')
                            for _ in range(action_index):
                                next_action.click(timeout=5000)
                                page.wait_for_timeout(35)
                        page.bring_to_front()
                        if headless:
                            return
                        while any(not open_page.is_closed() for open_page in context.pages):
                            time.sleep(1.0)
                    finally:
                        try:
                            context.close()
                        except Exception:
                            pass
                        try:
                            browser.close()
                        except Exception:
                            pass

            if __name__ == "__main__":
                main()
            """
        )

    def _launch_ptcgl_replay_helper(self, log_file_path, *, headless=False, action_index=0):
        command = [sys.executable, "-c", self._build_ptcgl_replay_helper_script(), log_file_path]
        if headless:
            command.append("--headless")
        if action_index:
            command.append(f"--action-index={int(action_index)}")
        popen_kwargs = {
            "cwd": BASE_DIR,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.Popen(command, **popen_kwargs)

    def open_battle_replay(self, log_file_path):
        """Open a battle log in PTCGL Replay and auto-load the .txt file."""
        try:
            resolved_path = self._resolve_log_file_path(log_file_path)
            if not resolved_path:
                print("No log file associated with this battle")
                return
            if not os.path.exists(resolved_path):
                print(f"Log file not found: {resolved_path}")
                return

            if WEBENGINE_AVAILABLE and getattr(self, "replay_view", None) is not None and getattr(self, "replay_page", None) is not None:
                self._replay_request_token += 1
                self.replay_pending_log_path = resolved_path
                self.replay_status_label.setText(f"Closing previous replay and loading {os.path.basename(resolved_path)}…")
                self._rebuild_replay_page()
                self.replay_page.queue_upload(resolved_path)
                self._set_replay_tab_visible(True)
                self.tab_widget.setCurrentIndex(self.replay_tab_index)
                self.replay_view.load(QUrl(PTCGL_REPLAY_URL))
                print(f"Opening battle replay in embedded tab for: {resolved_path}")
                return

            def worker():
                try:
                    self._launch_ptcgl_replay_browser(resolved_path, headless=False)
                except Exception as e:
                    print(f"Error opening PTCGL Replay: {e}")
                    try:
                        self._launch_ptcgl_replay_helper(resolved_path, headless=False)
                    except Exception as helper_error:
                        print(f"Replay helper fallback failed: {helper_error}")
                        try:
                            webbrowser.open(PTCGL_REPLAY_URL)
                        except Exception:
                            pass

            threading.Thread(target=worker, daemon=True).start()
            print(f"Opening battle replay for: {resolved_path}")
        except Exception as e:
            print(f"Error starting PTCGL Replay launch: {e}")

    def _set_battle_mgmt_status(self, message, *, error=False):
        if not hasattr(self, "battle_mgmt_status_label"):
            return
        color = "rgba(255, 170, 170, 0.9)" if error else "rgba(255, 255, 255, 0.62)"
        self.battle_mgmt_status_label.setStyleSheet(f"color: {color}; font-size: 10px;")
        self.battle_mgmt_status_label.setText(message)

    def _handle_battle_mgmt_cell_clicked(self, row, column):
        table = getattr(self, "battle_mgmt_table", None)
        if table is None:
            return
        # Clicking the Log column opens the battle log file on the PC.
        if column == 7:
            item = table.item(row, column)
            if item is None:
                return
            log_name = item.data(Qt.ItemDataRole.UserRole + 1)
            if log_name:
                self.open_log_file_on_pc(log_name)
            return
        if column not in (1, 2, 3, 4, 5, 6):
            return
        item = table.item(row, column)
        if item and (item.flags() & Qt.ItemFlag.ItemIsEditable):
            table.editItem(item)

    def open_log_file_on_pc(self, log_file_path):
        """Open a battle log .txt file with the default text editor."""
        try:
            resolved_path = self._resolve_log_file_path(log_file_path)
            if not resolved_path or not os.path.exists(resolved_path):
                self._set_battle_mgmt_status(f"Log file not found: {log_file_path}", error=True)
                return
            if os.name == "nt":
                os.startfile(resolved_path)  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open", resolved_path])
            self._set_battle_mgmt_status(f"Opened log: {os.path.basename(resolved_path)}")
        except Exception as exc:
            self._set_battle_mgmt_status(f"Could not open log: {exc}", error=True)

    def _normalize_battle_mgmt_field(self, column, raw_value):
        text = (raw_value or "").strip()
        if column in (1, 2):
            return text or "Unknown"
        if column == 3:
            normalized = text.casefold()
            result_map = {
                "win": "Win",
                "w": "Win",
                "loss": "Loss",
                "lose": "Loss",
                "l": "Loss",
                "tie": "Tie",
                "draw": "Tie",
                "t": "Tie",
            }
            if normalized not in result_map:
                raise ValueError("Result must be Win, Loss, or Tie.")
            return result_map[normalized]
        if column == 4:
            if not text:
                return None
            rank = int(text)
            if rank < 0:
                raise ValueError("Rank must be 0 or higher.")
            return rank
        if column == 5:
            if not text:
                return None
            confidence = int(text)
            if confidence < 0 or confidence > 100:
                raise ValueError("Confidence must be between 0 and 100.")
            return confidence
        if column == 6:
            return text or "Manual"
        raise ValueError("That field is not editable.")

    def _make_battle_mgmt_item(self, battle_id, value, *, editable=False):
        item = QTableWidgetItem("" if value is None else str(value))
        item.setData(Qt.ItemDataRole.UserRole, battle_id)
        item.setData(Qt.ItemDataRole.UserRole + 1, value)
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
        if editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        item.setFlags(flags)
        return item

    def _populate_battle_mgmt_action_cell(self, row, column, label, callback, object_name):
        button = QPushButton(label)
        button.setObjectName(object_name)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedHeight(28)
        # Give the button a comfortable minimum width so it's always readable.
        button.setMinimumWidth(84)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(callback)
        # Wrap in a container with small margins so the button fills the cell
        # width and has breathing room.
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wrap_layout = QHBoxLayout(wrapper)
        wrap_layout.setContentsMargins(4, 3, 4, 3)
        wrap_layout.setSpacing(0)
        wrap_layout.addWidget(button)
        self.battle_mgmt_table.setCellWidget(row, column, wrapper)

    def _handle_battle_mgmt_item_changed(self, item):
        if not item or getattr(self, "_battle_mgmt_populating", False):
            return

        column = item.column()
        if column not in (1, 2, 3, 4, 5, 6):
            return

        battle_id = item.data(Qt.ItemDataRole.UserRole)
        original_value = item.data(Qt.ItemDataRole.UserRole + 1)
        if not battle_id:
            return

        try:
            normalized_value = self._normalize_battle_mgmt_field(column, item.text())
        except Exception as exc:
            self._battle_mgmt_populating = True
            try:
                item.setText("" if original_value is None else str(original_value))
            finally:
                self._battle_mgmt_populating = False
            self._set_battle_mgmt_status(f"Battle #{battle_id} not saved: {exc}", error=True)
            return

        if normalized_value == original_value:
            return

        field_map = {
            1: "my_deck",
            2: "opponent_deck",
            3: "result",
            4: "my_rank",
            5: "confidence",
            6: "deck_source",
        }
        updates = {field_map[column]: normalized_value}

        try:
            changed = self.db.update_battle_record(battle_id, updates=updates)
        except Exception as exc:
            self._battle_mgmt_populating = True
            try:
                item.setText("" if original_value is None else str(original_value))
            finally:
                self._battle_mgmt_populating = False
            self._set_battle_mgmt_status(f"Battle #{battle_id} failed to save: {exc}", error=True)
            return

        if not changed:
            self._set_battle_mgmt_status(f"Battle #{battle_id} could not be updated.", error=True)
            return

        self._battle_mgmt_populating = True
        try:
            item.setText("" if normalized_value is None else str(normalized_value))
        finally:
            self._battle_mgmt_populating = False
        item.setData(Qt.ItemDataRole.UserRole + 1, normalized_value)
        self._set_battle_mgmt_status(f"Saved battle #{battle_id}.")
        self._deck_dashboards_dirty = True
        QTimer.singleShot(0, self.load_stats)
    
    def refresh_battle_management(self):
        """Refresh the battle management editor."""
        table = getattr(self, "battle_mgmt_table", None)
        if table is None:
            return

        try:
            self._battle_mgmt_populating = True
            table.clearContents()
            table.setRowCount(0)

            battles = self.db.get_recent_battles_with_ids(limit=20)
            if not battles:
                self._set_battle_mgmt_status("No battles found.")
                return

            for row, battle in enumerate(battles):
                table.insertRow(row)
                battle_id, timestamp, my_deck, opp_deck, result, my_rank, confidence, deck_source, log_file, is_tournament = battle

                try:
                    time_obj = datetime.fromisoformat(timestamp)
                    time_str = time_obj.strftime("%m/%d/%Y %H:%M:%S")
                except Exception:
                    time_str = timestamp

                items = [
                    self._make_battle_mgmt_item(battle_id, time_str, editable=False),
                    self._make_battle_mgmt_item(battle_id, my_deck, editable=True),
                    self._make_battle_mgmt_item(battle_id, opp_deck, editable=True),
                    self._make_battle_mgmt_item(battle_id, result, editable=True),
                    self._make_battle_mgmt_item(battle_id, my_rank, editable=True),
                    self._make_battle_mgmt_item(battle_id, confidence, editable=True),
                    self._make_battle_mgmt_item(battle_id, deck_source, editable=True),
                    self._make_battle_mgmt_item(battle_id, os.path.basename(log_file) if log_file else "", editable=False),
                    self._make_battle_mgmt_item(battle_id, "T" if is_tournament else "", editable=False),
                ]
                for column, item in enumerate(items):
                    table.setItem(row, column, item)

                if log_file:
                    self._populate_battle_mgmt_action_cell(
                        row,
                        9,
                        "Replay",
                        lambda checked=False, lf=log_file: self.open_battle_replay(lf),
                        "battleMgmtReplayBtn",
                    )
                else:
                    table.setItem(row, 9, self._make_battle_mgmt_item(battle_id, "", editable=False))

                self._populate_battle_mgmt_action_cell(
                    row,
                    10,
                    "Delete",
                    lambda checked=False, bid=battle_id: self.delete_battle(bid),
                    "battleMgmtDeleteBtn",
                )

            self._set_battle_mgmt_status("Click a field to edit it. Changes save automatically.")
            print(f"Loaded {len(battles)} battles for management")

        except Exception as e:
            print(f"Error refreshing battle management: {e}")
            import traceback
            traceback.print_exc()
            self._set_battle_mgmt_status(f"Could not load battle management: {e}", error=True)
        finally:
            self._battle_mgmt_populating = False
    
    def delete_battle(self, battle_id):
        """Delete a battle from the database"""
        try:
            # Confirm deletion
            reply = QMessageBox.question(
                self, 
                'Confirm Delete',
                f'Are you sure you want to delete battle #{battle_id}?\n\nThis will also update your session stats.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                return

            if not self.db.delete_battle(battle_id):
                self._set_battle_mgmt_status(f"Battle #{battle_id} was not found.", error=True)
                return
            
            print(f"✓ Deleted battle #{battle_id}")
            
            # Refresh the list and main stats
            self.refresh_battle_management()
            self._set_battle_mgmt_status(f"Deleted battle #{battle_id}.")
            self._deck_dashboards_dirty = True
            self.load_stats()
            
        except Exception as e:
            print(f"Error deleting battle: {e}")
            import traceback
            traceback.print_exc()
            self._set_battle_mgmt_status(f"Could not delete battle #{battle_id}: {e}", error=True)
    
    def apply_modern_style(self):
        """Apply modern glass-morphism styling"""
        scale = getattr(self, "surface_opacity_scale", 1.0)

        def alpha(value):
            return max(0.0, min(1.0, value * scale))

        style = """
            /* Main glass container */
            QFrame#glassContainer {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(15, 15, 15, __GLASS_TOP__),
                    stop:1 rgba(10, 10, 10, __GLASS_BOTTOM__));
                border: 1px solid rgba(255, 255, 255, __GLASS_BORDER__);
                border-radius: 12px;
            }
            
            /* Title bar */
            QFrame#titleBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(25, 25, 25, __TITLE_TOP__),
                    stop:1 rgba(15, 15, 15, __TITLE_BOTTOM__));
                border-bottom: 1px solid rgba(255, 255, 255, __TITLE_BORDER__);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }

            QFrame#footerBar {
                background: rgba(12, 17, 26, __FOOTER_BG__);
                border-top: 1px solid rgba(255, 255, 255, __FOOTER_BORDER__);
                border-bottom-left-radius: 12px;
                border-bottom-right-radius: 12px;
            }

            QSlider#opacitySlider {
                background: transparent;
            }
            QSlider#opacitySlider::groove:horizontal {
                height: 4px;
                background: rgba(255,255,255,__SLIDER_GROOVE__);
                border-radius: 2px;
            }
            QSlider#opacitySlider::sub-page:horizontal {
                background: rgba(74,159,216,__SLIDER_FILL__);
                border-radius: 2px;
            }
            QSlider#opacitySlider::handle:horizontal {
                width: 9px;
                margin: -4px 0;
                border-radius: 4px;
                background: rgba(235,243,252,__SLIDER_HANDLE__);
                border: 1px solid rgba(255,255,255,__SLIDER_HANDLE_BORDER__);
            }
            QSlider#opacitySlider::handle:horizontal:hover {
                background: rgba(255,255,255,__SLIDER_HANDLE_HOVER__);
                border-color: rgba(74,159,216,__SLIDER_HANDLE_HOVER_BORDER__);
            }

            QLabel#titleText {
                color: rgba(255, 255, 255, 0.95);
                font-family: 'Segoe UI', 'San Francisco', Arial;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 2px;
            }
            
            /* Buttons */
            QPushButton#minBtn, QPushButton#closeBtn {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                color: rgba(255, 255, 255, 0.7);
                font-size: 18px;
                font-weight: 300;
            }
            
            QPushButton#minBtn:hover {
                background-color: rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.9);
            }
            
            QPushButton#closeBtn:hover {
                background-color: rgba(239, 83, 80, 0.3);
                border-color: rgba(239, 83, 80, 0.5);
                color: #EF5350;
            }
            
            /* Scroll area */
            QScrollArea#scrollArea {
                background-color: transparent;
                border: none;
            }
            
            QWidget#contentWidget {
                background-color: transparent;
            }
            
            /* Scrollbar */
            QScrollBar:vertical {
                background-color: transparent;
                width: 8px;
                margin: 0px;
            }
            
            QScrollBar::handle:vertical {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                min-height: 20px;
            }
            
            QScrollBar::handle:vertical:hover {
                background-color: rgba(255, 255, 255, 0.15);
            }
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            
            /* Section cards */
            QFrame#graphCard, QFrame#deckCard, QFrame#battlesCard, QFrame#limitlessCard, QFrame#deckDashboardCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 255, 255, 0.03),
                    stop:1 rgba(255, 255, 255, 0.01));
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 10px;
            }

            QFrame#deckRecentBattleRow {
                background-color: rgba(255,255,255,0.025);
                border: 1px solid rgba(255,255,255,0.04);
                border-radius: 8px;
            }
            
            QLabel#graphTitle, QLabel#sectionHeader {
                color: rgba(255, 255, 255, 0.7);
                font-family: 'Segoe UI', 'San Francisco', Arial;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 1.5px;
            }

            QLabel#deckInsightText {
                color: rgba(212,224,241,0.78);
                font-size: 10px;
                line-height: 1.35;
            }

            QLabel#deckPageTitle {
                color: rgba(246,250,255,0.98);
                font-size: 24px;
                font-weight: 700;
            }

            QLabel#deckPageSubtitle {
                color: rgba(168,182,204,0.82);
                font-size: 11px;
                font-weight: 500;
            }

            QFrame#deckMetricCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255,255,255,0.045),
                    stop:1 rgba(255,255,255,0.018));
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 9px;
            }

            QLabel#deckScaleValue {
                color: rgba(245,249,255,0.96);
                font-size: 20px;
                font-weight: 700;
            }

            QLabel#deckMetricNote {
                color: rgba(164,181,203,0.72);
                font-size: 9px;
            }

            QFrame#deckScaleTrack {
                min-height: 8px;
                background-color: rgba(255,255,255,0.06);
                border-radius: 4px;
            }

            QFrame#metaStatsBar {
                background: transparent;
                border: none;
            }

            QFrame#metaStatCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255,255,255,0.05),
                    stop:1 rgba(255,255,255,0.02));
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 8px;
            }

            QLabel#metaStatValue {
                color: rgba(245,249,255,0.96);
                font-size: 16px;
                font-weight: 700;
            }

            QLabel#metaStatTitle {
                color: rgba(164,181,203,0.72);
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1px;
            }
            
            /* Limitless button */
            QPushButton#limitlessBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(74, 159, 216, 0.3),
                    stop:1 rgba(107, 182, 232, 0.3));
                border: 1px solid rgba(74, 159, 216, 0.4);
                border-radius: 6px;
                color: rgba(255, 255, 255, 0.95);
                font-family: 'Segoe UI', Arial;
                font-size: 11px;
                font-weight: 600;
                padding: 8px 16px;
            }
            
            QPushButton#limitlessBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(74, 159, 216, 0.5),
                    stop:1 rgba(107, 182, 232, 0.5));
                border-color: rgba(74, 159, 216, 0.6);
            }
            
            QLabel#placeholder {
                color: rgba(255, 255, 255, 0.3);
                font-size: 10px;
                font-style: italic;
            }
            
            /* Tab Widget */
            QTabWidget#mainTabs {
                background-color: transparent;
                border: none;
            }
            
            QTabWidget::pane {
                background: transparent;
                border: none;
                border-top: 1px solid rgba(255, 255, 255, 0.05);
            }
            
            QTabBar::tab {
                background: rgba(255, 255, 255, 0.02);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                color: rgba(255, 255, 255, 0.5);
                font-family: 'Segoe UI', Arial;
                font-size: 11px;
                font-weight: 600;
                padding: 8px 20px;
                margin-right: 4px;
            }
            
            QTabBar::tab:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(74, 159, 216, 0.15),
                    stop:1 rgba(74, 159, 216, 0.05));
                border-color: rgba(74, 159, 216, 0.3);
                color: rgba(255, 255, 255, 0.95);
            }
            
            QTabBar::tab:hover:!selected {
                background: rgba(255, 255, 255, 0.05);
                color: rgba(255, 255, 255, 0.7);
            }

            QTabWidget#deckTabs::pane {
                border: none;
                background: transparent;
                margin-top: 6px;
            }
            QTabWidget#deckTabs QTabBar::tab {
                padding: 6px 14px;
                margin-right: 3px;
                font-size: 10px;
            }

            QLineEdit#deckSearchInput {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 6px;
                color: rgba(245,249,255,0.92);
                font-size: 10px;
                padding: 5px 8px;
            }

            QToolButton#deckSearchBtn {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 6px;
                color: rgba(255,255,255,0.82);
                font-size: 13px;
                font-weight: 700;
                padding: 3px 8px;
            }
            QToolButton#deckSearchBtn:hover {
                background: rgba(74,159,216,0.22);
                border-color: rgba(74,159,216,0.45);
            }

            QToolButton#deckIconArrowBtn {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 6px;
                color: rgba(255,255,255,0.76);
                font-size: 12px;
                font-weight: 700;
                min-width: 22px;
                min-height: 18px;
                padding: 0px 4px 1px 4px;
            }
            QToolButton#deckIconArrowBtn:hover {
                background: rgba(74,159,216,0.22);
                border-color: rgba(74,159,216,0.45);
                color: rgba(255,255,255,0.95);
            }
            
            /* Settings cards and buttons */
            QFrame#settingsCard {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 255, 255, 0.03),
                    stop:1 rgba(255, 255, 255, 0.01));
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 10px;
            }
            
            QPushButton#settingsBtn {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 255, 255, 0.06),
                    stop:1 rgba(255, 255, 255, 0.02));
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                color: rgba(255, 255, 255, 0.9);
                font-family: 'Segoe UI', Arial;
                font-size: 12px;
                font-weight: 500;
                padding: 8px 16px;
            }
            
            QPushButton#settingsBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(74, 159, 216, 0.3),
                    stop:1 rgba(74, 159, 216, 0.1));
                border-color: rgba(74, 159, 216, 0.4);
            }
            QPushButton#settingsBtn:checked {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(74, 159, 216, 0.34),
                    stop:1 rgba(74, 159, 216, 0.14));
                border-color: rgba(74, 159, 216, 0.55);
            }
            
            QLabel#settingsDesc {
                color: rgba(255, 255, 255, 0.5);
                font-size: 11px;
                font-style: italic;
            }

            QPushButton#battleMgmtReplayBtn {
                background: rgba(74,159,216,0.22);
                border: 1px solid rgba(74,159,216,0.40);
                border-radius: 6px;
                color: rgba(238,246,255,0.96);
                font-size: 11px;
                font-weight: 700;
                padding: 4px 10px;
            }
            QPushButton#battleMgmtReplayBtn:hover {
                background: rgba(74,159,216,0.34);
                border-color: rgba(74,159,216,0.55);
            }

            QPushButton#battleMgmtDeleteBtn {
                background: rgba(239, 83, 80, 0.20);
                border: 1px solid rgba(239, 83, 80, 0.36);
                border-radius: 6px;
                color: rgba(255, 204, 204, 0.96);
                font-size: 11px;
                font-weight: 700;
                padding: 4px 10px;
            }
            QPushButton#battleMgmtDeleteBtn:hover {
                background: rgba(239, 83, 80, 0.32);
                border-color: rgba(239, 83, 80, 0.52);
            }

            QLineEdit#metaSearch {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 6px;
                color: rgba(245,249,255,0.92);
                font-size: 11px;
                padding: 8px 10px;
            }

            QLineEdit#metaSearch:focus {
                border-color: rgba(74,159,216,0.45);
                background: rgba(255,255,255,0.07);
            }

            QCheckBox#settingsCheck {
                color: rgba(235,242,250,0.88);
                font-size: 11px;
                spacing: 8px;
            }

            QCheckBox#settingsCheck::indicator {
                width: 14px;
                height: 14px;
                border-radius: 4px;
                border: 1px solid rgba(255,255,255,0.18);
                background: rgba(255,255,255,0.05);
            }

            QCheckBox#settingsCheck::indicator:checked {
                background: rgba(74,159,216,0.75);
                border-color: rgba(74,159,216,0.85);
            }
            
            /* Buy Me a Coffee button */
            QPushButton#coffeeBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(255, 221, 87, 0.4),
                    stop:1 rgba(255, 193, 7, 0.4));
                border: 2px solid rgba(255, 221, 87, 0.6);
                border-radius: 25px;
                color: rgba(255, 255, 255, 0.95);
                font-family: 'Segoe UI', Arial;
                font-size: 14px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }
            
            QPushButton#coffeeBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(255, 221, 87, 0.6),
                    stop:1 rgba(255, 193, 7, 0.6));
                border-color: rgba(255, 221, 87, 0.8);
            }
            
            /* Meta tab buttons */
            QPushButton#metaRefreshBtn {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 5px;
                color: rgba(255,255,255,0.8);
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton#metaRefreshBtn:hover {
                background: rgba(74,159,216,0.25);
                border-color: rgba(74,159,216,0.5);
            }
            QPushButton#metaRefreshBtn:disabled {
                color: rgba(255,255,255,0.25);
            }
            
            QPushButton#metaNavBtn {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 5px;
                color: rgba(255,255,255,0.7);
                font-size: 10px;
                font-weight: 600;
                padding: 4px 8px;
            }
            QPushButton#metaNavBtn:hover {
                background: rgba(74,159,216,0.2);
                border-color: rgba(74,159,216,0.4);
                color: rgba(255,255,255,0.95);
            }

            QPushButton#sizePresetBtn {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 4px;
                color: rgba(236,242,252,0.88);
                font-size: 10px;
                font-weight: 700;
            }
            QPushButton#sizePresetBtn:hover {
                background: rgba(74,159,216,0.26);
                border-color: rgba(74,159,216,0.40);
            }

            QPushButton#eloScaleBtn {
                background: rgba(255,255,255,0.035);
                border: 1px solid rgba(255,255,255,0.09);
                border-radius: 5px;
                color: rgba(226,235,246,0.72);
                font-size: 10px;
                font-weight: 600;
                padding: 0px 8px;
            }
            QPushButton#eloScaleBtn:hover {
                background: rgba(255,255,255,0.06);
                border-color: rgba(255,255,255,0.16);
                color: rgba(240,246,255,0.90);
            }
            QPushButton#eloScaleBtn:checked {
                background: rgba(74,159,216,0.18);
                border-color: rgba(74,159,216,0.34);
                color: rgba(244,249,255,0.95);
            }
            
            QComboBox#metaCombo {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 5px;
                color: rgba(255,255,255,0.85);
                font-size: 11px;
                padding: 2px 8px;
            }
            QComboBox#metaCombo::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox#metaCombo QAbstractItemView {
                background: rgb(20,20,20);
                color: rgba(255,255,255,0.85);
                selection-background-color: rgba(74,159,216,0.3);
                border: 1px solid rgba(255,255,255,0.1);
            }

            QFrame#windowSizeHandle {
                background: transparent;
                border: none;
                border-radius: 4px;
            }
            QFrame#windowSizeHandle:hover {
                background: rgba(74,159,216,0.12);
            }
        """
        style = (
            style
            .replace("__GLASS_TOP__", f"{alpha(0.85):.3f}")
            .replace("__GLASS_BOTTOM__", f"{alpha(0.88):.3f}")
            .replace("__GLASS_BORDER__", f"{alpha(0.10):.3f}")
            .replace("__TITLE_TOP__", f"{alpha(0.50):.3f}")
            .replace("__TITLE_BOTTOM__", f"{alpha(0.30):.3f}")
            .replace("__TITLE_BORDER__", f"{alpha(0.05):.3f}")
            .replace("__FOOTER_BG__", f"{alpha(0.88):.3f}")
            .replace("__FOOTER_BORDER__", f"{alpha(0.05):.3f}")
            .replace("__SLIDER_GROOVE__", f"{alpha(0.10):.3f}")
            .replace("__SLIDER_FILL__", f"{alpha(0.34):.3f}")
            .replace("__SLIDER_HANDLE__", f"{alpha(0.68):.3f}")
            .replace("__SLIDER_HANDLE_BORDER__", f"{alpha(0.16):.3f}")
            .replace("__SLIDER_HANDLE_HOVER__", f"{alpha(0.86):.3f}")
            .replace("__SLIDER_HANDLE_HOVER_BORDER__", f"{alpha(0.38):.3f}")
        )
        self.setStyleSheet(style)


def main():
    """Run the stats window standalone"""
    app = QApplication(sys.argv)
    
    window = StatsWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
