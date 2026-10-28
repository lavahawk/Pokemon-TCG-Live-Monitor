"""
OCR Bounding Box Debug overlay (Settings): semi-transparent boxes over the
game showing every area the app is reading right now, from ocr_debug.

  green   the check found what it looks for (with its match score)
  red     the check ran and found nothing
  blue    OCR read this area (with the text it read)
  yellow  "Edit boxes" is on: the OCR areas, drag a corner to resize or the
          middle to move; saved to screen_regions.json on release

Normally the window ignores the mouse. In edit mode only the yellow boxes
take it: the rest of the window is fully transparent, so clicks there still
reach the game. The window is excluded from screen capture, so it never
changes what the checks see. Started by the monitor while the game is open
and debug mode is on; exits when it is turned off or the monitor is gone.

Usage: python debug_overlay.py [--parent PID]
"""

import argparse
import sys
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

import ocr_debug

WDA_EXCLUDEFROMCAPTURE = 0x11
HIT = QColor(63, 185, 80)
MISS = QColor(248, 81, 73)
READ = QColor(88, 166, 255)
EDIT = QColor(227, 179, 65)
HANDLE = 9      # corner handle size, logical px
MIN_SIDE = 8    # smallest box, physical px


def box_color(entry):
    if "text" in entry:
        return READ
    if entry.get("hit") is True:
        return HIT
    if entry.get("hit") is False:
        return MISS
    return READ


def box_label(name, entry):
    parts = [name]
    if "score" in entry:
        parts.append(f"{entry['score']:.2f}")
    if entry.get("text"):
        parts.append(f"“{entry['text']}”")
    return "  ".join(parts)


def drag_box(box, corner, dx, dy):
    """box (physical px) after dragging `corner` ("tl", "tr", "bl", "br",
    or "move") by dx, dy; never smaller than MIN_SIDE."""
    l, t = box["left"], box["top"]
    r, b = l + box["width"], t + box["height"]
    if corner == "move":
        l, t, r, b = l + dx, t + dy, r + dx, b + dy
    else:
        if "l" in corner:
            l = min(l + dx, r - MIN_SIDE)
        if "r" in corner:
            r = max(r + dx, l + MIN_SIDE)
        if "t" in corner:
            t = min(t + dy, b - MIN_SIDE)
        if "b" in corner:
            b = max(b + dy, t + MIN_SIDE)
    return {"left": int(l), "top": int(t), "width": int(r - l), "height": int(b - t)}


class DebugOverlay(QWidget):
    def __init__(self, parent_pid=None):
        super().__init__()
        self.parent_pid = parent_pid
        self.boxes = {}
        self.game = None
        self.editing = False
        self.edit_boxes = {}   # name -> physical box, in edit mode
        self.drag = None       # (name, corner, start point, box at start)
        self._set_flags(False)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.font_ = QFont("Segoe UI", 8)
        from game_window import GameWindowCache
        self.window_cache = GameWindowCache(refresh_s=1.0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(100)
        self.checks = 0

    def _set_flags(self, editing):
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.WindowDoesNotAcceptFocus
        if not editing:
            flags |= Qt.WindowTransparentForInput
        self.setWindowFlags(flags)

    def showEvent(self, event):
        super().showEvent(event)
        try:
            import ctypes
            ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), WDA_EXCLUDEFROMCAPTURE)
        except Exception:
            pass

    # ── state ──
    def tick(self):
        self.checks += 1
        if self.checks % 10 == 1:
            if not self._should_run():
                QApplication.quit()
                return
            self._update_edit_mode()
        game = self.window_cache.rect()
        if not game:
            self.hide()
            return
        if game != self.game:
            self.game = game
            self._place(game)
            self._load_edit_boxes()
        if not self.isVisible():
            self.show()
            self._place(game)
        self.boxes = ocr_debug.read_all()
        self.update()

    def _should_run(self):
        ocr_debug._state["checked"] = 0.0  # re-read the setting now
        if not ocr_debug.enabled():
            return False
        if self.parent_pid:
            try:
                import psutil
                return psutil.pid_exists(self.parent_pid)
            except Exception:
                pass
        return True

    def _update_edit_mode(self):
        try:
            from app_settings import load_app_settings
            editing = bool(load_app_settings().get("ocr_box_edit", False))
        except Exception:
            editing = False
        if editing == self.editing:
            return
        self.editing, self.drag = editing, None
        self._set_flags(editing)  # hides the window; tick() shows it again
        self._load_edit_boxes()

    def _load_edit_boxes(self):
        self.edit_boxes = {}
        if not (self.editing and self.game):
            return
        regions = ocr_debug.load_regions()
        for name in ocr_debug.EDITABLE:
            box = ocr_debug.region_box(regions.get(name), self.game)
            if box:
                self.edit_boxes[name] = box

    def _place(self, game):
        # Physical pixels via win32, like the Continue blocker: Qt geometry
        # is in logical pixels and would be DPI-scaled off the game window.
        try:
            import win32con
            import win32gui
            win32gui.SetWindowPos(int(self.winId()), win32con.HWND_TOPMOST, game["left"], game["top"],
                                  game["width"], game["height"],
                                  win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW)
        except Exception:
            self.setGeometry(game["left"], game["top"], game["width"], game["height"])

    # ── geometry ──
    def _dpr(self):
        return self.devicePixelRatioF() or 1.0

    def _to_view(self, box):
        dpr = self._dpr()
        return QRectF((box["left"] - self.game["left"]) / dpr, (box["top"] - self.game["top"]) / dpr,
                      box["width"] / dpr, box["height"] / dpr)

    def _corners(self, rect):
        return {"tl": rect.topLeft(), "tr": rect.topRight(), "bl": rect.bottomLeft(), "br": rect.bottomRight()}

    def _grab_at(self, pos):
        """(name, corner) under the mouse, corners first."""
        for name, box in self.edit_boxes.items():
            rect = self._to_view(box)
            for corner, pt in self._corners(rect).items():
                if abs(pos.x() - pt.x()) <= HANDLE and abs(pos.y() - pt.y()) <= HANDLE:
                    return name, corner
        for name, box in self.edit_boxes.items():
            if self._to_view(box).contains(pos):
                return name, "move"
        return None

    # ── mouse (edit mode only) ──
    def mousePressEvent(self, event):
        grab = self._grab_at(event.position()) if self.editing and self.game else None
        if grab:
            name, corner = grab
            self.drag = (name, corner, event.position(), dict(self.edit_boxes[name]))

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self.drag:
            name, corner, start, box = self.drag
            dpr = self._dpr()
            self.edit_boxes[name] = drag_box(box, corner, (pos.x() - start.x()) * dpr, (pos.y() - start.y()) * dpr)
            self.update()
            return
        grab = self._grab_at(pos) if self.editing else None
        cursors = {"tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor,
                   "bl": Qt.SizeBDiagCursor, "move": Qt.SizeAllCursor}
        self.setCursor(cursors[grab[1]] if grab else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if self.drag:
            name = self.drag[0]
            self.drag = None
            try:
                ocr_debug.save_region(name, self.edit_boxes[name], self.game)
            except Exception:
                self._load_edit_boxes()  # not saved: show the stored box again
            self.update()

    # ── drawing ──
    def _draw_tag(self, p, metrics, rect, label, fade=1.0):
        w = metrics.horizontalAdvance(label) + 8
        h = metrics.height() + 2
        y = rect.top() - h if rect.top() - h >= 0 else rect.bottom()
        tag = QRectF(rect.left(), y, w, h)
        p.fillRect(tag, QColor(10, 10, 10, int(200 * fade)))
        p.setPen(QColor(235, 235, 235, int(255 * fade)))
        p.drawText(tag, Qt.AlignCenter, label)

    def paintEvent(self, event):
        if not self.game:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(self.font_)
        metrics = QFontMetrics(self.font_)
        now = time.time()
        for name, entry in sorted(self.boxes.items()):
            if name in self.edit_boxes:
                continue  # drawn below, where it can be dragged
            fade = max(0.25, 1.0 - (now - entry["t"]) / ocr_debug.KEEP_S)
            color = box_color(entry)
            rect = self._to_view({"left": entry["x"], "top": entry["y"], "width": entry["w"], "height": entry["h"]})
            fill, edge = QColor(color), QColor(color)
            fill.setAlpha(int(45 * fade))
            edge.setAlpha(int(220 * fade))
            p.fillRect(rect, fill)
            p.setPen(QPen(edge, 1.5))
            p.drawRect(rect)
            self._draw_tag(p, metrics, rect, box_label(name, entry), fade)
        for name, box in self.edit_boxes.items():
            rect = self._to_view(box)
            fill = QColor(EDIT)
            fill.setAlpha(50)  # never 0: the box has to take the mouse
            p.fillRect(rect, fill)
            p.setPen(QPen(EDIT, 1.5, Qt.DashLine))
            p.drawRect(rect)
            p.setPen(Qt.NoPen)
            p.setBrush(EDIT)
            for pt in self._corners(rect).values():
                p.drawRect(QRectF(pt - QPointF(HANDLE / 2, HANDLE / 2), QRectF(0, 0, HANDLE, HANDLE).size()))
            p.setBrush(Qt.NoBrush)
            reading = self.boxes.get(name, {}).get("text")
            self._draw_tag(p, metrics, rect, box_label(name, {"text": reading} if reading else {}))
        title = "OCR Bounding Box Debug" + (" · drag corners to resize, the middle to move" if self.editing else "")
        tag = QRectF(8, 8, metrics.horizontalAdvance(title) + 12, metrics.height() + 4)
        p.fillRect(tag, QColor(10, 10, 10, 170))
        p.setPen(QColor(235, 235, 235))
        p.drawText(tag, Qt.AlignCenter, title)
        p.end()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent", type=int, default=None)
    args = ap.parse_args()
    app = QApplication.instance() or QApplication(sys.argv)
    overlay = DebugOverlay(args.parent)
    overlay.tick()
    app.exec()


if __name__ == "__main__":
    main()
