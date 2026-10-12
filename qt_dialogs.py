"""
Tiny modal dialogs (text prompt / message box) built on PySide6.

Replaces the old tkinter dialogs: the self-contained runtime shipped by the
installer has no tkinter, and Qt is already a dependency. Safe to call from a
process that has no QApplication yet (one is created on demand).
"""


def _app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def ask_string(title, prompt, secret=False):
    """Return the entered text (stripped), or None if cancelled/unavailable."""
    try:
        from PySide6.QtWidgets import QInputDialog, QLineEdit
        _app()
        mode = QLineEdit.EchoMode.Password if secret else QLineEdit.EchoMode.Normal
        text, ok = QInputDialog.getText(None, title, prompt, mode)
        return text.strip() if ok else None
    except Exception:
        return None


def show_message(title, text, error=False):
    try:
        from PySide6.QtWidgets import QMessageBox
        _app()
        (QMessageBox.critical if error else QMessageBox.information)(None, title, text)
    except Exception:
        pass
