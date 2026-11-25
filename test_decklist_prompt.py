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
    _game_is_foreground = staticmethod(lambda: FakeHud.from_game)
    _update_action = OverlayUI.MinimalOverlay._update_action
    _update_deck_from_clipboard = OverlayUI.MinimalOverlay._update_deck_from_clipboard
    _hud_anchor = OverlayUI.MinimalOverlay._hud_anchor
    db = None
    picked = []

    def _pick_deck_to_update(self, text):
        FakeHud.picked.append(text)
    from_game = True
    opened = []

    def _open_deck_import(self, text):
        FakeHud.opened.append(text)

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


def test_copied_elsewhere_opens_the_import_box():
    """A new list copied outside the game: Import opens the shared-deck box
    (into the game and the Decks tab). One you already have never asks."""
    FakeHud.from_game = False
    try:
        hud = FakeHud()
        hud.show()
        QApplication.clipboard().setText(DRAGAPULT)      # saved by the first test
        hud._on_clipboard_changed()
        assert hud._pending_decklist is None
        reordered = "\n".join(reversed(DRAGAPULT.strip().splitlines()))
        QApplication.clipboard().setText(reordered)       # same cards, another order
        hud._on_clipboard_changed()
        assert hud._pending_decklist is None or not D.is_ptcgl_decklist(reordered)
        new_list = DRAGAPULT.replace("Pokémon:", "Pokémon:\n1 Fezandipiti ex SFA 38", 1)
        QApplication.clipboard().setText(new_list)
        hud._on_clipboard_changed()
        assert hud._pending_decklist
        hud._poll_decklist_card((600, 380))
        from PySide6.QtWidgets import QPushButton
        btn = next(b for b in hud._decklist_card.findChildren(QPushButton) if b.text() == "Import")
        btn.click()
        assert FakeHud.opened and D.is_ptcgl_decklist(FakeHud.opened[-1])
        # once you've imported it, copying it again doesn't ask
        D.save_decklist(new_list)
        hud._pending_decklist = None
        hud._on_clipboard_changed()
        assert hud._pending_decklist is None
    finally:
        FakeHud.from_game = True


def test_update_a_deck_instead():
    """A new version of one of your decks: the card's second button updates
    the closest deck; with no close deck it opens the picker."""
    from PySide6.QtWidgets import QPushButton
    base = D.save_decklist(DRAGAPULT)
    D.link_decklist("Pult Hammers", base["id"])
    tweaked = DRAGAPULT.rstrip() + "\n1 Budew PRE 4\n"
    hud = FakeHud()
    hud.show()
    hud._pending_decklist, hud._pending_from_game = tweaked, False
    hud._poll_decklist_card((600, 380))
    update = next(b for b in hud._decklist_card.findChildren(QPushButton) if b.text().startswith("Update"))
    assert update.text() == "Update Pult Hammers"
    update.click()
    assert D.decklist_for_deck("Pult Hammers")["id"] == D.list_id(tweaked)
    assert any("Budew" in l.text() for l in hud._decklist_card.findChildren(OverlayUI.QLabel))   # DECK UPDATED: +1 Budew
    # a list nothing like your decks: pick which deck on the dashboard
    other = "Pokémon: 1\n4 Charmander PAF 7\nTrainer: 1\n4 Arven SVI 166\nEnergy: 1\n10 Basic {R} Energy SVE 2\n"
    hud._decklist_card.close()
    QApplication.processEvents()
    hud._pending_decklist, hud._pending_from_game = other, True
    hud._poll_decklist_card((600, 380))
    pick = next(b for b in hud._decklist_card.findChildren(QPushButton) if b.text().startswith("Update"))
    assert pick.text() == "Update a deck…"
    pick.click()
    assert FakeHud.picked == [other]


def test_link_round_trip():
    import deck_share
    text, _name = deck_share.parse(deck_share.share_url(DRAGAPULT, web=False))
    assert D.list_id(text) == D.list_id(DRAGAPULT)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
