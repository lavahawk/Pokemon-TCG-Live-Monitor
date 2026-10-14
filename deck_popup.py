"""
"Opponent deck" card: a small frameless card above the overlay's mini GUI,
shown after each saved battle (requests come from deck_confirm.py).

  show  - the top 3 decks (AI / card evidence) as one-click choices with
          icons and probabilities, the pick highlighted. Clicking one saves
          it; "Other…" types a name. Fades once the game is back on the main
          menu, unless the pick is a low-confidence one (then it waits).
  edit  - type the deck (autocomplete: your recorded opponent decks, then
          Limitless archetypes). Used straight away when no AI pick exists
          (local-only mode, no API key, AI failed).
  new   - the typed name isn't known: add it as a new deck or save as Other.
  done  - saved: chime, check mark with a ring, then fades.
"""

import math
import time

from PySide6.QtCore import Qt, QTimer, QVariantAnimation, QEasingCurve, QStringListModel, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton, QCompleter,
)

from deck_confirm import OTHER, canonical_name, deck_icon_paths, known_deck_names, mark_handled, play_chime

BLUE = QColor(74, 159, 216)
AMBER = QColor(240, 180, 60)
GREEN = QColor(102, 199, 120)
RED = QColor(239, 83, 80)

RESULT_COLORS = {"WIN": GREEN, "LOSS": RED}

CARD_W = 250
MIN_VISIBLE_S = 4.0     # an AI pick stays at least this long
FADE_AFTER_MENU_S = 2.5  # ...and fades this long after the main menu is seen
MAX_SHOW_S = 90.0       # fallback when the menu is never reported
LOW_CONFIDENCE = 50     # below this the card asks instead of fading on the menu
ICON_PX = 18


class ChoiceButton(QPushButton):
    """One deck option: icons, name, probability; `picked` = the current pick."""

    def __init__(self, deck, probability, picked):
        super().__init__()
        self.deck = deck
        self.setObjectName("choicePicked" if picked else "choice")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(26)
        row = QHBoxLayout(self)
        row.setContentsMargins(6, 0, 7, 0)
        row.setSpacing(3)
        icons = deck_icon_paths(deck)
        for path in icons:
            pix = QPixmap(path)
            if pix.isNull():
                continue
            label = QLabel()
            label.setPixmap(pix.scaled(ICON_PX, ICON_PX, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation))
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(label)
        if not icons:
            row.addSpacing(2)
        name = QLabel()
        name.setObjectName("choiceName")
        name.setText(name.fontMetrics().elidedText(deck, Qt.TextElideMode.ElideRight, CARD_W - 110))
        name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row.addWidget(name, 1)
        if probability is not None:
            pct = QLabel("<1%" if probability < 0.01 else f"{probability * 100:.0f}%")
            pct.setObjectName("choicePct")
            pct.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(pct)
        if picked:
            mark = QLabel("✓")
            mark.setObjectName("choiceMark")
            mark.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            row.addWidget(mark)
        self.setToolTip(f"Save “{deck}” as the opponent's deck")


class DeckConfirmPopup(QWidget):
    def __init__(self, db):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(CARD_W)
        self.db = db
        self.request = None
        self.mode = None
        self.current = ""
        self.pending = ""
        self.names = []
        self.accent = BLUE
        self._anchor = None
        self._lift = 0.0
        self._shake = 0.0
        self._success = 0.0
        self._shown_at = 0.0
        self._fade_deadline = None
        self._leaving = False
        self._build()

        self._intro = QVariantAnimation(self, duration=280, easingCurve=QEasingCurve.Type.OutCubic)
        self._intro.valueChanged.connect(self._on_intro)
        self._outro = QVariantAnimation(self, duration=450, easingCurve=QEasingCurve.Type.InCubic)
        self._outro.valueChanged.connect(self._on_intro)
        self._outro.finished.connect(self._after_outro)
        self._shaker = QVariantAnimation(self, duration=320, startValue=0.0, endValue=1.0)
        self._shaker.valueChanged.connect(self._on_shake)
        self._tick = QVariantAnimation(self, duration=620, startValue=0.0, endValue=1.0,
                                       easingCurve=QEasingCurve.Type.OutCubic)
        self._tick.valueChanged.connect(self._on_success)

    # ── layout ──
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 8, 10, 9)
        root.setSpacing(3)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.caption = QLabel()
        self.caption.setObjectName("cap")
        head.addWidget(self.caption)
        head.addStretch()
        self.chip = QLabel()
        self.chip.setObjectName("chip")
        head.addWidget(self.chip)
        self.close_btn = QToolButton()
        self.close_btn.setObjectName("close")
        self.close_btn.setText("✕")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setToolTip("Keep this deck and close")
        self.close_btn.clicked.connect(self._close_clicked)
        head.addWidget(self.close_btn)
        root.addLayout(head)

        self.name = QLabel()
        self.name.setObjectName("name")
        self.name.setCursor(Qt.CursorShape.PointingHandCursor)
        root.addWidget(self.name)

        self.choices_box = QWidget()
        self.choices = QVBoxLayout(self.choices_box)
        self.choices.setContentsMargins(0, 2, 0, 0)
        self.choices.setSpacing(3)
        root.addWidget(self.choices_box)

        self.field = QLineEdit()
        self.field.setObjectName("field")
        self.field.setPlaceholderText("Type the opponent's deck…")
        self.field.returnPressed.connect(self._submit)
        self.model = QStringListModel(self)
        self.completer = QCompleter(self.model, self.field)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.completer.setMaxVisibleItems(7)
        self.completer.activated.connect(lambda text: QTimer.singleShot(0, lambda: self._submit(text)))
        self.completer.popup().setStyleSheet(POPUP_STYLE)
        self.field.setCompleter(self.completer)
        root.addWidget(self.field)

        self.new_box = QWidget()
        new_col = QVBoxLayout(self.new_box)
        new_col.setContentsMargins(0, 0, 0, 0)
        new_col.setSpacing(5)
        self.new_msg = QLabel()
        self.new_msg.setObjectName("msg")
        self.new_msg.setWordWrap(True)
        new_col.addWidget(self.new_msg)
        nb = QHBoxLayout()
        nb.setContentsMargins(0, 0, 0, 0)
        nb.setSpacing(5)
        new_col.addLayout(nb)
        self.add_btn = QPushButton("Add new deck")
        self.add_btn.setObjectName("primary")
        self.add_btn.clicked.connect(lambda: self._save(self.pending))
        self.other_btn = QPushButton(f"Save as {OTHER}")
        self.other_btn.setObjectName("secondary")
        self.other_btn.clicked.connect(lambda: self._save(OTHER))
        self.back_btn = QPushButton("Back")
        self.back_btn.setObjectName("link")
        self.back_btn.clicked.connect(lambda: self._set_mode("edit", prefill=self.pending))
        for btn in (self.add_btn, self.other_btn, self.back_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            nb.addWidget(btn)
        nb.addStretch()
        root.addWidget(self.new_box)

        self.hint = QLabel()
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        self.hint.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.hint.linkActivated.connect(lambda _l: self._set_mode("edit", prefill=""))
        root.addWidget(self.hint)
        self.setStyleSheet(CARD_STYLE)

    # ── public: driven by the overlay ──
    def offer(self, request, anchor):
        """Show the card for a new request (ignored if it's already showing).
        anchor = (right, bottom) of the space above the mini GUI."""
        if self.request and self.request.get("battle_id") == request.get("battle_id"):
            return
        self._anchor = anchor
        self.request = dict(request)
        self.current = (request.get("deck") or "").strip()
        self.names = known_deck_names(self.db)
        self.model.setStringList(self.names)
        self._fade_deadline = None
        self._leaving = False
        self._outro.stop()
        if request.get("needs_input") and not self._candidates():
            guess = self.current if request.get("source") == "guess" else ""
            self._set_mode("edit", prefill=guess, focus=False)
        else:
            self._set_mode("show")
        self._shown_at = time.time()
        self.setWindowOpacity(0.0)
        self.show()
        self._intro.setStartValue(0.0)
        self._intro.setEndValue(1.0)
        self._intro.start()

    def tick(self, menu_seen, anchor, overlay_visible):
        """Called about once a second: follow the overlay, fade when due."""
        if self.request is None:
            return
        self._anchor = anchor
        if not overlay_visible:
            if self.isVisible():
                self.hide()
            return
        if not self.isVisible():
            self.show()
        self._reposition()
        if self.mode != "show" or self._leaving:
            return
        now = time.time()
        if self.underMouse():
            self._fade_deadline = None
            return
        if self._fade_deadline is None:
            if menu_seen > float(self.request.get("created") or 0) and not self._low_confidence():
                self._fade_deadline = max(now + FADE_AFTER_MENU_S, self._shown_at + MIN_VISIBLE_S)
            elif now - self._shown_at > MAX_SHOW_S:
                self._fade_deadline = now
        if self._fade_deadline is not None and now >= self._fade_deadline:
            self._finish()

    # ── modes ──
    def _set_mode(self, mode, prefill="", focus=True):
        self.mode = mode
        result = (self.request or {}).get("result", "").upper()
        source = (self.request or {}).get("source")
        has_choices = mode == "show" and bool(self._candidates())
        self.name.setVisible(mode == "done" or (mode == "show" and not has_choices))
        self.choices_box.setVisible(has_choices)
        self.field.setVisible(mode == "edit")
        self.new_box.setVisible(mode == "new")
        self.chip.setVisible(mode in ("show", "edit"))
        self.close_btn.setVisible(mode != "done")
        self.name.setContentsMargins(0, 0, 26 if mode == "done" else 0, 0)
        if mode == "show":
            low = self._low_confidence()
            self.accent = BLUE if source in ("ai", "cards") and not low else AMBER
            self.caption.setText(("WHICH DECK WAS IT?" if low else "OPPONENT DECK")
                                 + (f"  ·  {result}" if result else ""))
            # cards = picked from the opponent's revealed cards vs public decklists
            chip = {"ai": "AI", "cards": "CARDS"}.get(source, "GUESS")
            confidence = (self.request or {}).get("confidence")
            if confidence is not None:
                chip += f" {int(confidence)}%"
            self._set_chip(chip, self.accent)
            self.chip.setVisible(source in ("ai", "cards", "guess"))
            self._set_name(self.current or "Unknown")
            self._fill_choices()
            if has_choices:
                self.hint.setText("Click the right deck to confirm  ·  <a href='other' style='color:#B8C2CC;'>"
                                  "Other…</a>")
            else:
                self.hint.setText("Wrong? Click to fix" if self.current else "Click to set the deck")
        elif mode == "edit":
            self.accent = AMBER if (self.request or {}).get("needs_input") else BLUE
            asked = (self.request or {}).get("needs_input")
            self.caption.setText("WHAT DID YOU PLAY AGAINST?" if asked else "FIX OPPONENT DECK")
            self._set_chip(result or "", RESULT_COLORS.get(result, AMBER))
            self.chip.setVisible(bool(result))
            self.field.setText(prefill)
            self.field.selectAll()
            self.hint.setText("Enter to save  ·  Esc to cancel" if not asked else "Enter to save")
            if focus:
                self.activateWindow()
                self.raise_()
                self.field.setFocus()
        elif mode == "new":
            self.accent = AMBER
            self.caption.setText("NEW DECK NAME")
            self.new_msg.setText(f"“{self.pending}” isn't a deck you've recorded or a Limitless "
                                 f"archetype. Add it as a new deck, or file it under {OTHER}?")
            self.hint.setText("")
        elif mode == "done":
            self.accent = GREEN
            self.caption.setText("SAVED")
            self.hint.setText("")
        self.hint.setVisible(bool(self.hint.text()))
        self.adjustSize()
        # sizeHint ignores word-wrapped labels; size to the height they need at CARD_W.
        needed = self.layout().totalHeightForWidth(CARD_W)
        if needed > self.height():
            self.resize(CARD_W, needed)
        self._reposition()
        self.update()

    def _candidates(self):
        """[(deck, probability or None)] from the request, the pick first."""
        out, seen = [], set()
        for item in [{"deck": self.current, "p": None}] + list((self.request or {}).get("candidates") or []):
            deck = " ".join(str((item or {}).get("deck") or "").split())
            key = deck.casefold()
            if not deck or key in seen or key.startswith("unknown"):
                continue
            if key == self.current.casefold() and item.get("p") is None and out:
                continue
            seen.add(key)
            out.append((deck, item.get("p")))
        # The pick's probability comes from the candidates list when present.
        probs = {(i.get("deck") or "").casefold(): i.get("p") for i in (self.request or {}).get("candidates") or []}
        out = [(d, p if p is not None else probs.get(d.casefold())) for d, p in out]
        return out[:3] if len(out) > 1 else []

    def _low_confidence(self):
        confidence = (self.request or {}).get("confidence")
        return confidence is not None and int(confidence) < LOW_CONFIDENCE

    def _fill_choices(self):
        while self.choices.count():
            item = self.choices.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for deck, probability in self._candidates():
            button = ChoiceButton(deck, probability, picked=deck.casefold() == self.current.casefold())
            button.clicked.connect(lambda _c=False, d=deck: self._save(d))
            self.choices.addWidget(button)

    def _set_name(self, text):
        metrics = self.name.fontMetrics()
        self.name.setText(metrics.elidedText(text, Qt.TextElideMode.ElideRight, CARD_W - 40))
        self.name.setToolTip(text)

    def _set_chip(self, text, color):
        self.chip.setText(text)
        self.chip.setStyleSheet(
            f"color: rgb({color.red()},{color.green()},{color.blue()});"
            f"background: rgba({color.red()},{color.green()},{color.blue()},0.16);"
            f"border: 1px solid rgba({color.red()},{color.green()},{color.blue()},0.45);")

    # ── actions ──
    def mousePressEvent(self, event):
        if self.mode == "show" and event.button() == Qt.MouseButton.LeftButton:
            self._fade_deadline = None
            self._set_mode("edit", prefill=self.current)
            return
        if self.mode == "edit":
            self.activateWindow()
            self.field.setFocus()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.mode == "new":
                self._set_mode("edit", prefill=self.pending)
            elif self.mode == "edit":
                self._set_mode("show")
            return
        super().keyPressEvent(event)

    def _submit(self, text=None):
        if self.mode != "edit":
            return
        text = " ".join((text if text is not None else self.field.text()).split())
        if not text:
            self._shaker.start()
            return
        known = canonical_name(text, self.names)
        if known:
            self._save(known)
        else:
            self.pending = text
            self._set_mode("new")

    def _save(self, deck):
        battle_id = (self.request or {}).get("battle_id")
        try:
            ok = self.db.update_battle_record(battle_id, opponent_deck=deck, deck_source="Manual", confidence=100)
        except Exception:
            ok = False
        if not ok:
            self.caption.setText("COULDN'T SAVE - TRY AGAIN")
            self.accent = RED
            self._shaker.start()
            self.update()
            return
        mark_handled(battle_id)
        self.current = deck
        play_chime()
        self._set_mode("done")
        self._set_name(deck)
        self._tick.start()
        QTimer.singleShot(1500, self._finish)

    def _close_clicked(self):
        self._finish()

    def _finish(self):
        """Fade out; the request counts as handled (the shown deck stays)."""
        if self._leaving or self.request is None:
            return
        self._leaving = True
        mark_handled(self.request.get("battle_id"))
        self._outro.setStartValue(1.0)
        self._outro.setEndValue(0.0)
        self._outro.start()

    def _after_outro(self):
        self.hide()
        self.request = None
        self.mode = None
        self._leaving = False

    # ── animation ──
    def _on_intro(self, value):
        value = float(value)
        self.setWindowOpacity(0.97 * value)
        self._lift = (1.0 - value) * 12.0
        self._reposition()

    def _on_shake(self, value):
        value = float(value)
        self._shake = math.sin(value * math.pi * 6) * (1.0 - value) * 6.0
        self._reposition()

    def _on_success(self, value):
        self._success = float(value)
        self.update()

    def _reposition(self):
        if not self._anchor:
            return
        right, bottom = self._anchor
        self.move(int(right - self.width() + self._shake), int(bottom - self.height() - self._lift))

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(80, 80, 80, 215), 1))
        p.setBrush(QColor(20, 20, 20, 236))
        p.drawRoundedRect(card, 10, 10)
        # accent bar
        accent = QColor(self.accent)
        accent.setAlpha(230)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(5, 9, 3, self.height() - 18), 1.5, 1.5)
        if self.mode == "done":
            self._paint_check(p)
        p.end()

    def _paint_check(self, p):
        s = self._success
        geo = self.name.geometry()
        center = QPointF(self.width() - 24, geo.center().y())
        # expanding ring
        ring = QColor(GREEN)
        ring.setAlphaF(max(0.0, 0.55 * (1.0 - s)))
        p.setPen(QPen(ring, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        radius = 8 + 10 * s
        p.drawEllipse(center, radius, radius)
        # filled disc (springs in)
        scale = min(1.0, s * 1.6)
        disc = QColor(GREEN)
        disc.setAlphaF(0.9)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(disc)
        p.drawEllipse(center, 8 * scale, 8 * scale)
        # check stroke drawn progressively
        progress = max(0.0, min(1.0, (s - 0.25) / 0.6))
        if progress <= 0:
            return
        a = center + QPointF(-4.0, 0.2)
        b = center + QPointF(-1.2, 3.0)
        c = center + QPointF(4.2, -3.2)
        path = QPainterPath(a)
        first = min(1.0, progress / 0.4)
        path.lineTo(a + (b - a) * first)
        if progress > 0.4:
            second = (progress - 0.4) / 0.6
            path.lineTo(b + (c - b) * second)
        pen = QPen(QColor(16, 30, 18), 2.0)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPath(path)


CARD_STYLE = """
    QLabel { background: transparent; font-family: 'Segoe UI', Arial; }
    QLabel#cap { color: #8E959E; font-size: 9px; font-weight: 700; letter-spacing: 0.6px; }
    QLabel#chip { font-size: 8px; font-weight: 800; border-radius: 6px; padding: 0px 5px; }
    QLabel#name { color: #F2F4F7; font-size: 13px; font-weight: 600; }
    QLabel#hint { color: #7D848D; font-size: 9px; }
    QLabel#msg { color: #C9CED6; font-size: 10px; }
    QPushButton#choice, QPushButton#choicePicked {
        background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.10);
        border-radius: 7px; padding: 0px; text-align: left; }
    QPushButton#choice:hover { background: rgba(255,255,255,0.09); border-color: rgba(255,255,255,0.26); }
    QPushButton#choicePicked { background: rgba(74,159,216,0.16); border-color: rgba(74,159,216,0.55); }
    QPushButton#choicePicked:hover { background: rgba(74,159,216,0.26); }
    QLabel#choiceName { color: #EEF1F5; font-size: 11px; font-weight: 600; }
    QLabel#choicePct { color: #8E959E; font-size: 9px; font-weight: 700; }
    QLabel#choiceMark { color: #7CC4F0; font-size: 10px; font-weight: 800; }
    QToolButton#close { background: transparent; border: none; color: #6F767F; font-size: 9px; padding: 0 2px; }
    QToolButton#close:hover { color: #E6E6E6; }
    QLineEdit#field {
        background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14);
        border-radius: 6px; color: #F2F4F7; font-family: 'Segoe UI', Arial; font-size: 12px;
        padding: 4px 7px; selection-background-color: rgba(74,159,216,0.45);
    }
    QLineEdit#field:focus { border-color: rgba(240,180,60,0.70); background: rgba(255,255,255,0.09); }
    QPushButton { font-family: 'Segoe UI', Arial; font-size: 9px; font-weight: 700;
                  border-radius: 9px; padding: 3px 9px; }
    QPushButton#primary { background: rgba(240,180,60,0.22); border: 1px solid rgba(240,180,60,0.60); color: #FFE7B8; }
    QPushButton#primary:hover { background: rgba(240,180,60,0.34); }
    QPushButton#secondary { background: transparent; border: 1px solid rgba(255,255,255,0.22); color: #D6DAE0; }
    QPushButton#secondary:hover { border-color: rgba(255,255,255,0.40); color: #FFFFFF; }
    QPushButton#link { background: transparent; border: none; color: #7D848D; padding: 3px 4px; }
    QPushButton#link:hover { color: #D6DAE0; }
"""

POPUP_STYLE = """
    QListView {
        background: #181A1E; border: 1px solid rgba(240,180,60,0.45); color: #E8EBEF;
        font-family: 'Segoe UI', Arial; font-size: 11px; outline: none;
    }
    QListView::item { padding: 3px 6px; }
    QListView::item:selected { background: rgba(240,180,60,0.25); color: #FFFFFF; }
"""
