"""Tests for infotip.py (run: python test_infotip.py). Offscreen Qt; the tip
window is created but nothing is shown on a real screen."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QHeaderView, QLabel, QTableWidget, QTableWidgetItem

import infotip as I

app = QApplication.instance() or QApplication([])
I.HINTS_FILE = os.path.join(os.environ.get("TEMP", "."), "test_ui_hints.json")


def test_split_marker():
    assert I.split(I.tip("Score 53", "Rank #4<br>formula")) == ("Score 53", "Rank #4<br>formula")
    assert I.split("Short tip") == ("Short tip", "")


def test_long_tip_without_marker_splits_at_first_break():
    text = "<b>Headline</b><br>" + " ".join(["word"] * 20)
    head, more = I.split(text)
    assert head == "<b>Headline</b>" and more.startswith("word")
    # short two-liners stay whole
    assert I.split("A<br>B c")[1] == ""


def test_whole_tip_is_never_split():
    text = "<b>Headline</b><br>" + " ".join(["word"] * 20)
    assert I.split(I.whole(text)) == (text, "")


def test_plain_newlines_become_breaks():
    head, more = I.split("Opponents:\n" + "\n".join(f"Player number {i}" for i in range(8)))
    assert head == "Opponents:" and "<br>" in more


def test_show_expand_hide():
    label = QLabel("x")
    label.resize(100, 20)
    label.show()
    tip = I._instance()
    I.show_text(QPoint(10, 10), I.tip("Summary", "Details here"), label)
    assert tip.isVisible() and tip.has_more and not tip.expanded
    assert tip.details.maximumHeight() == 0
    tip.expand()
    tip._grow.setCurrentTime(I.EXPAND_MS)
    assert tip.expanded and tip.details.maximumHeight() > 0
    I.hide_text()
    assert not tip.isVisible()


def test_right_click_cycle_expand_pin_close():
    label = QLabel("x")
    label.show()
    tip = I._instance()
    I.show_text(QPoint(10, 10), I.tip("Summary", "Details"), label)
    assert not tip.cue.isHidden()
    assert tip.advance() and tip.expanded and not tip.pinned and tip.cue.isHidden()
    assert tip.advance() and tip.pinned
    I.hide_text()  # widgets' own hide calls leave a pinned tip alone
    assert tip.isVisible()
    I.show_text(QPoint(10, 10), "Another tip", label)
    assert tip.text != "Another tip"
    assert tip.advance() and not tip.isVisible()
    I.show_text(QPoint(10, 10), "Short", label)
    assert not tip.advance()  # nothing more: the right-click goes to the widget
    I.hide_text()


def test_tip_shrinks_to_new_content():
    label = QLabel("x")
    label.show()
    tip = I._instance()
    I.show_text(QPoint(10, 10), I.tip("Summary", "<br>".join(["long details line"] * 20)), label)
    tip.expand()
    tip._grow.setCurrentTime(I.EXPAND_MS)
    big = tip.height()
    I.hide_text()
    I.show_text(QPoint(10, 10), "Short", label)
    assert tip.height() < big / 3
    I.hide_text()


def test_no_details_no_line():
    label = QLabel("x")
    label.show()
    I.show_text(QPoint(10, 10), "Only a summary", label)
    tip = I._instance()
    assert not tip.has_more and tip.line.isHidden() and tip.cue.isHidden()
    tip.expand()
    assert not tip.expanded
    I.hide_text()


def test_width_capped():
    label = QLabel("x")
    label.show()
    I.show_text(QPoint(10, 10), "word " * 200, label)
    assert I._instance().summary.width() <= I.MAX_WIDTH
    I.hide_text()


def test_lookup_header_and_cell():
    table = QTableWidget(2, 2)
    table.setHorizontalHeaderLabels(["A", "B"])
    table.horizontalHeaderItem(1).setToolTip("Header B tip")
    item = QTableWidgetItem("v")
    item.setToolTip("Cell tip")
    table.setItem(0, 0, item)
    table.resize(300, 200)
    table.show()
    app.processEvents()
    header = table.horizontalHeader()
    x = header.sectionViewportPosition(1) + 3
    text, rect = I.lookup(header.viewport(), QPoint(x, 3))
    assert text == "Header B tip" and rect.contains(QPoint(x, 3))
    cell = table.visualItemRect(item).center()
    text, rect = I.lookup(table.viewport(), cell)
    assert text == "Cell tip"
    assert I.lookup(table.viewport(), table.visualRect(table.model().index(1, 1)).center()) is None


def test_hint_label_limit():
    if os.path.exists(I.HINTS_FILE):
        os.remove(I.HINTS_FILE)
    for _ in range(3):
        hint = I.HintLabel("Drag to zoom", "test_zoom", limit=3)
        assert hint.is_new()
        hint.reveal()
        assert hint._shown
        hint.used()
    hint = I.HintLabel("Drag to zoom", "test_zoom", limit=3)
    assert not hint.is_new()
    hint.reveal()
    assert not hint._shown
    hint.reveal(always=True)  # stuck: still shown
    assert hint._shown
    os.remove(I.HINTS_FILE)


if __name__ == "__main__":
    failures = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    sys.exit(1 if failures else 0)
