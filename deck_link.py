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


def section_counts(text):
    """{"Pokémon": 19, ...}: copies per section (the export's headings count lines)."""
    import decklists
    counts = {}
    for line in decklists.list_lines(text):
        counts[line["section"]] = counts.get(line["section"], 0) + line["qty"]
    return counts


def import_list(text, name):
    """Save to the app's decklists (named `name` when it's new) and copy the
    list. Returns (entry, already_had)."""
    import decklists
    entry = decklists.save_decklist(text)
    if entry.get("new") and name:
        try:
            decklists.rename_decklist(entry["id"], name)
            entry["name"] = name
        except Exception:
            pass
    return entry, not entry.get("new")


def _toast_class():
    import ctypes
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

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
            self.step = QLabel("Starting…")
            self.step.setObjectName("shadeStep")
            hint = QLabel("Please don't use the mouse or keyboard until it's done  ·  Esc stops")
            hint.setObjectName("shadeHint")
            for label in (title, name, self.step, hint):
                box.addWidget(label)
            self._hwnd = None

        def show_over(self, hwnd):
            import ptcgl_import
            self._hwnd = hwnd
            for widget in (self.dim, self.card):
                widget.show()
                if not exclude_from_capture(widget):
                    ptcgl_import.hide_during_capture(int(widget.winId()))
            self._place()

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

        def say(self, message):
            self.step.setText(message)
            self._place()

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
    counts = section_counts(text)
    summary = QLabel(" · ".join(f"{counts.get(s, 0)} {s}" for s in deck_share.SECTIONS)
                     + f" · {decklists.card_count(text)} cards")
    summary.setObjectName("muted")
    summary.setToolTip(text.replace("\n", "<br>"))
    box.addWidget(summary)
    import game_window
    game_open = bool(game_window.find_game_hwnd())
    to_game = QCheckBox("Add it to Pokémon TCG Live")
    to_game.setChecked(game_open)
    to_game.setEnabled(game_open)
    to_game.setToolTip("Creates the deck in the game with the rarest prints you own. Esc stops it."
                       if game_open else "Open Pokémon TCG Live to add it there too")
    box.addWidget(to_game)
    rename = QCheckBox("Use this name in the game")
    rename.setChecked(game_open)
    rename.setEnabled(game_open)
    to_game.toggled.connect(rename.setEnabled)
    box.addWidget(rename)
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

    def finish(saved_note, ok=None, message=""):
        if toast is not None:
            toast.hide()
        if ok is None:
            text_out = saved_note + "The list is on your clipboard: in PTCGL open Decks → Create a deck → Import."
        elif ok:
            text_out = saved_note + message
        else:
            text_out = (saved_note + message + " The list is on your clipboard: in PTCGL open Decks → "
                        "Create a deck → Import.")
        status.setText(text_out)
        status.show()
        for widget in (name_field, to_game, rename):
            widget.setEnabled(False)
        cancel.hide()
        primary.setText("Done")
        primary.setEnabled(True)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.adjustSize()

    def do_import():
        nonlocal toast
        if primary.text() == "Done":
            dialog.accept()
            return
        deck_name = name_field.text().strip()
        entry, had = import_list(text, deck_name)
        QGuiApplication.clipboard().setText(text)
        saved_note = f"You already had this list ({entry['name']}). " if had else "Saved to your decklists. "
        if not (to_game.isChecked() and game_window.find_game_hwnd()):
            finish(saved_note)
            return
        import threading
        import ptcgl_import
        primary.setEnabled(False)
        dialog.hide()  # out of the way of the clicks
        toast = ImportShade(deck_name)
        relay.progress.connect(toast.say)
        toast.show_over(game_window.find_game_hwnd())
        relay.finished.connect(lambda ok, message: finish(saved_note, ok, message))
        importer = ptcgl_import.PTCGLImporter(text, deck_name if rename.isChecked() else None,
                                              status=relay.progress.emit)
        threading.Thread(target=lambda: relay.finished.emit(*importer.run()), daemon=True).start()

    primary.clicked.connect(do_import)
    buttons.addWidget(cancel)
    buttons.addWidget(primary)
    box.addLayout(buttons)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
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
