"""First-run tour: the HUD's arrow, then each dashboard tab, with an example
deck filling the stats while it runs.

The example games live in their own database file (.tutorial_demo.db). The
HUD and the dashboard read from it while the tour is on, and switch back to
tcg_battles.db when it ends or is skipped. The real database is never
written, and the demo file is deleted at the end (and again on the next start
if the app was closed mid-tour).
"""

import os
import random
from datetime import datetime, timedelta

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO_DB = os.path.join(BASE_DIR, ".tutorial_demo.db")
SETTING = "tutorial_done"
DEMO_DECK = "Gardevoir"
DEMO_DECK_2 = "Dragapult"

_active = None  # the running Tour, at most one per process


# ───────────────────────────── settings ─────────────────────────────
def is_done():
    from app_settings import load_app_settings
    return bool(load_app_settings().get(SETTING))


def mark_done():
    from app_settings import load_app_settings, save_app_settings
    settings = load_app_settings()
    if not settings.get(SETTING):
        settings[SETTING] = True
        save_app_settings(settings)


def should_offer(db=None):
    """True on a first run. Someone upgrading already has battles: they're
    marked done without seeing the tour."""
    if is_done():
        return False
    try:
        from BattleDatabase import BattleDatabase
        db = db or BattleDatabase()
        conn = db._connect()
        try:
            count = conn.execute("SELECT COUNT(*) FROM battles").fetchone()[0]
        finally:
            conn.close()
    except Exception:
        count = 0
    if count:
        mark_done()
        return False
    return True


def is_running():
    return _active is not None


# ───────────────────────────── example data ─────────────────────────────
OPPONENTS = [  # (deck, how often, your win chance with Gardevoir)
    ("Dragapult", 16, 0.66), ("Gholdengo", 11, 0.60), ("Raging Bolt", 9, 0.42),
    ("Alakazam Dudunsparce", 8, 0.74), ("Crustle", 5, 0.33), ("Lucario Hariyama", 6, 0.62),
    ("N's Zoroark", 6, 0.70), ("Charizard Pidgeot", 7, 0.55), ("Joltik Box", 4, 0.76),
]


def remove_demo_db():
    for suffix in ("", "-journal", "-wal", "-shm"):
        try:
            os.remove(DEMO_DB + suffix)
        except OSError:
            pass


def build_demo_db(path=DEMO_DB, now=None):
    """About 70 games over three weeks: Gardevoir climbing from ~1200 Elo,
    a few Dragapult games, 7-3 today, two tournament rounds."""
    from BattleDatabase import BattleDatabase
    if path == DEMO_DB:
        remove_demo_db()
    db = BattleDatabase(db_path=path)
    rng = random.Random(20261122)
    now = now or datetime.now()
    rank = 1188
    rows, ranks = [], []
    decks, weights = zip(*[(d, w) for d, w, _p in OPPONENTS])
    odds = {d: p for d, _w, p in OPPONENTS}

    def play(when, my_deck, result=None, tournament=False):
        nonlocal rank
        opp = rng.choices(decks, weights)[0]
        if result is None:
            chance = odds[opp] if my_deck == DEMO_DECK else odds[opp] - 0.12
            result = "Win" if rng.random() < chance else "Loss"
        rows.append((when.strftime("%Y-%m-%d %H:%M:%S"), my_deck, opp, result, rank,
                     rng.randint(78, 99), "AI", 1 if tournament else 0))
        rank += rng.randint(11, 17) if result == "Win" else -rng.randint(9, 14)
        ranks.append(((when + timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S"), rank, my_deck))

    # Earlier days: a session most evenings.
    start = (now - timedelta(days=20)).replace(hour=19, minute=10, second=0, microsecond=0)
    for day in range(20):
        if day in (3, 9, 15):
            continue  # days off
        when = start + timedelta(days=day, minutes=rng.randint(0, 50))
        for game in range(rng.randint(2, 5)):
            deck = DEMO_DECK_2 if day in (5, 6, 11) else DEMO_DECK
            play(when, deck, tournament=(day == 13 and game < 2))
            when += timedelta(minutes=rng.randint(16, 26))
    # Today: 7-3, the last game a few minutes ago.
    today = list("WWLWWLWWLW")
    # Just after midnight there isn't room for 14-minute gaps, so the games
    # are squeezed in after 00:00 to keep them on today's date.
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    gap = min(timedelta(minutes=14), (now - midnight) / (len(today) + 1))
    when = now - gap * len(today)
    for mark in today:
        play(when, DEMO_DECK, "Win" if mark == "W" else "Loss")
        when += gap

    conn = db._connect()
    try:
        conn.executemany(
            "INSERT INTO battles (timestamp, my_deck, opponent_deck, result, my_rank, confidence, "
            "deck_source, is_tournament) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.executemany("INSERT INTO rank_history (timestamp, rank, deck_name) VALUES (?, ?, ?)", ranks)
        conn.commit()
    finally:
        conn.close()
    db.rebuild_session_stats()
    return db


# ───────────────────────────── look ─────────────────────────────
CARD_CSS = """
QFrame#tourCard { background: transparent; border: none; }
QLabel#tourStep, QLabel#tourTitle, QLabel#tourBody {
    padding: 0; margin: 0; border: none; min-height: 0;
}
QLabel#tourStep {
    color: rgba(233, 240, 250, 0.50);
    font-family: Consolas;
    font-size: 10px;
    background: transparent;
}
QLabel#tourTitle {
    color: rgba(233, 240, 250, 0.97);
    font-size: 14px;
    font-weight: 700;
    background: transparent;
}
QLabel#tourBody {
    color: rgba(233, 240, 250, 0.82);
    font-size: 12px;
    background: transparent;
}
QPushButton#tourNext {
    background: rgba(74, 159, 216, 0.30);
    border: 1px solid rgba(74, 159, 216, 0.65);
    border-radius: 8px;
    color: rgba(255, 255, 255, 0.96);
    font-size: 11px;
    font-weight: 700;
    padding: 0 14px;
}
QPushButton#tourNext:hover { background: rgba(74, 159, 216, 0.45); }
QPushButton#tourBack {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 8px;
    color: rgba(233, 240, 250, 0.82);
    font-size: 11px;
    font-weight: 600;
    padding: 0 12px;
}
QPushButton#tourBack:hover { background: rgba(255, 255, 255, 0.10); }
QPushButton#tourSkip {
    background: transparent;
    border: none;
    color: rgba(233, 240, 250, 0.50);
    font-size: 11px;
    padding: 0 2px;
}
QPushButton#tourSkip:hover { color: rgba(233, 240, 250, 0.90); text-decoration: underline; }
"""


class TourCard(QFrame):
    """The callout: step count, title, text, Back / Next and Skip."""

    WIDTH = 330

    def __init__(self, parent, on_next, on_back, on_skip):
        super().__init__(parent)
        self.setObjectName("tourCard")
        self.setStyleSheet(CARD_CSS)
        self.setFixedWidth(self.WIDTH)
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 12, 16, 14)
        box.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.step_label = QLabel()
        self.step_label.setObjectName("tourStep")
        top.addWidget(self.step_label)
        top.addStretch()
        self.skip_btn = QPushButton("Skip tour")
        self.skip_btn.setObjectName("tourSkip")
        self.skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.skip_btn.clicked.connect(on_skip)
        top.addWidget(self.skip_btn)
        box.addLayout(top)

        self.title_label = QLabel()
        self.title_label.setObjectName("tourTitle")
        self.title_label.setWordWrap(True)
        box.addWidget(self.title_label)
        self.body_label = QLabel()
        self.body_label.setObjectName("tourBody")
        self.body_label.setWordWrap(True)
        self.body_label.setTextFormat(Qt.TextFormat.PlainText)
        box.addWidget(self.body_label)
        # Wrapped labels size themselves for the wrong width otherwise (tall gaps).
        inner = self.WIDTH - 32
        self.title_label.setFixedWidth(inner)
        self.body_label.setFixedWidth(inner)

        box.addSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch()
        self.back_btn = QPushButton("Back")
        self.back_btn.setObjectName("tourBack")
        self.back_btn.setFixedHeight(30)
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(on_back)
        row.addWidget(self.back_btn)
        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("tourNext")
        self.next_btn.setFixedHeight(30)
        self.next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.next_btn.clicked.connect(on_next)
        row.addWidget(self.next_btn)
        box.addLayout(row)

    def paintEvent(self, _event):
        # Painted, not QSS: the dashboard's own frame rules would win over a
        # stylesheet background here.
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        try:
            import theme
            fill = theme.qcolor(13, 20, 31, 250)
        except Exception:
            fill = QColor(13, 20, 31, 250)
        p.setPen(QPen(_accent(150), 1))
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        p.end()

    def set_step(self, index, total, title, body, *, back=True, next_text="Next", skip=True):
        self.step_label.setText(f"{index} / {total}")
        self.title_label.setText(title)
        self.body_label.setText(body)
        self.back_btn.setVisible(back)
        self.next_btn.setText(next_text)
        self.skip_btn.setVisible(skip)
        self.adjustSize()


def _accent(alpha=255):
    try:
        import theme
        return theme.qcolor(74, 159, 216, alpha)
    except Exception:
        return QColor(74, 159, 216, alpha)


class Spotlight(QWidget):
    """Covers the dashboard: dims everything but a rounded hole around the
    widget being explained, and holds the card. Clicks outside the card are
    eaten, so nothing changes under the tour."""

    PAD = 6
    MARGIN = 12

    def __init__(self, host, tour):
        super().__init__(host)
        self.host = host
        self.tour = tour
        self.hole = QRect()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.card = TourCard(self, tour.next, tour.back, tour.skip)
        host.installEventFilter(self)
        self.setGeometry(host.rect())
        self._pulse = 0.0
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1800, loopCount=-1)
        self._anim.valueChanged.connect(self._tick)
        self._anim.start()
        self.show()
        self.raise_()

    def _tick(self, value):
        self._pulse = float(value)
        if not self.hole.isNull():
            self.update(self.hole.adjusted(-12, -12, 12, 12))

    def eventFilter(self, obj, event):
        if obj is self.host and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.host.rect())
            QTimer.singleShot(0, self.tour.relayout)
        return False

    def set_hole(self, rect):
        self.hole = rect.adjusted(-self.PAD, -self.PAD, self.PAD, self.PAD).intersected(
            self.rect().adjusted(2, 2, -2, -2)) if rect is not None and not rect.isNull() else QRect()
        self.place_card()
        self.update()

    def place_card(self):
        card = self.card
        card.adjustSize()
        w, h = card.width(), card.height()
        area = self.rect().adjusted(self.MARGIN, self.MARGIN, -self.MARGIN, -self.MARGIN)
        hole = self.hole
        if hole.isNull():
            card.move(area.center().x() - w // 2, area.center().y() - h // 2)
            card.raise_()
            return
        gap = 14
        cx = hole.center().x() - w // 2
        cy = hole.center().y() - h // 2
        candidates = [
            QPoint(hole.right() + gap, hole.top()),       # right
            QPoint(hole.left() - gap - w, hole.top()),    # left
            QPoint(cx, hole.bottom() + gap),              # below
            QPoint(cx, hole.top() - gap - h),             # above
            QPoint(hole.right() + gap, cy),
            QPoint(hole.left() - gap - w, cy),
        ]

        def clamp(p):
            x = min(max(p.x(), area.left()), area.right() - w)
            y = min(max(p.y(), area.top()), area.bottom() - h)
            return QPoint(x, y)

        def overlap(p):
            r = QRect(p, card.size()).intersected(hole)
            return 0 if r.isEmpty() else r.width() * r.height()

        best = None
        for p in candidates:
            q = clamp(p)
            if overlap(q) == 0:
                best = q
                break
        if best is None:  # the hole fills the window: the corner that covers it least
            corners = [QPoint(area.right() - w, area.bottom() - h), QPoint(area.left(), area.bottom() - h),
                       QPoint(area.right() - w, area.top()), QPoint(area.left(), area.top())]
            best = min(corners, key=overlap)
        card.move(best)
        card.raise_()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        if not self.hole.isNull():
            cut = QPainterPath()
            cut.addRoundedRect(QRectF(self.hole), 10, 10)
            path = path.subtracted(cut)
        p.fillPath(path, QColor(3, 7, 13, 195))
        if not self.hole.isNull():
            import math
            glow = 0.5 + 0.5 * math.sin(self._pulse * math.pi * 2)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(_accent(int(60 + 60 * glow)), 6))
            p.drawRoundedRect(QRectF(self.hole).adjusted(-2, -2, 2, 2), 12, 12)
            p.setPen(QPen(_accent(235), 2))
            p.drawRoundedRect(QRectF(self.hole), 10, 10)
        p.end()

    # Nothing under the tour reacts while it is up.
    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.tour.skip()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.tour.next()
        elif key == Qt.Key.Key_Left:
            self.tour.back()
        else:
            event.accept()

    def close_down(self):
        self._anim.stop()
        try:
            self.host.removeEventFilter(self)
        except RuntimeError:
            pass
        self.hide()
        self.deleteLater()


class HudRing(QWidget):
    """A pulsing ring around the HUD's arrow. Mouse clicks go through it to
    the arrow."""

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                         | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._v = 0.0
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=1400, loopCount=-1)
        self._anim.valueChanged.connect(self._tick)
        self._anim.start()

    def _tick(self, value):
        self._v = float(value)
        self.update()

    def around(self, global_rect):
        r = 22
        c = global_rect.center()
        self.setGeometry(c.x() - r, c.y() - r, 2 * r, 2 * r)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        v = self._v
        full = self.width() / 2 - 2
        radius = 8 + (full - 8) * v
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(_accent(int(230 * (1 - v))), 2))
        p.drawEllipse(QRectF(self.rect()).center(), radius, radius)
        p.setPen(QPen(_accent(220), 2))
        p.drawEllipse(QRectF(self.rect()).center(), 9, 9)
        p.end()


class HudCardWindow(QWidget):
    """The card for the HUD step, in its own window just above the HUD."""

    def __init__(self, tour):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        self.card = TourCard(self, tour.next, tour.back, tour.skip)
        box.addWidget(self.card)

    def place_above(self, hud_global_rect):
        self.adjustSize()
        screen = QApplication.screenAt(hud_global_rect.center()) or QApplication.primaryScreen()
        area = screen.availableGeometry()
        x = hud_global_rect.right() - self.width()
        y = hud_global_rect.top() - self.height() - 46  # leaves room for the ring and chat
        x = min(max(x, area.left() + 8), area.right() - self.width() - 8)
        y = min(max(y, area.top() + 8), area.bottom() - self.height() - 8)
        self.move(x, y)


def _to_front(*windows):
    """Topmost and above the HUD, which re-asserts HWND_TOPMOST every second."""
    try:
        import win32con
        import win32gui
    except ImportError:
        for w in windows:
            if w is not None:
                w.raise_()
        return
    for w in windows:
        if w is None or not w.isVisible():
            continue
        try:
            win32gui.SetWindowPos(int(w.winId()), win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE)
        except Exception:
            w.raise_()


# ───────────────────────────── the steps ─────────────────────────────
def _graph_card(widget):
    w = widget
    while w is not None and w.objectName() != "graphCard":
        w = w.parentWidget()
    return w or widget


def _tab_button(win, name):
    index = win._main_tab_index(name)
    if index < 0:
        return None
    bar = win.tab_widget.tabBar()
    return bar, bar.tabRect(index)


def _steps():
    """(tab, target(win) -> widget | (widget, rect) | None, title, body).
    Written to match what each control does; keep it plain."""
    import StatsUI
    settings_tab = StatsUI.SETTINGS_TAB
    return [
        (None, None, "How it works",
         "Keep the app open while you play. After each battle, it saves the game, works out both decks "
         "and adds it to your stats. You don't need to copy or paste anything.\n\nThe games in this "
         "tour are made up. They go away when the tour ends."),
        ("Stats", lambda w: w.stats_summary, "The summary",
         "Your Elo, your best Elo, your win rate, today's games and your last few results."),
        ("Stats", lambda w: _graph_card(w.elo_chart), "Elo over time",
         "Green means your Elo went up. Red means it went down.\n\nDrag to zoom in. The buttons change "
         "how far back it goes."),
        ("Stats", lambda w: _graph_card(w.winrate_chart), "Win rate",
         "Your win rate over your recent games. Use the menu to pick a deck."),
        ("Stats", lambda w: w.deck_usage_widget, "Your decks",
         "Every deck you've played and its record. Click one to see its page."),
        ("Stats", lambda w: w.recent_battles_widget, "Recent battles",
         "Your latest games and who won.\n\nIf a deck name is wrong, fix it in Settings under Battle "
         "Database."),
        ("Decks", lambda w: w.deck_tabs, "A page per deck",
         "See how each deck does against every other deck, and your last 10 games with it.\n\nPin a "
         "deck to keep it first. Ignore a deck to leave it out of the HUD's daily record."),
        ("Meta", lambda w: _tab_button(w, "Meta"), "Meta",
         "What people are playing online, in person and in Japan, with win rates and matchups. You can "
         "add your own games too."),
        ("In Person", lambda w: _tab_button(w, "In Person"), "In Person",
         "Find events near you and see how your friends did. You can also print a tournament decklist "
         "sheet from a deck you exported."),
        ("Limitless Dashboard", lambda w: w.limitless_dashboard_view
         if hasattr(w, "limitless_dashboard_view") else _tab_button(w, "Limitless Dashboard"),
         "Limitless online tournaments",
         "Sign in to Limitless here once and it stays signed in.\n\nDuring an online tournament, the "
         "app watches your match page for you."),
        ("Limitless Dashboard", lambda w: w.limitless_dashboard_autocheck_btn, "Auto check-in",
         "Turn this on and the app checks you in when check-in opens. It plays a sound when it does."),
        ("Limitless Dashboard", lambda w: w.limitless_auto_friend_btn, "Friend requests",
         "Each round, the app can add your opponent as a friend in the game, so you can invite "
         "them.\n\nOff: it asks you first. On: it just sends it."),
        ("Limitless Dashboard", lambda w: getattr(w, "limitless_opp_deck_btn", None), "Chat and decklists",
         "Match chat shows over the game, above the HUD. Point at it to reply.\n\nWhen Limitless shows "
         "your opponent's deck, it opens in its own window. This button opens it again."),
        ("TrainerHill", lambda w: _tab_button(w, "TrainerHill"), "TrainerHill",
         "TrainerHill's meta and matchup tools, right in the app."),
        ("Japan Data", lambda w: _tab_button(w, "Japan Data"), "Japan Data",
         "Top decks from Japan. Japan gets new cards first, so this shows what may be coming next."),
        ("PokeData", lambda w: _tab_button(w, "PokeData"), "PokeData",
         "Event results, standings, Championship Points, a hand simulator and a decklist compare tool."),
        (settings_tab, lambda w: getattr(w, "export_card", None), "Auto-export",
         "This is what saves your battles. When a battle ends, it exports the battle log from the game "
         "for you.\n\nLeave it on unless you want to do it yourself."),
        (settings_tab, lambda w: getattr(w, "parser_card", None), "Deck detection",
         "How the app knows which decks were played. Automatic uses AI when it can. You can also use "
         "your own OpenAI key or a local model.\n\nWith AI off, the app guesses from the cards and "
         "asks you to check the opponent's deck after each battle."),
        (None, None, "You're set",
         "The example games are gone. Your stats start with your next battle.\n\nTo see this tour "
         "again, go to Settings, then Startup."),
    ]


class Tour(QObject):
    """Runs the tour. `overlay` is the HUD (MinimalOverlay) when there is
    one; `window` is the dashboard (StatsWindow), built on demand."""

    def __init__(self, overlay=None, window=None, start_at_hud=True):
        super().__init__()
        self.overlay = overlay
        self.window = window
        self.start_at_hud = bool(start_at_hud and overlay is not None)
        self.steps = _steps()
        self.index = -1 if self.start_at_hud else 0
        self.spot = None
        self.hud_card = None
        self.ring = None
        self.demo = None
        self._real_overlay_db = None
        self._real_window_db = None
        self._start_tab = None
        self._added_icons = {}
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._watch)

    # ── start / stop ──
    def start(self):
        global _active
        if _active is not None:
            return
        _active = self
        try:
            self.demo = build_demo_db()
        except Exception as exc:
            print(f"Tutorial: no example data ({exc})")
            self.demo = None
        if self.overlay is not None and self.demo is not None:
            self._real_overlay_db = self.overlay.db
            self.overlay.db = self.demo
            self._refresh_hud()
        self._timer.start()
        if self.start_at_hud:
            self._show_hud_step()
        else:
            self._open_window()
            self.go(0)

    def _finish(self, skipped):
        global _active
        self._timer.stop()
        for w in (self.ring, self.hud_card):
            if w is not None:
                w.hide()
                w.deleteLater()
        self.ring = self.hud_card = None
        if self.spot is not None:
            self.spot.close_down()
            self.spot = None
        if self.overlay is not None and self._real_overlay_db is not None:
            self.overlay.db = self._real_overlay_db
            self._refresh_hud()
        win = self.window
        if win is not None and self._real_window_db is not None:
            try:
                win.db = self._real_window_db
                for deck, icons in self._added_icons.items():
                    if win.deck_icon_overrides.get(deck) == icons:
                        win.deck_icon_overrides.pop(deck, None)
                win.load_stats()
                win._refresh_deck_dashboards(win.deck_analyses)
                index = win._main_tab_index("Stats")
                if index >= 0 and win.isVisible():
                    win.tab_widget.setCurrentIndex(index)
            except Exception as exc:
                print(f"Tutorial: restoring the dashboard failed ({exc})")
        self.demo = None
        remove_demo_db()
        try:
            mark_done()
        except Exception:
            pass
        _active = None

    def skip(self):
        self._finish(skipped=True)

    # ── HUD step ──
    def _hud_rects(self):
        ov = self.overlay
        arrow = ov.arrow_label
        top_left = arrow.mapToGlobal(QPoint(0, 0))
        return QRect(top_left, arrow.size()), QRect(ov.mapToGlobal(QPoint(0, 0)), ov.size())

    def _show_hud_step(self):
        self.index = -1
        if self.spot is not None:
            self.spot.hide()
        if self.ring is None:
            self.ring = HudRing()
        if self.hud_card is None:
            self.hud_card = HudCardWindow(self)
        total = len(self.steps) + 1
        self.hud_card.card.set_step(
            1, total, "Your HUD",
            "This bar sits on the corner of the game."
            "\n\nElo is your rating, Max is your best, and the last number is today's wins and losses."
            "\n\nClick the ▲ arrow to open the app.",
            back=False, next_text="Open it for me")
        self._place_hud_step()
        self.ring.show()
        self.hud_card.show()
        self.hud_card.raise_()

    def _place_hud_step(self):
        if self.overlay is None or not self.overlay.isVisible():
            for w in (self.ring, self.hud_card):
                if w is not None:
                    w.hide()
            return
        arrow, hud = self._hud_rects()
        if self.ring is not None:
            self.ring.around(arrow)
            if not self.ring.isVisible():
                self.ring.show()
        if self.hud_card is not None:
            self.hud_card.place_above(hud)
            if not self.hud_card.isVisible():
                self.hud_card.show()
        _to_front(self.hud_card, self.ring)  # the ring last: over the HUD and its buddy

    def _leave_hud_step(self):
        for w in (self.ring, self.hud_card):
            if w is not None:
                w.hide()

    # ── dashboard ──
    DEMO_ICONS = {DEMO_DECK: ["gardevoir"], DEMO_DECK_2: ["dragapult"]}

    def _use_demo(self, win):
        """The dashboard on the example data. The example decks get their
        Pokémon icons in memory only (Gardevoir may not be in today's meta);
        the user's own icon choices file isn't touched."""
        self._real_window_db = win.db
        win.db = self.demo
        for deck, icons in self.DEMO_ICONS.items():
            if not win.deck_icon_overrides.get(deck):
                win.deck_icon_overrides[deck] = list(icons)
                self._added_icons[deck] = list(icons)
        win.load_stats()
        win._refresh_deck_dashboards(win.deck_analyses)

    def _open_window(self):
        ov = self.overlay
        if self.window is None and ov is not None:
            self.window = ov._ensure_stats_window()
        win = self.window
        if win is None:
            return None
        if self.demo is not None and self._real_window_db is None:
            self._use_demo(win)
        if not win.isVisible():
            if ov is not None:
                ov.animate_arrow("▼")
                ov.open_stats_dashboard()
            else:
                win.show()
        win.raise_()
        win.activateWindow()
        if self.spot is None:
            self.spot = Spotlight(win.container, self)
        self.spot.show()
        self.spot.raise_()
        self.spot.setFocus()
        return win

    def go(self, index):
        if index < 0:
            if self.start_at_hud:
                self._show_hud_step()
            return
        if index >= len(self.steps):
            self._finish(skipped=False)
            return
        if self.index < 0:
            self._leave_hud_step()
        self.index = index
        win = self._open_window()
        if win is None:
            self._finish(skipped=True)
            return
        tab, _target, title, body = self.steps[index]
        if tab:
            i = win._main_tab_index(tab)
            if i >= 0 and win.tab_widget.currentIndex() != i:
                win.tab_widget.setCurrentIndex(i)
        offset = 1 if self.start_at_hud else 0
        total = len(self.steps) + offset
        last = index == len(self.steps) - 1
        self.spot.card.set_step(index + 1 + offset, total, title, body,
                                back=(index > 0 or self.start_at_hud),
                                next_text="Finish" if last else "Next", skip=not last)
        self.spot.set_hole(QRect())  # the card shows at once; the hole follows the layout
        QTimer.singleShot(60, self.relayout)
        QTimer.singleShot(260, self.relayout)

    def _target_rect(self):
        """The current step's target in Spotlight coordinates (None: no hole)."""
        if self.spot is None or self.index < 0:
            return None
        target = self.steps[self.index][1]
        if target is None:
            return None
        try:
            found = target(self.window)
        except Exception:
            return None
        if found is None:
            return None
        widget, rect = found if isinstance(found, tuple) else (found, None)
        if widget is None or not widget.isVisible():
            return None
        if rect is None:
            rect = widget.rect()
            self._scroll_into_view(widget)
        top_left = widget.mapTo(self.window.container, rect.topLeft())
        return QRect(top_left, rect.size())

    def _scroll_into_view(self, widget):
        from PySide6.QtWidgets import QScrollArea
        w = widget.parentWidget()
        while w is not None:
            if isinstance(w, QScrollArea):
                view = w.viewport().rect()
                pos = widget.mapTo(w.viewport(), QPoint(0, 0))
                if pos.y() < 0 or pos.y() + min(widget.height(), view.height()) > view.height():
                    w.ensureWidgetVisible(widget, 0, 24)
                return
            w = w.parentWidget()

    def relayout(self):
        if self.spot is None or self.index < 0:
            return
        self.spot.setGeometry(self.window.container.rect())
        rect = self._target_rect()
        if rect is not None:
            rect = rect.intersected(self.spot.rect())
        self.spot.set_hole(rect if rect is not None and not rect.isEmpty() else QRect())
        self.spot.raise_()

    def next(self):
        self.go(self.index + 1)

    def back(self):
        self.go(self.index - 1)

    def _watch(self):
        """Follows the HUD for the first step, notices the arrow being
        clicked, and ends the tour if the dashboard is closed under it."""
        if self.index < 0:
            win = self.window or (self.overlay.stats_window if self.overlay is not None else None)
            if win is not None and self.demo is not None and self._real_window_db is None:
                self.window = win  # example data in before the arrow opens it
                self._use_demo(win)
            if win is not None and win.isVisible():
                self.window = win
                self.go(0)  # they clicked the arrow
                return
            self._place_hud_step()
            return
        if self.window is not None and not self.window.isVisible():
            self.skip()
            return
        if self.spot is not None:
            rect = self._target_rect()
            hole = rect.adjusted(-Spotlight.PAD, -Spotlight.PAD, Spotlight.PAD, Spotlight.PAD) \
                .intersected(self.spot.rect().adjusted(2, 2, -2, -2)) if rect is not None else QRect()
            if hole != self.spot.hole:
                self.relayout()

    def _refresh_hud(self):
        ov = self.overlay
        try:
            ov.load_stats()
            ov.update_display()
        except Exception:
            pass


def start(overlay=None, window=None, start_at_hud=True):
    """Start the tour unless one is already running. Returns it."""
    if _active is not None:
        return _active
    tour = Tour(overlay=overlay, window=window, start_at_hud=start_at_hud)
    tour.start()
    return tour


def cleanup_stale():
    """A demo file left by a tour that never finished (app closed mid-tour)."""
    if _active is None and os.path.exists(DEMO_DB):
        remove_demo_db()
