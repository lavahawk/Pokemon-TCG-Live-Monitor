"""A decklist copied to the clipboard: the HUD asks whether to import it
(OverlayUI._on_clipboard_changed / _poll_decklist_card). Uses a temp store;
the user's .decklists.json is never touched."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import decklists as D  # noqa: E402

TMP = tempfile.mkdtemp(prefix="ptcgl_test_decklist_prompt_")
D.STORE_FILE = os.path.join(TMP, ".decklists.json")

from test_decklists import DRAGAPULT  # noqa: E402
D.STORE_FILE = os.path.join(TMP, ".decklists.json")   # (test_decklists set its own)

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402
app = QApplication.instance() or QApplication([])
import OverlayUI  # noqa: E402


class FakeHud(QWidget):
    HUD_CARD_ORDER = OverlayUI.MinimalOverlay.HUD_CARD_ORDER
    _hud_card_stack = OverlayUI.MinimalOverlay._hud_card_stack
    _stack_anchor = OverlayUI.MinimalOverlay._stack_anchor
    _on_clipboard_changed = OverlayUI.MinimalOverlay._on_clipboard_changed
    _poll_decklist_card = OverlayUI.MinimalOverlay._poll_decklist_card
    _menu_deck = staticmethod(lambda: "Dragapult ex")

    def __init__(self):
        super().__init__()
        self.stats_window = None
        self._pending_decklist = None
        self._decklist_card = None
        self.resize(200, 40)
        self.move(400, 400)


def test_asks_then_imports():
    hud = FakeHud()
    hud.show()
    QApplication.clipboard().setText("just some text")
    hud._on_clipboard_changed()
    assert hud._pending_decklist is None
    QApplication.clipboard().setText(DRAGAPULT)
    hud._on_clipboard_changed()
    assert hud._pending_decklist
    assert D.all_decklists() == []          # nothing stored until you say so
    hud._poll_decklist_card((600, 380))
    card = hud._decklist_card
    assert card is not None and card.isVisible() and hud._pending_decklist is None
    from PySide6.QtWidgets import QPushButton
    btn = next(b for b in card.findChildren(QPushButton) if b.text() == "Import")
    btn.click()
    stored = D.all_decklists()
    assert len(stored) == 1 and stored[0]["menu_deck"] == "Dragapult ex"
    # copying the same list again doesn't ask twice
    hud._on_clipboard_changed()
    assert hud._pending_decklist is None


def test_not_while_link_window_open():
    hud = FakeHud()
    hud.show()
    hud.stats_window = type("S", (), {"_decklist_dialog_open": True})()
    QApplication.clipboard().setText(DRAGAPULT.replace("4 Dreepy", "3 Dreepy", 1) if "4 Dreepy" in DRAGAPULT else DRAGAPULT + "\n")
    hud._on_clipboard_changed()
    assert hud._pending_decklist is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
