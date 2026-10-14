"""
HUD buddy: a small pixel-art Pokemon that lives next to the overlay's mini
GUI. It walks back and forth, idles, emotes (nod / pose / spin / snack / hop),
naps now and then, and rarely says something cute. Click it: it hops, smiles
and sends a heart.

Off by default: Advanced → Preferences · Overlay → "HUD buddy" (overlay_pet,
overlay_pet_species). Sprites: pet_sprites/<species>/ from the PMD Sprite
Repository (SpriteCollab, CC BY-NC 4.0, see pet_sprites/CREDITS.txt). Each
sheet is one row per facing direction, one column per frame; anim.json
holds the frame size and per-frame durations (1/60 s).
"""

import json
import math
import os
import random
import time

from PySide6.QtCore import Qt, QTimer, QRect, QRectF, QPoint
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITE_DIR = os.path.join(BASE_DIR, "pet_sprites")
SPECIES = ("pikachu", "gengar", "eevee")

SCALE = 2           # whole-pixel scaling keeps the pixel art crisp
STRIP_W = 300       # how far left of the mini GUI it roams (logical px)
STRIP_H = 150
TICK_MS = 33
WALK_SPEED = 26.0   # px/s
ROW_DOWN, ROW_RIGHT, ROW_LEFT = 0, 2, 6
EMOTES = ("Nod", "Pose", "Rotate", "Eat", "Hop", "Twirl")
KAOMOJI = ("(◕‿◕)", "(^▽^)", "(｡♥‿♥｡)", "♪ ~", "(>ω<)", "(˘ω˘)", "(•‿•)/", "♥", "(^_^)b", "(✿◠‿◠)")
HEART = ("01010", "11111", "11111", "01110", "00100")   # pixel heart, 5x5


def available_species():
    return [s for s in SPECIES if os.path.exists(os.path.join(SPRITE_DIR, s, "anim.json"))]


class Sheet:
    """One animation: frames[row][col] pixmaps (scaled) + durations in ms."""

    def __init__(self, path, meta):
        pix = QPixmap(path)
        w, h = meta["w"], meta["h"]
        self.durations = [max(16, int(d * 1000 / 60)) for d in meta["durations"]]
        cols = max(1, pix.width() // w)
        rows = max(1, pix.height() // h)
        self.frames = [[pix.copy(c * w, r * h, w, h).scaled(w * SCALE, h * SCALE,
                                                            Qt.AspectRatioMode.IgnoreAspectRatio,
                                                            Qt.TransformationMode.FastTransformation)
                        for c in range(min(cols, len(self.durations)))] for r in range(rows)]
        self.length = sum(self.durations[:len(self.frames[0])])

    def frame(self, row, elapsed_ms, loop=True):
        row = min(row, len(self.frames) - 1)
        frames = self.frames[row]
        t = elapsed_ms % self.length if loop else min(elapsed_ms, self.length - 1)
        for i, d in enumerate(self.durations[:len(frames)]):
            if t < d:
                return frames[i]
            t -= d
        return frames[-1]


class PetWidget(QWidget):
    def __init__(self, species="pikachu"):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(STRIP_W, STRIP_H)
        self.species = None
        self.sheets = {}
        self.portrait = None
        self.x = STRIP_W * 0.6
        self.target = self.x
        self.state, self.anim, self.row = "idle", "Idle", ROW_DOWN
        self.state_started = time.monotonic()
        self.state_until = self.state_started + 3.0
        self.loop = True
        self.bubble = None        # (text or "portrait", until)
        self.hearts = []          # [(x, y, born)]
        self.zs = []              # sleep z's [(x, born)]
        self._click_through = None
        self.set_species(species)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(TICK_MS)

    # ── setup ──
    def set_species(self, species):
        if species == "random":
            if self.species is not None:
                return  # picked once per overlay start
            species = random.choice(available_species() or [None])
        species = species if species in available_species() else (available_species() or [None])[0]
        if species is None or species == self.species:
            return
        folder = os.path.join(SPRITE_DIR, species)
        with open(os.path.join(folder, "anim.json"), "r", encoding="utf-8") as handle:
            meta = json.load(handle)
        self.sheets = {name: Sheet(os.path.join(folder, f"{name}.png"), m) for name, m in meta.items()
                       if os.path.exists(os.path.join(folder, f"{name}.png"))}
        portrait = QPixmap(os.path.join(folder, "Happy.png"))
        self.portrait = None if portrait.isNull() else portrait  # 40x40, shown 1:1 in the bubble
        self.species = species
        self._enter("idle", 2.0)

    def follow(self, overlay_geo):
        """Sit just left of the mini GUI, bottoms aligned."""
        self.move(overlay_geo.left() - STRIP_W - 6, overlay_geo.bottom() + 1 - STRIP_H)

    # ── behaviour ──
    def _enter(self, state, seconds=None, anim=None, loop=True):
        now = time.monotonic()
        self.state, self.state_started, self.loop = state, now, loop
        if state == "walk":
            margin = 24
            self.target = random.uniform(margin, STRIP_W - margin)
            self.anim = "Walk"
            self.row = ROW_RIGHT if self.target > self.x else ROW_LEFT
            self.state_until = now + 30.0
        elif state == "idle":
            self.anim, self.row = "Idle", ROW_DOWN
            self.state_until = now + (seconds or random.uniform(3.0, 8.0))
        elif state == "sleep":
            self.anim, self.row = "Sleep", 0
            self.state_until = now + (seconds or random.uniform(15.0, 40.0))
        elif state == "emote":
            self.anim, self.row = anim, ROW_DOWN
            sheet = self.sheets.get(anim)
            loops = 1 if not loop else random.randint(1, 3)
            self.state_until = now + (sheet.length / 1000.0 * loops if sheet else 1.0)
        if self.anim not in self.sheets:
            self.anim = "Idle" if "Idle" in self.sheets else next(iter(self.sheets), None)

    def _next(self):
        roll = random.random()
        if roll < 0.04 and self.bubble is None:
            self.bubble = (random.choice(KAOMOJI), time.monotonic() + 3.0)
        if roll < 0.08:
            self._enter("sleep")
        elif roll < 0.45:
            self._enter("walk")
        elif roll < 0.75:
            self._enter("idle")
        else:
            emotes = [e for e in EMOTES if e in self.sheets]
            if emotes:
                self._enter("emote", anim=random.choice(emotes), loop=True)
            else:
                self._enter("idle")

    def _tick(self):
        now = time.monotonic()
        if self.state == "walk":
            step = WALK_SPEED * TICK_MS / 1000.0
            if abs(self.target - self.x) <= step:
                self.x = self.target
                self._next()
            else:
                self.x += step if self.target > self.x else -step
        elif now >= self.state_until:
            if self.state == "sleep":
                self._enter("emote", anim="Nod", loop=False) if "Nod" in self.sheets else self._enter("idle")
            else:
                self._next()
        if self.state == "sleep" and (not self.zs or now - self.zs[-1][1] > 1.4):
            self.zs.append((self.x + 10, now))
        self.zs = [z for z in self.zs if now - z[1] < 2.8]
        self.hearts = [h for h in self.hearts if now - h[2] < 1.6]
        if self.bubble and now > self.bubble[1]:
            self.bubble = None
        self._update_click_through()
        self.update()

    # ── input: clickable only on the sprite, click-through elsewhere ──
    def _sprite_rect(self):
        return QRect(int(self.x) - 18, STRIP_H - 62, 36, 54)

    def _update_click_through(self):
        if os.name != "nt" or not self.isVisible():
            return
        from PySide6.QtGui import QCursor
        through = not self._sprite_rect().contains(self.mapFromGlobal(QCursor.pos()))
        if through == self._click_through:
            return
        self._click_through = through
        try:
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE, WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_NOACTIVATE = -20, 0x20, 0x80000, 0x08000000
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_NOACTIVATE
            style = style | WS_EX_TRANSPARENT if self._click_through else style & ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._sprite_rect().contains(event.position().toPoint()):
            return
        now = time.monotonic()
        self.hearts.append((self.x + random.uniform(-6, 6), STRIP_H - 70, now))
        self.bubble = ("portrait", now + 2.2) if self.portrait is not None else ("♥", now + 2.0)
        self.zs = []
        self._enter("emote", anim="Hop" if "Hop" in self.sheets else "Pose", loop=False)
        self.state_until = now + max(1.2, (self.sheets.get(self.anim).length / 1000.0) if self.sheets.get(self.anim) else 1.2)

    # ── drawing ──
    def paintEvent(self, _event):
        sheet = self.sheets.get(self.anim)
        if sheet is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        now = time.monotonic()
        elapsed = (now - self.state_started) * 1000.0
        frame = sheet.frame(self.row, elapsed, loop=self.loop)
        ground = STRIP_H - 6
        # PMD frames are centred on the character's anchor; its feet sit a bit below centre.
        cx, cy = self.x, ground - 16 * SCALE // 2 - 4
        # soft pixel shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(QRectF(cx - 11, ground - 5, 22, 6))
        p.drawPixmap(int(cx - frame.width() / 2), int(cy - frame.height() / 2), frame)
        for zx, born in self.zs:
            age = now - born
            self._pixel_text(p, "z", int(zx + age * 6), int(ground - 44 - age * 14),
                             QColor(200, 220, 255, int(220 * (1 - age / 2.8))), 9 + int(age * 2))
        if self.bubble:
            self._paint_bubble(p, self.bubble[0], int(cx), int(ground - 62))
        for hx, hy, born in self.hearts:
            age = now - born
            self._pixel_heart(p, int(hx + 30 + math.sin(age * 6) * 3), int(hy - age * 26),
                              int(255 * max(0.0, 1 - age / 1.6)))
        p.end()

    def _pixel_heart(self, p, x, y, alpha):
        size = 3
        p.setPen(Qt.PenStyle.NoPen)
        for r, line in enumerate(HEART):
            for c, bit in enumerate(line):
                if bit == "1":
                    p.setBrush(QColor(255, 92, 128, alpha) if (r, c) != (1, 1) else QColor(255, 210, 220, alpha))
                    p.drawRect(x + c * size - 7, y + r * size, size, size)

    def _pixel_text(self, p, text, x, y, color, size):
        font = QFont("Consolas", size)
        font.setBold(True)
        p.setFont(font)
        p.setPen(color)
        p.drawText(QPoint(x, y), text)

    def _paint_bubble(self, p, content, cx, bottom):
        """Square pixel speech bubble (2 px border, stepped corners, tail)."""
        if content == "portrait":
            w, h = self.portrait.width() + 8, self.portrait.height() + 8
        else:
            font = QFont("Segoe UI Symbol", 9)
            font.setBold(True)
            p.setFont(font)
            w, h = p.fontMetrics().horizontalAdvance(content) + 14, 20
        x = max(2, min(STRIP_W - w - 2, cx - w // 2))
        y = bottom - h - 6
        p.setPen(Qt.PenStyle.NoPen)
        border, fill = QColor(30, 30, 40, 235), QColor(250, 250, 245, 240)
        p.setBrush(border)
        p.drawRect(x + 2, y, w - 4, h)
        p.drawRect(x, y + 2, w, h - 4)
        p.setBrush(fill)
        p.drawRect(x + 2, y + 2, w - 4, h - 4)
        # tail
        tx = max(x + 6, min(x + w - 10, cx - 2))
        p.setBrush(border)
        p.drawRect(tx, y + h, 6, 2)
        p.drawRect(tx + 2, y + h + 2, 2, 2)
        p.setBrush(fill)
        p.drawRect(tx + 2, y + h - 2, 2, 2)
        if content == "portrait":
            p.drawPixmap(x + 4, y + 4, self.portrait)
        else:
            p.setPen(QColor(40, 40, 52))
            p.drawText(QRect(x, y, w, h), Qt.AlignmentFlag.AlignCenter, content)
