"""
Stats Dashboard for Pokemon TCG Live Monitor v2.1
Modern, sleek UI with transparent glass-morphism design
"""

from version import VERSION

import sys
import os
import re
import math
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
    QDialogButtonBox, QComboBox, QCompleter, QSlider, QCheckBox, QListWidget, QListWidgetItem,
    QButtonGroup, QListView
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property, QThread, Signal, QSize, QObject, QPoint, QEvent
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QLinearGradient, QFont, QIcon
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QSizePolicy
from PySide6.QtTest import QTest
from BattleDatabase import BattleDatabase
from weights import cached_expansions, load_weights, save_weights, DEFAULT_WEIGHTS, LABELS as WEIGHT_LABELS
from deck_analytics import (
    CREDIBLE_LEVEL,
    TIE_MODES,
    battle_weight,
    result_rate,
    tie_mode,
    weighted_record,
    bayesian_binomial_summary,
    match_meta_row,
    meta_adjusted_winrate,
    probability_above,
    rank_weighted_winrate,
    sample_confidence,
    verdict_from_probability,
    wilson_interval,
    win_rate_posterior,
)
import japan_data
from charts import SeriesChart
from deck_score import compute_scores
import formulas
from ui_widgets import DeckFlagButton, DeckTabBar, MineRowDelegate, MINE_ROLE
from leagues import LEAGUES, league_name
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


def _short_day(value):
    """'Oct 12' (adds the year when it isn't this year)."""
    text = f"{value:%b} {value.day}"
    return text if value.year == datetime.now().year else f"{text}, {value.year}"


def _clock(value):
    hour = value.hour % 12 or 12
    return f"{hour}:{value:%M} {'AM' if value.hour < 12 else 'PM'}"


def _pct_range(low, high):
    """'53–79%' - how every confidence range is written."""
    return f"{low * 100:.0f}–{high * 100:.0f}%"


RANGE_EXPLAINED = ("Confidence range ({level}%): where the true win rate most likely sits. "
                   "It narrows as you play more games.")


def _range_dates(items, key="t"):
    first, last = items[0][key], items[-1][key]
    if first.date() == last.date():
        return _short_day(first)
    return f"{_short_day(first)} – {_short_day(last)}"


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
# Shared capture file written by the Limitless dashboard manager and read by
# AIParseBattleLog.py so the current match's chat (with round info) can be
# attached to the battle record for later review.
LIMITLESS_CHAT_CAPTURE_FILE = os.path.join(BASE_DIR, ".chat_capture.json")
LIMITLESS_SOUND_FILE = os.path.join(BASE_DIR, "ding.mp3")
LIMITLESS_CHECK_INTERVAL_MS = 60000
LIMITLESS_CHECK_DELAY_MS = 12000
LIMITLESS_CHAT_POLL_INTERVAL_MS = 3000
DECK_ICON_OVERRIDE_FILE = os.path.join(BASE_DIR, ".deck_icon_overrides.json")
PINNED_DECKS_FILE = os.path.join(BASE_DIR, ".pinned_decks.json")
DECK_FLAGS_FILE = os.path.join(BASE_DIR, ".deck_flags.json")  # starred / ignored decks
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


def _invert_str(value):
    """Invert a string so ascending sort yields descending order.

    Complements each byte so lexicographic order reverses. Empty strings sort
    last (least recently played) which is what we want for deck tabs.
    """
    if not value:
        return "\uffff"
    return "".join(chr(0xFFFF - ord(ch)) for ch in value)


def _sprite_cache_path(sprite_name):
    normalized = _normalize_sprite_name(sprite_name)
    if not normalized:
        return None
    # Only [a-z0-9-] reach the filesystem (names come from remote APIs; SEC-08).
    safe = re.sub(r"[^a-z0-9-]", "_", normalized)
    return os.path.join(META_ICON_CACHE_DIR, f"{safe}.png")


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


def _is_safe_web_url(url):
    """Only plain https links are opened in the user's browser (SEC-04)."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(str(url or ""))
    except Exception:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc) and "\\" not in str(url)


def _is_limitless_url(url):
    from urllib.parse import urlparse
    try:
        host = (urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return False
    return _is_safe_web_url(url) and (host == "limitlesstcg.com" or host.endswith(".limitlesstcg.com"))


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

        # While enrolled in a tournament, poll the dashboard every 10s so a
        # new round's match URL (and its check-in button) is picked up immediately —
        # match check-in windows are short and missing one = auto-loss.
        self.tournament_poll_timer = QTimer(self)
        self.tournament_poll_timer.setInterval(10000)
        self.tournament_poll_timer.timeout.connect(self._tournament_poll)

        self.delayed_poll_timer = QTimer(self)
        self.delayed_poll_timer.setSingleShot(True)
        self.delayed_poll_timer.timeout.connect(self.poll_for_checkin)

        self.chat_poll_timer = QTimer(self)
        self.chat_poll_timer.setInterval(LIMITLESS_CHAT_POLL_INTERVAL_MS)
        self.chat_poll_timer.timeout.connect(self.poll_for_chat)

        self._load_state()
        if WEBENGINE_AVAILABLE:
            self._ensure_profile()

    def _tournament_poll(self):
        """Fast poll while in a tournament: reload the dashboard so fresh
        round pairings appear, then scan for the active match + check-in."""
        self.poll_for_checkin()
        # Reload the background dashboard so new-round pairings show up
        # (the React page may otherwise sit stale).
        try:
            if self.background_page is not None:
                self.background_page.load(QUrl(LIMITLESS_DASHBOARD_URL))
        except Exception:
            pass


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

    def _set_enrolled(self, enrolled):
        """Fast-poll the dashboard while a tournament match/check-in is live."""
        try:
            if enrolled:
                if not self.tournament_poll_timer.isActive():
                    self.tournament_poll_timer.start()
            else:
                self.tournament_poll_timer.stop()
        except Exception:
            pass

    def _update_tournament_flag(self, in_tournament, opponent=None):
        """Persist the current tournament-MATCH state for AIParseBattleLog.

        The flag is only written when an active match with a known opponent
        is open (from the match chat page). The parser tags a battle as a
        tournament game only if the battle-log opponent matches, and ignores
        flags older than a few hours. (v2.4: the dashboard-wide "inTournament"
        heuristic matched almost any page and left a stale flag - BUG-017.)
        """
        opponent = (opponent or "").strip()
        self.in_tournament = bool(in_tournament and opponent)
        try:
            if self.in_tournament:
                payload = {"in_tournament": True, "opponent": opponent,
                           "updated_at": datetime.now().isoformat(timespec="seconds")}
                with open(LIMITLESS_TOURNAMENT_FLAG_FILE, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle)
            elif os.path.exists(LIMITLESS_TOURNAMENT_FLAG_FILE):
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
                const clickables = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"], div[role="button"], [role="button"], span[role="button"]'));
                const authText = clickables.map(el => ((el.innerText || el.value || el.getAttribute('aria-label') || '') + '').trim()).join(' ');
                const loginForm = !!document.querySelector('input[type="password"]');
                // Match tournament check-in, match check-in, and late check-in.
                const checkinRe = /(?:match\\s+)?check[\\s-]?in|checkin|late\\s+check[\\s-]?in/i;
                const candidates = [];
                clickables.forEach((el, index) => {
                    const text = ((el.innerText || el.value || el.getAttribute('aria-label') || '') + '').replace(/\\s+/g, ' ').trim();
                    const href = el.href || el.getAttribute('href') || '';
                    if (!visible(el)) return;
                    if (!checkinRe.test(text) && !checkinRe.test(href)) return;
                    el.setAttribute('data-tcglive-checkin-id', String(index));
                    let context = '';
                    const container = el.closest('article, section, .card, .event, .tournament, [class*="event"], [class*="tournament"], li, tr, .dashboard-card, main');
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
                const tournamentHints = /check[\\s-]?in|enrolled|registered|tournament|round \\d+|\\brounds?\\b|\\bstandings\\b|\\bdecklist\\b|\\bmatch\\b/i;
                const inTournament = tournamentHints.test(bodyText) && !/\\/login(?:[?#]|$)/i.test(window.location.pathname + window.location.search);

                // Detect the active match link on the dashboard so the app can
                // navigate to the match page (where match check-in happens).
                // The dashboard only links to YOUR matches, so any /match/
                // link is ours. Prefer the one marked "Active Match" or the
                // current round ("R# vs ..."), else take the first.
                const cleanText = (t) => (t || '').replace(/\\s+/g, ' ').trim();
                let activeMatchUrl = '';
                const matchLinks = Array.from(document.querySelectorAll('a[href*="/match/"]'));
                const activeLink = matchLinks.find(el => /active match/i.test(cleanText(el.innerText || '')))
                    || matchLinks.find(el => /^R\\d+\\s+vs/i.test(cleanText(el.innerText || '')))
                    || matchLinks[0];
                if (activeLink && activeLink.href) {
                    activeMatchUrl = activeLink.href;
                }

                return JSON.stringify({
                    url: window.location.href,
                    title: document.title || '',
                    loggedIn: !/\\/login(?:[?#]|$)/i.test(window.location.pathname + window.location.search) && !loginForm && !/\\blog\\s*in\\b|\\bsign\\s*in\\b/i.test(authText),
                    inTournament,
                    activeMatchUrl,
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
        # Poll faster only while a match or check-in is actually live.
        self._set_enrolled(bool(result.get("activeMatchUrl")) or bool(result.get("candidates")))

        # If the dashboard shows an active match, navigate the hidden chat
        # page to it so match check-in (and chat capture) can happen there.
        active_match_url = result.get("activeMatchUrl") or ""
        if active_match_url and not _is_limitless_url(active_match_url):
            active_match_url = ""
        if active_match_url and self.chat_page is not None:
            try:
                current = self.chat_page.url().toString()
                if current != active_match_url:
                    self.chat_target_url = active_match_url
                    self.chat_page.load(QUrl(active_match_url))
            except Exception:
                pass

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
        # Inject the player's username so the overlay can tell their messages
        # apart from the opponent's (for left/right conversation alignment).
        try:
            from app_settings import load_username
            own_name = (load_username() or "").strip()
        except Exception:
            own_name = ""
        own_js = json.dumps(own_name)
        return r"""
            (() => {
                const ownName = """ + own_js + r""";
                const clean = (text) => (text || '').replace(/\s+/g, ' ').trim();
                const visible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
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

                // Detect a match check-in button on the match page. The match
                // page shows a "Check in" button when the round uses match
                // check-in and the player hasn't checked in yet. The button
                // is a plain styled element (no button/role semantics), so we
                // scan ALL elements and match the text loosely.
                let checkin = false;
                const checkinRe = /^\\s*check[\\s-]?in\\s*$/i;
                const checkinEl = Array.from(document.querySelectorAll('*')).find(el => {
                    // Only leaf-ish elements so we don't match a huge container.
                    if (el.children.length > 2) return false;
                    if (!visible(el)) return false;
                    const t = clean(el.innerText || el.getAttribute('aria-label') || '');
                    return checkinRe.test(t);
                });
                if (checkinEl) {
                    checkin = true;
                    checkinEl.setAttribute('data-tcglive-match-checkin', '1');
                }

                // Detect the "Open as image" button on the match page. This
                // opens the opponent's decklist as an image — critical during
                // tournament rounds. We capture its href (if it's a link) so
                // the app can open it in a front tab automatically; if it's
                // a JS button with no href, the app clicks it instead.
                let openAsImageUrl = '';
                let openAsImagePresent = false;
                const openImageEl = Array.from(document.querySelectorAll('a, button, [role="button"]')).find(el => {
                    if (!visible(el)) return false;
                    const t = clean(el.innerText || el.getAttribute('aria-label') || '');
                    return /open as image/i.test(t);
                });
                if (openImageEl) {
                    openAsImagePresent = true;
                    openAsImageUrl = openImageEl.href || openImageEl.getAttribute('href') || '';
                    openImageEl.setAttribute('data-tcglive-open-image', '1');
                }

                if (best) {
                    const headerNode = best.node.closest('main, article, section, div')?.querySelector('h1, h2, h3');
                    header = clean(headerNode ? headerNode.innerText : document.title || 'Limitless Match');

                    // Extract the opponent username from the match header
                    // ("Round 2 vs OpponentName" or "You are playing against").
                    const headerText = clean(best.node.closest('main, article, section, div')?.innerText || '');
                    const vsMatch = headerText.match(/\bvs\.?\s+([A-Za-z0-9_\- ]+)/i);
                    if (vsMatch && vsMatch[1]) {
                        opponent = clean(vsMatch[1]);
                    }
                    const roundMatch = headerText.match(/\bround\s+(\d+)\b/i);
                    if (roundMatch && roundMatch[1]) {
                        subtitle = 'Round ' + roundMatch[1];
                    }

                    // Limitless renders each chat message as its own element
                    // containing a timestamp like "08:31:35 PM". We extract
                    // each message element individually so messages stay
                    // separate instead of being concatenated into one blob.
                    const timeRe = /\\b\\d{1,2}:\\d{2}(?::\\d{2})?\\s*(?:AM|PM)/i;
                    const rawMessages = [];
                    // Collect ALL descendant elements that contain a timestamp
                    // (message rows). We then keep only the deepest ones so a
                    // wrapper containing the whole chat doesn't swallow the
                    // individual messages.
                    const timed = [];
                    const walk = (el, depth) => {
                        if (depth > 6) return;
                        for (const child of el.children) {
                            const t = clean(child.innerText || '');
                            if (!t) continue;
                            const hasTime = timeRe.test(t);
                            const hasInput = child.querySelector('textarea, input[type="text"]');
                            if (hasTime && !hasInput) {
                                timed.push({ el: child, text: t });
                            }
                            walk(child, depth + 1);
                        }
                    };
                    walk(best.node, 0);
                    // Keep only elements that are not ancestors of another
                    // timestamped element (i.e. the deepest message rows).
                    for (const item of timed) {
                        const isAncestor = timed.some(other => other.el !== item.el && item.el.contains(other.el));
                        if (!isAncestor) {
                            rawMessages.push(item.text);
                        }
                    }

                    // If the walk found zero or only ONE timestamped element
                    // (meaning the whole chat is one blob, not per-message
                    // elements), split the container text on timestamp
                    // boundaries so each message stays separate.
                    if (rawMessages.length <= 1) {
                        rawMessages.length = 0;
                        const blob = clean(best.node.innerText || '');
                        const parts = blob.split(/(?<=\\s)(?=\\d{1,2}:\\d{2}(?::\\d{2})?\\s*(?:AM|PM))/i);
                        for (const part of parts) {
                            const cleaned = clean(part);
                            if (cleaned) rawMessages.push(cleaned);
                        }
                    }

                    // Clean each message and extract its sender so the overlay can align
                    // them like a conversation (mine right, theirs left).
                    // Two DOM shapes are handled:
                    //  1. Per-message element: "SenderName 08:35 PM text"
                    //  2. Blob fallback part: "08:35 PM text SenderNameOfNext"
                    // System/action messages have no sender.
                    const actionRe = /(?:has checked in|has reported game|the match has finished|has joined|has left|is now|won the|lost the|has been|check in|checked in)/i;
                    const knownNames = [ownName, opponent].filter(Boolean);
                    let pendingSender = '';
                    for (const raw of rawMessages) {
                        let sender = '';
                        let text = '';
                        let trailingSender = '';
                        // Shape 1: leading sender before the timestamp.
                        const lead = raw.match(/^([A-Za-z0-9_\\- ]{1,30}?)\\s+\\d{1,2}:\\d{2}(?::\\d{2})?\\s*(?:AM|PM)\\s+(.+)$/i);
                        if (lead) {
                            sender = clean(lead[1]);
                            text = clean(lead[2]);
                        } else {
                            // Shape 2: timestamp first, possible trailing
                            // sender (the NEXT message's sender).
                            let t = raw.replace(timeRe, '').trim();
                            t = t.replace(/^(Send|Request a judge|Match chat)\\b/i, '').trim();
                            t = t.replace(/\\s*send$/i, '').trim();
                            // If the text ends with a known player name, that
                            // name is the NEXT message's sender.
                            for (const name of knownNames) {
                                if (name && t.length > name.length && t.toLowerCase().endsWith(name.toLowerCase())) {
                                    text = t.slice(0, t.length - name.length).trim();
                                    trailingSender = name;
                                    break;
                                }
                            }
                            if (!text) text = t;
                        }
                        const effSender = sender || pendingSender;
                        pendingSender = trailingSender;
                        // Drop pure UI-chrome leftovers.
                        if (!text || text.length < 2) continue;
                        if (drop.has(text.toLowerCase())) continue;
                        if (/^(send|request a judge|match chat)$/i.test(text)) continue;
                        const type = actionRe.test(text) ? 'action' : 'chat';
                        messages.push({ text: text, type: type, sender: effSender });
                    }
                    // Dedupe by text, keep the latest.
                    const seen = new Set();
                    const deduped = [];
                    for (const m of messages) {
                        const key = clean(m.text).toLowerCase();
                        if (!key || seen.has(key)) continue;
                        seen.add(key);
                        deduped.push(m);
                    }
                    messages = deduped.slice(-8);
                }

                return JSON.stringify({
                    url: window.location.href,
                    title: clean(document.title || ''),
                    hasChat,
                    header,
                    subtitle,
                    opponent,
                    messages,
                    pageTextSnippet: pageText.slice(0, 400),
                    checkin,
                    openAsImageUrl,
                    openAsImagePresent
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

        # Auto-check-in: if the match page shows a "Check in" button and
        # auto-check-in is enabled, click it so the player doesn't get an
        # automatic loss for not checking in to the round.
        if self.auto_checkin_enabled and result.get("checkin"):
            self._attempt_match_checkin(url_text)

        # Auto "Open as image": during a tournament round (before the result
        # is reported), automatically open the opponent's decklist image in a
        # new tab brought to the very front. This is critical tournament info.
        open_image_url = result.get("openAsImageUrl") or ""
        open_image_present = bool(result.get("openAsImagePresent"))
        if open_image_present and self._is_tournament_round_active():
            if open_image_url:
                self._open_decklist_image_tab(open_image_url)
            else:
                # JS button with no href — click it on the page that found it.
                self._click_open_as_image()

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
        # Each message is either a plain string (legacy) or a dict with
        # {text, type}. Normalize to dicts and attach a received timestamp so
        # the overlay can fade messages out over time.
        now_iso = datetime.now().isoformat(timespec="seconds")
        normalized_messages = []
        for msg in (state.get("messages") or []):
            if isinstance(msg, dict):
                text = str(msg.get("text") or "").strip()
                mtype = str(msg.get("type") or "chat")
                sender = str(msg.get("sender") or "").strip()
            else:
                text = str(msg).strip()
                mtype = "chat"
                sender = ""
            if not text:
                continue
            normalized_messages.append({"text": text, "type": mtype, "sender": sender, "ts": now_iso})
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
        # Persist the current match's chat (with round info) to a shared
        # capture file so AIParseBattleLog can attach it to the battle record
        # for later review.
        self._write_chat_capture(normalized)
        # If we have a tournament match with a known opponent, persist it so
        # AIParseBattleLog can match the battle-log opponent against it.
        # If the match chat is gone (no opponent), clear the tournament flag.
        if normalized.get("opponent"):
            self._update_tournament_flag(True, opponent=normalized["opponent"])
        elif self.in_tournament:
            self._update_tournament_flag(False)

    def _extract_round_number(self, subtitle):
        """Pull the round number from a subtitle like 'Round 3 vs Opponent'."""
        if not subtitle:
            return None
        match = re.search(r"\bround\s+(\d+)\b", subtitle, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    def _write_chat_capture(self, state):
        """Write the current match chat to a shared capture file.

        The capture includes the round number (if known), the opponent, and
        the raw messages. AIParseBattleLog.py reads this file when saving a
        battle so the chat can be reviewed alongside the game data.
        """
        try:
            round_number = self._extract_round_number(state.get("subtitle") or "")
            payload = {
                "round": round_number,
                "opponent": state.get("opponent") or "",
                "messages": state.get("messages") or [],
                "captured_at": datetime.now().isoformat(timespec="seconds"),
            }
            with open(LIMITLESS_CHAT_CAPTURE_FILE, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
        except Exception:
            pass

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

    def _attempt_match_checkin(self, url_text):
        """Auto-click the match check-in button on the match page.

        The match page shows a "Check in" button when the round uses match
        check-in and the player hasn't checked in yet. Clicking it prevents an
        automatic loss for not showing up to the round.
        """
        if self.auto_checkin_enabled is False:
            return
        # Dedupe: don't spam clicks every poll while the button is present.
        now = time.time()
        if getattr(self, "_last_match_checkin_time", 0) and now - self._last_match_checkin_time < 10:
            return
        self._last_match_checkin_time = now
        self.last_status = "Auto Check-In is checking you into the round."
        self.status_changed.emit(self.last_status)
        _play_limitless_notification_sound()
        click_js = """
            (() => {
                const clean = (t) => (t || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return style && style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                };
                // Prefer the element tagged by the scan; fall back to a
                // loose text match across ALL elements (the Limitless
                // check-in button is a plain styled element with no button
                // semantics).
                let target = document.querySelector('[data-tcglive-match-checkin]');
                if (!target || !visible(target)) {
                    target = Array.from(document.querySelectorAll('*')).find(el => {
                        if (el.children.length > 2) return false;
                        if (!visible(el)) return false;
                        const t = clean(el.innerText || el.getAttribute('aria-label') || '');
                        return /^\\s*check[\\s-]?in\\s*$/i.test(t);
                    });
                }
                if (target) {
                    target.click();
                    return true;
                }
                return false;
            })();
        """
        page = None
        try:
            # Prefer whichever page is actually ON the match URL — the
            # check-in button lives on the match page. The visible view is
            # usually on the dashboard, so clicking there would miss.
            if self.chat_page is not None:
                chat_url = self.chat_page.url().toString()
                if chat_url and "/match/" in chat_url:
                    page = self.chat_page
            if page is None and self.visible_view is not None:
                visible_url = self.visible_view.page().url().toString()
                if visible_url and "/match/" in visible_url:
                    page = self.visible_view.page()
        except Exception:
            page = None
        if page is not None:
            try:
                page.runJavaScript(click_js)
            except Exception:
                pass

    def _is_tournament_round_active(self):
        """True while a tournament match is in progress (before the result).

        A round is active when the tournament flag says we're in a match AND
        the match chat still exists (once the result is reported the match
        ends and the chat/flag clears).
        """
        if not self.in_tournament:
            return False
        # The chat state's opponent presence signals an active match; once
        # the round completes the flag is cleared by _publish_chat_state.
        return bool(self.last_chat_state.get("visible"))

    def _open_decklist_image_tab(self, image_url):
        """Open the opponent's decklist image in a new front tab.

        During a tournament round this is critical info. We open the image
        URL in the default browser as a new tab brought to the front. Deduped
        per match so it only opens once per round.
        """
        if not image_url or not _is_safe_web_url(image_url):
            return
        # Dedupe: only open once per match URL.
        if getattr(self, "_last_open_image_match", "") == self.chat_target_url:
            return
        self._last_open_image_match = self.chat_target_url
        self.last_status = "Opening opponent decklist image for the tournament round."
        self.status_changed.emit(self.last_status)
        try:
            import webbrowser
            webbrowser.open(image_url, new=2, autoraise=True)
        except Exception as exc:
            print(f"[Limitless] Could not open decklist image: {exc}")

    def _click_open_as_image(self):
        """Click the 'Open as image' button on the match page.

        Fallback for when the button is a JS button with no href. We first
        try to extract the decklist image URL directly from the page and open
        it in the browser (visible to the player); if that fails we click the
        button on the page that has it.
        """
        # Dedupe: only open once per match URL.
        if getattr(self, "_last_open_image_match", "") == self.chat_target_url:
            return
        self._last_open_image_match = self.chat_target_url

        # Prefer extracting the decklist image URL and opening it in the
        # player's browser (front tab) — clicking on the hidden chat page
        # would open the image where the player can't see it.
        extract_js = """
            (() => {
                // The decklist section usually contains an <img> or a link
                // to the rendered decklist image.
                const decklist = document.querySelector('#decklist, [id*="decklist"], [class*="decklist"]');
                if (decklist) {
                    const img = decklist.querySelector('img');
                    if (img && img.src) return img.src;
                    const link = decklist.querySelector('a[href*="image"], a[href*=".png"], a[href*=".jpg"], a[href*=".webp"]');
                    if (link && link.href) return link.href;
                }
                // Fall back to any image link on the page.
                const anyLink = document.querySelector('a[href*=".png"], a[href*=".jpg"], a[href*=".webp"]');
                if (anyLink && anyLink.href) return anyLink.href;
                return '';
            })();
        """

        def _handle_image_url(url, page_ref):
            url = str(url or "").strip()
            if url:
                self._open_decklist_image_tab(url)
                return
            # No URL found — click the button on the page as a last resort.
            click_js = """
                (() => {
                    const el = document.querySelector('[data-tcglive-open-image]') ||
                        Array.from(document.querySelectorAll('a, button, [role="button"]'))
                            .find(e => /open as image/i.test((e.innerText || '') + (e.getAttribute('aria-label') || '')));
                    if (el) { el.click(); return true; }
                    return false;
                })();
            """
            try:
                page_ref.runJavaScript(click_js)
            except Exception:
                pass

        page = None
        try:
            if self.chat_page is not None:
                chat_url = self.chat_page.url().toString()
                if chat_url and "/match/" in chat_url:
                    page = self.chat_page
            if page is None and self.visible_view is not None:
                visible_url = self.visible_view.page().url().toString()
                if visible_url and "/match/" in visible_url:
                    page = self.visible_view.page()
        except Exception:
            page = None
        if page is not None:
            try:
                page.runJavaScript(extract_js, lambda url, p=page: _handle_image_url(url, p))
            except Exception:
                pass

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


class GlassFrame(QFrame):
    """The dashboard's main glass surface, painted directly.

    It contains every other widget, so styling it with a stylesheet meant
    each opacity-slider tick re-polished the whole window (the slider lag).
    Painting it makes an opacity change a single repaint.
    """

    def __init__(self):
        super().__init__()
        self.scale = 1.0

    def set_scale(self, scale):
        self.scale = scale
        self.update()

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QLinearGradient, QPainterPath

        def a(value):
            return int(255 * max(0.0, min(1.0, value * self.scale)))

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QColor(15, 15, 15, a(0.85)))
        grad.setColorAt(1.0, QColor(10, 10, 10, a(0.88)))
        p.fillPath(path, grad)
        p.setPen(QPen(QColor(255, 255, 255, a(0.10)), 1))
        p.drawPath(path)
        p.end()


TOOLTIP_STYLE = """
    QToolTip {
        background-color: rgb(16, 22, 32);
        color: rgba(232, 238, 246, 0.96);
        border: 1px solid rgba(74, 159, 216, 0.55);
        border-radius: 6px;
        padding: 6px 9px;
        font-family: 'Segoe UI', Arial;
        font-size: 11px;
    }
"""


SPIN_STYLE = """
    QSpinBox, QDoubleSpinBox {
        background: rgba(255,255,255,0.06);
        border: 1px solid rgba(255,255,255,0.12);
        border-radius: 6px;
        color: #EEF4FF;
        padding: 3px 22px 3px 8px;
        font-size: 11px;
        min-height: 20px;
        selection-background-color: rgba(74,159,216,0.35);
    }
    QSpinBox:hover, QDoubleSpinBox:hover { border-color: rgba(74,159,216,0.35); }
    QSpinBox:focus, QDoubleSpinBox:focus { border-color: rgba(74,159,216,0.65); }
    QSpinBox::up-button, QDoubleSpinBox::up-button,
    QSpinBox::down-button, QDoubleSpinBox::down-button {
        subcontrol-origin: border; width: 18px; border: none;
        border-left: 1px solid rgba(255,255,255,0.08); background: transparent;
    }
    QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 6px; }
    QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 6px; }
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background: rgba(74,159,216,0.22); }
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
        width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent;
        border-bottom: 5px solid rgba(220,230,244,0.75);
    }
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
        width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent;
        border-top: 5px solid rgba(220,230,244,0.75);
    }
"""


def _hover_animation(owner, setter, duration=160):
    """0->1 / 1->0 float animation driving `setter` (hover polish)."""
    from PySide6.QtCore import QVariantAnimation
    anim = QVariantAnimation(owner)
    anim.setDuration(duration)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.valueChanged.connect(setter)
    return anim


class HoverCard(QFrame):
    """Metric card whose border/background softly light up on hover."""

    def __init__(self, accent="#4A9FD8"):
        super().__init__()
        self.setObjectName("deckHoverCard")
        self._accent = QColor(accent)
        self._h = 0.0
        self._anim = _hover_animation(self, self._set_h)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def _set_h(self, value):
        self._h = float(value)
        self.update()

    def _animate(self, target):
        self._anim.stop()
        self._anim.setStartValue(self._h)
        self._anim.setEndValue(float(target))
        self._anim.start()

    def enterEvent(self, event):
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        from PySide6.QtCore import QRectF
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(255, 255, 255, int(10 + 10 * self._h)))
        border = QColor(self._accent)
        border.setAlpha(int(28 + 120 * self._h))
        p.setPen(QPen(border, 1.0))
        p.drawRoundedRect(rect, 10, 10)
        p.end()


class ResultStrip(QWidget):
    """Last-N results as small green/red squares (oldest left, newest right).
    Hovering a square shows that game."""

    def __init__(self, games):
        super().__init__()
        self.games = list(games)  # [(won: bool, tooltip_text)], oldest first
        self.setMouseTracking(True)
        self.setFixedHeight(18)
        self._hover = -1

    def _cell(self, i):
        size, gap = 13, 4
        return 1 + i * (size + gap), 2, size

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for i, (won, _tip) in enumerate(self.games):
            x, y, s = self._cell(i)
            color = QColor("#66BB6A" if won else "#EF5350")
            if i != self._hover:
                color.setAlpha(200)
            p.setPen(QPen(QColor(255, 255, 255, 200), 1.2) if i == self._hover else Qt.PenStyle.NoPen)
            p.setBrush(color)
            grow = 1 if i == self._hover else 0
            p.drawRoundedRect(x - grow, y - grow, s + 2 * grow, s + 2 * grow, 3, 3)
        p.end()

    def mouseMoveEvent(self, event):
        from PySide6.QtWidgets import QToolTip
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        hit = -1
        for i in range(len(self.games)):
            x, y, s = self._cell(i)
            if x <= pos.x() <= x + s and y - 2 <= pos.y() <= y + s + 2:
                hit = i
                break
        if hit != self._hover:
            self._hover = hit
            self.update()
            if hit >= 0:
                QToolTip.showText(event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos(),
                                  self.games[hit][1], self)
            else:
                QToolTip.hideText()

    def leaveEvent(self, event):
        self._hover = -1
        self.update()
        super().leaveEvent(event)


class RangeBar(QWidget):
    """Win-rate range bar: dot = estimate, band = likely range, white tick =
    50%, gold tick = benchmark. Hover animates: band brightens, dot grows and
    the range's end values fade in (show_scale bars print a faint 0/50/100
    scale at rest)."""

    def __init__(self, low, mid, high, accent, benchmark=None, height=None,
                 show_scale=False, benchmark_label=None, level=0.9):
        super().__init__()
        self.low, self.mid, self.high = low, mid, high  # fractions 0..1
        self.accent = QColor(accent)
        self.benchmark = benchmark
        self.benchmark_label = benchmark_label
        self.show_scale = show_scale
        self.setFixedHeight(height or (30 if show_scale else 16))
        self.setMinimumWidth(80)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._h = 0.0
        self._anim = _hover_animation(self, self._set_h)
        tip = f"<b>{mid * 100:.0f}%</b> &nbsp;·&nbsp; range {_pct_range(low, high)}"
        if benchmark is not None:
            tip += f"<br><span style='color:#FFD54F'>▍</span> {benchmark_label or 'Benchmark'} {benchmark * 100:.0f}%"
        self.setToolTip(tip)

    def _set_h(self, value):
        self._h = float(value)
        self.update()

    def _animate(self, target):
        self._anim.stop()
        self._anim.setStartValue(self._h)
        self._anim.setEndValue(float(target))
        self._anim.start()

    def enterEvent(self, event):
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width() - 12
        x0 = 6
        h = self._h
        cy = 9.0 if self.show_scale else self.height() / 2.0

        def x(v):
            return x0 + max(0.0, min(1.0, v)) * w

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 18))
        p.drawRoundedRect(int(x0), int(cy - 3), int(w), 6, 3, 3)
        band = QColor(self.accent)
        band.setAlpha(int(105 + 90 * h))
        p.setBrush(band)
        p.drawRoundedRect(int(x(self.low)), int(cy - 3), max(3, int(x(self.high) - x(self.low))), 6, 3, 3)
        p.setPen(QPen(QColor(255, 255, 255, 130), 1))
        p.drawLine(int(x(0.5)), int(cy - 6), int(x(0.5)), int(cy + 6))
        if self.benchmark is not None:
            p.setPen(QPen(QColor(255, 213, 79, 210), 2))
            p.drawLine(int(x(self.benchmark)), int(cy - 6), int(x(self.benchmark)), int(cy + 6))
        r = 4.0 + 1.6 * h
        p.setPen(QPen(QColor(12, 16, 24), 1.5))
        p.setBrush(self.accent)
        from PySide6.QtCore import QPointF
        p.drawEllipse(QPointF(x(self.mid), cy), r, r)

        if self.show_scale:
            font = p.font()
            font.setPointSizeF(7.0)
            p.setFont(font)
            ty = self.height() - 3
            # Rest: faint 0/50/100 scale. Hover: the range's end values.
            rest = int(110 * (1.0 - h))
            if rest > 4:
                p.setPen(QColor(155, 168, 188, rest))
                p.drawText(int(x0), int(ty), "0")
                p.drawText(int(x(0.5) - 6), int(ty), "50")
                p.drawText(int(x(1.0) - 17), int(ty), "100")
            if h > 0.02:
                p.setPen(QColor(235, 242, 250, int(230 * h)))
                lo_txt, hi_txt = f"{self.low * 100:.0f}", f"{self.high * 100:.0f}"
                p.drawText(int(max(x0, x(self.low) - 8)), int(ty), lo_txt)
                p.drawText(int(min(x(1.0) - 16, x(self.high) - 6)), int(ty), hi_txt)
        p.end()


class SpriteDownloader(QObject):
    """Downloads missing Pokemon sprites on a background thread.

    Building a deck page used to download every uncached sprite on the UI
    thread (~0.45 s each), which froze the dashboard for seconds when it
    opened. Now the page shows placeholder letters at once and `downloaded`
    fires (on the UI thread) when a batch of sprites has landed in the cache.
    Names that fail are not retried this session.
    """

    downloaded = Signal(list)

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._queue = []
        self._seen = set()
        self._running = False

    def request(self, sprite_name):
        if not REQUESTS_AVAILABLE or not sprite_name:
            return
        with self._lock:
            if sprite_name in self._seen:
                return
            self._seen.add(sprite_name)
            self._queue.append(sprite_name)
            if self._running:
                return
            self._running = True
        threading.Thread(target=self._run, name="SpriteDownloader", daemon=True).start()

    def _run(self):
        session = _build_retry_session()
        fetched = []
        while True:
            with self._lock:
                if not self._queue:
                    self._running = False
                    break
                name = self._queue.pop(0)
            try:
                if _fetch_sprite_to_cache(name, session=session):
                    fetched.append(name)
            except Exception as exc:
                print(f"Sprite download failed for {name}: {exc}")
        if fetched:
            self.downloaded.emit(fetched)


class LazyDeckPage(QWidget):
    """Deck tab placeholder: the real dashboard page (cards + a matplotlib
    chart, the expensive part) is built the first time the tab is shown or
    when the background preloader reaches it - never all at once."""

    def __init__(self, analysis):
        super().__init__()
        self.analysis = analysis
        self.page = None
        self.pending_scroll = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)


class DeckIconPickerDialog(QDialog):
    """Pick up to three Pokemon icons for a deck.

    Three slot tiles (click one to select it) above ONE search box and a
    grid of sprite results. Clicking a result - or Enter for the first one -
    fills the selected slot and moves on to the next empty slot. Names that
    aren't in the list can be looked up online; the lookup runs in the
    background, so typing never stalls.

    (Rework: the old dialog had a search box plus three editable combo boxes,
    each opening its own completer popup on every keystroke, which stole the
    keyboard focus and made typing/autofill unreliable.)
    """

    MAX_RESULTS = 60
    lookup_finished = Signal(str, bool)

    def __init__(self, owner, deck_name, choices, current_icons=None, default_icons=None):
        super().__init__(owner)
        self.owner = owner
        self.deck_name = deck_name
        self.reset_requested = False
        self.default_icons = [_normalize_sprite_name(n) for n in (default_icons or []) if n][:3]
        self.slots = [None, None, None]
        for i, name in enumerate([_normalize_sprite_name(n) for n in (current_icons or []) if n][:3]):
            self.slots[i] = name
        self.active_slot = next((i for i, v in enumerate(self.slots) if v is None), 0)
        self.names = []
        seen = set()
        for name in list(self.default_icons) + [s for s in self.slots if s] + sorted(choices or []):
            norm = _normalize_sprite_name(name)
            if norm and norm not in seen:
                seen.add(norm)
                self.names.append(norm)
        self._items_by_name = {}
        self._lookups = set()

        self.setObjectName("deckIconPickerDialog")
        self.setWindowTitle(f"{deck_name} - Icons")
        self.setModal(True)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint |
                            Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumSize(520, 560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel(f"{deck_name}")
        title.setObjectName("deckIconPickerTitle")
        layout.addWidget(title)
        hint = QLabel("Pick up to three icons. Select a slot, then click a Pokémon below "
                      "(or press Enter for the top result).")
        hint.setObjectName("deckIconPickerBody")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ── slot tiles ──
        slots_row = QHBoxLayout()
        slots_row.setSpacing(10)
        self.slot_buttons = []
        self.slot_group = QButtonGroup(self)
        self.slot_group.setExclusive(True)
        for i in range(3):
            col = QVBoxLayout()
            col.setSpacing(4)
            tile = QToolButton()
            tile.setObjectName("deckIconSlot")
            tile.setCheckable(True)
            tile.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            tile.setIconSize(QSize(44, 44))
            tile.setFixedSize(132, 84)
            tile.setCursor(Qt.CursorShape.PointingHandCursor)
            tile.clicked.connect(lambda _checked=False, slot=i: self._select_slot(slot))
            self.slot_group.addButton(tile, i)
            col.addWidget(tile, alignment=Qt.AlignmentFlag.AlignHCenter)
            remove = QPushButton("Remove")
            remove.setObjectName("deckIconSlotRemove")
            remove.setCursor(Qt.CursorShape.PointingHandCursor)
            remove.clicked.connect(lambda _checked=False, slot=i: self._clear_slot(slot))
            col.addWidget(remove, alignment=Qt.AlignmentFlag.AlignHCenter)
            slots_row.addLayout(col)
            self.slot_buttons.append((tile, remove))
        slots_row.addStretch()
        layout.addLayout(slots_row)

        # ── search + results ──
        self.search_input = QLineEdit()
        self.search_input.setObjectName("deckIconSearch")
        self.search_input.setPlaceholderText("Search Pokémon (e.g. dragapult, iron hands)…")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._refresh_results)
        self.search_input.returnPressed.connect(self._pick_first_result)
        self.search_input.installEventFilter(self)
        layout.addWidget(self.search_input)

        self.results = QListWidget()
        self.results.setObjectName("deckIconResults")
        self.results.setViewMode(QListView.ViewMode.IconMode)
        self.results.setIconSize(QSize(40, 40))
        self.results.setGridSize(QSize(108, 80))
        self.results.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.results.setResizeMode(QListView.ResizeMode.Adjust)
        self.results.setMovement(QListView.Movement.Static)
        self.results.setUniformItemSizes(True)
        self.results.setWordWrap(True)
        self.results.itemActivated.connect(self._on_result_activated)
        self.results.itemClicked.connect(self._on_result_activated)
        layout.addWidget(self.results, stretch=1)

        self.status = QLabel("")
        self.status.setObjectName("deckIconPickerHint")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        # ── buttons ──
        buttons = QHBoxLayout()
        self.default_btn = QPushButton("Use Limitless default")
        self.default_btn.setEnabled(bool(self.default_icons))
        self.default_btn.setToolTip(", ".join(self.default_icons) if self.default_icons else "No Limitless match for this deck")
        self.default_btn.clicked.connect(self._reset_to_default)
        clear_btn = QPushButton("Clear all")
        clear_btn.clicked.connect(self._clear_all)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("deckIconSave")
        save_btn.clicked.connect(self.accept)
        save_btn.setAutoDefault(False)
        for b in (self.default_btn, clear_btn):
            buttons.addWidget(b)
        buttons.addStretch()
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

        self.setStyleSheet("""
            QDialog#deckIconPickerDialog { background: rgb(12, 17, 26); }
            QLabel#deckIconPickerTitle { color: rgba(245,249,255,0.96); font-size: 16px; font-weight: 700; }
            QLabel#deckIconPickerBody { color: rgba(168,182,204,0.85); font-size: 11px; }
            QLabel#deckIconPickerHint { color: rgba(201,218,238,0.80); font-size: 11px; min-height: 16px; }
            QToolButton#deckIconSlot {
                background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px; color: rgba(235,242,250,0.9); font-size: 11px; padding: 4px;
            }
            QToolButton#deckIconSlot:hover { background: rgba(255,255,255,0.07); }
            QToolButton#deckIconSlot:checked {
                background: rgba(74,159,216,0.16); border: 2px solid rgba(74,159,216,0.75);
            }
            QPushButton#deckIconSlotRemove {
                background: transparent; border: none; color: rgba(255,255,255,0.45); font-size: 10px; padding: 0 6px;
            }
            QPushButton#deckIconSlotRemove:hover { color: rgba(239,83,80,0.95); }
            QPushButton#deckIconSlotRemove:disabled { color: rgba(255,255,255,0.15); }
            QLineEdit#deckIconSearch {
                background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14);
                border-radius: 8px; color: rgba(245,249,255,0.95); font-size: 12px; padding: 7px 10px;
            }
            QLineEdit#deckIconSearch:focus { border-color: rgba(74,159,216,0.6); }
            QListWidget#deckIconResults {
                background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.10);
                border-radius: 8px; color: rgba(235,242,250,0.9); font-size: 10px; outline: none; padding: 6px;
            }
            QListWidget#deckIconResults::item { border-radius: 8px; padding: 4px; }
            QListWidget#deckIconResults::item:hover { background: rgba(255,255,255,0.07); }
            QListWidget#deckIconResults::item:selected { background: rgba(74,159,216,0.28); color: white; }
            QPushButton {
                background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px; color: rgba(255,255,255,0.88); font-size: 11px; font-weight: 600;
                min-height: 28px; padding: 3px 14px;
            }
            QPushButton:hover { background: rgba(74,159,216,0.22); border-color: rgba(74,159,216,0.45); }
            QPushButton:disabled { color: rgba(255,255,255,0.3); }
            QPushButton#deckIconSave { background: rgba(74,159,216,0.35); border-color: rgba(74,159,216,0.6); }
        """)

        self.lookup_finished.connect(self._on_lookup_finished)
        try:
            owner._sprite_downloader().downloaded.connect(self._on_sprites_downloaded)
        except Exception:
            pass
        self._refresh_slots()
        self._refresh_results()
        self.search_input.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        # Re-flow the icon grid to the dialog's real width once it's shown.
        QTimer.singleShot(0, self.results.doItemsLayout)

    # ── helpers ──
    @staticmethod
    def _display(name):
        return (name or "").replace("-", " ").replace("/", " ").title()

    def _pixmap(self, name, size):
        pixmap = self.owner._load_sprite_pixmap(name, size) if name else None
        return pixmap or self.owner._build_placeholder_sprite((name or self.deck_name)[:1], size)

    def eventFilter(self, obj, event):
        # Down arrow in the search box moves into the results grid.
        if obj is self.search_input and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Down:
            if self.results.count():
                self.results.setFocus()
                self.results.setCurrentRow(0)
            return True
        return super().eventFilter(obj, event)

    # ── slots ──
    def _select_slot(self, slot):
        self.active_slot = slot
        self._refresh_slots()
        self.search_input.setFocus()

    def _clear_slot(self, slot):
        self.slots[slot] = None
        self.active_slot = slot
        self._refresh_slots()
        self._refresh_results()

    def _clear_all(self):
        self.slots = [None, None, None]
        self.active_slot = 0
        self._refresh_slots()
        self._refresh_results()

    def _refresh_slots(self):
        for i, (tile, remove) in enumerate(self.slot_buttons):
            name = self.slots[i]
            if name:
                tile.setIcon(QIcon(self._pixmap(name, 44)))
                tile.setText(self._display(name))
            else:
                tile.setIcon(QIcon(self.owner._build_placeholder_sprite("+", 44, accent="#2E445A")))
                tile.setText(f"Slot {i + 1} - empty")
            tile.setChecked(i == self.active_slot)
            remove.setEnabled(bool(name))
        filled = sum(1 for s in self.slots if s)
        self.status.setText(f"{filled}/3 icons chosen. Selected: slot {self.active_slot + 1}.")

    # ── results ──
    def _refresh_results(self):
        query = _normalize_sprite_name(self.search_input.text())
        self.results.clear()
        self._items_by_name = {}
        if query:
            starts = [n for n in self.names if n.startswith(query)]
            contains = [n for n in self.names if query in n and not n.startswith(query)]
            matches = starts + contains
        else:
            matches = list(self.names)
        used = {s for s in self.slots if s}
        for name in matches[:self.MAX_RESULTS]:
            label = self._display(name) + ("  ✓" if name in used else "")
            item = QListWidgetItem(QIcon(self._pixmap(name, 40)), label)
            item.setData(Qt.ItemDataRole.UserRole, ("sprite", name))
            item.setToolTip(name + (" (already chosen)" if name in used else ""))
            self.results.addItem(item)
            self._items_by_name[name] = item
        # Online lookup: after the local matches (first only when nothing
        # matches locally, so Enter picks a real result whenever there is one).
        if query and query not in self.names and len(query) >= 3:
            busy = query in self._lookups
            item = QListWidgetItem(QIcon(self.owner._build_placeholder_sprite("?", 40, accent="#3B4B63")),
                                   "Searching…" if busy else f'Find "{query}" online')
            item.setData(Qt.ItemDataRole.UserRole, ("lookup", query))
            item.setToolTip("Look this Pokémon up on the sprite server")
            self.results.addItem(item)

    def _on_sprites_downloaded(self, names):
        for name in names:
            item = self._items_by_name.get(_normalize_sprite_name(name))
            if item is not None:
                item.setIcon(QIcon(self._pixmap(item.data(Qt.ItemDataRole.UserRole)[1], 40)))
        self._refresh_slots()

    def _pick_first_result(self):
        if self.results.count():
            self._on_result_activated(self.results.item(0))

    def _on_result_activated(self, item):
        if item is None:
            return
        kind, name = item.data(Qt.ItemDataRole.UserRole)
        if kind == "lookup":
            self._lookup_online(name)
        else:
            self._pick(name)

    def _pick(self, name):
        if name in self.slots:
            self.status.setText(f"{self._display(name)} is already in slot {self.slots.index(name) + 1}.")
            return
        self.slots[self.active_slot] = name
        empties = [i for i, v in enumerate(self.slots) if v is None]
        later = [i for i in empties if i > self.active_slot]
        self.active_slot = (later or empties or [self.active_slot])[0]
        self._refresh_slots()
        self._refresh_results()
        self.search_input.selectAll()
        self.search_input.setFocus()

    # ── online lookup (background) ──
    def _lookup_online(self, name):
        if name in self._lookups:
            return
        self._lookups.add(name)
        self.status.setText(f'Looking up "{name}"…')
        self._refresh_results()

        def worker():
            try:
                ok = bool(_fetch_sprite_to_cache(name))
            except Exception:
                ok = False
            self.lookup_finished.emit(name, ok)

        threading.Thread(target=worker, name="SpriteLookup", daemon=True).start()

    def _on_lookup_finished(self, name, ok):
        self._lookups.discard(name)
        if ok:
            if name not in self.names:
                self.names.append(name)
            self._pick(name)
            self.status.setText(f"Found {self._display(name)}.")
        else:
            self._refresh_results()
            self.status.setText(f'No sprite found for "{name}". Check the spelling, e.g. "iron-hands" or "charizard".')

    def _reset_to_default(self):
        self.reset_requested = True
        self.reject()

    def chosen_icons(self):
        return [s for s in self.slots if s]


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


def _console_python():
    """python.exe (not pythonw.exe) so debug tools get a visible console."""
    exe = sys.executable or "python"
    if exe.lower().endswith("pythonw.exe"):
        candidate = exe[: -len("pythonw.exe")] + "python.exe"
        if os.path.exists(candidate):
            return candidate
    return exe


_RUNNING_THREADS = set()


def _start_thread(thread):
    """Start a QThread and keep a strong reference until it finishes.

    Fetchers used to live only on the StatsWindow; closing the window
    mid-fetch destroyed a running QThread and aborted the process (BUG-022).
    """
    _RUNNING_THREADS.add(thread)
    thread.finished.connect(lambda t=thread: _RUNNING_THREADS.discard(t))
    thread.start()
    return thread


class MetaFetcher(QThread):
    """Background thread for fetching meta data from web sources.
    Caches results to disk for 1 hour to avoid hammering APIs."""
    data_ready = Signal(str, object)  # (source_name, data)
    error = Signal(str, str)           # (source_name, error_message)

    CACHE_TTL = 3600  # 1 hour
    CACHE_SCHEMA_VERSION = 3  # v3 = unified meta sheet (meta_sources.py)

    def __init__(self, source, parent=None, force=False):
        super().__init__(parent)
        self.source = source  # 'limitless_standard', 'limitless_pocket', 'trainerhill'
        self.force = force    # skip the 1 h cache (e.g. after changing weights)
        self.session = _build_retry_session() if REQUESTS_AVAILABLE else None

    def run(self):
        try:
            cache_file = os.path.join(BASE_DIR, f".meta_cache_{self.source}.json")
            # Use cache if fresh enough
            if os.path.exists(cache_file) and not self.force:
                age = time.time() - os.path.getmtime(cache_file)
                if age < self.CACHE_TTL:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if self._is_cache_usable(data):
                        self.data_ready.emit(self.source, data)
                        return

            if self.source == 'limitless_standard':
                # Unified, weighted sheet: online + in-person + Japan, by era.
                from meta_sources import build_meta_sheet, make_session
                data = build_meta_sheet(make_session())
                try:
                    self._prefetch_sprite_icons(data.get("rows", [])[:25])
                except Exception:
                    pass
            elif self.source == 'limitless_pocket':
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
        app = QApplication.instance()
        if app is not None and "QToolTip" not in (app.styleSheet() or ""):
            app.setStyleSheet((app.styleSheet() or "") + TOOLTIP_STYLE)  # dark, rounded hover tips
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
        self.pinned_decks = self._load_pinned_decks()
        self.starred_decks, self.ignored_decks = self._load_deck_flags()
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
        self.chart_range = self.app_settings.get("dashboard_chart_range", "auto")
        if self.chart_range not in {key for key, _label, _tip in self.CHART_RANGES}:
            self.chart_range = "auto"
        try:
            self.winrate_window = int(self.app_settings.get("dashboard_winrate_window", 10))
        except (TypeError, ValueError):
            self.winrate_window = 10
        
        self.init_ui()
        self.load_stats()
        
        # Auto-refresh every 15 seconds
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._refresh_if_changed)
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
        self.container = GlassFrame()
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

        # Unified meta (online + in-person + Japan, preference-weighted)
        self.meta_tab_index = self.tab_widget.addTab(self.create_meta_tab(), "Meta")

        # In-person play tools (event finder, homies, decklist printing)
        self.in_person_tab_index = self.tab_widget.addTab(self.create_in_person_tab(), "In Person")

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
        # Save once the slider settles, not on every tick (disk write each step).
        if not hasattr(self, "_opacity_save_timer"):
            self._opacity_save_timer = QTimer(self)
            self._opacity_save_timer.setSingleShot(True)
            self._opacity_save_timer.timeout.connect(self.save_window_geometry)
        self._opacity_save_timer.start(500)

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

    def _schedule_geometry_save(self):
        """Debounced: write geometry once movement/resizing pauses (BUG-028)."""
        timer = getattr(self, "_geometry_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self.save_window_geometry)
            self._geometry_timer = timer
        timer.start(400)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_geometry_save()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._schedule_geometry_save()

    def closeEvent(self, event):
        if self.parent_overlay is not None and not getattr(self, "_really_close", False):
            # Owned by the mini hub: hide instead of destroying, so reopening
            # is instant (rebuilding the whole window on every open was the
            # "not responding" freeze when opening from the hub).
            self._update_window_interaction_state(force_release=True)
            while self.is_protected_interaction_active():
                self.end_protected_interaction()
            try:
                self.parent_overlay.arrow_label.setText("▲")
            except Exception:
                pass
            self.hide()
            event.ignore()
            return
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
        content_layout.addWidget(self.create_graphs_section())
        
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
        self.deck_tab_bar = DeckTabBar()
        self.deck_tabs.setTabBar(self.deck_tab_bar)
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

        marker_row = QLabel(f"{low_pct:.0f}–{high_pct:.0f}%")
        marker_row.setObjectName("deckMetricNote")
        meter_layout.addWidget(marker_row)
        layout.addWidget(meter)

        if subtitle:
            note = QLabel(subtitle)
            note.setObjectName("deckMetricNote")
            note.setWordWrap(True)
            layout.addWidget(note)

        return card

    # One colour rule for the whole deck page, based on how sure we are the
    # deck wins more than it loses (P(win rate > 50%)) - not on raw cut-offs.
    WINNING, UNCLEAR, LOSING, NEUTRAL = "#66BB6A", "#F9A825", "#EF5350", "#6BB6E8"

    def _confidence_accent(self, p_above_even):
        if p_above_even is None:
            return self.NEUTRAL
        if p_above_even >= 0.7:
            return self.WINNING
        if p_above_even <= 0.3:
            return self.LOSING
        return self.UNCLEAR

    def _card_label(self, text, style):
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setStyleSheet(f"background: transparent; border: none; {style}")
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        return label

    def _create_estimate_card(self, title, headline, accent, low, mid, high, caption, tooltip,
                              benchmark=None, tag=None, benchmark_label=None):
        """Headline card: title, big number, range bar, one short caption.
        Everything else lives in the (styled) hover tooltip."""
        card = HoverCard(accent)
        card.setToolTip(tooltip)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        layout.addWidget(self._card_label(title, "color: rgba(168,182,204,0.75); font-size: 9px; font-weight: 700; letter-spacing: 1px;"))
        tag_html = f" <span style='font-size:10px; font-weight:500; color:#8A97AA'>{tag}</span>" if tag else ""
        layout.addWidget(self._card_label(f"{headline}{tag_html}", f"color: {accent}; font-size: 24px; font-weight: 700;"))
        if mid is not None:
            layout.addWidget(RangeBar(low, mid, high, accent, benchmark=benchmark, show_scale=True,
                                      benchmark_label=benchmark_label))
        if caption:
            layout.addWidget(self._card_label(caption, "color: rgba(200,212,228,0.72); font-size: 10px;"))
        layout.addStretch()
        return card

    def _create_mini_stat(self, title, value_text, accent, tooltip, extra_widget=None):
        card = HoverCard(accent)
        card.setToolTip(tooltip)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)
        layout.addWidget(self._card_label(title, "color: rgba(168,182,204,0.75); font-size: 9px; font-weight: 700; letter-spacing: 1px;"))
        if value_text:
            layout.addWidget(self._card_label(value_text, f"color: {accent}; font-size: 15px; font-weight: 700;"))
        if extra_widget is not None:
            layout.addWidget(extra_widget)
        return card

    def _create_deck_visual_metrics(self, analysis):
        """Three headline cards (win rate / vs the meta / verdict) plus a row
        of compact stats. Visual first; details on hover."""
        post = analysis.get("posterior") or {}
        meta_adj = analysis.get("meta_adjusted")
        rank_summary = analysis.get("rank_summary", {})
        games = int(analysis.get("games") or 0)  # real games (estimate uses the weighted sample)
        # "Actual" = your real record; the estimate uses the weighted record.
        raw_games = analysis.get("games") or 0
        observed = (analysis.get("wins", 0) / raw_games) if raw_games else None
        limitless_wr = analysis.get("limitless_wr")

        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        top = QGridLayout()
        top.setHorizontalSpacing(8)
        outer.addLayout(top)

        # 1. Win rate
        est = post.get("mean", 0.5) * 100.0
        deck_accent = self._confidence_accent(post.get("p_above_even") if games else None)
        level = int(round(post.get("level", 0.9) * 100))
        tip = (f"<b>Estimated win rate: {est:.0f}%</b><br>"
               f"Range {_pct_range(post.get('low', 0), post.get('high', 1))}. {RANGE_EXPLAINED.format(level=level)}<br>"
               f"<span style='color:#8A97AA'>Actual {analysis.get('record')} ({(observed or 0) * 100:.0f}%). "
               f"{post.get('games', 0):.1f} effective games.</span><br>"
               + (formulas.estimate(post) if post.get("alpha") else ""))
        if limitless_wr is not None:
            tip += f"<br><span style='color:#FFD54F'>▍</span> Limitless average for this archetype: {limitless_wr * 100:.1f}%"
        top.addWidget(self._create_estimate_card(
            "WIN RATE", f"{est:.0f}%" if games else "--", deck_accent,
            post.get("low", 0), post.get("mean", 0.5), post.get("high", 1),
            ("Older format: not counted" if post.get("games", 0) <= 0 else
             f"Range {_pct_range(post.get('low', 0), post.get('high', 1))}") if games else "No games yet",
            tip, benchmark=limitless_wr, benchmark_label="Limitless",
        ), 0, 0)

        # 2. Meta Score (deck_score.py) - same number as the Meta tab
        scores, score_info = self._deck_scores()
        score = scores.get(f"you:{analysis.get('deck_name', '')}")
        if score and score.get("eff_games", 0) > 0:
            sc = score["score"] * 100.0
            ranked = score_info.get("ranked", 0)
            caption = (f"Would rank #{score['rank']} of {ranked} · range {_pct_range(score['low'], score['high'])}" if score.get("rank")
                       else f"{score.get('eff_games', 0):.0f} of {score_info.get('n_needed', 0):.0f} effective games to rank · "
                            f"range {_pct_range(score['low'], score['high'])}")
            top.addWidget(self._create_estimate_card(
                "META SCORE", f"{sc:.0f}", self._confidence_accent(score["p_above_even"]),
                score["low"], score["score"], score["high"], caption,
                self._score_tooltip(analysis.get("deck_name", ""), score, score_info, True),
            ), 0, 1)
        elif meta_adj:
            adj = meta_adj["mean"] * 100.0
            diff = (observed or 0) * 100.0 - adj
            mix = ("Your opponents were close to the real meta mix."
                   if abs(diff) < 2 else
                   f"Your opponents were {'easier' if diff > 0 else 'tougher'} than the meta "
                   f"({(observed or 0) * 100:.0f}% raw → {adj:.0f}%).")
            tip = (f"<b>Expected win rate vs today's meta: {adj:.0f}%</b><br>"
                   f"Range {_pct_range(meta_adj['low'], meta_adj['high'])}.<br>"
                   f"<span style='color:#8A97AA'>Your matchups re-weighted by how common each deck is on Limitless. "
                   f"{mix} Decks you haven't faced count at your overall rate.</span>")
            top.addWidget(self._create_estimate_card(
                "VS THE META", f"{adj:.0f}%", self._confidence_accent(meta_adj.get("p_above_even")),
                meta_adj["low"], meta_adj["mean"], meta_adj["high"],
                f"Range {_pct_range(meta_adj['low'], meta_adj['high'])}", tip,
            ), 0, 1)
        else:
            top.addWidget(self._create_estimate_card(
                "VS THE META", "--", "#AAB7CB", 0, None, 0, "needs Limitless meta data",
                "Open the Limitless TCG Live Meta tab once to load meta shares."), 0, 1)

        # 3. Verdict
        p_even = post.get("p_above_even", 0.5)
        verdict = verdict_from_probability(p_even) if games else "No games"
        tip = (f"<b>{p_even * 100:.0f}% chance</b> this deck wins more than it loses.<br>"
               f"<span style='color:#8A97AA'>{analysis.get('confidence_note', '')}</span><br>"
               + formulas.verdict(p_even))
        if analysis.get("p_beats_limitless") is not None:
            tip += (f"<br>{analysis['p_beats_limitless'] * 100:.0f}% chance you beat the Limitless average "
                    f"({limitless_wr * 100:.1f}%).")
        top.addWidget(self._create_estimate_card(
            "VERDICT", verdict, self._confidence_accent(p_even if games else None), 0, None, 0,
            f"{p_even * 100:.0f}% chance it's above 50%" if games else "", tip), 0, 2)
        for col in range(3):
            top.setColumnStretch(col, 1)

        # Compact row
        adv = QGridLayout()
        adv.setHorizontalSpacing(8)
        outer.addLayout(adv)
        own = (score or {}).get("own")
        if own and score.get("eff_games", 0) > 0:
            own_rank = f" · #{own['rank']}" if own.get("rank") and score.get("qualifies") else ""
            adv.addWidget(self._create_mini_stat(
                "OWN GAMES SCORE", f"{own['score'] * 100:.0f}{own_rank}", "#B39DDB",
                f"<b>Own games only: {own['score'] * 100:.1f}</b> · range {_pct_range(own['low'], own['high'])}"
                + (f" · would rank #{own['rank']} of {score_info.get('ranked', 0)}" if own_rank else "")
                + "<br>" + formulas.own_score(own, score_info)), 0, 0)
        else:
            rw = rank_summary.get("weighted_winrate", 0.0) * 100.0
            adv.addWidget(self._create_mini_stat(
                "RANK-WEIGHTED", f"{rw:.0f}%" if games else "--", self.NEUTRAL,
                "Win rate where games at higher ranks count more"
                + (f" (avg rank {rank_summary['avg_rank']:.0f})." if rank_summary.get("avg_rank") is not None else ".")), 0, 0)
        form = analysis.get("recent_form") or {}
        strip = ResultStrip(form.get("games_list", [])) if form.get("games") else None
        adv.addWidget(self._create_mini_stat(
            f"LAST {form.get('games', 0)}" if form.get("games") else "RECENT",
            f"{form['wins']}-{form['games'] - form['wins']}" if form.get("games") else "--",
            self.NEUTRAL, "Oldest on the left, newest on the right. Hover a square for the game.",
            extra_widget=strip), 0, 1)
        if limitless_wr is not None:
            edge = est - limitless_wr * 100.0
            adv.addWidget(self._create_mini_stat(
                "VS LIMITLESS", f"{edge:+.0f} pts", self._delta_accent(edge),
                f"Your estimate ({est:.0f}%) vs this archetype's Limitless average ({limitless_wr * 100:.1f}%)."), 0, 2)
        else:
            adv.addWidget(self._create_mini_stat("VS LIMITLESS", "--", "#AAB7CB",
                                                 "No Limitless archetype matched this deck name."), 0, 2)
        adv.addWidget(self._create_mini_stat(
            "META FACED", f"{(meta_adj or {}).get('coverage', 0) * 100:.0f}%", self.NEUTRAL,
            "Share of the current meta you've played at least once with this deck."), 0, 3)
        for col in range(4):
            adv.setColumnStretch(col, 1)
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
            # Same model and 90% range as the cards above the chart.
            post = win_rate_posterior(wins, losses, ties)
            times.append(dt)
            observed.append((post["observed"] or 0.0) * 100.0)
            bayes.append(post["mean"] * 100.0)
            lows.append(post["low"] * 100.0)
            highs.append(post["high"] * 100.0)

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

        legend = QLabel(
            "<span style='color:#6BB6E8'>━●</span> estimate &nbsp;&nbsp;"
            "<span style='color:#9CC344'>┅</span> actual &nbsp;&nbsp;"
            "<span style='color:#6BB6E8'>▒</span> confidence range"
        )
        legend.setToolTip("Estimate: true win rate after each game. Actual: your raw win % so far.<br>"
                          + RANGE_EXPLAINED.format(level=90) + " Early swings are mostly noise.")
        legend.setTextFormat(Qt.TextFormat.RichText)
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
        if self._deck_initial(deck_name) == "?":
            icons = []  # catch-all bucket: pixel "?" icon
        for sprite_name in (icons or [])[:2]:
            pixmap = self._load_sprite_pixmap(sprite_name, size)
            if pixmap is not None:
                return QIcon(pixmap)
        return QIcon(self._build_placeholder_sprite(self._deck_initial(deck_name), size))

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

    def _build_deck_analysis(self, deck_name, games, wins, losses, ties=0, last_played=None):
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

        # ── v2.4.1 statistics (see deck_analytics) ──
        # Your games are weighted (expansion era x tournament / league; adjustable
        # in Advanced → Preferences) and rescaled to the effective sample size.
        detailed = self.db.get_deck_battles_detailed(deck_name)
        expansions = cached_expansions("en")
        ww, wl, wt = weighted_record(detailed, expansions)
        posterior = win_rate_posterior(ww, wl, wt)
        by_opponent = {}
        for battle in detailed:
            by_opponent.setdefault(battle.get("opponent"), []).append(battle)
        for entry in matchup_entries:
            entry["w_record"] = weighted_record(by_opponent.get(entry.get("deck"), []), expansions)
        confidence_label, confidence_note = sample_confidence(posterior["games"])
        # Every meta archetype (not just the top 8), with your record against
        # it. Opponents that match no archetype count toward "Other".
        meta_rows = self._top_limitless_rows()
        field = []
        field_index = {}
        for meta_row in meta_rows:
            key = meta_row.get("id") or meta_row.get("deck")
            # English-legal field only: Japan-only decks (cards not released
            # in English yet) can't be faced on the ladder.
            share = meta_row.get("share_en", meta_row.get("share", 0))
            if not share:
                continue
            field_index[key] = len(field)
            field.append({"key": key, "deck": meta_row.get("deck", ""), "share": share,
                          "meta_row": meta_row, "wins": 0, "losses": 0, "ties": 0})
        other_index = next((i for i, f in enumerate(field) if str(f["deck"]).strip().lower() == "other"), None)
        for entry in matchup_entries:
            opp_meta = entry.get("matched_meta")
            idx = field_index.get((opp_meta.get("row", {}).get("id") or opp_meta.get("row", {}).get("deck"))) if opp_meta else None
            if idx is None:
                idx = other_index
            entry["field_index"] = idx
            if idx is None:
                continue
            for k, v in zip(("wins", "losses", "ties"), entry.get("w_record") or (0, 0, 0)):
                field[idx][k] += v                                  # weighted (statistics)
                field[idx]["raw_" + k] = field[idx].get("raw_" + k, 0) + (entry.get(k, 0) or 0)  # display
        meta_adjusted = meta_adjusted_winrate(posterior, field) if field and games else None
        # Matchup estimates pooled toward the deck's own win rate.
        for entry in matchup_entries:
            entry["posterior"] = win_rate_posterior(*(entry.get("w_record") or (0, 0, 0)),
                                                    prior_mean=posterior["mean"], prior_strength=6.0)
        # In-person / Japan-only archetypes have placements but no W/L record.
        limitless_wr = (result_rate(matched_row.get("wins"), matched_row.get("losses"), matched_row.get("ties"))
                        if matched_row and (matched_row.get("wins") or matched_row.get("losses")) else None)
        p_beats_limitless = probability_above(posterior, limitless_wr) if limitless_wr else None
        form_rows = self.db.get_deck_recent_battles(deck_name, limit=10)
        form_wins = sum(1 for r in form_rows if str(r[3]).lower() == "win")
        recent_form = {
            "games": len(form_rows),
            "wins": form_wins,
            # oldest first: (won, tooltip)
            "games_list": [
                (str(r[3]).lower() == "win",
                 f"<b>{'Win' if str(r[3]).lower() == 'win' else 'Loss'}</b> vs {r[2]}<br>"
                 f"<span style='color:#8A97AA'>{str(r[0])[:16]}</span>")
                for r in reversed(form_rows)
            ],
        }

        return {
            "posterior": posterior,
            "confidence_label": confidence_label,
            "confidence_note": confidence_note,
            "meta_adjusted": meta_adjusted,
            "limitless_wr": limitless_wr,
            "p_beats_limitless": p_beats_limitless,
            "recent_form": recent_form,
            "deck_name": deck_name,
            "games": games,
            "wins": wins,
            "losses": losses,
            "ties": ties,
            "last_played": last_played,
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

    def _deck_summary_text(self, analysis):
        """Plain-language read-out of the deck's numbers (2-3 sentences)."""
        post = analysis.get("posterior") or {}
        games = int(analysis.get("games") or 0)  # real games (estimate uses the weighted sample)
        if not games:
            return "No games logged with this deck yet."
        parts = []
        meta_adj = analysis.get("meta_adjusted")
        observed = (analysis.get("wins", 0) / analysis["games"] * 100.0) if analysis.get("games") else 0.0
        verdict = verdict_from_probability(post.get("p_above_even", 0.5)).lower()
        if meta_adj:
            parts.append(f"{analysis.get('record')} ({observed:.0f}%). Against today's meta this projects to about "
                         f"{meta_adj['mean'] * 100:.0f}% (range {_pct_range(meta_adj['low'], meta_adj['high'])}) - {verdict}.")
            swing = max((r for r in meta_adj["rows"] if r.get("posterior")), key=lambda r: abs(r["impact"]), default=None)
            if swing and abs(swing["impact"]) >= 0.3:
                parts.append(f"Biggest swing matchup: {swing['deck']} ({float(swing.get('share') or 0):.1f}% of the meta, "
                             f"{self._format_record_text(swing.get('raw_wins', 0), swing.get('raw_losses', 0), swing.get('raw_ties', 0))}, "
                             f"{swing['impact']:+.1f} pts).")
        else:
            parts.append(f"{analysis.get('record')} ({observed:.0f}%), estimated true win rate {post.get('mean', 0.5) * 100:.0f}% - {verdict}.")
        matched_meta = analysis.get("matched_meta")
        if matched_meta and analysis.get("limitless_wr") is not None:
            parts.append(f"Matched to Limitless archetype {matched_meta['row'].get('deck')} "
                         f"(#{matched_meta.get('rank')}, {analysis['limitless_wr'] * 100:.1f}% WR there).")
        else:
            parts.append("No Limitless archetype matched this deck name.")
        parts.append(analysis.get("confidence_note", ""))
        return " ".join(p for p in parts if p)

    def _create_matchup_overview_table(self, analysis, max_rows=14):
        """One table for "how does this deck do against the meta".

        Rows: every archetype you've faced plus the biggest ones you haven't,
        sorted by meta share. Estimates are pooled toward the deck's own win
        rate; Impact = how many points the matchup adds to / removes from the
        meta-adjusted win rate (share x edge), so the matchups that actually
        matter stand out.
        """
        table = self._make_meta_table(
            ["Opponent", "Meta share", "Your record", "Estimate", "Range", "Field", "Verdict", "Impact"],
            [None, 76, 82, 72, 130, 64, 120, 70],
        )
        # This archetype's matchup records across Limitless online games
        # (weighted, from round pairings) - the benchmark for each row.
        my_row = (analysis.get("matched_meta") or {}).get("row") or {}
        field_matchups = my_row.get("matchups") or {}
        table.setRowCount(0)
        meta_adj = analysis.get("meta_adjusted")
        rows = []
        if meta_adj:
            names_by_index = {}
            for entry in analysis.get("matchups", []):
                if entry.get("field_index") is not None:
                    names_by_index.setdefault(entry["field_index"], []).append(entry.get("deck", ""))
            for idx, r in enumerate(meta_adj["rows"]):
                r = dict(r, opponents=names_by_index.get(idx, []))
                rows.append(r)
            faced = [r for r in rows if r.get("posterior")]
            unfaced = [r for r in rows if not r.get("posterior") and str(r.get("deck", "")).lower() != "other"]
            unfaced.sort(key=lambda r: -float(r.get("share") or 0))
            rows = faced + unfaced[:max(0, max_rows - len(faced))]
            rows.sort(key=lambda r: -float(r.get("share") or 0))
        else:
            for entry in analysis.get("matchups", []):
                rows.append({"deck": entry.get("deck", ""), "share": None, "meta_row": {},
                             "wins": entry.get("wins", 0), "losses": entry.get("losses", 0), "ties": entry.get("ties", 0),
                             "posterior": entry.get("posterior"), "impact": None, "opponents": []})

        row_links = []
        for i, r in enumerate(rows[:max_rows]):
            post = r.get("posterior")
            meta_row = r.get("meta_row") or {}
            table.insertRow(i)
            table.setRowHeight(i, 42)
            subtitle = f"{int(meta_row.get('count', 0) or 0)} Limitless finishes" if meta_row.get("count") else ""
            if r.get("opponents") and str(r.get("deck", "")).lower() == "other":
                subtitle = "Decks outside the listed archetypes"
            cell = self._create_deck_cell_widget(r.get("deck", ""), meta_row.get("icons", []), subtitle=subtitle)
            if r.get("opponents"):
                cell.setToolTip("Your logged opponents counted here:\n" + "\n".join(sorted(set(r["opponents"]))))
            table.setCellWidget(i, 0, cell)
            share = r.get("share")
            self._set_meta_item(table, i, 1, f"{float(share):.1f}%" if share is not None else "--", muted=share is None)
            raw = [r.get("raw_" + k, r.get(k)) or 0 for k in ("wins", "losses", "ties")]
            games = sum(raw)
            self._set_meta_item(table, i, 2, self._format_record_text(*raw) if games else "", muted=not games)
            if post:
                est = post["mean"] * 100.0
                accent = self._confidence_accent(post["p_above_even"])
                few = games < 3
                self._set_meta_item(table, i, 3, f"{est:.0f}%", accent=self.NEUTRAL if few else accent)
                item = table.item(i, 3)
                if item is not None:
                    item.setToolTip(f"<b>{est:.0f}%</b> vs {r.get('deck', '')} · range {_pct_range(post['low'], post['high'])}<br>"
                                    f"{post['p_above_even'] * 100:.0f}% chance you're favored<br>"
                                    + formulas.pooled_matchup(post, (analysis.get("posterior") or {}).get("mean", 0.5)))
                bar_wrap = QWidget()
                bar_layout = QHBoxLayout(bar_wrap)
                bar_layout.setContentsMargins(6, 0, 6, 0)
                bar_layout.addWidget(RangeBar(post["low"], post["mean"], post["high"],
                                              self.NEUTRAL if few else accent, height=14))
                table.setCellWidget(i, 4, bar_wrap)
                if few:
                    # One or two games can't support a verdict: the estimate is
                    # still mostly this deck's overall rate.
                    self._set_meta_item(table, i, 6, "Too few games", muted=True)
                    item = table.item(i, 6)
                    if item is not None:
                        item.setToolTip(f"Only {int(games)} game{'s' if games != 1 else ''}: the estimate leans on this "
                                        "deck's overall win rate. Play 3+ games for a matchup verdict.")
                else:
                    self._set_meta_item(table, i, 6, verdict_from_probability(post["p_above_even"]), accent=accent)
            else:
                self._set_meta_item(table, i, 3, "", muted=True)
                self._set_meta_item(table, i, 4, "", muted=True)
                self._set_meta_item(table, i, 6, "Not faced", muted=True)
                item = table.item(i, 6)
                if item is not None:
                    item.setToolTip("Counts at this deck's overall win rate until you play it.")
            impact = r.get("impact")
            if impact is not None and post and abs(impact) >= 0.05:
                arrow = "▲" if impact > 0 else "▼"
                self._set_meta_item(table, i, 7, f"{arrow} {abs(impact):.1f}",
                                    accent=self.WINNING if impact > 0 else self.LOSING)
            else:
                self._set_meta_item(table, i, 7, "", muted=True)
            # Field benchmark: this archetype vs that one across Limitless.
            fm = field_matchups.get(r.get("key")) if r.get("key") else None
            fm_games = sum(fm) if fm else 0
            if fm and fm_games >= 10:
                fm_post = win_rate_posterior(*fm)
                fm_pct = fm_post["mean"] * 100.0
                self._set_meta_item(table, i, 5, f"{fm_pct:.0f}%", accent=self._confidence_accent(fm_post["p_above_even"]))
                item = table.item(i, 5)
                if item is not None:
                    item.setToolTip(f"{my_row.get('deck', 'This archetype')} vs {r.get('deck')} on Limitless: "
                                    f"{fm_pct:.0f}% over ~{fm_games:.0f} weighted games")
            else:
                self._set_meta_item(table, i, 5, "", muted=True)
            row_links.append(meta_row.get("deck_url"))

        header_tips = [
            "Opposing archetype. 'Other' = decks outside the listed ones. Double-click to open on Limitless.",
            "Share of today's Limitless meta.",
            "Your wins-losses vs this deck.",
            "Estimated win rate in this matchup (leans on your overall rate until there are a few games).",
            "Confidence range (90%) · dot = estimate · white tick = 50%",
            "Your archetype vs this deck across Limitless online games (the benchmark).",
            "Needs 3+ games.",
            "▲ lifts / ▼ drags your win rate vs the meta. Bigger = matters more.",
        ]
        for col, tip in enumerate(header_tips):
            header_item = table.horizontalHeaderItem(col)
            if header_item is not None:
                header_item.setToolTip(tip)

        # Show every row (the page scrolls, not a tiny box inside it).
        table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table.setFixedHeight(table.horizontalHeader().sizeHint().height() + 42 * table.rowCount() + 6)
        table.cellDoubleClicked.connect(lambda row, col, links=row_links: self._open_row_link(links, row))
        return table

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

        # Pin (front of the tabs) · Star (Meta analysis) · Ignore (left out of
        # the dashboard and overall stats).
        flag_deck = analysis.get("deck_name", "")
        flag_group = QWidget()
        flag_row = QHBoxLayout(flag_group)
        flag_row.setContentsMargins(0, 0, 4, 0)
        flag_row.setSpacing(0)
        for kind, active in (("pin", flag_deck in self.pinned_decks),
                             ("star", flag_deck in self.starred_decks),
                             ("ignore", flag_deck in self.ignored_decks)):
            flag_btn = DeckFlagButton(kind, checked=active)
            flag_btn.toggled.connect(lambda on, k=kind, name=flag_deck: self._set_deck_flag(k, name, on))
            flag_row.addWidget(flag_btn)
        hero_top.addWidget(flag_group)

        if matched_row.get("deck_url"):
            open_btn = QPushButton("Limitless ↗")
            open_btn.setObjectName("limitlessBtn")
            open_btn.setFixedHeight(30)
            open_btn.clicked.connect(lambda checked=False, url=matched_row.get("deck_url"): _is_safe_web_url(url) and webbrowser.open(url))
            hero_top.addWidget(open_btn)
        hero_layout.addLayout(hero_top)

        comparison_text = self._deck_summary_text(analysis)

        # The plain-language read-out lives on the deck title's hover.
        deck_title.setToolTip(comparison_text)
        hero_layout.addWidget(self._create_deck_visual_metrics(analysis))
        layout.addWidget(hero_card)

        layout.addWidget(self._create_deck_trend_card(analysis))

        matchup_card, matchup_layout = self._create_dashboard_card("MATCHUPS VS THE META")
        matchup_layout.addWidget(self._create_matchup_overview_table(analysis))
        layout.addWidget(matchup_card)

        layout.addWidget(self._create_recent_deck_battles_card(analysis))
        layout.addStretch()

        scroll.setWidget(content)
        return scroll

    def _load_pinned_decks(self):
        if not os.path.exists(PINNED_DECKS_FILE):
            return []
        try:
            with open(PINNED_DECKS_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return [str(v) for v in data] if isinstance(data, list) else []
        except Exception:
            return []

    def _save_pinned_decks(self):
        try:
            with open(PINNED_DECKS_FILE, "w", encoding="utf-8") as handle:
                json.dump(self.pinned_decks, handle, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_deck_flags(self):
        """(starred, ignored) deck name lists. First run: the decks that were
        starred under the old single star/pin button start out starred."""
        try:
            with open(DECK_FLAGS_FILE, "r", encoding="utf-8") as handle:
                data = json.load(handle) or {}
            return ([str(v) for v in data.get("starred", [])],
                    [str(v) for v in data.get("ignored", [])])
        except FileNotFoundError:
            return list(self.pinned_decks), []
        except Exception:
            return [], []

    def _save_deck_flags(self):
        try:
            with open(DECK_FLAGS_FILE, "w", encoding="utf-8") as handle:
                json.dump({"starred": self.starred_decks, "ignored": self.ignored_decks},
                          handle, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _set_deck_flag(self, kind, deck_name, on):
        """Pin / star / ignore toggled on a deck page. Applied in place (tabs
        reordered, dashboard refreshed) so the page and its button animation
        aren't rebuilt."""
        target = {"pin": self.pinned_decks, "star": self.starred_decks, "ignore": self.ignored_decks}[kind]
        if on and deck_name not in target:
            target.insert(0, deck_name)  # newest pin first
        elif not on and deck_name in target:
            target.remove(deck_name)
        if kind == "pin":
            self._save_pinned_decks()
        else:
            self._save_deck_flags()
        if kind in ("pin", "ignore"):
            self._reorder_deck_tabs()
        if kind == "ignore":
            self._refresh_dashboard_summary()
        if kind in ("star", "ignore"):
            self._meta_tab_dirty = True
            if hasattr(self, "tab_widget") and self.tab_widget.tabText(self.tab_widget.currentIndex()) == "Meta":
                self._populate_meta_tab()

    def _reorder_deck_tabs(self):
        """Move tabs into sort order without rebuilding any page."""
        if not hasattr(self, "deck_tabs"):
            return
        bar = self.deck_tabs.tabBar()
        order = [a.get("deck_name", "") for a in self._sort_deck_analyses(self.deck_analyses or [])]
        for target, name in enumerate(order):
            current = next((i for i in range(bar.count()) if bar.tabToolTip(i) == name), None)
            if current is not None and current != target:
                bar.moveTab(current, target)
        self.deck_tab_lookup = {bar.tabToolTip(i): i for i in range(bar.count())}
        self._update_deck_tab_flags()

    def _update_deck_tab_flags(self):
        bar = getattr(self, "deck_tab_bar", None)
        if bar is not None:
            bar.set_flags(self.pinned_decks, self.ignored_decks)

    def _refresh_dashboard_summary(self):
        """Stats tab pieces that depend on which decks are ignored."""
        try:
            self._timeline = self._load_timeline()
            self._update_headline_cards(*self._timeline)
            self.update_elo_graph()
            self.update_winrate_graph()
            self.update_deck_usage(self.deck_analyses)
            self.update_recent_battles()
        except Exception as e:
            print(f"Error refreshing dashboard: {e}")

    def _sort_deck_analyses(self, analyses):
        """Pinned first (newest pin first), ignored last, else by last played."""
        def sort_key(analysis):
            name = analysis.get("deck_name", "")
            if name in self.pinned_decks:
                return (0, self.pinned_decks.index(name))
            last = analysis.get("last_played") or ""
            # Descending by last_played: invert the string for sort().
            return (2 if name in self.ignored_decks else 1, _invert_str(last))
        return sorted(analyses, key=sort_key)

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
                if isinstance(widget, LazyDeckPage):
                    if widget.page is not None:
                        widget = widget.page
                    elif widget.pending_scroll is not None and deck_name:
                        prior_scrolls[deck_name] = widget.pending_scroll
                        continue
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

        self._deck_preload_generation = getattr(self, "_deck_preload_generation", 0) + 1
        if not getattr(self, "_lazy_deck_tabs_connected", False):
            self.deck_tabs.currentChanged.connect(self._ensure_deck_page)
            self._lazy_deck_tabs_connected = True

        for analysis in self._sort_deck_analyses(deck_analyses):
            page = LazyDeckPage(analysis)
            icon = self._icon_for_deck(analysis.get("deck_name", ""), analysis.get("deck_icons", []), size=18)
            deck_name = analysis.get("deck_name", "")
            label = self._deck_tab_label(deck_name)
            idx = self.deck_tabs.addTab(page, icon, label)
            self.deck_tabs.tabBar().setTabToolTip(idx, deck_name)
            self.deck_tab_lookup[deck_name] = idx

        self._update_deck_tab_flags()
        for deck_name, scroll_value in prior_scrolls.items():
            idx = self.deck_tab_lookup.get(deck_name)
            widget = self.deck_tabs.widget(idx) if idx is not None else None
            if isinstance(widget, LazyDeckPage):
                widget.pending_scroll = scroll_value  # applied when the page is built
        if current_name in self.deck_tab_lookup:
            self.deck_tabs.setCurrentIndex(self.deck_tab_lookup[current_name])

        self._deck_dashboards_dirty = False
        # Build the visible deck now, the rest one by one in the background.
        self._ensure_deck_page(self.deck_tabs.currentIndex())
        generation = self._deck_preload_generation
        QTimer.singleShot(250, lambda g=generation: self._preload_next_deck_page(g))

    def _prebuild_deck_dashboards(self):
        if getattr(self, "_deck_dashboards_dirty", False):
            self._refresh_deck_dashboards()

    def _ensure_deck_page(self, index):
        """Build the real dashboard page behind a deck tab (once)."""
        if not hasattr(self, "deck_tabs") or index is None or index < 0:
            return
        holder = self.deck_tabs.widget(index)
        if not isinstance(holder, LazyDeckPage) or holder.page is not None:
            return
        try:
            holder.page = self._create_deck_dashboard_page(holder.analysis)
        except Exception as exc:
            print(f"Deck page build failed for {holder.analysis.get('deck_name')}: {exc}")
            holder.page = QLabel("Could not build this deck's dashboard.")
        holder.layout().addWidget(holder.page)
        if holder.pending_scroll is not None and hasattr(holder.page, "verticalScrollBar"):
            value = holder.pending_scroll
            holder.pending_scroll = None
            QTimer.singleShot(0, lambda w=holder.page, v=value: self._restore_scroll_value(w, v))

    def _preload_next_deck_page(self, generation):
        """Build one not-yet-built deck page, then schedule the next.

        One page per tick keeps every step short, so the UI stays responsive
        while all decks become instant to open. A newer refresh (new
        generation) cancels this chain.
        """
        if generation != getattr(self, "_deck_preload_generation", None) or not hasattr(self, "deck_tabs"):
            return
        for index in range(self.deck_tabs.count()):
            holder = self.deck_tabs.widget(index)
            if isinstance(holder, LazyDeckPage) and holder.page is None:
                self._ensure_deck_page(index)
                QTimer.singleShot(120, lambda g=generation: self._preload_next_deck_page(g))
                return

    def _refresh_decks_meta(self, force=False):
        if not REQUESTS_AVAILABLE:
            return
        if hasattr(self, "_decks_meta_fetcher") and self._decks_meta_fetcher.isRunning():
            return

        self._decks_meta_fetcher = MetaFetcher("limitless_standard")
        self._decks_meta_fetcher.data_ready.connect(self._on_decks_meta_data)
        self._decks_meta_fetcher.error.connect(self._on_decks_meta_error)
        _start_thread(self._decks_meta_fetcher)

    def _on_decks_meta_data(self, source, data):
        self.limitless_standard_meta = data
        self._deck_dashboards_dirty = True
        self._meta_tab_dirty = True
        if hasattr(self, "tab_widget") and self.tab_widget.currentIndex() == getattr(self, "meta_tab_index", -1):
            self._populate_meta_tab()
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
            # Loaded on first view of the tab (see handle_tab_changed).
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
    
    def _create_weights_card(self):
        """Advanced → Preferences: data weights for the meta sheet and your games."""
        from PySide6.QtWidgets import QDoubleSpinBox
        card = self.create_card("Preferences · Data Weights")
        body = QVBoxLayout()
        body.setContentsMargins(12, 8, 12, 12)
        body.setSpacing(10)
        columns = QHBoxLayout()
        columns.setSpacing(24)
        self._weight_spins = {}
        current = load_weights()
        for group, title in (("meta", "META DATA"), ("ladder", "YOUR GAMES"), ("strength", "OPPONENT STRENGTH")):
            col = QGridLayout()
            col.setHorizontalSpacing(10)
            col.setVerticalSpacing(6)
            header = QLabel(title)
            header.setObjectName("metaStatTitle")
            col.addWidget(header, 0, 0, 1, 2)
            for row, (key, (label_text, tip)) in enumerate(WEIGHT_LABELS[group].items(), start=1):
                label = QLabel(label_text)
                label.setStyleSheet("color: rgba(235,242,250,0.85); font-size: 11px;")
                spin = QDoubleSpinBox()
                is_gap = key in ("ladder_gap", "rank_margin")
                spin.setRange(1.0 if key == "rank_margin" else 0.0, 30.0 if key == "rank_margin" else 15.0 if is_gap else 5.0)
                spin.setSingleStep(0.5 if is_gap else 0.05)
                spin.setDecimals(1 if is_gap else 2)
                spin.setSuffix(" pts" if is_gap else "×")
                spin.setFixedWidth(84)
                spin.setValue(float(current[group][key]))
                default = DEFAULT_WEIGHTS[group][key]
                hint = f"Default {default:g}{' pts' if is_gap else '×'}" + (f" · {tip}" if tip else "")
                label.setToolTip(hint)
                spin.setToolTip(hint)
                spin.setStyleSheet(SPIN_STYLE)
                col.addWidget(label, row, 0)
                col.addWidget(spin, row, 1)
                self._weight_spins[(group, key)] = spin
            col.setRowStretch(len(WEIGHT_LABELS[group]) + 1, 1)
            columns.addLayout(col)
        columns.addStretch()
        body.addLayout(columns)

        tie_row = QHBoxLayout()
        tie_label = QLabel("Ties count as")
        tie_label.setStyleSheet("color: rgba(235,242,250,0.85); font-size: 11px;")
        tie_row.addWidget(tie_label)
        self.prefs_tie_combo = QComboBox()
        self.prefs_tie_combo.setObjectName("metaCombo")
        for key, (name, formula) in TIE_MODES.items():
            self.prefs_tie_combo.addItem(f"{name}   {formula}", key)
        self.prefs_tie_combo.setCurrentIndex(list(TIE_MODES).index(tie_mode()))
        self.prefs_tie_combo.setToolTip("Applies immediately to the meta, matchups and your own decks.")
        # Same setting as the Meta tab's selector: keep the two in step.
        self.prefs_tie_combo.currentIndexChanged.connect(
            lambda idx: hasattr(self, "meta_tie_combo") and self.meta_tie_combo.setCurrentIndex(idx))
        tie_row.addWidget(self.prefs_tie_combo)
        tie_row.addStretch()
        body.addLayout(tie_row)

        note = QLabel("Expansion multipliers apply to both columns; data older than two expansions is ignored. "
                      "Your games are rescaled to their effective sample size, so weights never invent certainty.")
        note.setObjectName("settingsDesc")
        note.setWordWrap(True)
        body.addWidget(note)

        buttons = QHBoxLayout()
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.setObjectName("settingsBtn")
        reset_btn.setFixedHeight(32)
        reset_btn.clicked.connect(self._reset_weight_spins)
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("settingsBtn")
        apply_btn.setFixedHeight(32)
        apply_btn.clicked.connect(self._apply_weights)
        self._weights_status = QLabel("")
        self._weights_status.setObjectName("settingsDesc")
        buttons.addWidget(reset_btn)
        buttons.addWidget(apply_btn)
        buttons.addWidget(self._weights_status, 1)
        body.addLayout(buttons)
        card.layout().addLayout(body)
        return card

    def _reset_weight_spins(self):
        for (group, key), spin in self._weight_spins.items():
            spin.setValue(DEFAULT_WEIGHTS[group][key])
        self._weights_status.setText("Defaults restored - press Apply to use them.")

    def _apply_weights(self):
        weights = {group: {} for group in DEFAULT_WEIGHTS}
        for (group, key), spin in self._weight_spins.items():
            weights[group][key] = spin.value()
        try:
            save_weights(weights)
        except Exception as exc:
            self._weights_status.setText(f"Could not save: {exc}")
            return
        self._weights_status.setText("Saved. Recalculating…")
        # Your games: recompute every deck analysis now.
        QTimer.singleShot(0, self.load_stats)
        # Meta sheet: rebuild from cached events (a few seconds, no re-download).
        if REQUESTS_AVAILABLE:
            fetcher = MetaFetcher("limitless_standard", force=True)
            fetcher.data_ready.connect(self._on_limitless_data)
            fetcher.data_ready.connect(lambda *_: self._weights_status.setText("Applied to your stats and the meta sheet."))
            fetcher.error.connect(lambda _s, msg: self._weights_status.setText(f"Meta rebuild failed: {msg}"))
            self._weights_fetcher = fetcher
            _start_thread(fetcher)
        else:
            self._weights_status.setText("Applied to your stats.")

    def create_settings_tab(self):
        """Create settings/advanced tab with debug controls"""
        scroll = self._create_standard_scroll_area()
        self.settings_scroll = scroll
        
        content = QWidget()
        content.setObjectName("contentWidget")
        layout = QVBoxLayout(content)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addWidget(self._create_weights_card())

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

        self.auto_export_checkbox = QCheckBox("Auto-export the battle log at the end of each battle")
        self.auto_export_checkbox.setObjectName("settingsCheck")
        self.auto_export_checkbox.setToolTip(
            "Clicks BATTLE LOG and export for you when a battle ends (only while the game window is focused). "
            "Takes effect within a few seconds - no restart needed."
        )
        self.auto_export_checkbox.setChecked(bool(self.app_settings.get("auto_export_battle_log", True)))
        self.auto_export_checkbox.toggled.connect(self._save_auto_export_setting)
        parser_layout.addWidget(self.auto_export_checkbox)

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

    def _sprite_downloader(self):
        downloader = getattr(self, "_sprites_bg", None)
        if downloader is None:
            downloader = self._sprites_bg = SpriteDownloader()
            downloader.downloaded.connect(self._on_sprites_downloaded)
        return downloader

    def _on_sprites_downloaded(self, names):
        """Show freshly downloaded sprites: one debounced refresh per batch."""
        if not hasattr(self, "_sprite_refresh_timer"):
            self._sprite_refresh_timer = QTimer(self)
            self._sprite_refresh_timer.setSingleShot(True)
            self._sprite_refresh_timer.timeout.connect(self.load_stats)
        self._sprite_refresh_timer.start(800)

    def _load_sprite_pixmap(self, sprite_name, size=24):
        if not sprite_name:
            return None
        cache_key = (sprite_name, size)
        cached = self._sprite_pixmap_cache.get(cache_key)
        if cached is not None:
            return cached
        cache_path = _find_cached_sprite_path(sprite_name)
        if cache_path is None:
            # Never download on the UI thread: callers draw a placeholder now
            # and the page refreshes when the background download lands.
            self._sprite_downloader().request(sprite_name)
            return None
        if not os.path.exists(cache_path):
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

    # 5x7 pixel-art question mark (1 = filled), matching the 8-bit sprite style.
    _PIXEL_QUESTION = ("01110", "10001", "00001", "00110", "00100", "00000", "00100")

    @staticmethod
    def _deck_initial(deck_name):
        """Placeholder label for a deck: '?' for the catch-all 'Other' bucket."""
        name = (deck_name or "").strip()
        return "?" if not name or name.lower() == "other" else name[:1]

    def _build_placeholder_sprite(self, label_text, size=24, accent="#4A9FD8"):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        if (label_text or "?") == "?":
            # Pixel-art "?" on a dark slate tile (unknown / catch-all decks).
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#2E3A4E"))
            painter.drawRoundedRect(0, 0, size, size, max(2, size // 6), max(2, size // 6))
            cell = max(1, size // 9)
            ox = (size - 5 * cell) // 2
            oy = (size - 7 * cell) // 2
            painter.setBrush(QColor("#FFD54F"))
            for r, row in enumerate(self._PIXEL_QUESTION):
                for c, bit in enumerate(row):
                    if bit == "1":
                        painter.drawRect(ox + c * cell, oy + r * cell, cell, cell)
            painter.end()
            return pixmap
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

    def _create_deck_cell_widget(self, deck_name, icons=None, subtitle=None, icon_size=24, mine=False):
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

        if self._deck_initial(deck_name) == "?":
            icons = []  # the catch-all bucket always uses the pixel "?" icon
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
            fallback.setPixmap(self._build_placeholder_sprite(self._deck_initial(deck_name), icon_size))
            fallback.setFixedSize(icon_size + 2, icon_size + 2)
            icon_row.addWidget(fallback)

        layout.addWidget(icon_wrap)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        title = QLabel(deck_name)
        title.setStyleSheet(("color: #E4D9FF; font-size: 11px; font-weight: 800;" if mine else
                             "color: rgba(242,247,255,0.96); font-size: 11px; font-weight: 600;")
                            + " background: transparent;")
        # Ensure the label reports its full text width so the column is wide
        # enough to show the whole deck name (never cut off).
        title.setMinimumWidth(title.fontMetrics().horizontalAdvance(deck_name) + 4)
        text_col.addWidget(title)

        if mine:
            badge = QLabel(f"<span style='background:#B39DDB; color:#14101F; font-weight:800;'>&nbsp;YOUR DECK&nbsp;</span>"
                           f"<span style='color:#B39DDB;'>&nbsp; {subtitle or ''}</span>")
            badge.setTextFormat(Qt.TextFormat.RichText)
            badge.setStyleSheet("font-size: 8px; background: transparent;")
            text_col.addWidget(badge)
        elif subtitle:
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

    def _set_meta_deck_cell(self, table, row, col, deck_name, icons=None, subtitle=None, *, sort_value=None, link=None,
                            mine=False):
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
            self._create_deck_cell_widget(deck_name, icons, subtitle=subtitle, mine=mine),
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
                if _is_safe_web_url(link):
                    webbrowser.open(link)
                return

    def _trend_display(self, trend):
        if trend == "up":
            return "UP", "#66BB6A"
        if trend == "down":
            return "DOWN", "#EF5350"
        return "EVEN", "#F9A825"

    def _open_row_link(self, links, row):
        if 0 <= row < len(links) and links[row] and _is_safe_web_url(links[row]):
            webbrowser.open(links[row])

    def handle_tab_changed(self, index):
        tab_name = self.tab_widget.tabText(index)
        if tab_name == "Limitless TCG Live Meta" and self.limitless_table.rowCount() == 0 and self.limitless_refresh_btn.isEnabled():
            self._fetch_limitless_data()
        elif tab_name == "In Person":
            self._refresh_decklist_choices()
        elif tab_name == "Meta":
            if not self._top_limitless_rows():
                self._refresh_decks_meta()
            elif getattr(self, "_meta_tab_dirty", True):
                self._populate_meta_tab()
        elif tab_name == "Decks":
            if not self._top_limitless_rows():
                self._refresh_decks_meta()
            if self._deck_dashboards_dirty:
                self._refresh_deck_dashboards()
        elif tab_name == "Limitless Dashboard":
            if self.limitless_manager:
                self.limitless_manager.enable_background_mode()
                self.limitless_manager.ensure_visible_dashboard_loaded()
        elif tab_name == "Replay":
            view = getattr(self, "replay_view", None)
            if view is not None and view.url().isEmpty():
                view.load(QUrl(PTCGL_REPLAY_URL))
        elif tab_name == "PokeData":
            view = getattr(self, "_pokedata_webview", None)
            if view is not None and view.url().isEmpty():
                view.load(QUrl(self._pokedata_home_url))
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

    # ── In Person tab ────────────────────────────────────────────────────
    IN_PERSON_LINKS = {
        "events": "https://www.seagrovetcg.com/event-finder",
        "homies": "https://www.seagrovetcg.com/homies",
        "print": "https://www.pokedata.ovh/paper/",
    }

    def create_in_person_tab(self):
        outer = QWidget()
        outer.setObjectName("contentWidget")
        vlayout = QVBoxLayout(outer)
        vlayout.setContentsMargins(12, 10, 12, 12)
        vlayout.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(8)
        title = QLabel("IN PERSON")
        title.setObjectName("sectionHeader")
        row.addWidget(title)
        row.addSpacing(8)
        self._in_person_buttons = {}
        for key, text, tip in (
                ("events", "Event finder", "Find Pokémon TCG events near you (Seagrove TCG)."),
                ("homies", "Track your homies", "Follow your friends' tournament results (Seagrove TCG)."),
                ("print", "Print your decklist", "Tournament decklist sheet (pokedata.ovh), pre-filled with your "
                                                   "deck exported from Pokémon TCG Live.")):
            btn = QPushButton(text)
            btn.setObjectName("limitlessBtn")
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _checked=False, k=key: self._open_in_person(k))
            row.addWidget(btn)
            self._in_person_buttons[key] = btn
        row.addSpacing(10)
        self.in_person_deck_combo = QComboBox()
        self.in_person_deck_combo.setObjectName("metaCombo")
        self.in_person_deck_combo.setFixedHeight(30)
        self.in_person_deck_combo.setMinimumWidth(200)
        self.in_person_deck_combo.setToolTip("Which captured decklist to print.")
        self.in_person_deck_combo.currentIndexChanged.connect(lambda *_: self._fill_decklist_if_open())
        row.addWidget(self.in_person_deck_combo)
        row.addStretch()
        open_ext = QPushButton("Open in browser ↗")
        open_ext.setObjectName("limitlessBtn")
        open_ext.setFixedHeight(32)
        open_ext.clicked.connect(lambda: webbrowser.open(self.IN_PERSON_LINKS.get(getattr(self, "_in_person_current", "events"))))
        row.addWidget(open_ext)
        vlayout.addLayout(row)

        self.in_person_status = QLabel("")
        self.in_person_status.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 10px;")
        self.in_person_status.setWordWrap(True)
        vlayout.addWidget(self.in_person_status)

        if WEBENGINE_AVAILABLE:
            self.in_person_view = QWebEngineView()
            self.in_person_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            self.in_person_view.loadFinished.connect(self._on_in_person_loaded)
            vlayout.addWidget(self.in_person_view, stretch=1)
        else:
            self.in_person_view = None
            vlayout.addStretch()
        self._refresh_decklist_choices()
        return outer

    def _refresh_decklist_choices(self):
        try:
            from decklists import all_decklists, latest_decklist
            decks, latest = all_decklists(), latest_decklist()
        except Exception:
            decks, latest = {}, None
        combo = self.in_person_deck_combo
        current = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for name, entry in sorted(decks.items(), key=lambda kv: kv[1].get("captured_at", ""), reverse=True):
            combo.addItem(f"{name} · {entry.get('cards', '?')} cards", name)
        if current is not None and combo.findData(current) >= 0:
            combo.setCurrentIndex(combo.findData(current))
        combo.blockSignals(False)
        combo.setVisible(combo.count() > 0)
        if latest:
            self.in_person_status.setText(
                f"Decklist ready: {latest['deck']} ({latest['cards']} cards, exported {latest['captured_at']}). "
                "To update: Pokémon TCG Live → Decks → your deck → Export → Copy to clipboard.")
        else:
            self.in_person_status.setText(
                "No decklist captured yet - in Pokémon TCG Live open Decks → your deck → Export → Copy to clipboard "
                "while the monitor is running, and it's saved here automatically.")

    def _selected_decklist_text(self):
        try:
            from decklists import all_decklists, latest_decklist
            name = self.in_person_deck_combo.currentData()
            entry = all_decklists().get(name) if name else latest_decklist()
            return (entry or {}).get("text")
        except Exception:
            return None

    def _open_in_person(self, key):
        self._in_person_current = key
        for k, btn in self._in_person_buttons.items():
            btn.setChecked(k == key)
        if key == "print":
            self._refresh_decklist_choices()
        if self.in_person_view is None:
            webbrowser.open(self.IN_PERSON_LINKS[key])
            return
        self.in_person_view.load(QUrl(self.IN_PERSON_LINKS[key]))

    def _on_in_person_loaded(self, ok):
        if ok and getattr(self, "_in_person_current", None) == "print":
            self._fill_decklist_if_open()

    def _fill_decklist_if_open(self):
        """Put the captured decklist into pokedata's paper tool (its own
        'Paste Decklist' reads the clipboard; we hand the text over directly)."""
        if getattr(self, "_in_person_current", None) != "print" or self.in_person_view is None:
            return
        text = self._selected_decklist_text()
        if not text:
            return
        # pokedata reads card lines only; PTCGL's section headers
        # ("Pokémon: 12", "Total Cards: 60") would show as "not found".
        text = "\n".join(line for line in text.splitlines()
                         if line.strip() and not re.match(r"^\s*(Pok[eé]mon|Trainer|Energy|Total Cards)\s*:", line, re.I))
        script = ("(function(){var el=document.getElementById('data');"
                  "if(!el||typeof translateDecklist!=='function')return false;"
                  f"el.textContent={json.dumps(text)};translateDecklist();return true;}})()")
        self.in_person_view.page().runJavaScript(
            script, lambda ok: ok or self.in_person_status.setText(
                "The print page changed and couldn't be filled automatically - use its Paste Decklist button."))

    # ── Meta tab: unified, preference-weighted analysis ───────────────────
    def create_meta_tab(self):
        """All sources combined (online W/L + matchups, in-person placings,
        Japan), weighted per Advanced → Preferences. TrainerHill-style
        result-rate options for ties."""
        from PySide6.QtWidgets import QSpinBox
        outer = QWidget()
        outer.setObjectName("contentWidget")
        vlayout = QVBoxLayout(outer)
        vlayout.setContentsMargins(12, 10, 12, 12)
        vlayout.setSpacing(8)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        title = QLabel("META")
        title.setObjectName("sectionHeader")
        controls.addWidget(title)
        controls.addSpacing(8)

        def label(text, tip=None):
            lbl = QLabel(text)
            lbl.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
            if tip:
                lbl.setToolTip(tip)
            return lbl

        controls.addWidget(label("Ties:"))
        self.meta_tie_combo = QComboBox()
        self.meta_tie_combo.setObjectName("metaCombo")
        self.meta_tie_combo.setFixedHeight(28)
        for key, (name, formula) in TIE_MODES.items():
            self.meta_tie_combo.addItem(f"{name}   {formula}", key)
        self.meta_tie_combo.setCurrentIndex(list(TIE_MODES).index(tie_mode()))
        self.meta_tie_combo.setToolTip("How ties count in every win rate (meta, matchups and your own decks).")
        self.meta_tie_combo.currentIndexChanged.connect(self._on_meta_tie_mode_changed)
        controls.addWidget(self.meta_tie_combo)

        controls.addWidget(label("Min games:", "Matchups / archetypes with fewer (weighted) games are greyed or skipped."))
        self.meta_min_games = QSpinBox()
        self.meta_min_games.setRange(0, 2000)
        self.meta_min_games.setSingleStep(10)
        self.meta_min_games.setValue(30)
        self.meta_min_games.setFixedWidth(80)
        self.meta_min_games.setStyleSheet(SPIN_STYLE)
        self.meta_min_games.valueChanged.connect(lambda *_: self._populate_meta_tab())
        controls.addWidget(self.meta_min_games)

        self.meta_matrix_size_label = label("Matrix:", "Number of most-played archetypes in the matchup matrix.")
        controls.addWidget(self.meta_matrix_size_label)
        self.meta_matrix_size = QSpinBox()
        self.meta_matrix_size.setRange(4, 30)
        self.meta_matrix_size.setValue(14)
        self.meta_matrix_size.setFixedWidth(66)
        self.meta_matrix_size.setStyleSheet(SPIN_STYLE)
        self.meta_matrix_size.valueChanged.connect(lambda *_: self._populate_meta_tab())
        controls.addWidget(self.meta_matrix_size)

        self.meta_include_jp = QCheckBox("Japan-only decks")
        self.meta_include_jp.setToolTip("Show decks that only appear in Japan (cards not yet released in English).")
        self.meta_include_jp.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 11px;")
        self.meta_include_jp.toggled.connect(lambda *_: self._populate_meta_tab())
        controls.addWidget(self.meta_include_jp)

        self.meta_include_mine = QCheckBox("★ Starred decks")
        self.meta_include_mine.setChecked(True)
        self.meta_include_mine.setToolTip("Add your starred decks (star button on a deck's page) as rows and matrix "
                                          "rows, using your weighted games vs each meta archetype. Kept separate "
                                          "from the public data.")
        self.meta_include_mine.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 11px;")
        self.meta_include_mine.toggled.connect(lambda *_: self._populate_meta_tab())
        controls.addWidget(self.meta_include_mine)
        self.meta_mine_basis = QComboBox()
        self.meta_mine_basis.setObjectName("metaCombo")
        self.meta_mine_basis.setFixedHeight(28)
        self.meta_mine_basis.addItem("scored with archetype", "blended")
        self.meta_mine_basis.addItem("scored on own games only", "own")
        self.meta_mine_basis.setToolTip(
            "<b>With archetype</b>: your deck counts as a version of the Limitless archetype it matches - "
            "your games adjust that archetype's measured strength (best for comparing decks).<br>"
            "<b>Own games only</b>: your games alone, nothing borrowed from Limitless - your results with "
            "this deck vs the field, still adjusted for sample size.")
        self.meta_mine_basis.currentIndexChanged.connect(lambda *_: self._populate_meta_tab())
        controls.addWidget(self.meta_mine_basis)
        controls.addStretch()

        refresh = QPushButton("↻ Refresh")
        refresh.setObjectName("limitlessBtn")
        refresh.setFixedHeight(28)
        refresh.clicked.connect(self._refresh_meta_tab_data)
        controls.addWidget(refresh)
        vlayout.addLayout(controls)

        # Which data feeds the sheet: sources, and Preferences weights on/off.
        # Applied to this tab only (deck pages keep the full weighted sheet).
        view_row = QHBoxLayout()
        view_row.setSpacing(4)
        view_row.addWidget(label("Data:", "Which events feed this sheet. Records, Win % and Scores need online "
                                          "events (in-person and Japan publish placings only)."))
        self.meta_source_buttons = {}
        for key, text, tip in (("all", "All sources", "Online + in-person + Japan"),
                               ("online", "Online", "play.limitlesstcg.com events: shares, records, matchups"),
                               ("in_person", "In-person", "Regionals / Internationals / Worlds: shares and top cuts"),
                               ("japan", "Japan", "City Leagues: shares and top cuts")):
            btn = QPushButton(text)
            btn.setObjectName("eloScaleBtn")
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.setFixedHeight(24)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _c=False, k=key: self._set_meta_view(source=k))
            view_row.addWidget(btn)
            self.meta_source_buttons[key] = btn
        view_row.addSpacing(14)
        self.meta_weights_btn = QPushButton("Custom weights")
        self.meta_weights_btn.setObjectName("eloScaleBtn")
        self.meta_weights_btn.setCheckable(True)
        self.meta_weights_btn.setChecked(True)
        self.meta_weights_btn.setFixedHeight(24)
        self.meta_weights_btn.setToolTip(
            "<b>On</b>: weighted by your Preferences (Advanced → Preferences)<br>" + formulas.event_weights()
            + "<br>" + formulas.game_weights()
            + "<br><b>Off</b>: every event and game counts once (raw data, same date window).")
        self.meta_weights_btn.toggled.connect(lambda on: self._set_meta_view(weights=on))
        view_row.addWidget(self.meta_weights_btn)
        view_row.addStretch()
        vlayout.addLayout(view_row)

        self.meta_status = QLabel("Loading meta data…")
        self.meta_status.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 10px;")
        vlayout.addWidget(self.meta_status)

        key = QLabel(
            "<span style='color:#FFD54F'>⚖</span> weighted by your Preferences (event type · expansion · size) &nbsp;│&nbsp; "
            "<span style='color:#6BB6E8'>●</span> online: W/L, Win %, matchups &nbsp; "
            "<span style='color:#FFD54F'>●</span> in-person: share, top cut &nbsp; "
            "<span style='color:#EF7A9A'>●</span> Japan: share, top cut &nbsp; "
            "<span style='color:#B39DDB'>★</span> your games")
        key.setTextFormat(Qt.TextFormat.RichText)
        key.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 10px;")
        key.setToolTip("Win % and records come only from online events - in-person and Japanese results publish "
                       "placings, not match records. Shares blend all sources.")
        vlayout.addWidget(key)

        self.meta_views = QTabWidget()
        self.meta_views.setObjectName("deckTabs")
        self.meta_views.setDocumentMode(True)

        self.meta_arch_table = self._make_meta_table(
            ["#", "Deck", "Score", "Range", "Share ⚖", "Top cut ⚖", "Record ⚖", "Win % ⚖", "Converts ⚖", "Sources"],
            [40, None, 62, 120, 72, 80, 126, 70, 86, 74], sortable=True, stretch_last=False)
        self.meta_arch_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.meta_arch_table.cellDoubleClicked.connect(lambda row, col: self._open_table_row_link(self.meta_arch_table, row))
        self._meta_row_delegate = MineRowDelegate(self.meta_arch_table)
        self.meta_arch_table.setItemDelegate(self._meta_row_delegate)
        for col, tip in enumerate([
                "Rank by Score (decks with enough games). ★ = your deck.",
                "Double-click to open the archetype on Limitless. ★ rows are your own decks.",
                "<b>Score</b> = expected win rate vs today's meta<br>"
                + formulas.F + "Score = Σ share × matchup estimate" + formulas.END + "<br>"
                + formulas.F + "matchup estimate = (k·θ + wins) / (k + games)" + formulas.END + "<br>"
                + formulas.DIM + "θ = deck strength; k and the typical deck are fitted to all Limitless data. Sample "
                "size, player clustering and your weights are all included. Hover a score for its numbers."
                + formulas.END,
                "Confidence range (90%) of the Score · white tick = 50%",
                "<b>Share of the field</b> · English-legal unless Japan-only decks are shown<br>"
                + formulas.SHARE + "<br>" + formulas.event_weights(),
                "<b>Share of top finishes</b> (in-person + Japan)<br>" + formulas.TOP_CUT,
                "<b>W-L-T</b> · online events only, weighted (not raw counts)<br>" + formulas.event_weights()
                + "<br><span style='color:#8A97AA'>★ rows: your games, weighted by your Preferences.</span>",
                "Raw result rate under the selected tie rule · from the weighted record.",
                "<b>Top 32 conversion</b> (in-person only)<br>" + formulas.CONVERTS,
                "● online  ● in-person  ● Japan  ★ you"]):
            if tip and self.meta_arch_table.horizontalHeaderItem(col):
                self.meta_arch_table.horizontalHeaderItem(col).setToolTip(tip)
        self.meta_views.addTab(self.meta_arch_table, "Archetypes")

        self.meta_matrix = QTableWidget()
        self.meta_matrix.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.meta_matrix.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.meta_matrix.setShowGrid(False)
        self.meta_matrix.setIconSize(QSize(26, 26))
        self.meta_matrix.setStyleSheet(
            "QTableWidget { background: rgba(10,14,22,0.92); border: 1px solid rgba(255,255,255,0.08);"
            " border-radius: 8px; color: #EEF4FF; font-size: 11px; }"
            "QHeaderView { background: rgb(12,17,26); border: none; }"
            "QHeaderView::section { background: rgb(16,22,32); color: rgba(220,230,244,0.85);"
            " border: none; padding: 3px; font-size: 10px; }"
            "QTableCornerButton::section { background: rgb(12,17,26); border: none; }")
        self.meta_views.addTab(self.meta_matrix, "Matchups")
        self.meta_views.currentChanged.connect(self._on_meta_view_changed)
        vlayout.addWidget(self.meta_views, stretch=1)
        self._on_meta_view_changed(0)
        return outer

    def _refresh_meta_tab_data(self):
        self.meta_status.setText("Refreshing… (new events only; cached events are instant)")
        fetcher = MetaFetcher("limitless_standard", force=True)
        fetcher.data_ready.connect(self._on_limitless_data)
        fetcher.error.connect(lambda _s, msg: self.meta_status.setText(f"Refresh failed: {msg}"))
        self._meta_fetcher = fetcher
        _start_thread(fetcher)

    def _on_meta_tie_mode_changed(self, index):
        mode = self.meta_tie_combo.itemData(index)
        if hasattr(self, "prefs_tie_combo") and self.prefs_tie_combo.currentIndex() != index:
            self.prefs_tie_combo.blockSignals(True)
            self.prefs_tie_combo.setCurrentIndex(index)
            self.prefs_tie_combo.blockSignals(False)
        try:
            from app_settings import load_app_settings, save_app_settings
            settings = load_app_settings()
            settings["tie_mode"] = mode
            save_app_settings(settings)
        except Exception:
            pass
        from deck_analytics import set_tie_mode_cached
        set_tie_mode_cached(mode)
        self._populate_meta_tab()
        QTimer.singleShot(0, self.load_stats)  # your decks use the same tie rule

    def _meta_rate_posterior(self, w, l, t, prior_mean=0.5, strength=4.0):
        return win_rate_posterior(w, l, t, prior_mean=prior_mean, prior_strength=strength)

    @staticmethod
    def _beta_mean_sd(w, l, t, prior_mean=0.5, strength=4.0):
        """Posterior mean/sd only (closed form, no quantiles) - fast path for
        the thousands of matchup cells behind 'Vs field'."""
        from deck_analytics import tie_split
        tw, tl = tie_split(t)
        a = float(w or 0) + tw + prior_mean * strength
        b = float(l or 0) + tl + (1.0 - prior_mean) * strength
        n = a + b
        return a / n, math.sqrt(a * b / (n * n * (n + 1.0)))

    def _my_deck_meta_rows(self, meta_rows, starred_only=True, use_weights=True):
        """Your decks as meta rows: weighted record + matchups vs meta archetypes
        (opponents mapped to Limitless archetypes; unmatched -> 'Other').
        mirror_id = the archetype the deck itself matches (its mirror)."""
        expansions = cached_expansions("en")
        other_key = next((r["id"] for r in meta_rows if str(r.get("deck", "")).lower() == "other"), None)

        def record(battles):
            if use_weights:
                return weighted_record(battles, expansions)
            kinds = [str(b.get("result", "")).strip().lower() for b in battles]
            wins = kinds.count("win")
            ties = sum(1 for k in kinds if k in ("tie", "draw"))
            return float(wins), float(len(kinds) - wins - ties), float(ties)
        match_cache = {}
        icons_by_deck = {a.get("deck_name"): a.get("deck_icons") or [] for a in (self.deck_analyses or [])}
        mine = []
        for deck_name, games, *_rest in self.db.get_deck_usage_stats(limit=None):
            if deck_name in self.ignored_decks or (starred_only and deck_name not in self.starred_decks):
                continue
            detailed = self.db.get_deck_battles_detailed(deck_name)
            ww, wl, wt = record(detailed)
            if ww + wl + wt <= 0:
                continue

            def ladder_frac(battles):
                """Share of the (weighted) games that were ladder, not Limitless tournament."""
                ws = [(battle_weight(b, expansions) if use_weights else 1.0, bool(b.get("is_tournament")))
                      for b in battles]
                total = sum(w for w, _t in ws)
                return sum(w for w, tour in ws if not tour) / total if total > 0 else 1.0
            groups = {}
            for b in detailed:
                opp = b.get("opponent") or ""
                if opp not in match_cache:
                    hit = match_meta_row(opp, meta_rows)
                    match_cache[opp] = hit["row"]["id"] if hit else other_key
                key = match_cache[opp]
                if key:
                    groups.setdefault(key, []).append(b)
            mine.append({
                "id": f"you:{deck_name}", "deck": deck_name, "icons": icons_by_deck.get(deck_name, []),
                "is_mine": True, "wins": ww, "losses": wl, "ties": wt, "raw_games": games,
                "matchups": {k: list(record(v)) for k, v in groups.items()},
                "ladder_frac": ladder_frac(detailed),
                "matchup_ladder_frac": {k: ladder_frac(v) for k, v in groups.items()},
                "sources": {"you": games}, "deck_url": None,
                "mirror_id": (match_meta_row(deck_name, meta_rows) or {}).get("row", {}).get("id"),
            })
        return mine

    def _set_meta_view(self, source=None, weights=None):
        if source is not None:
            self._meta_source = source
            for key, btn in getattr(self, "meta_source_buttons", {}).items():
                btn.setChecked(key == source)
        if weights is not None:
            self._meta_use_weights = bool(weights)
        self._populate_meta_tab()

    def _meta_view_sheet(self):
        """The sheet for the Meta tab's Data / Custom weights choice. The
        default view is the regular sheet; others are re-assembled from the
        cached events (no downloads, ~0.2 s) and kept in memory."""
        base = self.limitless_standard_meta or {}
        source = getattr(self, "_meta_source", "all")
        use_weights = getattr(self, "_meta_use_weights", True)
        if source == "all" and use_weights:
            return base
        key = (base.get("fetched_at"), source, use_weights)
        cache = getattr(self, "_meta_view_cache", {})
        if key not in cache:
            from meta_sources import ALL_SOURCES, rebuild_meta_sheet
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                sheet = rebuild_meta_sheet(use_weights, ALL_SOURCES if source == "all" else (source,))
            except Exception as e:
                print(f"Meta view rebuild failed: {e}")
                sheet = None
            finally:
                QApplication.restoreOverrideCursor()
            if sheet is None:
                return None
            sheet["fetched_at"] = base.get("fetched_at")
            cache = {key: sheet}  # keep only the latest alternative view
            self._meta_view_cache = cache
        return cache[key]

    def _deck_scores(self, data=None, use_weights=True):
        """Deck Scores (deck_score.py) for every archetype and all your
        non-ignored decks. Cached until the meta sheet, your games, the tie
        rule, your preferences or the deck flags change."""
        data = data if data is not None else (self.limitless_standard_meta or {})
        rows = list(data.get("rows") or [])
        if not rows:
            return {}, {}
        try:
            signature = self.db.data_signature()
        except Exception:
            signature = None
        try:
            prefs = os.path.getmtime(os.path.join(BASE_DIR, ".app_settings.json"))
        except OSError:
            prefs = None
        key = (id(data), data.get("fetched_at"), len(rows), signature, tie_mode(), prefs, tuple(self.ignored_decks),
               use_weights, self.meta_min_games.value() if hasattr(self, "meta_min_games") else 0)
        caches = getattr(self, "_score_caches", {})
        if key in caches:
            return caches[key]
        mine = self._my_deck_meta_rows(rows, starred_only=False, use_weights=use_weights)
        try:
            results, info = compute_scores(rows, mine, pilot_sd=data.get("pilot_sd"), min_meta_games=key[-1],
                                           strength=load_weights()["strength"] if use_weights else None)
        except Exception as e:
            print(f"Deck score error: {e}")
            results, info = {}, {}
        info["mine"] = {m["id"]: m for m in mine}
        # Two entries: the regular sheet (deck pages) and the Meta tab's view.
        caches = {k: v for k, v in caches.items() if k[0] == id(self.limitless_standard_meta or {})}
        caches[key] = (results, info)
        self._score_caches = caches
        return results, info

    def _score_tooltip(self, name, res, info, is_mine):
        level = int(round(info.get("level", 0.9) * 100))
        lines = [f"<b>{name}</b>",
                 f"Score <b>{res['score'] * 100:.1f}</b> · range {_pct_range(res['low'], res['high'])}"]
        if res.get("rank"):
            lines.append(f"{'Would rank' if is_mine else 'Rank'} #{res['rank']} of {info.get('ranked', 0)} meta decks · "
                         f"{res.get('p_top5', 0) * 100:.0f}% chance it's really top 5"
                         + (f" · {res['p_first'] * 100:.0f}% #1" if res.get("p_first", 0) >= 0.01 else ""))
        elif not res.get("qualifies") and info.get("n_needed"):
            lines.append(f"Not ranked yet: {res['eff_games']:.1f} of {info['n_needed']:.0f} effective games")
            lines.append(f"{formulas.F}ranked when effective games ≥ (1.645 × 0.5 / {info.get('rank_margin', 15):g}%)² "
                         f"= {info['n_needed']:.0f}{formulas.END}  {formulas.DIM}(± {info.get('rank_margin', 15):g} pts "
                         f"precision at 90%; effective = after weighting and opponent strength){formulas.END}")
        lines.append(f"{res['p_above_even'] * 100:.0f}% chance it beats the field (above 50%) · "
                     f"{res['eff_games']:.0f} effective games · matchups seen for {res['coverage'] * 100:.0f}% of the field")
        lines.append("<b>How it's calculated</b> · expected win rate vs today's meta "
                     f"({level}% range)")
        rows = (self.limitless_standard_meta or {}).get("rows") or []
        names = {r["id"]: r.get("deck", r["id"]) for r in rows}
        archetype = names.get(res.get("mirror_id")) if is_mine else None
        lines.append(formulas.score(res, info, is_mine, names, archetype))
        own = res.get("own") if is_mine else None
        if own:
            lines.append(f"<b>Own games only</b>: {own['score'] * 100:.1f} · range {_pct_range(own['low'], own['high'])}"
                         + (f" · would rank #{own['rank']}" if own.get("rank") and res.get("qualifies") else ""))
            lines.append(formulas.own_score(own, info))
        if is_mine:
            lines.append("<span style='color:#8A97AA'>Your games also carry your piloting and ladder opponents; "
                         "meta rows are an average Limitless player.</span>")
        return "<br>".join(lines)

    def _populate_meta_tab(self):
        if not hasattr(self, "meta_arch_table"):
            return
        data = self._meta_view_sheet()
        if data is None:
            self.meta_status.setText("This view is built from the event cache - press ↻ Refresh once to create it.")
            data = self.limitless_standard_meta or {}
        rows = list(data.get("rows") or [])
        self._meta_tab_dirty = False
        if not rows:
            self.meta_status.setText("No meta data yet - press ↻ Refresh.")
            return
        use_weights = getattr(self, "_meta_use_weights", True)
        include_jp = self.meta_include_jp.isChecked()
        min_games = self.meta_min_games.value()
        share_key = "share" if include_jp else "share_en"
        rows = [r for r in rows if (r.get(share_key) or 0) > 0]
        rows.sort(key=lambda r: -(r.get(share_key) or 0))
        by_key = {r["id"]: r for r in rows}
        field_total = sum(r.get("share_en") or 0 for r in rows) or 1.0

        def overall(r):
            return self._meta_rate_posterior(r.get("wins"), r.get("losses"), r.get("ties"))

        scores, score_info = self._deck_scores(data, use_weights)
        mine = ([m for m in score_info.get("mine", {}).values() if m["deck"] in self.starred_decks]
                if self.meta_include_mine.isChecked() else [])

        mode_name = TIE_MODES[tie_mode()][0]
        events = data.get("events") or {}
        exp = ((data.get("expansions") or {}).get("en") or [{}])[0]
        fetched = data.get("fetched_at")
        stamp = datetime.fromtimestamp(fetched).strftime("%b %d %H:%M") if fetched else "?"
        self.meta_status.setText(
            f"{len(rows)} archetypes · {events.get('online', 0)} online · {events.get('in_person', 0)} in-person · "
            f"{events.get('japan', 0)} Japan events · set: {exp.get('name', '?')} · ties: {mode_name} · updated {stamp}"
            + (f" · sorted by Score ({score_info.get('ranked', 0)} ranked)" if score_info.get("ranked") else
               " · no Score here: in-person and Japan publish placings, not match records")
            + ("" if use_weights else " · raw data (custom weights off)"))

        table = self.meta_arch_table
        sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)
        table.setUpdatesEnabled(False)  # one repaint at the end, not one per cell
        # Ranked decks by Score first (yours included once they have enough
        # games), then the rest by share.
        pool = mine + rows[:80]

        own_basis = (getattr(self, "meta_mine_basis", None) is not None
                     and self.meta_mine_basis.currentData() == "own")

        def score_for(r):
            res = scores.get(r["id"]) or {}
            if r.get("is_mine") and own_basis and res.get("own"):
                return dict(res["own"], eff_games=res.get("eff_games", 0), qualifies=res.get("qualifies"),
                            needs=res.get("needs"), mirror_id=res.get("mirror_id"), is_mine=True, own_of=res)
            return res

        def order(r):
            # Everything with a Score in Score order (ranked or not - an
            # unranked deck just shows no rank number); rows without match
            # records (placings only) last, by share.
            res = score_for(r)
            if res and res.get("eff_games", 0) > 0:
                return (0, -res["score"], 0 if r.get("is_mine") else 1)
            return (1, -(r.get(share_key) or 0), 0)
        shown = sorted(pool, key=order)
        table.setRowCount(0)
        table.setRowCount(len(shown))
        for i, r in enumerate(shown):
            link = r.get("deck_url")
            is_mine = bool(r.get("is_mine"))
            res = score_for(r)
            table.setRowHeight(i, 40)
            share = r.get(share_key) or 0.0
            rank = res.get("rank")
            self._set_meta_item(table, i, 0, (f"★{rank}" if rank else "★") if is_mine else (str(rank) if rank else ""),
                                accent="#B39DDB" if is_mine else None, muted=not rank and not is_mine,
                                sort_value=rank or 9999, link=link)
            table.item(i, 0).setData(MINE_ROLE, is_mine)
            basis = "own games" if (is_mine and own_basis) else "with archetype"
            eff = res.get("eff_games", 0)
            self._set_meta_deck_cell(table, i, 1, r.get("deck", ""), r.get("icons", []),
                                     subtitle=(f"{r.get('raw_games', 0)} games ≈ {eff:.0f} effective · {basis}"
                                               if is_mine else None),
                                     sort_value=r.get("deck", "").lower(), link=link, mine=is_mine)
            # Score + its range
            if res and res.get("eff_games", 0) > 0:
                sc = res["score"]
                sacc = self._confidence_accent(res["p_above_even"])
                self._set_meta_item(table, i, 2, f"{sc * 100:.1f}", accent=sacc, sort_value=sc, link=link)
                tip = self._score_tooltip(r.get("deck", ""), res.get("own_of", res), score_info, is_mine)
                table.item(i, 2).setToolTip(tip)
                bar_wrap = QWidget()
                bar_layout = QHBoxLayout(bar_wrap)
                bar_layout.setContentsMargins(6, 0, 6, 0)
                bar = RangeBar(res["low"], sc, res["high"], sacc, height=14)
                bar.setToolTip(tip)
                bar_layout.addWidget(bar)
                table.setCellWidget(i, 3, bar_wrap)
                self._set_meta_item(table, i, 3, "", sort_value=res["low"], link=link)
            else:
                self._set_meta_item(table, i, 2, "", muted=True, sort_value=-1, link=link)
                self._set_meta_item(table, i, 3, "", muted=True, sort_value=-1, link=link)
            if is_mine:
                self._set_meta_item(table, i, 4, "", muted=True, sort_value=-1)
                self._set_meta_item(table, i, 5, "", muted=True, sort_value=-1)
            else:
                self._set_meta_item(table, i, 4, f"{share:.1f}%", sort_value=share, link=link)
                top = r.get("top_share")
                self._set_meta_item(table, i, 5, f"{top:.1f}%" if top else "", muted=not top, sort_value=top or 0, link=link)
            w, l, t = (float(r.get(k) or 0) for k in ("wins", "losses", "ties"))
            games = w + l + t
            if games < (1 if is_mine else max(1, min_games)):
                for col in (6, 7):
                    self._set_meta_item(table, i, col, "", muted=True, sort_value=-1, link=link)
            else:
                rate = result_rate(w, l, t)
                self._set_meta_item(table, i, 6, f"{w:,.0f}-{l:,.0f}-{t:,.0f}", sort_value=games, link=link)
                rec_item = table.item(i, 6)
                if rec_item is not None:
                    rec_item.setToolTip(
                        f"<b>Your games, weighted</b> ({r.get('raw_games', 0)} played)<br>{formulas.game_weights()}"
                        if is_mine and use_weights else
                        f"Your games, unweighted ({r.get('raw_games', 0)} played)." if is_mine else
                        f"<b>Online events, weighted</b><br>{formulas.event_weights()}<br>"
                        f"{formulas.effective_games(r, data.get('pilot_sd'))}")
                self._set_meta_item(table, i, 7, f"{rate * 100:.1f}%", sort_value=rate, link=link)
            conv = (scores.get(r["id"]) or {}).get("conversion")
            if conv and not is_mine:
                p1 = conv["p_above_1"]
                cacc = self.WINNING if p1 >= 0.8 else self.LOSING if p1 <= 0.2 else self.UNCLEAR
                self._set_meta_item(table, i, 8, f"{conv['mean']:.2f}×", accent=cacc, sort_value=conv["mean"], link=link)
                table.item(i, 8).setToolTip(f"<b>{r.get('deck', '')}</b> · Top 32 conversion<br>" + formulas.conversion(conv))
            else:
                self._set_meta_item(table, i, 8, "", muted=True, sort_value=-1, link=link)
            src = r.get("sources") or {}
            if is_mine:
                dots = "<span style='color:#B39DDB'>★</span>"
            else:
                dots = "".join(f"<span style='color:{c if src.get(k) else 'rgba(255,255,255,0.12)'}'>●</span>"
                               for k, c in (("online", "#6BB6E8"), ("in_person", "#FFD54F"), ("japan", "#EF7A9A")))
            lbl = QLabel(dots)
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("background: transparent; font-size: 13px; letter-spacing: 3px;")
            lbl.setToolTip("Your own games" if is_mine else
                           f"{src.get('online', 0)} online · {src.get('in_person', 0)} in-person · "
                           f"{src.get('japan', 0)} Japan events")
            table.setCellWidget(i, 9, lbl)
            self._set_meta_item(table, i, 9, "", sort_value=sum(1 for k in ("online", "in_person", "japan") if src.get(k)))
        table.setSortingEnabled(sorting)
        table.setSortingEnabled(sorting)
        table.setUpdatesEnabled(True)
        # The matrix is built only when its view is opened (lazy).
        self._meta_matrix_args = (rows, by_key, min_games, mine)
        self._meta_matrix_dirty = True
        if self.meta_views.currentIndex() == 1:
            self._ensure_meta_matrix()

    def _on_meta_view_changed(self, index):
        """The matchup matrix is opt-in: built and its size control shown only
        when the Matchups view is selected."""
        matrix = index == 1
        self.meta_matrix_size_label.setVisible(matrix)
        self.meta_matrix_size.setVisible(matrix)
        if matrix:
            self._ensure_meta_matrix()

    def _ensure_meta_matrix(self):
        if not getattr(self, "_meta_matrix_dirty", False) or not getattr(self, "_meta_matrix_args", None):
            return
        self._meta_matrix_dirty = False
        self.meta_matrix.setUpdatesEnabled(False)
        try:
            self._populate_meta_matrix(*self._meta_matrix_args)
        finally:
            self.meta_matrix.setUpdatesEnabled(True)

    def _populate_meta_matrix(self, rows, by_key, min_games, mine=()):
        """Archetype x archetype result rates from online pairings. Your decks
        (★) are extra rows against the same archetype columns."""
        size = self.meta_matrix_size.value()
        top = [r for r in rows if (float(r.get("wins") or 0) + float(r.get("losses") or 0)) > 0][:size]
        row_decks = list(mine) + top
        m = self.meta_matrix
        m.clear()
        m.setRowCount(len(row_decks))
        m.setColumnCount(len(top))
        for j, r in enumerate(top):
            head = QTableWidgetItem(self._icon_for_deck(r.get("deck", ""), r.get("icons", []), size=24), "")
            head.setToolTip(r.get("deck", ""))
            m.setHorizontalHeaderItem(j, head)
        for i, r in enumerate(row_decks):
            label = f"★ {r.get('deck', '')}" if r.get("is_mine") else r.get("deck", "")
            row_head = QTableWidgetItem(self._icon_for_deck(r.get("deck", ""), r.get("icons", []), size=22), label)
            if r.get("is_mine"):
                row_head.setForeground(QColor("#B39DDB"))
                row_head.setToolTip("Your deck · your weighted games vs each archetype")
            m.setVerticalHeaderItem(i, row_head)
        for i, a in enumerate(row_decks):
            for j, b in enumerate(top):
                item = QTableWidgetItem()
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if i == j:
                    item.setText("—")
                    item.setForeground(QColor(255, 255, 255, 60))
                    item.setBackground(QColor(255, 255, 255, 8))
                    item.setToolTip(f"{a.get('deck')} mirror")
                else:
                    rec = (a.get("matchups") or {}).get(b["id"])
                    games = sum(rec) if rec else 0
                    rate = result_rate(*rec) if rec else None
                    if rate is None or games <= 0:
                        item.setText("")
                        item.setBackground(QColor(255, 255, 255, 5))
                        item.setToolTip(f"{a.get('deck')} vs {b.get('deck')}: no games")
                    else:
                        mean, sd = self._beta_mean_sd(*rec)
                        post = {"low": max(0.0, mean - 1.645 * sd), "high": min(1.0, mean + 1.645 * sd)}
                        # Red (<50%) - grey - green (>50%), faded when the sample is small.
                        edge = max(-1.0, min(1.0, (rate - 0.5) / 0.15))
                        strength = min(1.0, games / max(1.0, float(min_games) * 3)) if min_games else 1.0
                        base = QColor(102, 187, 106) if edge >= 0 else QColor(239, 83, 80)
                        base.setAlpha(int(25 + 170 * abs(edge) * (0.35 + 0.65 * strength)))
                        item.setBackground(base)
                        item.setText(f"{rate * 100:.0f}")
                        item.setForeground(QColor(255, 255, 255, 235 if games >= min_games else 110))
                        w, l, t = rec
                        item.setToolTip(f"<b>{a.get('deck')}</b> vs <b>{b.get('deck')}</b>: {rate * 100:.1f}%<br>"
                                        f"{w:,.0f}-{l:,.0f}-{t:,.0f} (weighted) · range "
                                        f"{_pct_range(post['low'], post['high'])}"
                                        + ("" if games >= min_games else "<br><i>small sample</i>"))
                m.setItem(i, j, item)
        m.horizontalHeader().setDefaultSectionSize(46)
        m.verticalHeader().setDefaultSectionSize(34)
        m.verticalHeader().setMinimumWidth(190)

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
        cols = ["#", "Deck", "Finishes", "Share", "Wins", "Losses", "Ties", "Actual", "Estimate", "Range", "Chance >50%"]
        widths = [34, None, 68, 64, 58, 62, 52, 72, 78, 98, 56]
        self.limitless_table = self._make_meta_table(cols, widths, sortable=True, stretch_last=False)
        self.limitless_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.limitless_table.cellDoubleClicked.connect(lambda row, col: self._open_table_row_link(self.limitless_table, row))

        # Views: blended meta | in-person results
        self.limitless_views = QTabWidget()
        self.limitless_views.setObjectName("deckTabs")
        self.limitless_views.setDocumentMode(True)
        self.limitless_views.addTab(self.limitless_table, "Meta")
        self.limitless_views.addTab(self._create_in_person_view(), "In-person")
        vlayout.addWidget(self.limitless_views, stretch=1)

        return outer

    def _create_in_person_view(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        events_title = QLabel("EVENTS")
        events_title.setObjectName("metaStatTitle")
        layout.addWidget(events_title)
        self.ip_events_table = self._make_meta_table(
            ["Date", "Event", "Players", "Winner", "Format", "Weight"], [78, None, 70, 170, 210, 64], stretch_last=False)
        self.ip_events_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.ip_events_table.cellDoubleClicked.connect(lambda row, col: self._open_table_row_link(self.ip_events_table, row))
        for col, tip in enumerate([None, "Double-click to open on Limitless.", None, None,
                                   "Legal sets at the event. Events in the current format get the in-person boost.",
                                   "How much the event counts: in-person 1.75× (Worlds 3×) in the current format, "
                                   "0.7× one expansion back, 0.4× two back, scaled by size."]):
            if tip and self.ip_events_table.horizontalHeaderItem(col):
                self.ip_events_table.horizontalHeaderItem(col).setToolTip(tip)
        layout.addWidget(self.ip_events_table, stretch=2)

        results_title = QLabel("ARCHETYPE RESULTS")
        results_title.setObjectName("metaStatTitle")
        layout.addWidget(results_title)
        self.ip_results_table = self._make_meta_table(
            ["Deck", "Day 2", "Top 32", "Top 8", "Wins", "Converts", "Top 8 rate", "Best finish"],
            [None, 62, 64, 58, 52, 78, 78, 210], sortable=True, stretch_last=False)
        self.ip_results_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.ip_results_table.cellDoubleClicked.connect(lambda row, col: self._open_table_row_link(self.ip_results_table, row))
        for col, tip in enumerate([None, "Day 2 / listed placings across these events.", "Top 32 finishes.", "Top 8 finishes.",
                                   "Event wins.",
                                   "How often it reaches Top 32 vs how often it's played (weighted). "
                                   "1.0× = as expected · above = over-performs · below = under-performs.",
                                   "Same, for Top 8.", None]):
            if tip and self.ip_results_table.horizontalHeaderItem(col):
                self.ip_results_table.horizontalHeaderItem(col).setToolTip(tip)
        layout.addWidget(self.ip_results_table, stretch=3)
        return page

    def _populate_in_person(self, data):
        if not hasattr(self, "ip_events_table"):
            return
        events = data.get("in_person_events") or []
        table = self.ip_events_table
        table.setRowCount(0)
        for i, ev in enumerate(events):
            table.insertRow(i)
            table.setRowHeight(i, 34)
            link = ev.get("url")
            current = ev.get("era", 9) == 0
            self._set_meta_item(table, i, 0, ev.get("date", ""), link=link)
            self._set_meta_item(table, i, 1, ev.get("name", ""), align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, link=link)
            self._set_meta_item(table, i, 2, f"{int(ev.get('players') or 0):,}", link=link)
            self._set_meta_item(table, i, 3, ev.get("winner") or "--", link=link)
            self._set_meta_item(table, i, 4, ev.get("legal") or "--", muted=not current, link=link)
            self._set_meta_item(table, i, 5, f"{ev.get('weight', 0):.1f}×", accent=self.WINNING if current else None,
                                muted=not current, link=link)

        results = [r for r in (data.get("rows") or []) if r.get("in_person")]
        results.sort(key=lambda r: (-(r["in_person"].get("top8") or 0), -(r["in_person"].get("top32") or 0)))
        table = self.ip_results_table
        sorting = table.isSortingEnabled()
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for i, r in enumerate(results[:40]):
            ip = r["in_person"]
            link = r.get("deck_url")
            table.insertRow(i)
            table.setRowHeight(i, 40)
            self._set_meta_deck_cell(table, i, 0, r.get("deck", ""), r.get("icons", []),
                                     subtitle=f"{ip.get('day2_share', 0):.1f}% of Day 2", sort_value=r.get("deck", "").lower(), link=link)
            for col, key in ((1, "day2"), (2, "top32"), (3, "top8"), (4, "wins")):
                value = int(ip.get(key) or 0)
                self._set_meta_item(table, i, col, str(value) if value else "", muted=not value, sort_value=value, link=link)
            for col, key in ((5, "conversion_top32"), (6, "conversion_top8")):
                conv = ip.get(key)
                if conv is None or not ip.get("top32"):
                    self._set_meta_item(table, i, col, "", muted=True, sort_value=-1, link=link)
                    continue
                accent = self.WINNING if conv >= 1.15 else self.LOSING if conv <= 0.85 else self.UNCLEAR
                self._set_meta_item(table, i, col, f"{conv:.2f}×", accent=accent, sort_value=conv, link=link)
            best = ip.get("best") or {}
            place = best.get("rank")
            label = {1: "1st", 2: "2nd", 3: "3rd"}.get(place, f"{place}th" if place else "--")
            self._set_meta_item(table, i, 7, f"{label} · {best.get('event', '')}" if place else "--",
                                accent="#FFD54F" if place == 1 else None, sort_value=place or 999, link=link)
        table.setSortingEnabled(sorting)

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
            # Loaded when the tab is first opened (handle_tab_changed ->
            # ensure_visible_dashboard_loaded), not while the dashboard starts.
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
        _start_thread(self._limitless_fetcher)

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
            events = data.get("events") or {}
            if events:
                exp = ((data.get("expansions") or {}).get("en") or [{}])[0]
                self.limitless_status.setText(
                    f"{len(rows)} archetypes · {events.get('online', 0)} online, {events.get('in_person', 0)} in-person, "
                    f"{events.get('japan', 0)} Japan events · current set: {exp.get('name', '?')}"
                )
                self.limitless_status.setToolTip(
                    "Weighted: in-person 1.75×, Worlds 3×, Japan 0.75× (Bo1); events one expansion old 0.7×, "
                    "two old 0.4×; bigger events count more. W/L comes from online events.")
            else:
                self.limitless_status.setText(f"Loaded {len(rows)} archetypes from {processed} recent tournaments.")
        else:
            self.limitless_status.setText("No recent data was returned by the Limitless API for this format.")
        self.limitless_metric_labels["tournaments"].setText(str(processed))
        self.limitless_metric_labels["entries"].setText(str(total_entries))
        self.limitless_metric_labels["decks"].setText(str(len(rows)))
        if source == "limitless_standard":
            self._populate_in_person(data)
            self._meta_tab_dirty = True
            if self.tab_widget.currentIndex() == getattr(self, "meta_tab_index", -1):
                self._populate_meta_tab()
        if hasattr(self, "limitless_views"):
            # In-person results exist only for PTCG Standard.
            self.limitless_views.setTabEnabled(1, source == "limitless_standard")

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
            has_record = (wins + losses + ties) > 0
            # (Display only - the shared rows are no longer modified here; doing
            # so stamped 0% on decks that only have in-person placements.)
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
            if not has_record:
                for col in range(4, 11):
                    self._set_meta_item(self.limitless_table, i, col, "--", muted=True, sort_value=-1, link=link)
                continue
            self._set_meta_item(self.limitless_table, i, 4, f"{wins:,.0f}", accent="#66BB6A", sort_value=wins, link=link)
            self._set_meta_item(self.limitless_table, i, 5, f"{losses:,.0f}", accent="#EF5350", sort_value=losses, link=link)
            self._set_meta_item(self.limitless_table, i, 6, f"{ties:,.0f}", accent="#F9A825", sort_value=ties, link=link)
            pct_color = "#66BB6A" if raw_pct >= 55 else "#EF5350" if raw_pct < 45 else "#F9A825"
            self._set_meta_item(self.limitless_table, i, 7, f"{raw_pct:.1f}%", accent=pct_color, sort_value=raw_pct, link=link)
            bayes_color = "#66BB6A" if bayes_pct >= 55 else "#EF5350" if bayes_pct < 45 else "#F9A825"
            self._set_meta_item(self.limitless_table, i, 8, f"{bayes_pct:.1f}%", accent=bayes_color, sort_value=bayes_pct, link=link)
            self._set_meta_item(self.limitless_table, i, 9, f"{ci_low:.0f}–{ci_high:.0f}%", sort_value=(ci_high - ci_low), link=link)
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
        _start_thread(self._trainerhill_fetcher)

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
        cols = ["#", "Deck", "Finishes", "Share", "Wins", "Losses", "Actual", "Estimate", "Range", "Chance >50%"]
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
        _start_thread(self._japan_fetcher)

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
        _start_thread(self._japan_fetcher)

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
            # Japanese sources report top finishes, not match records, so
            # win-rate columns would be meaningless (they showed 100%).
            has_record = (row.get("losses") or 0) > 0 or (row.get("ties") or 0) > 0
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
                subtitle=(f"{int(row.get('count', 0) or 0)} finishes • {summary.get('confidence_label', 'n/a')}"
                          if has_record else f"{row.get('count', 0)} weighted top finishes"),
                sort_value=(row.get("deck", "") or "").lower(),
            )
            self._set_meta_item(self.japan_table, i, 2, str(row.get('count', 0)), sort_value=int(row.get('count', 0) or 0))
            self._set_meta_item(self.japan_table, i, 3, f"{row.get('share', 0):.1f}%", sort_value=float(row.get('share', 0) or 0))
            if not has_record:
                for col in range(4, 10):
                    self._set_meta_item(self.japan_table, i, col, "—", muted=True, sort_value=-1)
                continue
            self._set_meta_item(self.japan_table, i, 4, str(int(wins)), accent="#66BB6A", sort_value=wins)
            self._set_meta_item(self.japan_table, i, 5, str(int(losses)), accent="#EF5350", sort_value=losses)
            pct_color = "#66BB6A" if raw_pct >= 55 else "#EF5350" if raw_pct < 45 else "#F9A825"
            self._set_meta_item(self.japan_table, i, 6, f"{raw_pct:.1f}%", accent=pct_color, sort_value=raw_pct)
            bayes_color = "#66BB6A" if bayes_pct >= 55 else "#EF5350" if bayes_pct < 45 else "#F9A825"
            self._set_meta_item(self.japan_table, i, 7, f"{bayes_pct:.1f}%", accent=bayes_color, sort_value=bayes_pct)
            self._set_meta_item(self.japan_table, i, 8, f"{ci_low:.0f}–{ci_high:.0f}%", sort_value=(ci_high - ci_low))
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
        self._pokedata_home_url = POKEDATA_PAGES[0][1]  # loaded on first view of the tab

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
            # Loaded on first view of the tab (see handle_tab_changed).

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
            subprocess.Popen([_console_python(), os.path.join(BASE_DIR, "TCGLiveMonitor.py"), "--ocr-test"], cwd=BASE_DIR, **kwargs)
        except Exception as e:
            print(f"Error launching OCR test: {e}")
    
    def launch_ai_parser(self):
        """Launch AI battle log parser"""
        import subprocess
        try:
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen([_console_python(), os.path.join(BASE_DIR, "AIParseBattleLog.py")], cwd=BASE_DIR, **kwargs)
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

    def _save_auto_export_setting(self, checked):
        self.app_settings = load_app_settings()
        self.app_settings["auto_export_battle_log"] = bool(checked)
        save_app_settings(self.app_settings)

    def save_parser_settings(self):
        key_value = (self.api_key_input.text() if hasattr(self, "api_key_input") else "").strip()
        self.app_settings = {**load_app_settings(), **self.app_settings}
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
        """Headline cards: the numbers you check first, one row."""
        container = QFrame()
        container.setObjectName("statsGrid")

        layout = QGridLayout(container)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        self.headline_cards = {}
        cards = [
            ("rank", "CURRENT RANK", "#F9A825"),
            ("winrate", "WIN RATE", "#9CC344"),
            ("session", "TODAY", "#4A9FD8"),
            ("form", "LAST 10", "#B388FF"),
        ]
        for col, (key, title, color) in enumerate(cards):
            card, title_label, value_label, sub_label = self.create_stat_card(title, color)
            self.headline_cards[key] = (title_label, value_label, sub_label)
            layout.addWidget(card, 0, col)
            layout.setColumnStretch(col, 1)

        return container

    def create_stat_card(self, title, accent_color):
        """Card with a title, a big value and one line of context."""
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
        card.setFixedHeight(88)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("cardTitle")
        title_label.setStyleSheet(f"color: {accent_color}; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        layout.addWidget(title_label)

        value_label = QLabel("--")
        value_label.setObjectName("cardValue")
        value_label.setTextFormat(Qt.TextFormat.RichText)
        value_label.setStyleSheet("color: rgba(255, 255, 255, 0.95); font-size: 28px; font-weight: 700;")
        layout.addWidget(value_label)

        sub_label = QLabel("")
        sub_label.setObjectName("cardSub")
        sub_label.setTextFormat(Qt.TextFormat.RichText)
        sub_label.setStyleSheet("color: rgba(214, 225, 240, 0.62); font-size: 10px;")
        layout.addWidget(sub_label)

        layout.addStretch()
        return card, title_label, value_label, sub_label

    def create_graphs_section(self):
        """Rank and win-rate charts with one shared range selector."""
        container = QFrame()
        container.setObjectName("graphsContainer")
        outer = QVBoxLayout(container)
        outer.setSpacing(6)
        outer.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 0, 0)
        header.setSpacing(4)
        self.chart_hint_label = QLabel("Hover for details · drag to zoom · double-click to reset")
        self.chart_hint_label.setObjectName("chartHint")
        header.addWidget(self.chart_hint_label)
        header.addStretch()
        self.chart_range_buttons = {}
        for key, label, tip in self.CHART_RANGES:
            btn = QPushButton(label)
            btn.setObjectName("eloScaleBtn")
            btn.setCheckable(True)
            btn.setChecked(key == self.chart_range)
            btn.setFixedHeight(22)
            btn.setMinimumWidth(30)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda checked=False, range_key=key: self._set_chart_range(range_key))
            header.addWidget(btn)
            self.chart_range_buttons[key] = btn
        outer.addLayout(header)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.setContentsMargins(0, 0, 0, 0)

        self.elo_chart = SeriesChart("#F9A825")
        self.elo_chart.y_format = lambda v: f"{v:,.0f}"
        self.elo_chart.y_min_pad = 6
        self.elo_chart.y_clamp = (0, float("inf"))
        self.elo_chart.empty_text = "No rank readings in this range"
        self.elo_chart.viewChanged.connect(self._update_elo_summary)
        self.elo_summary_label = QLabel("")
        row.addWidget(self.create_graph_card("RANK", self.elo_chart, summary_label=self.elo_summary_label), 1)

        self.winrate_chart = SeriesChart("#9CC344")
        self.winrate_chart.y_format = lambda v: f"{v:.0f}%"
        self.winrate_chart.y_clamp = (0, 100)
        self.winrate_chart.y_include = (50,)
        self.winrate_chart.y_min_pad = 5
        self.winrate_chart.empty_text = "No games in this range"
        self.winrate_chart.ref_lines = [(50, "50%", QColor(255, 255, 255, 60))]
        self.winrate_chart.viewChanged.connect(self._update_winrate_summary)
        self.winrate_summary_label = QLabel("")
        window_box = QComboBox()
        window_box.setObjectName("metaCombo")
        for size in (5, 10, 20, 50):
            window_box.addItem(f"Last {size}", size)
        window_box.setCurrentIndex(max(0, window_box.findData(self.winrate_window)))
        window_box.setToolTip("Games in the dashed rolling line")
        window_box.currentIndexChanged.connect(lambda _i, box=window_box: self._set_winrate_window(box.currentData()))
        row.addWidget(self.create_graph_card("WIN RATE", self.winrate_chart, header_widget=window_box,
                                             summary_label=self.winrate_summary_label), 1)
        outer.addLayout(row)
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

    # (key, button text, tooltip)
    CHART_RANGES = (
        ("auto", "Auto", "Most useful stretch: your current climb / recent games"),
        ("session", "Session", "Your latest day of play"),
        ("1w", "1W", "Last 7 days"),
        ("1m", "1M", "Last 30 days"),
        ("3m", "3M", "Last 90 days"),
        ("all", "All", "Everything"),
    )
    CHART_RANGE_DAYS = {"1w": 7, "1m": 30, "3m": 90}

    def _set_chart_range(self, range_key):
        self.chart_range = range_key
        for key, button in getattr(self, "chart_range_buttons", {}).items():
            button.setChecked(key == range_key)
        try:
            self.app_settings["dashboard_chart_range"] = range_key
            save_app_settings(self.app_settings)
        except Exception:
            pass
        self.update_elo_graph()
        self.update_winrate_graph()

    def _set_winrate_window(self, size):
        try:
            self.winrate_window = int(size)
        except (TypeError, ValueError):
            return
        try:
            self.app_settings["dashboard_winrate_window"] = self.winrate_window
            save_app_settings(self.app_settings)
        except Exception:
            pass
        self.update_winrate_graph()

    def _chart_view(self, times, auto_view):
        """(first, last) indices for the selected range, or None if empty."""
        n = len(times)
        if n == 0:
            return None
        key = self.chart_range
        if key == "auto":
            return auto_view
        if key == "all":
            return (0, n - 1)
        if key == "session":
            day = times[-1].date()
            first = next(i for i, t in enumerate(times) if t.date() == day)
            return (first, n - 1)
        cutoff = datetime.now() - timedelta(days=self.CHART_RANGE_DAYS.get(key, 7))
        first = next((i for i, t in enumerate(times) if t >= cutoff), None)
        return None if first is None else (first, n - 1)

    def create_graph_card(self, title, chart, header_widget=None, summary_label=None):
        """Graph card: title row, one-line summary of the visible range, chart."""
        card = QFrame()
        card.setObjectName("graphCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

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

        if summary_label is not None:
            summary_label.setObjectName("chartSummary")
            summary_label.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(summary_label)

        chart.setMinimumHeight(220)
        layout.addWidget(chart, 1)
        return card

    def _load_timeline(self):
        """Battles (oldest first) and de-duplicated rank readings."""
        battles = []
        for row in self.db.get_battle_timeline():
            if (row[1] or "") in self.ignored_decks:
                continue
            try:
                stamp = datetime.fromisoformat(str(row[0]))
            except (TypeError, ValueError):
                continue
            battles.append({
                "t": stamp, "deck": row[1] or "", "opp": row[2] or "", "result": str(row[3] or ""),
                # what deck_analytics.battle_weight() reads
                "raw": {"timestamp": str(row[0]), "my_rank": row[4], "is_tournament": bool(row[5])},
            })
        ranks = []
        for stamp, rank in self.db.get_elo_history(limit=None) or []:
            try:
                stamp, rank = datetime.fromisoformat(str(stamp)), int(rank)
            except (TypeError, ValueError):
                continue
            # The OCR re-reads the same value many times; keep each change once.
            if ranks and ranks[-1][1] == rank:
                continue
            ranks.append((stamp, rank))
        return battles, ranks

    @staticmethod
    def _result_kind(result):
        value = (result or "").strip().lower()
        if value == "win":
            return "W"
        if value == "loss":
            return "L"
        return "T"

    def _update_headline_cards(self, battles, ranks):
        cards = getattr(self, "headline_cards", None)
        if not cards:
            return
        win_c, loss_c, tie_c = "#66BB6A", "#EF5350", "#9AA5B1"

        def record(games):
            w = sum(1 for b in games if self._result_kind(b["result"]) == "W")
            l = sum(1 for b in games if self._result_kind(b["result"]) == "L")
            return w, l, len(games) - w - l

        def record_text(w, l, t):
            return f"{w}-{l}-{t}" if t else f"{w}-{l}"

        # Current rank
        _title, value, sub = cards["rank"]
        if ranks:
            current = ranks[-1][1]
            peak = max(r for _t, r in ranks)
            value.setText(f"{current:,}")
            parts = [league_name(current)]
            parts.append("at peak" if current >= peak else f"peak {peak:,}")
            sub.setText(" · ".join(p for p in parts if p))
        else:
            value.setText("--")
            sub.setText("No rank read yet")

        # Win rate (under the chosen tie rule)
        _title, value, sub = cards["winrate"]
        w, l, t = record(battles)
        rate = result_rate(w, l, t)
        value.setText(f"{rate * 100:.1f}%" if rate is not None else "--")
        estimate = ""
        tip = f"<b>Actual win rate</b>: {record_text(w, l, t)} in {len(battles)} games"
        if t:
            tip += f" ({TIE_MODES[tie_mode()][0].lower()})"
        try:
            expansions = cached_expansions("en")
            post = win_rate_posterior(*weighted_record([b["raw"] | {"result": b["result"]} for b in battles], expansions))
            if post["games"] > 0:
                estimate = f" · est. {post['mean'] * 100:.0f}%"
                level = int(round(post["level"] * 100))
                tip += (f"<br><b>Estimated win rate</b>: {post['mean'] * 100:.0f}% · range {_pct_range(post['low'], post['high'])}"
                        f"<br><span style='color:#8A97AA'>{RANGE_EXPLAINED.format(level=level)} "
                        f"{post['games']:.1f} effective games.</span><br>" + formulas.estimate(post))
        except Exception:
            pass
        sub.setText(f"{record_text(w, l, t)}{estimate}")
        sub.parentWidget().setToolTip(tip)

        # Latest session (today, or the last day you played)
        title, value, sub = cards["session"]
        if battles:
            day = battles[-1]["t"].date()
            session = [b for b in battles if b["t"].date() == day]
            title.setText("TODAY" if day == datetime.now().date() else f"LAST SESSION · {_short_day(day)}")
            w, l, t = record(session)
            value.setText(record_text(w, l, t))
            details = []
            day_ranks = [r for stamp, r in ranks if stamp.date() == day]
            before = [r for stamp, r in ranks if stamp.date() < day]
            if day_ranks:
                start = before[-1] if before else day_ranks[0]
                delta = day_ranks[-1] - start
                color = win_c if delta > 0 else loss_c if delta < 0 else tie_c
                details.append(f"<span style='color:{color}'>{delta:+,} pts</span>")
            rate = result_rate(w, l, t)
            if rate is not None:
                details.append(f"{rate * 100:.0f}%")
            sub.setText(" · ".join(details))
        else:
            title.setText("TODAY")
            value.setText("--")
            sub.setText("No games yet")

        # Last 10 games: record, form dots, streak
        _title, value, sub = cards["form"]
        recent = battles[-10:]
        if recent:
            w, l, t = record(recent)
            value.setText(record_text(w, l, t))
            colors = {"W": win_c, "L": loss_c, "T": tie_c}
            dots = "".join(f"<span style='color:{colors[self._result_kind(b['result'])]}'>●</span>" for b in recent)
            last_kind = self._result_kind(battles[-1]["result"])
            streak = 0
            for b in reversed(battles):
                if self._result_kind(b["result"]) != last_kind:
                    break
                streak += 1
            sub.setText(f"<span style='letter-spacing:1px'>{dots}</span> &nbsp;{last_kind}{streak}")
        else:
            value.setText("--")
            sub.setText("")

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
    
    def _refresh_if_changed(self):
        """15 s timer: reload only when the database actually changed.

        A full load_stats rebuilds every deck analysis, both graphs and marks
        all deck pages for rebuilding, which made the UI stutter every 15 s
        and the Decks tab freeze on the next visit even with no new data.
        """
        try:
            signature = self.db.data_signature()
        except Exception:
            signature = None
        if signature is not None and signature == getattr(self, "_last_data_signature", None):
            return
        self.load_stats()

    def load_stats(self):
        """Load and display all statistics"""
        try:
            try:
                self._last_data_signature = self.db.data_signature()
            except Exception:
                self._last_data_signature = None
            stats_scroll_value = None
            if hasattr(self, "stats_scroll"):
                try:
                    stats_scroll_value = self.stats_scroll.verticalScrollBar().value()
                except Exception:
                    stats_scroll_value = None

            # Headline cards + charts share one read of the timeline
            self._timeline = self._load_timeline()
            self._update_headline_cards(*self._timeline)
            try:
                self.update_elo_graph()
                self.update_winrate_graph()
            except Exception as graph_error:
                print(f"Graph error: {graph_error}")
                import traceback
                traceback.print_exc()
            
            deck_rows = self.db.get_deck_usage_stats(limit=None)
            self.deck_analyses = [
                self._build_deck_analysis(deck_name, games, wins, losses, ties, last_played)
                for deck_name, games, wins, losses, ties, last_played in deck_rows
            ]
            
            # Load deck usage
            self.update_deck_usage(self.deck_analyses)
            self._deck_dashboards_dirty = True
            if hasattr(self, "tab_widget") and self.tab_widget.currentIndex() == getattr(self, "decks_tab_index", -1):
                self._refresh_deck_dashboards(self.deck_analyses)
            else:
                # Pre-build the deck tabs shortly after loading (tab shells
                # now, pages one by one), so the first click into Decks or on
                # a deck is instant instead of freezing.
                QTimer.singleShot(1500, self._prebuild_deck_dashboards)

            # Load recent battles
            self.update_recent_battles()

            if stats_scroll_value is not None and hasattr(self, "stats_scroll"):
                QTimer.singleShot(0, lambda v=stats_scroll_value: self._restore_scroll_value(self.stats_scroll, v))
            
        except Exception as e:
            print(f"Error loading stats: {e}")
            import traceback
            traceback.print_exc()
    
    def update_elo_graph(self):
        """Rank chart: one point per rank change, coloured up/down."""
        try:
            battles, ranks = getattr(self, "_timeline", None) or self._load_timeline()
            chart = self.elo_chart
            points = []
            b_index = 0
            for i, (stamp, rank) in enumerate(ranks):
                # Most recent battle saved before this reading (rank is read
                # just after the game ends).
                while b_index < len(battles) and battles[b_index]["t"] <= stamp + timedelta(minutes=2):
                    b_index += 1
                battle = battles[b_index - 1] if b_index else None
                delta = rank - ranks[i - 1][1] if i else 0
                if delta > 0:
                    dot, head = "#66BB6A", f"{rank:,}   ▲ {delta:,}"
                elif delta < 0:
                    dot, head = "#EF5350", f"{rank:,}   ▼ {-delta:,}"
                else:
                    dot, head = None, f"{rank:,}"
                tip = [head, f"{_short_day(stamp)} · {_clock(stamp)} · {league_name(rank)}"]
                if battle and stamp - battle["t"] < timedelta(hours=3):
                    kind = {"W": "Win", "L": "Loss", "T": "Tie"}[self._result_kind(battle["result"])]
                    tip.append(f"{kind} vs {battle['opp']}" if battle["opp"] else kind)
                    if battle["deck"]:
                        tip.append(f"with {battle['deck']}")
                points.append({"y": rank, "t": stamp, "dot": dot, "tip": tip})

            # Auto: the current climb - walk back until a league-scale jump
            # (e.g. ladder points → Master points) or a 3-week break.
            n = len(points)
            first = n - 1
            while first > 0 and first > n - 60:
                gap = ranks[first][0] - ranks[first - 1][0]
                if abs(ranks[first][1] - ranks[first - 1][1]) >= 300 or gap > timedelta(days=21):
                    break
                first -= 1
            first = min(first, max(0, n - 3))
            view = self._chart_view([p["t"] for p in points], (max(0, first), n - 1))
            if view and view[0] > 0 and self.chart_range in self.CHART_RANGE_DAYS.keys() | {"session"}:
                # Start from the rank you had going into the window, so the
                # change matches the Today card (+pts since last session).
                view = (view[0] - 1, view[1])

            chart.ref_lines = [(threshold, name, QColor(249, 168, 37, 70)) for threshold, _key, name in LEAGUES if threshold > 0]
            if view is None:
                chart.set_data([])
            else:
                chart.set_data(points, auto_view=view)
        except Exception as e:
            print(f"Error in Elo graph: {e}")
            import traceback
            traceback.print_exc()

    def _update_elo_summary(self, first, last, custom):
        self._update_chart_hint()
        points = self.elo_chart.visible_points()
        if not points:
            self.elo_summary_label.setText("<span style='color:rgba(214,225,240,0.5)'>No rank changes in this range</span>")
            return
        start, end = points[0]["y"], points[-1]["y"]
        peak = max(p["y"] for p in points)
        delta = end - start
        color = "#66BB6A" if delta > 0 else "#EF5350" if delta < 0 else "#9AA5B1"
        arrow = "▲" if delta > 0 else "▼" if delta < 0 else "■"
        self.elo_summary_label.setText(
            f"<span style='color:#F4F9FF;font-size:13px;font-weight:700'>{start:,} → {end:,}</span>"
            f"&nbsp;&nbsp;<span style='color:{color};font-weight:700'>{arrow} {abs(delta):,}</span>"
            f"<span style='color:rgba(214,225,240,0.55)'>&nbsp;&nbsp;·&nbsp; {_range_dates(points)}</span>"
        )
        low = min(p["y"] for p in points)
        self.elo_summary_label.setToolTip(
            f"<b>{start:,} → {end:,}</b> ({delta:+,})<br>Peak {peak:,} · low {low:,} · {len(points)} rank changes<br>"
            f"<span style='color:#8A97AA'>Dots: green = up, red = down. Dashed lines = league thresholds.</span>")

    def update_winrate_graph(self):
        """Win-rate chart: weighted Bayesian estimate with its 90% likely range
        (narrows as games accumulate), rolling last-N dashed, result strip.

        Same maths as the deck pages: each game weighted by era x league /
        tournament (Advanced → Preferences), record rescaled to Kish's
        effective sample, Beta(2, 2) posterior under the tie rule.
        """
        try:
            battles, _ranks = getattr(self, "_timeline", None) or self._load_timeline()
            chart = self.winrate_chart
            size = self.winrate_window
            expansions = cached_expansions("en")
            level = int(round(CREDIBLE_LEVEL * 100))
            points = []
            win_c, loss_c, tie_c = "#66BB6A", "#EF5350", "#9AA5B1"
            kinds = [self._result_kind(b["result"]) for b in battles]
            total = sq = ws = ls = ts = 0.0
            for i, battle in enumerate(battles):
                kind = kinds[i]
                weight = battle_weight(battle["raw"], expansions)
                if weight > 0:
                    total += weight
                    sq += weight * weight
                    if kind == "W":
                        ws += weight
                    elif kind == "L":
                        ls += weight
                    else:
                        ts += weight
                scale = total / sq if sq else 0.0  # (sum w)^2 / sum w^2 / sum w
                post = win_rate_posterior(ws * scale, ls * scale, ts * scale)
                window = kinds[max(0, i - size + 1):i + 1]
                w, l, t = window.count("W"), window.count("L"), window.count("T")
                rolling = result_rate(w, l, t)
                color = {"W": win_c, "L": loss_c, "T": tie_c}[kind]
                label = {"W": "Win", "L": "Loss", "T": "Tie"}[kind]
                record = f"{w}-{l}-{t}" if t else f"{w}-{l}"
                tip = [
                    f"{post['mean'] * 100:.0f}%   range {_pct_range(post['low'], post['high'])}",
                    f"Game {i + 1} · {_short_day(battle['t'])} · {_clock(battle['t'])}",
                    f"{label} vs {battle['opp']}" if battle["opp"] else label,
                ]
                if battle["deck"]:
                    tip.append(f"with {battle['deck']}")
                if rolling is not None:
                    tip.append(f"Last {len(window)}: {rolling * 100:.0f}% ({record})")
                tip.append(f"Counts ×{weight:.2f} · {post['games']:.1f} effective games"
                           if weight > 0 else "Older format, not counted")
                points.append({
                    "y": post["mean"] * 100,
                    "lo": post["low"] * 100,
                    "hi": post["high"] * 100,
                    "alt": rolling * 100 if rolling is not None else None,
                    "t": battle["t"],
                    "dot": color,
                    "strip": color,
                    "tip": tip,
                    "post": post,
                })
            self._winrate_level = level
            n = len(points)
            # Auto: enough games to watch the range narrow, still readable.
            view = self._chart_view([p["t"] for p in points], (max(0, n - 100), n - 1))
            if view is None:
                chart.set_data([])
            else:
                chart.set_data(points, auto_view=view)
        except Exception as e:
            print(f"Error in win rate graph: {e}")
            import traceback
            traceback.print_exc()

    def _update_winrate_summary(self, first, last, custom):
        self._update_chart_hint()
        battles = (getattr(self, "_timeline", None) or ([], []))[0]
        games = battles[first:last + 1] if self.winrate_chart.points else []
        if not games:
            self.winrate_summary_label.setText("<span style='color:rgba(214,225,240,0.5)'>No games in this range</span>")
            return
        post = self.winrate_chart.points[last]["post"]
        kinds = [self._result_kind(b["result"]) for b in games]
        w, l, t = kinds.count("W"), kinds.count("L"), kinds.count("T")
        record = f"{w}-{l}-{t}" if t else f"{w}-{l}"
        color = "#66BB6A" if post["low"] > 0.5 else "#EF5350" if post["high"] < 0.5 else "#F4F9FF"
        level = getattr(self, "_winrate_level", 90)
        self.winrate_summary_label.setText(
            f"<span style='color:{color};font-size:13px;font-weight:700'>{post['mean'] * 100:.0f}%</span>"
            f"<span style='color:rgba(214,225,240,0.75)'>&nbsp; {_pct_range(post['low'], post['high'])}</span>"
            f"<span style='color:rgba(214,225,240,0.55)'>&nbsp;&nbsp;·&nbsp; {record} &nbsp;·&nbsp; "
            f"{_range_dates(games, key='t')}</span>"
        )
        self.winrate_summary_label.setToolTip(
            f"<b>Estimated win rate {post['mean'] * 100:.0f}%</b> · range {_pct_range(post['low'], post['high'])}<br>"
            f"{post['p_above_even'] * 100:.0f}% chance it's above 50% · {post['games']:.1f} effective games<br>"
            f"<span style='color:#8A97AA'>{RANGE_EXPLAINED.format(level=level)}<br>"
            f"Solid line = estimate · band = range · dashed = last {self.winrate_window} games · "
            f"strip = results.</span><br>" + formulas.estimate(post))

    def _update_chart_hint(self):
        label = getattr(self, "chart_hint_label", None)
        if label is None:
            return
        zoomed = any(getattr(c, "custom", False) for c in (getattr(self, "elo_chart", None), getattr(self, "winrate_chart", None)) if c)
        label.setText("Zoomed in · double-click a chart to reset" if zoomed
                      else "Hover for details · drag to zoom · double-click to reset")

    def update_deck_usage(self, deck_analyses=None):
        """Update the dashboard deck summary with richer, clickable deck stats."""
        try:
            # Clear existing
            while self.deck_list_layout.count():
                child = self.deck_list_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            deck_analyses = deck_analyses if deck_analyses is not None else self.deck_analyses
            hidden = sum(1 for a in deck_analyses if a.get("deck_name") in self.ignored_decks)
            deck_analyses = [a for a in deck_analyses if a.get("deck_name") not in self.ignored_decks]
            if hidden:
                note = QLabel(f"{hidden} ignored deck{'s' if hidden != 1 else ''} hidden · un-ignore on its Decks page")
                note.setStyleSheet("color: rgba(214,225,240,0.38); font-size: 10px;")
                self.deck_list_layout.addWidget(note)

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
                    subtitle=f"{analysis.get('record')}",
                )
                self._set_mouse_passthrough(deck_cell)
                top_row.addWidget(deck_cell)
                top_row.addStretch()

                right_col = QVBoxLayout()
                right_col.setContentsMargins(0, 0, 0, 0)
                right_col.setSpacing(1)

                # Same estimate and range as the deck's own page.
                post = analysis.get("posterior") or {}
                if post:
                    bayes_pct = post["mean"] * 100.0
                    ci_low, ci_high = post["low"] * 100.0, post["high"] * 100.0
                raw_games = analysis.get("games") or 0
                actual = (analysis.get("wins", 0) / raw_games * 100.0) if raw_games else 0.0
                row_tip = (f"<b>{analysis.get('deck_name', '')}</b><br>"
                           f"Estimated win rate {bayes_pct:.0f}% · range {ci_low:.0f}–{ci_high:.0f}%<br>"
                           f"Actual {analysis.get('record')} in {raw_games} game{'s' if raw_games != 1 else ''} "
                           f"({actual:.0f}%)")
                if post:
                    row_tip += f"<br>{post['p_above_even'] * 100:.0f}% chance it's above 50%"
                    if post.get("alpha"):
                        row_tip += "<br>" + formulas.estimate(post)
                if matched_meta:
                    row_tip += f"<br>Limitless archetype: {matched_meta['row'].get('deck')} (#{matched_meta.get('rank')})"
                row_tip += "<br><span style='color:#8A97AA'>Click to open its page</span>"
                stale = bool(post) and post.get("games", 0) <= 0  # every game is from an older format
                if stale:
                    row_tip += "<br>All games are from an older format, so they don't count toward the estimate."
                row_button.setToolTip(row_tip)
                wr_label = QLabel("--" if stale else f"{bayes_pct:.0f}%")
                wr_label.setStyleSheet(f"color: {'#8A97AA' if stale else self._percent_accent(bayes_pct)}; font-size: 13px; font-weight: 700;")
                wr_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                wr_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                right_col.addWidget(wr_label)

                meta_label = QLabel("Older format" if stale else f"{ci_low:.0f}–{ci_high:.0f}%")
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
                    "stop:0 #5C6675, stop:1 #6B7585" if stale else
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
                fill = 0 if stale else max(0, min(100, int(round(bayes_pct))))
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
            
            battles = [b for b in self.db.get_recent_battles(limit=200)
                       if (b[1] or "") not in self.ignored_decks][:10]
            
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
            /* Tab scroll buttons: bigger, clearly visible when many decks
               overflow the tab bar. */
            QTabWidget#deckTabs QTabBar::scroller {
                background: transparent;
            }
            QTabWidget#deckTabs QToolButton::menu-indicator {
                image: none;
            }
            QTabWidget#deckTabs QTabBar QToolButton {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 6px;
                color: rgba(255,255,255,0.85);
                width: 22px;
                margin: 2px 1px;
            }
            QTabWidget#deckTabs QTabBar QToolButton:hover {
                background: rgba(74,159,216,0.35);
                border-color: rgba(74,159,216,0.6);
                color: white;
            }
            QTabWidget#deckTabs QTabBar QToolButton:disabled {
                background: rgba(255,255,255,0.02);
                border-color: rgba(255,255,255,0.05);
                color: rgba(255,255,255,0.2);
            }

            QToolButton#deckPinBtn {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 6px;
                color: rgba(255,255,255,0.6);
                font-size: 15px;
            }
            QToolButton#deckPinBtn:hover {
                background: rgba(249,168,37,0.18);
                border-color: rgba(249,168,37,0.45);
                color: rgba(249,168,37,0.9);
            }
            QToolButton#deckPinBtn:checked {
                background: rgba(249,168,37,0.22);
                border-color: rgba(249,168,37,0.55);
                color: #F9A825;
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

            QLabel#chartHint {
                color: rgba(214,225,240,0.42);
                font-size: 10px;
            }
            QLabel#chartSummary {
                color: rgba(214,225,240,0.75);
                font-size: 11px;
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
        # Only the glass/title/footer/slider rules depend on the opacity. The
        # other ~80 rules are applied once: re-applying the whole sheet to
        # the window re-polished every widget on every slider tick (lag).
        start = style.index("/* Main glass container */")
        end = style.index("QLabel#titleText {")
        dynamic, static = style[start:end], style[:start] + style[end:]
        if getattr(self, "_static_style", None) != static:
            self._static_style = static
            self.setStyleSheet(static)
        if hasattr(self, "container") and isinstance(self.container, GlassFrame):
            self.container.set_scale(scale)
        # Title bar and footer (with the slider) are small subtrees.
        for name in ("titleBar", "footerBar"):
            bar = self.findChild(QFrame, name)
            if bar is not None:
                bar.setStyleSheet(dynamic)


def main():
    """Run the stats window standalone"""
    app = QApplication(sys.argv)
    
    window = StatsWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
