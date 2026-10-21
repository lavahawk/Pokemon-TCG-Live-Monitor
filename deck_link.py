"""
Opens shared deck links (ptcglmonitor://d#...): Windows starts this script
with the link; it shows the deck, and on Import saves it to the app's
decklists and puts the list on the clipboard, ready for PTCGL's Decks ->
New deck -> Import.

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


def main(argv):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                                   QVBoxLayout)
    app = QApplication.instance() or QApplication(argv[:1])
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
    status = QLabel("")
    status.setWordWrap(True)
    status.hide()
    box.addWidget(status)
    cancel = QPushButton("Cancel")
    cancel.clicked.connect(dialog.reject)
    primary = QPushButton("Import")
    primary.setObjectName("primary")
    primary.setDefault(True)

    def do_import():
        if primary.text() == "Done":
            dialog.accept()
            return
        entry, had = import_list(text, name_field.text().strip())
        QGuiApplication.clipboard().setText(text)
        status.setText((f"You already had this list ({entry['name']}). " if had else "Saved to your decklists. ")
                       + "The list is on your clipboard: in PTCGL open Decks → New deck → Import.")
        status.show()
        name_field.setEnabled(False)
        cancel.hide()
        primary.setText("Done")
        dialog.adjustSize()

    primary.clicked.connect(do_import)
    buttons.addWidget(cancel)
    buttons.addWidget(primary)
    box.addLayout(buttons)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    result = dialog.exec()
    return 0 if result else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--register":
        print("registered" if register() else "already registered")
        sys.exit(0)
    sys.exit(main(sys.argv))
