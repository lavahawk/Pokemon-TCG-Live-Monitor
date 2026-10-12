import sys, os, types
sys.path.insert(0, '/home/claude/stubs'); import winstubs  # noqa
sys.modules['startup_utils'] = types.ModuleType('startup_utils')
sys.path.insert(0, os.getcwd())
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication([])
import StatsUI as S
S.REQUESTS_AVAILABLE = False  # no network fetches during render
w = S.StatsWindow()
w.resize(1200, 1400)
w.show()
def shoot():
    for i, name in [(0, "stats"), (1, "decks")]:
        w.tab_widget.setCurrentIndex(i); app.processEvents()
        w.grab().save(f"/home/claude/notes/shot_{name}.png")
    print("total:", w.total_games_label.text(), "wr:", w.win_rate_label.text(), "elo:", w.current_elo_label.text(), "best:", w.best_elo_label.text())
    app.quit()
QTimer.singleShot(1500, shoot)
app.exec()
