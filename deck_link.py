"""
Opens shared deck links (ptcglmonitor://d#...): Windows starts this script
with the link; it shows the deck, and on Import saves it to the app's
decklists, puts the list on the clipboard and - when Pokemon TCG Live is
running - adds it to the game (ptcgl_import: Decks -> Create a deck ->
Import with the rarest prints you own -> the deck's name).

    pythonw deck_link.py "ptcglmonitor://d#a...~Deck name"
    pythonw deck_link.py            (reads a link from the clipboard)

register() adds the ptcglmonitor:// scheme for the current Windows user
(HKCU, no admin); the monitor calls it at start so dev checkouts and installs
both point at their own copy. The installer writes the same keys (and removes
them on uninstall).
"""

import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import deck_share  # noqa: E402

SCHEME_KEY = rf"Software\Classes\{deck_share.SCHEME}"


def _gui_python():
    exe = sys.executable
    candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return candidate if os.path.exists(candidate) else exe


def command_line():
    return f'"{_gui_python()}" "{os.path.join(BASE_DIR, "deck_link.py")}" "%1"'


def register():
    """Point ptcglmonitor:// at this copy (HKCU). Returns True when it wrote."""
    if sys.platform != "win32":
        return False
    import winreg
    command = command_line()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SCHEME_KEY + r"\shell\open\command") as key:
            if winreg.QueryValueEx(key, "")[0] == command:
                return False
    except OSError:
        pass
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SCHEME_KEY) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "URL:Pokemon TCG Live Monitor deck link")
        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
    icon = os.path.join(BASE_DIR, "icon.ico")
    if os.path.exists(icon):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SCHEME_KEY + r"\DefaultIcon") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{icon}",0')
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, SCHEME_KEY + r"\shell\open\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)
    return True


_box_lock = None


def first_box_for(link):
    """False when an import box for this link is already open (a named
    mutex per link, held until this process ends)."""
    global _box_lock
    if sys.platform != "win32":
        return True
    import ctypes
    import hashlib
    name = "PTCGLMonitorDeckLink_" + hashlib.sha1(link.strip().split("~", 1)[0].encode()).hexdigest()[:16]
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, name)
    if handle and ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        return False
    _box_lock = handle
    return True


def import_list(text, name):
    """Save to the app's decklists (named `name` when it's new) and link it
    to the deck called `name`, so that deck's page in the monitor shows the
    list as soon as you play it. Returns (entry, already_had)."""
    import decklists
    entry = decklists.save_decklist(text)
    if entry.get("new") and name:
        try:
            decklists.rename_decklist(entry["id"], name)
            entry["name"] = name
        except Exception:
            pass
    if name:
        try:
            decklists.link_decklist(name, entry["id"])
        except Exception:
            pass
    return entry, not entry.get("new")


# The importer's steps and how far along each one is (for the progress bar).
STEP_PROGRESS = (("Waiting", 0.08), ("Leaving", 0.12), ("Opening Decks", 0.2), ("Creating", 0.38),
                 ("Choosing", 0.55), ("Importing", 0.72), ("Naming", 0.88))


def step_progress(message, current=0.0):
    """Progress (0-1) after the importer says `message`; never goes back."""
    for prefix, value in STEP_PROGRESS:
        if message.startswith(prefix):
            return max(current, value)
    return current


def fade(widget, start, end, ms, then=None):
    """Animate a window's opacity (Qt's own windows only; the game is never touched)."""
    from PySide6.QtCore import QEasingCurve, QVariantAnimation
    animation = QVariantAnimation(widget)
    animation.setStartValue(float(start))
    animation.setEndValue(float(end))
    animation.setDuration(ms)
    animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    animation.valueChanged.connect(lambda value: widget.setWindowOpacity(float(value)))
    if then is not None:
        animation.finished.connect(then)
    widget.setWindowOpacity(float(start))
    animation.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)
    return animation


def _toast_class():
    import ctypes
    from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
    from PySide6.QtGui import QColor, QPainter
    from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    FLAGS = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
             | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)

    def prepare(widget):
        widget.setWindowFlags(FLAGS)
        widget.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def place(widget, x, y, w, h):
        """Physical pixels (this process is per-monitor DPI aware), so it
        lines up with the game at any Windows scaling."""
        HWND_TOPMOST, SWP_NOACTIVATE, SWP_SHOWWINDOW = -1, 0x0010, 0x0040
        user32.SetWindowPos(ctypes.c_void_p(int(widget.winId())), ctypes.c_void_p(HWND_TOPMOST),
                            int(x), int(y), int(w), int(h), SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def exclude_from_capture(widget):
        """Hide from screen capture (Windows 10 2004+), so the import's OCR
        still sees the game. Needs a plain window: per-pixel transparency
        (WA_TranslucentBackground) is refused, whole-window opacity is fine."""
        return bool(user32.SetWindowDisplayAffinity(ctypes.c_void_p(int(widget.winId())), 0x11))

    class Dim(QWidget):
        def paintEvent(self, _event):
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(6, 8, 12))
            painter.end()

    class Progress(QWidget):
        """A thin bar that glides to each step's value."""

        def __init__(self):
            super().__init__()
            self.setFixedHeight(4)
            self.value = 0.0
            self._animation = QVariantAnimation(self)
            self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._animation.valueChanged.connect(self._set)

        def _set(self, value):
            self.value = float(value)
            self.update()

        def glide(self, target, ms=520):
            self._animation.stop()
            self._animation.setStartValue(self.value)
            self._animation.setEndValue(float(target))
            self._animation.setDuration(ms)
            self._animation.start()

        def paintEvent(self, _event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 22))
            painter.drawRoundedRect(QRectF(self.rect()), 2, 2)
            if self.value > 0:
                painter.setBrush(QColor(74, 159, 216))
                painter.drawRoundedRect(QRectF(0, 0, self.width() * min(1.0, self.value), self.height()), 2, 2)
            painter.end()

    class ImportShade:
        """While the import drives the game: the game dimmed, and a card with
        "Importing… please don't use the mouse or keyboard" and the current
        step. Both windows are click-through and focus-less (the game keeps
        every click and key) and excluded from screen capture. Where that
        isn't available, ptcgl_import hides them for each capture instead."""

        def __init__(self, deck_name=""):
            self.dim = Dim()
            prepare(self.dim)
            self.dim.setWindowOpacity(0.45)
            self.card = QWidget()
            prepare(self.card)
            self.card.setWindowOpacity(0.96)
            self.card.setObjectName("shadeCard")
            self.card.setStyleSheet(
                "QWidget#shadeCard { background: rgb(14, 18, 26); border: 1px solid rgba(74,159,216,0.8); }"
                "QLabel { background: transparent; color: rgba(232,238,246,0.96); }"
                "QLabel#shadeTitle { font-size: 11px; font-weight: 700; letter-spacing: 2px;"
                " color: rgba(168,182,204,0.9); }"
                "QLabel#shadeName { font-size: 18px; font-weight: 700; }"
                "QLabel#shadeStep { font-size: 13px; color: rgb(116,186,236); }"
                "QLabel#shadeHint { font-size: 12px; color: rgba(200,212,228,0.75); }")
            box = QVBoxLayout(self.card)
            box.setContentsMargins(24, 18, 24, 18)
            box.setSpacing(6)
            title = QLabel("IMPORTING INTO POKÉMON TCG LIVE")
            title.setObjectName("shadeTitle")
            name = QLabel(deck_name or "Shared deck")
            name.setObjectName("shadeName")
            self.step = QLabel("Saved to the monitor · opening Pokémon TCG Live…")
            self.step.setObjectName("shadeStep")
            self._step_fx = QGraphicsOpacityEffect(self.step)
            self._step_fx.setOpacity(1.0)
            self.step.setGraphicsEffect(self._step_fx)
            self._step_fade = QVariantAnimation(self.card)
            self._step_fade.valueChanged.connect(lambda v: self._step_fx.setOpacity(float(v)))
            self._after_fade = None
            self._step_fade.finished.connect(self._faded)
            self._next_step = None
            self.bar = Progress()
            self.bar.value = 0.04
            hint = QLabel("Please don't use the mouse or keyboard until it's done  ·  Esc stops")
            hint.setObjectName("shadeHint")
            for widget in (title, name, self.step):
                box.addWidget(widget)
            box.addSpacing(4)
            box.addWidget(self.bar)
            box.addSpacing(2)
            box.addWidget(hint)
            self.card.setMinimumWidth(460)  # steps change length; the card shouldn't jump
            self._hwnd = None

        def show_over(self, hwnd):
            import ptcgl_import
            self._hwnd = hwnd
            for widget in (self.dim, self.card):
                widget.setWindowOpacity(0.0)
                widget.show()
                if not exclude_from_capture(widget):
                    ptcgl_import.hide_during_capture(int(widget.winId()))
            self._place()
            fade(self.dim, 0.0, 0.45, 260)
            fade(self.card, 0.0, 0.96, 320)

        def _place(self):
            try:
                import win32gui
                _l, _t, w, h = win32gui.GetClientRect(self._hwnd)
                x, y = win32gui.ClientToScreen(self._hwnd, (0, 0))
            except Exception:
                return
            place(self.dim, x, y, w, h)
            ratio = self.card.devicePixelRatioF() or 1.0
            hint = self.card.sizeHint()
            cw, ch = int(hint.width() * ratio), int(hint.height() * ratio)
            place(self.card, x + (w - cw) // 2, y + (h - ch) // 2, cw, ch)

        def say(self, message, progress=None, ms=520):
            """Cross-fade to the next step and move the bar along."""
            self.bar.glide(step_progress(message, self.bar.value) if progress is None else progress, ms)
            self._next_step = message
            if self._step_fade.state() == QVariantAnimation.State.Running:
                return  # the running fade picks up the newest message
            self._fade_step(1.0, 0.0, 110, self._swap_step)

        def _fade_step(self, start, end, ms, then=None):
            self._step_fade.stop()
            self._after_fade = then
            self._step_fade.setStartValue(start)
            self._step_fade.setEndValue(end)
            self._step_fade.setDuration(ms)
            self._step_fade.start()

        def _faded(self):
            then, self._after_fade = self._after_fade, None
            if then is not None:
                then()

        def _swap_step(self):
            self.step.setText(self._next_step or "")
            self._place()  # a long message can widen the card
            self._fade_step(0.0, 1.0, 170)

        def finish(self, ok, message, then):
            """Fill the bar, show the outcome for a moment, then fade away."""
            self.step.setStyleSheet("" if ok else "color: rgb(239,143,143);")
            self.say("Done" if ok else (message or "Stopped"), 1.0 if ok else self.bar.value, 300)

            def away():
                fade(self.dim, self.dim.windowOpacity(), 0.0, 260)
                fade(self.card, self.card.windowOpacity(), 0.0, 260, lambda: (self.hide(), then()))
            from PySide6.QtCore import QTimer
            QTimer.singleShot(650 if ok else 1100, away)

        def hide(self):
            import ptcgl_import
            for widget in (self.dim, self.card):
                ptcgl_import.hide_during_capture(int(widget.winId()), remove=True)
                widget.hide()

    return ImportShade


def main(argv):
    from PySide6.QtCore import QObject, Qt, Signal
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                                   QVBoxLayout)
    app = QApplication.instance() or QApplication(argv[:1])
    app.setQuitOnLastWindowClosed(False)  # quits when the dialog finishes (it hides during an import)
    ImportShade = _toast_class()
    try:
        import theme
        theme.install(app)  # the user's theme, like the dashboard
    except Exception:
        pass
    link = argv[1] if len(argv) > 1 else (QGuiApplication.clipboard().text() or "")
    if not first_box_for(link):
        return 0  # this deck's box is already open (copied and clicked, say)
    deck_share.remember_seen(link)  # the clipboard watch won't offer it again

    dialog = QDialog()
    dialog.setWindowTitle("Shared deck")
    dialog.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                          | Qt.WindowType.Dialog)
    dialog.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    dialog.setMinimumWidth(400)
    # Same glass panel, buttons and checkboxes as the dashboard (StatsUI).
    dialog.setStyleSheet("""
        QFrame#glassContainer { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                    stop:0 rgba(15, 15, 15, 0.94), stop:1 rgba(10, 10, 10, 0.96));
                                border: 1px solid rgba(255, 255, 255, 0.10); border-radius: 12px; }
        QLabel { color: rgba(232, 238, 246, 0.95); font-size: 12px; background: transparent; }
        QLabel#title { font-size: 11px; font-weight: 700; letter-spacing: 1px; color: rgba(168, 182, 204, 0.85); }
        QLabel#muted { color: rgba(200, 212, 228, 0.65); font-size: 11px; }
        QLineEdit { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.12); border-radius: 6px;
                    color: white; padding: 7px 9px; font-size: 15px; font-weight: 600;
                    selection-background-color: rgba(74,159,216,0.5); }
        QLineEdit:focus { border-color: rgba(74,159,216,0.7); }
        QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255, 255, 255, 0.06),
                                                  stop:1 rgba(255, 255, 255, 0.02));
                      border: 1px solid rgba(255, 255, 255, 0.10); border-radius: 6px;
                      color: rgba(255, 255, 255, 0.9); padding: 6px 18px; font-size: 12px; }
        QPushButton:hover { background: rgba(255, 255, 255, 0.10); border-color: rgba(255, 255, 255, 0.18); }
        QPushButton#primary { background: rgba(74,159,216,0.75); border-color: rgba(74,159,216,0.9); color: white;
                              font-weight: 600; }
        QPushButton#primary:hover { background: rgba(74,159,216,0.95); }
        QPushButton#close { background: transparent; border: none; color: rgba(200,212,228,0.6); padding: 0;
                            font-size: 14px; }
        QPushButton#close:hover { color: white; }
        QCheckBox { color: rgba(235,242,250,0.88); font-size: 12px; spacing: 8px; background: transparent; }
        QCheckBox:disabled { color: rgba(235,242,250,0.38); }
        QCheckBox::indicator { width: 14px; height: 14px; border-radius: 4px;
                               border: 1px solid rgba(255,255,255,0.18); background: rgba(255,255,255,0.05); }
        QCheckBox::indicator:checked { background: rgba(74,159,216,0.75); border-color: rgba(74,159,216,0.85); }
        QCheckBox::indicator:disabled { border-color: rgba(255,255,255,0.08); }
    """)
    from PySide6.QtWidgets import QFrame
    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    panel = QFrame()
    panel.setObjectName("glassContainer")
    outer.addWidget(panel)
    box = QVBoxLayout(panel)
    box.setContentsMargins(20, 14, 16, 18)
    box.setSpacing(10)
    head = QHBoxLayout()
    title = QLabel("SHARED DECK")
    title.setObjectName("title")
    head.addWidget(title)
    head.addStretch()
    close_x = QPushButton("✕")
    close_x.setObjectName("close")
    close_x.setFixedSize(22, 22)
    close_x.setCursor(Qt.CursorShape.PointingHandCursor)
    close_x.clicked.connect(dialog.reject)
    head.addWidget(close_x)
    box.addLayout(head)

    class _Drag(QObject):
        """Move the frameless box by dragging anywhere on its background."""

        def eventFilter(self, obj, event):
            from PySide6.QtCore import QEvent
            kind = event.type()
            if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self.offset = event.globalPosition().toPoint() - dialog.frameGeometry().topLeft()
            elif kind == QEvent.Type.MouseMove and getattr(self, "offset", None) is not None \
                    and event.buttons() & Qt.MouseButton.LeftButton:
                dialog.move(event.globalPosition().toPoint() - self.offset)
            elif kind == QEvent.Type.MouseButtonRelease:
                self.offset = None
            return False

    drag = _Drag(dialog)
    panel.installEventFilter(drag)
    title.installEventFilter(drag)
    buttons = QHBoxLayout()
    buttons.addStretch()

    try:
        text, name = deck_share.parse(link)
    except deck_share.ShareError as exc:
        message = QLabel(f"This link can't be opened: {exc}.")
        message.setWordWrap(True)
        box.addWidget(message)
        close = QPushButton("Close")
        close.clicked.connect(dialog.reject)
        buttons.addWidget(close)
        box.addLayout(buttons)
        dialog.exec()
        return 1

    import decklists
    name_field = QLineEdit(name or decklists.auto_name(text))
    name_field.setMaxLength(deck_share.MAX_NAME)
    box.addWidget(name_field)
    import game_window
    from edition import APP_NAME
    game_open = bool(game_window.find_game_hwnd())
    to_game = QCheckBox("Add it to Pokémon TCG Live")
    to_game.setChecked(game_open)
    to_game.setEnabled(game_open)
    to_game.setToolTip("Creates the deck in the game under this name, with the rarest prints you own"
                       if game_open else "Open Pokémon TCG Live to add it there too")
    box.addWidget(to_game)
    to_app = QCheckBox(f"Add it to {APP_NAME}")
    to_app.setChecked(True)
    to_app.setToolTip("Saves the list to your decklists under this name")
    box.addWidget(to_app)
    status = QLabel("")
    status.setWordWrap(True)
    status.hide()
    box.addWidget(status)
    cancel = QPushButton("Cancel")
    cancel.clicked.connect(dialog.reject)
    primary = QPushButton("Import")
    primary.setObjectName("primary")
    primary.setDefault(True)

    class Relay(QObject):
        progress = Signal(str)
        finished = Signal(bool, str)

    relay = Relay()
    toast = None

    MANUAL = "The list is on your clipboard: in Pokémon TCG Live open Decks → Create a deck → Import."

    def finish(monitor_line, ok=None, message=""):
        """The box comes back with one line per place the deck went."""
        import html
        if ok is None:
            game_line = MANUAL
        elif ok:
            game_line = message.replace("Imported into Pokémon TCG Live", "imported")
        else:
            game_line = f"{message} {MANUAL}"
        status.setText(f"<b>{APP_NAME}:</b> {html.escape(monitor_line)}<br>"
                       f"<b>Pokémon TCG Live:</b> {html.escape(game_line)}")
        status.show()
        for widget in (name_field, to_game, to_app):
            widget.setEnabled(False)
        cancel.hide()
        primary.setText("Done")
        primary.setEnabled(True)
        dialog.adjustSize()
        if not dialog.isVisible():
            dialog.setWindowOpacity(0.0)
            dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        fade(dialog, dialog.windowOpacity(), 1.0, 220)

    def do_import():
        nonlocal toast
        if primary.text() == "Done":
            fade(dialog, 1.0, 0.0, 160, dialog.accept)
            return
        deck_name = name_field.text().strip()
        if to_app.isChecked():
            entry, had = import_list(text, deck_name)
            monitor_line = (f"you already had this list, as {entry['name']}." if had
                            else f"saved as {entry['name']}.") + (
                                f" Its deck page shows it once you play {deck_name}." if deck_name else "")
        else:
            monitor_line = "not added."
        QGuiApplication.clipboard().setText(text)
        if not (to_game.isChecked() and game_window.find_game_hwnd()):
            finish(monitor_line)
            return
        import threading
        import ptcgl_import
        primary.setEnabled(False)
        toast = ImportShade(deck_name)
        relay.progress.connect(toast.say)
        relay.finished.connect(lambda ok, message: toast.finish(ok, message,
                                                                lambda: finish(monitor_line, ok, message)))
        importer = ptcgl_import.PTCGLImporter(text, deck_name or None, status=relay.progress.emit)

        def start():
            dialog.hide()  # out of the way of the clicks
            toast.show_over(game_window.find_game_hwnd())
            threading.Thread(target=lambda: relay.finished.emit(*importer.run()), daemon=True).start()
        fade(dialog, 1.0, 0.0, 180, start)

    primary.clicked.connect(do_import)

    def can_import():  # nothing to do with both boxes off
        primary.setEnabled(to_app.isChecked() or (to_game.isChecked() and to_game.isEnabled()))
    to_app.toggled.connect(can_import)
    to_game.toggled.connect(can_import)
    can_import()
    buttons.addWidget(cancel)
    buttons.addWidget(primary)
    box.addLayout(buttons)
    dialog.setWindowOpacity(0.0)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    fade(dialog, 0.0, 1.0, 220)
    # The app's loop, not dialog.exec(): the dialog hides while the import
    # drives the game, and hiding would end exec() (and this process).
    outcome = {}
    dialog.finished.connect(lambda result: (outcome.setdefault("result", result), app.quit()))
    app.exec()
    return 0 if outcome.get("result") else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--register":
        print("registered" if register() else "already registered")
        sys.exit(0)
    sys.exit(main(sys.argv))
