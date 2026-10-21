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
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QLabel

    class StatusToast(QLabel):
        """Click-through status line near the bottom of the game window while
        the import drives it (no focus, no clicks: the game keeps both)."""

        def __init__(self):
            super().__init__()
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                                | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput
                                | Qt.WindowType.WindowDoesNotAcceptFocus)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.setStyleSheet("QLabel { background: rgba(16, 22, 32, 0.92); color: white; font-size: 13px;"
                               " padding: 8px 16px; border: 1px solid rgba(74,159,216,0.7); border-radius: 8px; }")
            self._hwnd = None

        def show_over(self, hwnd):
            self._hwnd = hwnd
            self.say("Adding the deck to Pokémon TCG Live… (Esc stops)")
            self.show()

        def say(self, message):
            self.setText(message + ("" if "Esc" in message else "   ·   Esc stops"))
            self.adjustSize()
            try:
                import win32gui
                left, top, right, bottom = win32gui.GetWindowRect(self._hwnd)
                self.move(left + (right - left - self.width()) // 2, bottom - int((bottom - top) * 0.06) - self.height())
            except Exception:
                pass

    return StatusToast


def main(argv):
    from PySide6.QtCore import QObject, Qt, Signal
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                                   QVBoxLayout)
    app = QApplication.instance() or QApplication(argv[:1])
    app.setQuitOnLastWindowClosed(False)  # quits when the dialog finishes (it hides during an import)
    StatusToast = _toast_class()
    try:
        import theme
        theme.install(app)  # the user's theme, like the dashboard
    except Exception:
        pass
    link = argv[1] if len(argv) > 1 else (QGuiApplication.clipboard().text() or "")

    dialog = QDialog()
    dialog.setWindowTitle("Shared deck")
    dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    dialog.setMinimumWidth(380)
    dialog.setStyleSheet("""
        QDialog { background: rgb(18, 24, 34); }
        QLabel { color: rgba(232, 238, 246, 0.95); font-size: 12px; }
        QLabel#title { font-size: 11px; font-weight: 700; letter-spacing: 1px; color: rgba(168, 182, 204, 0.85); }
        QLabel#muted { color: rgba(200, 212, 228, 0.65); font-size: 11px; }
        QLineEdit { background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.14); border-radius: 6px;
                    color: white; padding: 6px 8px; font-size: 14px; font-weight: 600; }
        QPushButton { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.16);
                      border-radius: 6px; color: white; padding: 6px 16px; font-size: 12px; }
        QPushButton:hover { background: rgba(255,255,255,0.14); }
        QPushButton#primary { background: rgba(74,159,216,0.85); border-color: rgba(74,159,216,1); }
        QPushButton#primary:hover { background: rgba(74,159,216,1); }
        QCheckBox { color: rgba(220, 228, 240, 0.9); font-size: 12px; spacing: 8px; }
    """)
    box = QVBoxLayout(dialog)
    box.setContentsMargins(18, 16, 18, 16)
    box.setSpacing(10)
    title = QLabel("SHARED DECK")
    title.setObjectName("title")
    box.addWidget(title)
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
    toast = StatusToast()
    relay.progress.connect(toast.say)

    def finish(saved_note, ok=None, message=""):
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
