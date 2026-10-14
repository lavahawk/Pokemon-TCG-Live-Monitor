"""
HUD buddy: a small pixel-art Pokemon living around the overlay's mini GUI.

It walks along the bottom, hops up onto the mini GUI, naps (hover it to wake
it), emotes, peeks up from below, now and then hops into the mini GUI's
Pokeball for a while, and rarely says something cute. 1 in 50 buddies is
shiny (alternate colours, shiny sparkle when it appears).
  Left-click:  it hops, smiles and sends hearts.
  Right-click: drops a berry; it walks over and eats it.

Off by default: Advanced → Preferences · Overlay → "HUD buddy" (overlay_pet,
overlay_pet_species). Sprites: pet_sprites/<species>/ (shiny in shiny/) from
the PMD Sprite Repository (SpriteCollab, CC BY-NC 4.0, see
pet_sprites/CREDITS.txt). Each sheet is one row per facing direction, one
column per frame; anim.json holds frame size and per-frame durations
(1/60 s). Frames are scaled by a whole number of physical pixels, so the
pixel art stays crisp at any DPI.
"""

import json
import math
import os
import random
import time

from PySide6.QtCore import Qt, QTimer, QRect, QRectF, QPointF
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITE_DIR = os.path.join(BASE_DIR, "pet_sprites")
SPECIES = ("pikachu", "gengar", "eevee")
SHINY_ODDS = 1 / 50

SIZE = 1.5          # logical size vs the source sprite
STRIP_W = 260       # floor to the left of the mini GUI (logical px)
WIN_H = 150
TICK_MS = 33
WALK_SPEED = {"pikachu": 26.0, "gengar": 18.0, "eevee": 52.0}  # px/s, matched to each walk cycle
ROW_DOWN, ROW_RIGHT, ROW_LEFT = 0, 2, 6
EMOTES = ("Nod", "Pose", "Rotate", "Eat", "Hop", "Twirl")
KAOMOJI = ("(◕‿◕)", "(^▽^)", "(｡♥‿♥｡)", "♪ ~", "(>ω<)", "(˘ω˘)", "(•‿•)/", "♥", "(^_^)b", "(✿◠‿◠)")
HEART = ("01010", "11111", "11111", "01110", "00100")
BERRY = ("00100", "01110", "11111", "11111", "01110")   # top pixel = leaf
STAR = ("00100", "00100", "11011", "00100", "00100")     # shiny sparkle


def available_species():
    return [s for s in SPECIES if os.path.exists(os.path.join(SPRITE_DIR, s, "anim.json"))]


def _ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


class Sheet:
    """One animation: frames[row][col] (crisp-scaled pixmaps) + durations (ms)."""

    def __init__(self, path, meta, ps, dpr):
        pix = QPixmap(path)
        w, h = meta["w"], meta["h"]
        self.w, self.h = w, h
        self.durations = [max(16, int(d * 1000 / 60)) for d in meta["durations"]]
        cols = min(max(1, pix.width() // w), len(self.durations))
        rows = max(1, pix.height() // h)
        self.raw = pix
        self.frames = []
        for r in range(rows):
            row = []
            for c in range(cols):
                f = pix.copy(c * w, r * h, w, h).scaled(w * ps, h * ps, Qt.AspectRatioMode.IgnoreAspectRatio,
                                                        Qt.TransformationMode.FastTransformation)
                f.setDevicePixelRatio(dpr)
                row.append(f)
            self.frames.append(row)
        self.length = sum(self.durations[:cols])
        top, bottom = self.visible_rows()
        self.foot = bottom + 1 - h / 2.0  # feet (last opaque row) below the frame centre, source px

    def frame(self, row, elapsed_ms, loop=True):
        frames = self.frames[min(row, len(self.frames) - 1)]
        t = elapsed_ms % self.length if loop else min(elapsed_ms, self.length - 1)
        for i, d in enumerate(self.durations[:len(frames)]):
            if t < d:
                return frames[i]
            t -= d
        return frames[-1]

    def visible_rows(self):
        """(top, bottom) of the non-transparent pixels of frame 0, source px."""
        img = self.raw.copy(0, 0, self.w, self.h).toImage().convertToFormat(QImage.Format.Format_ARGB32)
        rows = [y for y in range(self.h) if any(img.pixelColor(x, y).alpha() > 20 for x in range(self.w))]
        return (rows[0], rows[-1]) if rows else (0, self.h - 1)


class PetWidget(QWidget):
    def __init__(self, species="pikachu"):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(STRIP_W + 160, WIN_H)
        self.species = None
        self.shiny = False
        self._dpr = None
        self.sheets, self.portraits = {}, {}
        self.L, self.height_px = SIZE, 30.0
        self.drop = 8.0           # mini GUI bottom -> game window bottom (logical px)
        self.pill = QRect(STRIP_W, WIN_H - 30, 150, 30)   # mini GUI, local coords
        self.ball = QPointF(STRIP_W + 14, WIN_H - 15)
        self.x = STRIP_W * 0.6
        self.y_off = 0.0          # lift (hop arcs, positive = up) / sink (peeking, negative)
        self.state, self.anim, self.row, self.loop = "idle", "Idle", ROW_DOWN, True
        self.started = self.until = time.monotonic()
        self.target = self.x
        self.after_walk = None
        self.arc = None           # (x0, g0, x1, g1, t0, dur, then)
        self.bubble = None        # (kind, content, born, until)
        self.hearts, self.sparks, self.zs, self.stars = [], [], [], []
        self.berry = None         # [x, y, vy, landed]
        self.scale_fx = 1.0       # capture / release
        self.tint = 0.0
        self.flash = None         # time of the white burst at the ball
        self._next_twinkle = time.monotonic() + 20
        self._click_through = None
        self.set_species(species)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(TICK_MS)

    # ── setup ──
    def _load(self, species, dpr):
        folder = os.path.join(SPRITE_DIR, species)
        if self.shiny and os.path.exists(os.path.join(folder, "shiny", "anim.json")):
            folder = os.path.join(folder, "shiny")
        with open(os.path.join(folder, "anim.json"), "r", encoding="utf-8") as handle:
            meta = json.load(handle)
        ps = max(1, round(SIZE * dpr))
        self.L = ps / dpr  # logical px per source px
        self.sheets = {n: Sheet(os.path.join(folder, f"{n}.png"), m, ps, dpr) for n, m in meta.items()
                       if os.path.exists(os.path.join(folder, f"{n}.png"))}
        self.portraits = {}
        pr = max(1, round(dpr))
        for name in ("Happy", "Joyous", "Inspired", "Surprised", "Normal", "Sad", "Teary-Eyed"):
            pix = QPixmap(os.path.join(folder, f"{name}.png"))
            if not pix.isNull():
                pix = pix.scaled(40 * pr, 40 * pr, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.FastTransformation)
                pix.setDevicePixelRatio(pr * 40 / 32)  # shown at 32 logical px
                self.portraits[name] = pix
        idle = self.sheets.get("Idle") or next(iter(self.sheets.values()))
        top, bottom = idle.visible_rows()
        self.height_px = (bottom - top) * self.L  # visible height, logical px
        self._dpr = dpr

    def set_species(self, species):
        if species == "random":
            if self.species is not None:
                return  # picked once per overlay start
            species = random.choice(available_species() or [None])
        species = species if species in available_species() else (available_species() or [None])[0]
        if species is None or species == self.species:
            return
        self.shiny = random.random() < SHINY_ODDS
        self._load(species, self._screen_dpr())
        self.species = species
        self._enter("idle", 2.0)
        if self.shiny:
            self._shiny_burst()

    def _screen_dpr(self):
        screen = self.screen() or QGuiApplication.primaryScreen()
        return screen.devicePixelRatio() if screen else 1.0

    def follow(self, overlay_geo, ball_global=None, drop=None):
        """Live on the game window's bottom edge (`drop` px below the mini
        GUI) to the left of the mini GUI, with its top as a ledge."""
        if drop is not None:
            self.drop = float(drop)
        w = STRIP_W + overlay_geo.width() + 4
        if self.width() != w:
            self.setFixedSize(w, WIN_H)
        self.move(overlay_geo.right() + 1 - w, int(round(overlay_geo.bottom() + 1 + self.drop - WIN_H)))
        self.pill = QRect(w - overlay_geo.width(), int(round(WIN_H - self.drop - overlay_geo.height())),
                          overlay_geo.width(), overlay_geo.height())
        if ball_global is not None:
            self.ball = QPointF(self.mapFromGlobal(ball_global))
        if self.species and self._screen_dpr() != self._dpr:
            self._load(self.species, self._screen_dpr())

    # ── geometry ──
    def floor(self, x):
        on_pill = self.pill.left() + 6 <= x <= self.pill.right() - 6
        return float(self.pill.top() if on_pill else WIN_H)  # feet touch the surface

    def _feet_y(self):
        return self.floor(self.x) - self.y_off

    def _sprite_rect(self):
        h = max(20, int(self.height_px))
        return QRect(int(self.x - h * 0.6), int(self._feet_y() - h - 2), int(h * 1.2), h + 4)

    # ── states ──
    def _enter(self, state, seconds=None, anim=None, loop=True):
        now = time.monotonic()
        self.state, self.started, self.loop = state, now, loop
        self.until = now + (seconds if seconds is not None else random.uniform(3.0, 8.0))
        self.anim = anim or {"walk": "Walk", "sleep": "Sleep"}.get(state, "Idle")
        self.row = ROW_DOWN
        if self.anim not in self.sheets:
            self.anim = "Idle" if "Idle" in self.sheets else next(iter(self.sheets))
        if state == "emote":
            sheet = self.sheets.get(self.anim)
            loops = random.randint(1, 3) if loop else 1
            self.until = now + (sheet.length / 1000.0 * loops if sheet else 1.0)

    def walk_to(self, x, then=None):
        self.target = max(10.0, min(self.width() - 10.0, x))
        self.after_walk = then
        self._enter("walk", 60)
        self.row = ROW_RIGHT if self.target > self.x else ROW_LEFT

    def _next(self):
        roll = random.random()
        if roll < 0.04 and self.bubble is None:
            self.say(random.choice(KAOMOJI))
        if roll < 0.07:
            self._enter("sleep", random.uniform(15, 40))
        elif roll < 0.11:
            self.walk_to(self.ball.x() + 14, then=lambda: self._enter("capture", 0.55))
        elif roll < 0.15:
            self._enter("peek", random.uniform(5.0, 8.0))
        elif roll < 0.55:
            self.walk_to(random.uniform(12, self.width() - 12))
        elif roll < 0.78:
            self._enter("idle")
        else:
            emotes = [e for e in EMOTES if e in self.sheets]
            self._enter("emote", anim=random.choice(emotes)) if emotes else self._enter("idle")

    def say(self, text, seconds=3.0, kind="text"):
        now = time.monotonic()
        self.bubble = (kind, text, now, now + seconds)

    def _hop(self, x1, dur=0.42, then=None):
        self.arc = (self.x, self.floor(self.x), x1, self.floor(x1), time.monotonic(), dur, then)

    # ── tick ──
    def _tick(self):
        now = time.monotonic()
        dt = TICK_MS / 1000.0
        if self.arc:
            x0, g0, x1, g1, t0, dur, then = self.arc
            t = min(1.0, (now - t0) / dur)
            self.x = x0 + (x1 - x0) * t
            ground = g0 + (g1 - g0) * t
            peak = 12 + max(0.0, g0 - g1)
            self.y_off = self.floor(self.x) - (ground - peak * 4 * t * (1 - t))
            if t >= 1.0:
                self.arc, self.y_off = None, 0.0
                if then:
                    then()
        elif self.state == "walk":
            step = WALK_SPEED.get(self.species, 24.0) * dt * (1 if self.target > self.x else -1)
            nxt = self.x + step
            if abs(self.target - self.x) <= abs(step):
                self.x = self.target
                done, self.after_walk = self.after_walk, None
                done() if done else self._next()
            elif self.floor(nxt) != self.floor(self.x):
                self._hop(self.x + (16 if step > 0 else -16))  # a ledge: hop up / down
            else:
                self.x = nxt
        elif self.state == "capture":
            t = min(1.0, (now - self.started) / 0.55)
            self.tint, self.scale_fx = t, 1.0 - _ease(t)
            if t >= 1.0:
                self._enter("ball", random.uniform(6, 15))
        elif self.state == "release":
            t = min(1.0, (now - self.started) / 0.5)
            self.tint, self.scale_fx = 1.0 - t, _ease(t)
            if t >= 1.0:
                self.tint, self.scale_fx = 0.0, 1.0
                self._enter("idle", 3.0)
                pending, self._pending_result = getattr(self, "_pending_result", None), None
                if pending:
                    QTimer.singleShot(500, lambda r=pending: self.react(r))
                if self.shiny:
                    self._shiny_burst()
                self._hop(self.x - 22, then=lambda: self._enter("emote", anim="Pose", loop=False)
                          if "Pose" in self.sheets else None)
        elif self.state == "peek":
            t = (now - self.started) / max(0.1, self.until - self.started)
            h = self.height_px + 4
            # sink out of sight, rise to show the head and look around, sink, pop back up
            if t < 0.15:
                self.y_off = -h * _ease(t / 0.15)
            elif t < 0.3:
                self.y_off = -h
            elif t < 0.4:
                self.y_off = -h + h * 0.5 * _ease((t - 0.3) / 0.1)
            elif t < 0.65:
                self.y_off = -h * 0.5 + math.sin((t - 0.4) * 30) * 1.2
            elif t < 0.75:
                self.y_off = -h * 0.5 - h * 0.5 * _ease((t - 0.65) / 0.1)
            elif t < 0.85:
                self.y_off = -h
            else:
                self.y_off = -h * (1 - _ease((t - 0.85) / 0.15))
            if t >= 1.0:
                self.y_off = 0.0
                self._next()
        elif now >= self.until:
            if self.state == "ball":
                self.flash = now
                self._enter("release", 0.5)
            elif self.state == "sleep":
                self._enter("emote", anim="Nod", loop=False) if "Nod" in self.sheets else self._enter("idle")
            else:
                self._next()

        # wake up when the cursor rests on a sleeping buddy
        if self.state == "sleep" and self._sprite_rect().contains(self.mapFromGlobal(QCursor.pos())):
            self.zs = []
            self.say("Surprised", 1.6, kind="portrait") if "Surprised" in self.portraits else self.say("!", 1.2)
            self._enter("idle", 2.5)
            self._hop(self.x, dur=0.32)

        if self.berry and not self.berry[3]:
            b = self.berry
            b[2] += 600 * dt
            b[1] += b[2] * dt
            if b[1] >= self.floor(b[0]):
                b[1], b[3] = self.floor(b[0]), True
                if self.state not in ("ball", "capture", "release", "peek"):
                    self.walk_to(b[0] - 12 if self.x < b[0] else b[0] + 12, then=self._eat)
        if self.berry and self.berry[3] and self.state in ("idle", "emote") and self.anim != "Eat" \
                and self.arc is None:
            self.walk_to(self.berry[0] - 12 if self.x < self.berry[0] else self.berry[0] + 12, then=self._eat)

        if self.shiny and now >= self._next_twinkle and self.state not in ("ball", "capture", "peek"):
            self._next_twinkle = now + random.uniform(15, 30)
            self._shiny_burst(small=True)
        if self.state == "sleep" and (not self.zs or now - self.zs[-1][1] > 1.4):
            self.zs.append((self.x + 8, now))
        self.zs = [z for z in self.zs if now - z[1] < 2.8]
        self.hearts = [h for h in self.hearts if now - h[3] < 1.5]
        self.sparks = [s for s in self.sparks if now - s[2] < 0.6]
        self.stars = [s for s in self.stars if now - s[3] < 0.9]
        if self.bubble and now > self.bubble[3]:
            self.bubble = None
        if self.flash and now - self.flash > 0.5:
            self.flash = None
        self._update_click_through()
        self.update()

    # ── battle results (called by the overlay when a battle is saved) ──
    def react(self, result):
        """Win: a little celebration. Loss: mopes off to the corner and naps."""
        if self.state in ("ball", "capture", "release"):
            self._pending_result = result  # played once it has popped out
            if self.state != "release":
                self.flash = time.monotonic()
                self._enter("release", 0.5)
            return
        self.berry, self.after_walk, self.y_off = None, None, 0.0
        if str(result).lower().startswith("w"):
            self._celebrate()
        elif str(result).lower().startswith("l"):
            face = "Sad" if "Sad" in self.portraits else None
            self.say(face, 2.5, kind="portrait") if face else self.say("(._.)", 2.5)
            self.walk_to(12.0, then=lambda: (setattr(self, "row", ROW_DOWN),
                                               self._enter("sleep", random.uniform(25, 40))))

    def _celebrate(self, jumps=3):
        face = "Joyous" if "Joyous" in self.portraits else "Happy"
        self.say(face, 2.6, kind="portrait") if face in self.portraits else self.say("★ WIN! ★", 2.6)
        self._love(4)
        if self.shiny:
            self._shiny_burst()
        self._enter("emote", anim="Pose" if "Pose" in self.sheets else "Idle", loop=False)
        self.until = time.monotonic() + 2.0

        def jump(n):
            if n <= 0:
                spin = "Rotate" if "Rotate" in self.sheets else "Nod"
                self._enter("emote", anim=spin, loop=False)
                return
            for _ in range(4):
                a = random.uniform(0, math.tau)
                self.sparks.append((self.x + math.cos(a) * 16, self._feet_y() - self.height_px + math.sin(a) * 10,
                                    time.monotonic()))
            self._hop(self.x, dur=0.34, then=lambda: jump(n - 1))
        jump(jumps)

    def _eat(self):
        self.row = ROW_DOWN
        self._enter("emote", anim="Eat" if "Eat" in self.sheets else "Nod", loop=True)
        self.until = time.monotonic() + 2.2
        QTimer.singleShot(1600, self._finish_eating)

    def _finish_eating(self):
        if self.berry is None:
            return
        self.berry = None
        self._love(2)
        self.say("Joyous" if "Joyous" in self.portraits else "Happy", 2.0, kind="portrait")

    def _love(self, n=3):
        now = time.monotonic()
        top = self._feet_y() - self.height_px
        for i in range(n):
            self.hearts.append((self.x, top, (i - (n - 1) / 2) * 16, now + i * 0.08))
        for _ in range(6):
            a = random.uniform(0, math.tau)
            self.sparks.append((self.x + math.cos(a) * 14, top + 10 + math.sin(a) * 10, now))

    def _shiny_burst(self, small=False):
        """The games' shiny sparkle: stars popping out around the body."""
        now = time.monotonic()
        mid = self._feet_y() - self.height_px / 2
        for i in range(3 if small else 7):
            a = random.uniform(0, math.tau)
            r = random.uniform(8, self.height_px * 0.7)
            self.stars.append((self.x + math.cos(a) * r, mid + math.sin(a) * r, a, now + i * 0.07))

    # ── input: clickable only on the sprite, click-through elsewhere ──
    def _update_click_through(self):
        if os.name != "nt" or not self.isVisible():
            return
        through = self.state in ("ball", "capture") or \
            not self._sprite_rect().contains(self.mapFromGlobal(QCursor.pos()))
        if through == self._click_through:
            return
        self._click_through = through
        try:
            import ctypes
            hwnd = int(self.winId())
            GWL_EXSTYLE, WS_EX_TRANSPARENT, WS_EX_LAYERED, WS_EX_NOACTIVATE = -20, 0x20, 0x80000, 0x08000000
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_NOACTIVATE
            style = style | WS_EX_TRANSPARENT if through else style & ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def mousePressEvent(self, event):
        if not self._sprite_rect().contains(event.position().toPoint()) \
                or self.state in ("ball", "capture", "release"):
            return
        if event.button() == Qt.MouseButton.RightButton:
            if self.berry is None:
                bx = max(12.0, min(self.width() - 12.0, self.x + random.choice((-34, 34))))
                self.berry = [bx, -10.0, 0.0, False]
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.zs, self.after_walk = [], None
        self._love(3)
        self.say("pet", 2.2, kind="pet")
        self._enter("idle", 2.6)
        self._hop(self.x, dur=0.32, then=lambda: self._hop(self.x, dur=0.26))

    # ── drawing ──
    def paintEvent(self, _event):
        sheet = self.sheets.get(self.anim)
        if sheet is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        now = time.monotonic()
        feet = self._feet_y()
        floor = self.floor(self.x)
        if self.state != "ball":
            frame = sheet.frame(self.row, (now - self.started) * 1000.0, loop=self.loop)
            fw, fh = frame.width() / frame.devicePixelRatio(), frame.height() / frame.devicePixelRatio()
            cy = feet - sheet.foot * self.L
            if self.state == "peek":  # hidden below the surface it peeks over
                p.setClipRect(QRect(0, 0, self.width(), int(floor)))
            if self.tint > 0 or self.scale_fx < 1.0:
                frame = self._tinted(frame, self.tint)
                s = max(0.01, self.scale_fx)
                cx = self.ball.x() + (self.x - self.ball.x()) * s
                cyy = self.ball.y() + (cy - self.ball.y()) * s
                p.save()
                p.translate(cx, cyy)
                p.scale(s, s)
                p.drawPixmap(QPointF(-fw / 2, -fh / 2), frame)
                p.restore()
            else:
                p.drawPixmap(QPointF(self.x - fw / 2, cy - fh / 2), frame)
            p.setClipping(False)
        if self.flash:
            t = (now - self.flash) / 0.5
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, int(220 * (1 - t))))
            r = 4 + 16 * t
            p.drawEllipse(self.ball, r, r)
        if self.berry:
            self._pixel_art(p, BERRY, int(self.berry[0]), int(self.berry[1]) - 10, 2,
                            {(0, 2): QColor(90, 200, 90)}, QColor(214, 60, 120))
        for zx, born in self.zs:
            age = now - born
            self._pixel_text(p, "z", int(zx + age * 6), int(feet - self.height_px - age * 12),
                             QColor(200, 220, 255, int(220 * (1 - age / 2.8))), 8 + int(age * 2))
        for sx, sy, born in self.sparks:
            t = (now - born) / 0.6
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 240, 150, int(255 * (1 - t))))
            p.drawRect(QRectF(sx - 1, sy - 1 - t * 6, 2, 2))
        for sx, sy, a, born in self.stars:
            t = (now - born) / 0.9
            if t < 0:
                continue
            grow = math.sin(min(1.0, t) * math.pi)  # pop in, pop out
            size = 1 if grow < 0.5 else 2
            x = sx + math.cos(a) * t * 6
            y = sy + math.sin(a) * t * 6
            self._pixel_art(p, STAR, int(x), int(y) - 5, size, {(2, 2): QColor(255, 255, 255, int(255 * grow))},
                            QColor(255, 236, 120, int(255 * grow)))
        if self.bubble:
            self._paint_bubble(p, now)
        for hx, hy, spread, born in self.hearts:
            age = now - born
            if age < 0:
                continue
            alpha = int(255 * max(0.0, 1 - age / 1.5))
            drift = spread + (1 if spread >= 0 else -1) * (14 + age * 22)  # out to the sides, clear of the bubble
            self._pixel_art(p, HEART, int(hx + drift * min(1.0, age / 0.3 + 0.3) + math.sin(age * 7) * 2),
                            int(hy + 8 - age * 20),
                            2, {(1, 1): QColor(255, 220, 228, alpha)}, QColor(255, 92, 128, alpha))
        p.end()

    @staticmethod
    def _tinted(frame, amount):
        if amount <= 0:
            return frame
        out = QPixmap(frame.size())
        out.setDevicePixelRatio(frame.devicePixelRatio())
        out.fill(Qt.GlobalColor.transparent)
        q = QPainter(out)
        q.drawPixmap(0, 0, frame)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        q.fillRect(out.rect(), QColor(255, 60, 60, int(200 * amount)))
        q.end()
        return out

    @staticmethod
    def _pixel_art(p, grid, x, y, size, special, color):
        p.setPen(Qt.PenStyle.NoPen)
        w = len(grid[0]) * size
        for r, line in enumerate(grid):
            for c, bit in enumerate(line):
                if bit == "1":
                    p.setBrush(special.get((r, c), color))
                    p.drawRect(x - w // 2 + c * size, y + r * size, size, size)

    @staticmethod
    def _pixel_text(p, text, x, y, color, size):
        font = QFont("Consolas", size)
        font.setBold(True)
        p.setFont(font)
        p.setPen(color)
        p.drawText(QPointF(x, y), text)

    def _paint_bubble(self, p, now):
        """Square pixel speech bubble that pops in (overshoot) above the head."""
        kind, content, born, until = self.bubble
        if kind == "pet":  # flip through happy faces while being petted
            names = [n for n in ("Happy", "Joyous", "Inspired") if n in self.portraits]
            if names:
                content, kind = names[int((now - born) / 0.3) % len(names)], "portrait"
            else:
                content, kind = "♥", "text"
        if kind == "portrait":
            pix = self.portraits.get(content)
            if pix is None:
                return
            side = int(pix.width() / pix.devicePixelRatio())
            w = h = side + 8
        else:
            font = QFont()
            font.setFamilies(["Segoe UI Symbol", "Segoe UI", "Yu Gothic UI", "Meiryo", "MS Gothic"])
            font.setPointSize(9)
            font.setBold(True)
            p.setFont(font)
            fm = p.fontMetrics()
            w, h = fm.horizontalAdvance(content) + 14, fm.height() + 8
        pop = min(1.0, (now - born) / 0.18)
        s = pop * (1.0 + 0.25 * math.sin(pop * math.pi))  # overshoot
        if until - now < 0.2:
            s *= max(0.0, (until - now) / 0.2)
        if s <= 0.01:
            return
        tail_x = int(self.x)
        bottom = max(int(self._feet_y() - self.height_px - 6), h + 8)
        left = max(2, min(self.width() - w - 2, tail_x - w // 2))
        p.save()
        p.translate(tail_x, bottom)
        p.scale(s, s)
        x, y = left - tail_x, -h - 4
        border, fill = QColor(30, 30, 40, 235), QColor(250, 250, 245, 240)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(border)
        p.drawRect(x + 2, y, w - 4, h)
        p.drawRect(x, y + 2, w, h - 4)
        p.setBrush(fill)
        p.drawRect(x + 2, y + 2, w - 4, h - 4)
        p.setBrush(border)
        p.drawRect(-3, y + h, 6, 2)
        p.drawRect(-1, y + h + 2, 2, 2)
        p.setBrush(fill)
        p.drawRect(-1, y + h - 2, 2, 2)
        if kind == "portrait":
            p.drawPixmap(QPointF(x + 4, y + 4), self.portraits[content])
        else:
            p.setPen(QColor(40, 40, 52))
            p.drawText(QRect(x, y, w, h), Qt.AlignmentFlag.AlignCenter, content)
        p.restore()
