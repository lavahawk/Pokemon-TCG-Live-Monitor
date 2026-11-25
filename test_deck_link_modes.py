"""deck_link.py's ways in (run: python test_deck_link_modes.py): --to-game
(from the dashboard panel: straight into the game, nothing saved again) and
the shared-deck box updating one of your decks. Temp store; the game importer
is a stand-in, nothing is clicked in Pokémon TCG Live."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import decklists as D  # noqa: E402

D.STORE_FILE = os.path.join(tempfile.mkdtemp(prefix="ptcgl_test_link_modes_"), ".decklists.json")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QPushButton  # noqa: E402
app = QApplication.instance() or QApplication([])
import deck_link  # noqa: E402
import deck_share  # noqa: E402
import game_window  # noqa: E402
import ptcgl_import  # noqa: E402

from test_decklists import DRAGAPULT as SIXTY  # noqa: E402  (a full 60-card export)
D.STORE_FILE = os.path.join(tempfile.mkdtemp(prefix="ptcgl_test_link_modes_"), ".decklists.json")
NEWER = SIXTY.replace("25 Professor's Research", "24 Professor's Research").replace(
    "4 Ultra Ball MEG 131", "4 Ultra Ball MEG 131\n1 Iono PAF 80")
imported = []


class FakeImporter:
    def __init__(self, text, name=None, status=None, **_kw):
        self.text, self.name = text, name

    def run(self):
        imported.append((self.name, D.list_id(self.text)))
        return True, f"Imported into Pokémon TCG Live as {self.name}."


ptcgl_import.PTCGLImporter = FakeImporter
game_window.find_game_hwnd = lambda: 1234
deck_link.first_box_for = lambda link: True
deck_share.remember_seen = lambda link: None


def visible_dialog():
    return next((w for w in app.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible()), None)


def run(argv, during=None, wait_ms=2500):
    """main() with a timer that does `during(dialog)` and then closes it."""
    seen = {}

    def step():
        dialog = visible_dialog()
        seen["dialog"] = dialog
        if during and dialog is not None:
            during(dialog)
        QTimer.singleShot(wait_ms, lambda: [w.reject() for w in app.topLevelWidgets()
                                            if isinstance(w, QDialog) and w.isVisible()] or app.quit())
    QTimer.singleShot(400, step)
    QTimer.singleShot(12000, app.quit)
    deck_link.main(argv)
    return seen


def test_to_game_skips_the_box_and_saves_nothing_again():
    imported.clear()
    link = deck_share.share_url(SIXTY, "Pult", web=False)
    seen = run(["deck_link.py", link, "--to-game"])
    assert seen["dialog"] is None                # no box first: straight to the game
    assert imported == [("Pult", D.list_id(SIXTY))]
    assert D.all_decklists() == []               # the dashboard saved it, not this


def test_box_can_update_one_of_your_decks():
    imported.clear()
    D.import_decklist(SIXTY, "Pult Hammers")
    link = deck_share.share_url(NEWER, "Friend's list", web=False)

    def choose_update(dialog):
        combo = dialog.findChild(QComboBox)
        assert combo.currentIndex() == 0                     # Add as a new deck stays the default
        assert "closest match" in combo.itemText(1)
        combo.setCurrentIndex(1)
        button = next(b for b in dialog.findChildren(QPushButton) if b.text() == "Update")
        button.click()
    run(["deck_link.py", link, "--from-clipboard"], choose_update)
    assert D.decklist_for_deck("Pult Hammers")["id"] == D.list_id(NEWER)
    assert imported and imported[-1][0] == "Pult Hammers"   # the new version also went to the game


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
