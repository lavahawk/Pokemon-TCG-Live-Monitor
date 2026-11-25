"""The dashboard's Import decklist panel (StatsUI._import_decklist_dialog),
every path: new deck / update, app / game / both / neither, the same list,
a deck page's own import, Update list's waiting pill, the 60-card warning.
Temp decklist store; the game and the importer are stand-ins (nothing is
clicked in Pokémon TCG Live). Run: python test_import_panel.py"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import decklists as D  # noqa: E402

TMP = tempfile.mkdtemp(prefix="ptcgl_test_import_panel_")
D.STORE_FILE = os.path.join(TMP, ".decklists.json")

from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QLineEdit, QPushButton, QWidget  # noqa: E402
app = QApplication.instance() or QApplication([])
import StatsUI  # noqa: E402
import game_window  # noqa: E402

from test_decklists import DRAGAPULT as SIXTY  # noqa: E402  (a full 60-card export)
D.STORE_FILE = os.path.join(TMP, ".decklists.json")
NEWER = SIXTY.replace("25 Professor's Research", "24 Professor's Research").replace(
    "4 Ultra Ball MEG 131", "4 Ultra Ball MEG 131\n1 Iono PAF 80")
OTHER = ("Pokémon: 2\n4 Charmander PAF 7\n3 Charmeleon PAF 8\nTrainer: 2\n4 Arven SVI 166\n39 Iono PAF 80\n"
         "Energy: 1\n10 Basic {R} Energy SVE 2\n")

launched = []
subprocess.Popen = lambda args, **kw: launched.append(list(args))   # the game importer, not run


class Db:
    def get_known_deck_names(self):
        return ["Pult Hammers", "Charizard"]


class Win(QWidget):
    _import_decklist_dialog = StatsUI.StatsWindow._import_decklist_dialog
    _start_deck_import_mode = lambda self: None

    def __init__(self):
        super().__init__()
        self.db = Db()
        self.refreshed = 0
        self.minimized = 0
        self.restored = 0
        self._glass_panels = []

    def _refresh_deck_dashboards(self):
        self.refreshed += 1

    def minimize_to_overlay(self):
        self.minimized += 1

    def _restore_dashboard(self):
        self.restored += 1


def reset(game_open=True):
    if os.path.exists(D.STORE_FILE):
        os.remove(D.STORE_FILE)
    launched.clear()
    game_window.find_game_hwnd = (lambda: 1234) if game_open else (lambda: None)
    QApplication.clipboard().setText("")
    for _ in range(3):
        app.processEvents()


def panel_of(win):
    return win._decklist_panel


def widgets(panel):
    buttons = {b.text(): b for b in panel.findChildren(QPushButton)}
    boxes = {b.text(): b for b in panel.findChildren(QCheckBox)}
    cards = {c.title.text(): c for c in panel.findChildren(StatsUI.ChoiceCard)}
    return buttons, boxes, cards


def labels(panel):
    return " | ".join(l.text() for l in panel.findChildren(QLabel) if l.isVisibleTo(panel))


def primary(panel):
    return next(b for b in panel.findChildren(QPushButton) if b.objectName() == "primary")


def close(win):
    panel_of(win).close()
    for _ in range(3):
        app.processEvents()


def test_new_deck_into_the_app_only():
    reset()
    win = Win()
    win._import_decklist_dialog(None, preset_text=SIXTY)
    panel = panel_of(win)
    _buttons, boxes, cards = widgets(panel)
    assert cards["New deck"].isChecked() and not cards["Update one of your decks"].isChecked()
    boxes["Add it to Pokémon TCG Live"].setChecked(False)
    name = panel.findChild(QLineEdit)
    name.setText("Pult Test Deck Name Too Long For Game")
    assert len(name.text()) == D.GAME_NAME_MAX
    primary(panel).click()
    assert D.decklist_for_deck(name.text()) is not None and launched == []
    assert primary(panel).text() == "Done" and "imported" in labels(panel)
    close(win)


def test_new_deck_into_both():
    reset()
    win = Win()
    win._import_decklist_dialog(None, preset_text=SIXTY)
    panel = panel_of(win)
    panel.findChild(QLineEdit).setText("Pult")
    primary(panel).click()
    assert D.decklist_for_deck("Pult") is not None          # saved in the app
    assert launched and launched[0][-1] == "--to-game"      # and sent to the game
    assert "Pult" in launched[0][-2]                         # under its name
    assert win.minimized == 1                                # the dashboard steps aside


def test_game_only():
    reset()
    win = Win()
    win._import_decklist_dialog(None, preset_text=SIXTY)
    panel = panel_of(win)
    _b, boxes, _c = widgets(panel)
    boxes["Add it to PTCGL Monitor"].setChecked(False)
    primary(panel).click()
    assert D.all_decklists() == [] and len(launched) == 1


def test_neither_can_not_be_pressed():
    reset()
    win = Win()
    win._import_decklist_dialog(None, preset_text=SIXTY)
    panel = panel_of(win)
    _b, boxes, _c = widgets(panel)
    boxes["Add it to PTCGL Monitor"].setChecked(False)
    boxes["Add it to Pokémon TCG Live"].setChecked(False)
    assert not primary(panel).isEnabled()
    close(win)


def test_game_closed_means_app_only():
    reset(game_open=False)
    win = Win()
    win._import_decklist_dialog(None, preset_text=SIXTY)
    panel = panel_of(win)
    _b, boxes, _c = widgets(panel)
    game = boxes["Add it to Pokémon TCG Live"]
    assert not game.isEnabled() and not game.isChecked()
    primary(panel).click()
    assert launched == [] and len(D.all_decklists()) == 1
    close(win)


def test_update_closest_offered_not_chosen_and_previewed():
    reset()
    D.import_decklist(SIXTY, "Pult Hammers")
    D.import_decklist(OTHER, "Charizard")
    win = Win()
    win._import_decklist_dialog(None, preset_text=NEWER)
    panel = panel_of(win)
    _b, boxes, cards = widgets(panel)
    update = cards["Update one of your decks"]
    assert cards["New deck"].isChecked()                          # import stays the default
    assert "Pult Hammers" in update.sub.text()                    # but the closest deck is named
    update.picked.emit()
    assert primary(panel).text() == "Update"
    assert "+1" in labels(panel) and "Iono" in labels(panel)      # what would change, before pressing
    widgets(panel)[1]["Add the new version to Pokémon TCG Live"].setChecked(False)
    primary(panel).click()
    assert D.decklist_for_deck("Pult Hammers")["id"] == D.list_id(NEWER)
    assert D.decklist_for_deck("Charizard")["id"] == D.list_id(OTHER)   # the other deck untouched
    assert "updated" in labels(panel)
    close(win)


def test_update_with_the_same_list_is_refused():
    reset()
    D.import_decklist(SIXTY, "Pult Hammers")
    win = Win()
    win._import_decklist_dialog(None, preset_text=SIXTY.replace("4 Ultra Ball MEG 131", "4 Ultra Ball SVI 196"))
    panel = panel_of(win)
    _b, _boxes, cards = widgets(panel)
    cards["Update one of your decks"].picked.emit()
    # same cards in other prints is a real (print-only) change; the identical list is not
    assert primary(panel).isEnabled()
    close(win)
    win = Win()
    win._import_decklist_dialog(None, preset_text=SIXTY)
    panel = panel_of(win)
    _b, _boxes, cards = widgets(panel)
    cards["Update one of your decks"].picked.emit()
    assert not primary(panel).isEnabled() and "already has" in labels(panel)
    close(win)


def test_sixty_card_warning():
    reset()
    win = Win()
    win._import_decklist_dialog(None, preset_text=SIXTY + "1 Budew PRE 4\n")
    assert "61 cards. A deck needs 60." in labels(panel_of(win))
    close(win)
    win = Win()
    win._import_decklist_dialog(None, preset_text=SIXTY)
    assert "A deck needs 60" not in labels(panel_of(win))
    close(win)


def test_waiting_then_a_copied_list_arrives():
    reset()
    win = Win()
    win.show()
    win._import_decklist_dialog(None)
    panel = panel_of(win)
    assert panel._collapsed and win.minimized == 1                # the pill, dashboard aside
    QApplication.clipboard().setText("not a list")
    app.processEvents()
    assert panel._collapsed                                        # ignored
    QApplication.clipboard().setText(SIXTY)
    for _ in range(5):
        app.processEvents()
    assert not panel._collapsed and primary(panel).isEnabled()     # opened with the list, nothing saved yet
    assert D.all_decklists() == []
    close(win)
    assert win.restored == 1                                       # dashboard back on close


def test_a_deck_pages_own_import_saves_on_arrival():
    reset()
    win = Win()
    win._import_decklist_dialog("Pult Hammers")
    QApplication.clipboard().setText(SIXTY)
    for _ in range(5):
        app.processEvents()
    assert D.decklist_for_deck("Pult Hammers")["id"] == D.list_id(SIXTY) and launched == []
    close(win)


def test_update_list_pill():
    reset()
    D.import_decklist(SIXTY, "Pult Hammers")
    QApplication.clipboard().setText(SIXTY)              # the old list already copied: doesn't count
    for _ in range(3):
        app.processEvents()
    win = Win()
    win.show()
    win._import_decklist_dialog("Pult Hammers", update=True)
    panel = panel_of(win)
    assert panel._collapsed and panel._loader.isVisible()
    QApplication.clipboard().setText(SIXTY)               # copied again unchanged: still waiting
    for _ in range(3):
        app.processEvents()
    assert D.decklist_for_deck("Pult Hammers")["id"] == D.list_id(SIXTY)
    QApplication.clipboard().setText(NEWER)
    for _ in range(3):
        app.processEvents()
    assert D.decklist_for_deck("Pult Hammers")["id"] == D.list_id(NEWER)
    assert "updated" in panel.pill_label.text()
    close(win)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
