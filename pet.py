"""
HUD buddy: a small pixel-art Pokemon living around the overlay's mini GUI.

It walks along the bottom, hops up onto the mini GUI, naps (hover it to wake
it), emotes, peeks up from below, now and then hops into the mini GUI's
Pokeball for a while, and rarely says something cute. 1 in 50 buddies is
shiny (alternate colours, shiny sparkle when it appears).
  Left-click:  it hops and sends hearts (3 when fed in the last 3 games,
               1 when hungry, an angry fit when starving); a face bubble
               now and then (1 in 5 clicks, only when fed).
  Right-click: drops a treat; it walks over and eats it (= fed). Mostly
               berries with different effects (TREATS), 1 in 20 a Rare
               Candy (level up, meters maxed, 30 min cooldown).
  Battles: a cheer when one starts, then it slowly heads into the Pokeball
  or naps out of the way on the right. A win gets one of several
  celebrations (WIN_REACTIONS: hops, a victory lap, confetti, fireworks, a
  spin with notes, hearts), bigger on a streak and relieved after a losing
  run; a loss one of several sad reactions (LOSS_REACTIONS: mope and nap, a
  sigh under a rain cloud, facing the wall, kicking a pebble, tears, a
  grumble). Never the same one twice in a row. Hidden meters in
  .pet_state.json: hunger (games since fed), happiness 0-100 (hearts, mood),
  energy 0-100 (drains awake, refills asleep; low energy = more naps), the
  win/loss streak and gloom 0-100 (losses add it; wins, pets, treats and
  time take it away). Sad or depressed (sadness()), it walks slower, naps
  more, slumps facing away and gets the odd rain cloud.
  Rare extras (_extra, every few minutes at most): looking around, a
  sneeze, a butterfly, tripping, humming, grumbling, a rain cloud,
  stargazing at night. Rarer berries give off particles hinting at what
  they do (Cheri embers, Sitrus glints, Lum leaves, Colbur dusk motes,
  Enigma a rainbow).

Off by default: double-click the mini GUI's Pokeball to call it out (sets
overlay_pet); double-click again to recall it. Species in Settings →
Overlay (overlay_pet_species). Hungry or ignored for 10+ min:
a faint thought puff (berry / heart) now and then. Sprites: pet_sprites/<species>/ (shiny in shiny/) from
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

import theme

from PySide6.QtCore import Qt, QTimer, QRect, QRectF, QPointF
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QWidget

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPRITE_DIR = os.path.join(BASE_DIR, "pet_sprites")
SPECIES = ("pikachu", "gengar", "eevee")
SHINY_ODDS = 1 / 50
STATE_FILE = os.path.join(BASE_DIR, ".pet_state.json")
SLEEPINESS = {"fed": 0.07, "hungry": 0.18, "angry": 0.28}
ANGER = ("10001", "01010", "00000", "01010", "10001")  # anger mark

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
CANDY = ("1100011", "1111111", "0111110", "1111111", "1100011")
# right-click treats: (weight, colour, effects). happy/energy are meter changes;
# full = games it stays fed; hyper = seconds of zoomies; calm = no grumpiness;
# cure = the gloom is gone; sleepy = naps right after; enigma = a surprise.
# fx = the particles a rarer berry gives off, hinting at what it does.
TREATS = {
    "Oran":   (52, (70, 120, 230), {"happy": 10, "energy": 10, "full": 3}),
    "Pecha":  (11, (245, 150, 190), {"happy": 18, "energy": 5, "full": 3, "calm": True}),
    "Cheri":  (10, (225, 50, 60), {"happy": 8, "energy": 35, "full": 3, "hyper": 60, "fx": "ember"}),
    "Chesto": (8, (110, 80, 170), {"happy": 5, "energy": 60, "full": 3}),
    "Sitrus": (7, (240, 210, 70), {"happy": 22, "energy": 15, "full": 6, "fx": "glint"}),
    "Lum":    (5, (110, 200, 90), {"happy": 15, "energy": 20, "full": 4, "calm": True, "cure": True, "fx": "leaf"}),
    "Colbur": (5, (58, 44, 72), {"happy": 6, "full": 3, "sleepy": True, "fx": "dusk"}),
    "Enigma": (2, (150, 90, 200), {"happy": 12, "energy": 10, "full": 3, "enigma": True, "fx": "rainbow"}),
}
ROW_UP = 4
CLOUD = ("0011100", "0111110", "1111111")
BUTTERFLY = (("11011", "11111", "01110", "00100"), ("00000", "01110", "01110", "00100"))  # wings open / closed
WIN_REACTIONS = ("hops", "lap", "confetti", "fireworks", "spin", "hearts")
LOSS_REACTIONS = {"mope": 1.0, "sigh": 1.0, "away": 1.0, "pebble": 0.8, "tears": 1.0, "grumble": 0.45}
EXTRAS_EVERY_S = (150, 420)   # a rare idle extra at most this often
RARE_CANDY_ODDS = 1 / 20
RARE_CANDY_COOLDOWN_S = 30 * 60
NEEDY_AFTER_S = 10 * 60   # no clicks / treats this long: shows it wants attention
EMOTE_WEIGHTS = {"Hop": 0.25}  # hops are jumpy (Pikachu especially): rarer
STAR = ("00100", "00100", "11011", "00100", "00100")     # shiny sparkle


def available_species():
    return [s for s in SPECIES if os.path.exists(os.path.join(SPRITE_DIR, s, "anim.json"))]


def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, TypeError, AttributeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    state = {"games": 0, "fed_game": 0, "full_for": 3, "happiness": 60.0, "energy": 80.0, "level": 5,
             "candy_ready_at": 0.0, "recalled": False, "streak": 0, "gloom": 0.0}
    for key, default in state.items():
        value = data.get(key, default)
        if isinstance(default, bool):
            state[key] = value if isinstance(value, bool) else str(value).strip().lower() in ("1", "true", "yes")
            continue
        try:
            state[key] = type(default)(value)
        except (TypeError, ValueError):
            pass
    return state


def _save_state(state):
    tmp = STATE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
        os.replace(tmp, STATE_FILE)  # atomic: an interrupted write can't reset the meters
    except OSError:
        pass


def _bezier(p0, c, p1, t):
    a = (1 - t) * (1 - t)
    b = 2 * (1 - t) * t
    d = t * t
    return QPointF(a * p0.x() + b * c.x() + d * p1.x(), a * p0.y() + b * c.y() + d * p1.y())


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

    def half_width(self):
        """How far the body reaches from the frame centre (the wider side),
        over every frame of every row, source px."""
        img = self.raw.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        reach = 0.0
        for col in range(min(len(self.durations), max(1, self.raw.width() // self.w))):
            for x in range(self.w):
                if any(img.pixelColor(col * self.w + x, y).alpha() > 20 for y in range(0, img.height(), 2)):
                    reach = max(reach, abs(x + 0.5 - self.w / 2.0) + 0.5)
        return reach or self.w / 2.0


class PetWidget(QWidget):
    def __init__(self, species="pikachu", in_ball=False):
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
        self.tint = 0.0           # 0..1 white (capture / release)
        self.fx_pos, self.fx_scale = None, 1.0   # sprite centre / scale while flying to/from the ball
        self.fx_from = self.fx_to = None
        self.battle = False       # a battle is on: stay out of the way
        self.speed_mul = 1.0
        self.shake_until = self.anger_at = 0.0
        self.hyper_until = 0.0
        self.recalled = False
        self.mem = _load_state()
        self._saved_at = time.monotonic()
        self.flash = None         # time of the white burst at the ball
        self._next_twinkle = time.monotonic() + 20
        self._click_through = None
        self.last_touch = time.monotonic()
        self.thought = None       # (kind, born): faint "needs something" puff
        self._next_thought = time.monotonic() + 40
        self._pending_since = 0.0
        self.particles = []       # [x, y, vx, vy, born, life, (r, g, b), size, gravity, glyph]
        self.cloud_until = self.tears_until = self.grumble_until = self.trail_until = self.stars_until = 0.0
        self.critter = None       # a butterfly passing by: [x0, x1, y, born, dur, (r, g, b)]
        self.pebble = None        # [x, vx, born] kicked along after a loss
        self._last_pick = {}      # reaction pool -> last choice (never twice in a row)
        self._next_extra = time.monotonic() + random.uniform(*EXTRAS_EVERY_S)
        self.set_species(species)
        if in_ball or self.mem.get("recalled"):
            self.recalled = True
            self._enter("ball", 6 * 3600)
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
        for name in ("Happy", "Joyous", "Inspired", "Surprised", "Normal", "Sad", "Teary-Eyed", "Angry", "Sigh"):
            pix = QPixmap(os.path.join(folder, f"{name}.png"))
            if not pix.isNull():
                pix = pix.scaled(40 * pr, 40 * pr, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.FastTransformation)
                pix.setDevicePixelRatio(pr * 40 / 32)  # shown at 32 logical px
                self.portraits[name] = pix
        idle = self.sheets.get("Idle") or next(iter(self.sheets.values()))
        top, bottom = idle.visible_rows()
        self.height_px = (bottom - top) * self.L  # visible height, logical px
        walk = self.sheets.get("Walk") or idle
        self.half_w = max(idle.half_width(), walk.half_width()) * self.L  # body reach from x, logical px
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
        # The mini GUI grows / shrinks with its text: this window with it.
        # Keep the buddy (and its walk) inside, and anything on the floor
        # that the moved left wall now reaches steps back clear.
        self.x = max(10.0, min(self.width() - 10.0, self.x))
        self.target = max(10.0, min(self.width() - 10.0, self.target))
        stop = self._wall_stop()
        if stop < self.x < self._pill_edge() and self.arc is None and self.fx_pos is None:
            self.x = stop
            if self.state == "walk" and stop < self.target < self._pill_edge():
                self.target = stop
        if self.berry and stop - 12 < self.berry[0] < self._pill_edge() + 4 and self.berry[1] >= WIN_H - 1:
            self.berry[0] = stop - 14
        if self.species and self._screen_dpr() != self._dpr:
            self._load(self.species, self._screen_dpr())

    # ── geometry ──
    def floor(self, x):
        on_pill = self.pill.left() + 6 <= x <= self.pill.right() - 6
        return float(self.pill.top() + 2 if on_pill else WIN_H)  # feet touch (slightly on) the surface

    def _feet_y(self):
        return self.floor(self.x) - self.y_off

    # The mini GUI's left side is a wall: on the floor the body stops short
    # of it (the mini GUI's window sits on top, so anything past it would be
    # hidden), and it hops up / down over the corner, never through it.
    def _wall_stop(self):
        """The closest x the buddy gets to the wall on the floor."""
        hw = getattr(self, "half_w", 12.0)
        return float(self.pill.left()) - hw * 1.3 - 3

    def _pill_edge(self):
        """The first x standing on the mini GUI (its left end)."""
        return float(self.pill.left() + 6)

    def _sprite_rect(self):
        h = max(20, int(self.height_px))
        return QRect(int(self.x - h * 0.6), int(self._feet_y() - h - 2), int(h * 1.2), h + 4)

    # ── mood ──
    def mood(self):
        """fed / hungry / angry from hunger (games since fed) and happiness."""
        hunger = self.mem["games"] - self.mem["fed_game"]
        full = self.mem["full_for"]
        happy = self.mem["happiness"]
        if hunger > full + 3 or happy < 15:
            return "angry"
        if hunger > full or happy < 40:
            return "hungry"
        return "fed"

    def _meter(self, key, delta):
        self.mem[key] = max(0.0, min(100.0, float(self.mem[key]) + delta))

    def sadness(self):
        """ok / sad / depressed, from the gloom meter (losses add it, wins,
        pets, treats and time take it away) and the losing streak."""
        gloom, streak = float(self.mem.get("gloom", 0.0)), int(self.mem.get("streak", 0))
        if gloom >= 70 or streak <= -5:
            return "depressed"
        if gloom >= 40 or streak <= -3:
            return "sad"
        return "ok"

    def _pick_fresh(self, pool, options):
        """A weighted pick from `options` ({name: weight} or a sequence),
        never the same as last time for this pool, so nothing repeats."""
        weights = options if isinstance(options, dict) else {name: 1.0 for name in options}
        names = [n for n in weights if n != self._last_pick.get(pool)] or list(weights)
        choice = random.choices(names, [weights[n] for n in names])[0]
        self._last_pick[pool] = choice
        return choice

    def _later(self, ms, fn):
        QTimer.singleShot(int(ms), fn)

    def _emit(self, x, y, color, n=1, vx=(-10, 10), vy=(-20, -5), life=0.8, grav=0.0, size=2, glyph=None):
        """Particles: little pixels (or a glyph) that drift and fade."""
        now = time.monotonic()
        for _ in range(n):
            self.particles.append([x, y, random.uniform(*vx), random.uniform(*vy), now,
                                   life * random.uniform(0.8, 1.2), color, size, grav, glyph])
        del self.particles[:-180]  # a cap, so nothing piles up

    def _centre(self):
        sheet = self.sheets.get(self.anim) or next(iter(self.sheets.values()))
        return QPointF(self.x, self._feet_y() - sheet.foot * self.L)

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
        x = max(10.0, min(self.width() - 10.0, x))
        if self._wall_stop() < x < self._pill_edge():  # in front of the wall: stop short, or stand on the edge
            x = self._pill_edge() if self.floor(self.x) < WIN_H else self._wall_stop()
        self.target = x
        self.after_walk = then
        self._enter("walk", 60)
        self.row = ROW_RIGHT if self.target > self.x else ROW_LEFT

    def _next(self):
        if self.battle:  # stay put until the result
            self._enter(self.state if self.state in ("sleep", "ball") else "idle", 1800)
            return
        mood, sad = self.mood(), self.sadness()
        now = time.monotonic()
        if now >= self._next_extra and random.random() < 0.3 and self._extra():
            self._next_extra = now + random.uniform(*EXTRAS_EVERY_S)
            return
        roll = random.random()
        if roll < 0.04 and mood == "fed" and sad == "ok" and self.bubble is None:
            self.say(random.choice(KAOMOJI))
        elif roll < 0.03 and sad == "depressed" and self.bubble is None:
            self.say(random.choice(("(╥﹏╥)", "...", "(._.)")))
        sleep = SLEEPINESS[mood] + max(0.0, 40.0 - self.mem["energy"]) / 100.0
        sleep += {"ok": 0.0, "sad": 0.07, "depressed": 0.14}[sad]  # a gloomy buddy naps more
        if now < self.hyper_until or self.mem["energy"] > 90:
            sleep = 0.0
        if sad == "depressed" and sleep <= roll < sleep + 0.05:
            self.walk_to(self._nap_spot(), then=lambda: (self._enter("idle", random.uniform(6, 10)),
                                                         setattr(self, "row", ROW_UP)))  # slumps facing away
            return
        if roll < sleep:
            nap = random.uniform(15, 40) * (1.0 if mood == "fed" else 1.6)
            if random.random() < 0.75:
                self.walk_to(self._nap_spot(), then=lambda: self._enter("sleep", nap))
            else:
                self._enter("sleep", nap)
        elif roll < sleep + 0.02:
            self._into_ball()
        elif roll < sleep + 0.06:
            self._peek()
        elif roll < sleep + 0.46:
            self.walk_to(random.uniform(12, self.width() - 12))
        elif roll < sleep + 0.69:
            self._enter("idle")
        else:
            emotes = [e for e in EMOTES if e in self.sheets]
            if emotes:
                self._enter("emote", anim=random.choices(emotes, [EMOTE_WEIGHTS.get(e, 1.0) for e in emotes])[0])
            else:
                self._enter("idle")

    def _extra(self):
        """Something rare, so the day stays fresh: picked from what fits the
        mood, never the same one twice in a row. False when nothing fits."""
        mood, sad, now = self.mood(), self.sadness(), time.monotonic()
        hour = time.localtime().tm_hour
        pool = {"look": 1.0, "sneeze": 0.7, "butterfly": 0.9, "trip": 0.5}
        if mood == "fed" and sad == "ok":
            pool.update(hum=1.0)
        if mood != "fed" or sad != "ok":
            pool.update(grumble=0.9)
        if sad != "ok":
            pool.update(raincloud=1.2)
        if hour >= 21 or hour < 5:
            pool.update(stargaze=1.2)
        kind = self._pick_fresh("extra", pool)
        if kind == "look":  # left, right, then back at you
            self._enter("idle", 3.2)
            for ms, row in ((700, ROW_LEFT), (1500, ROW_RIGHT), (2400, ROW_DOWN)):
                self._later(ms, lambda r=row: self.state == "idle" and setattr(self, "row", r))
        elif kind == "sneeze":
            self._enter("idle", 2.4)
            self._later(600, lambda: setattr(self, "shake_until", time.monotonic() + 0.25))
            self._later(650, lambda: self._emit(self.x + 8, self._top() + 6, (240, 240, 235), n=7, vx=(4, 26),
                                                vy=(-10, 6), life=0.6, size=2))
            self._later(800, lambda: self._face("Surprised", fallback="!", seconds=1.4))
        elif kind == "butterfly":
            left = random.random() < 0.5
            x0, x1 = (-8.0, self.width() + 8.0) if left else (self.width() + 8.0, -8.0)
            color = random.choice(((255, 200, 230), (255, 236, 150), (190, 220, 255), (255, 255, 255)))
            self.critter = [x0, x1, self._top() - random.uniform(8, 24), now, random.uniform(6.5, 9.0), color]
            self._enter("idle", 7.0)
            self._later(3200, lambda: self.state == "idle" and self._hop(self.x, dur=0.36))  # a hop at it
        elif kind == "trip":
            self._enter("emote", anim="Hurt" if "Hurt" in self.sheets else "Nod", loop=False)
            self._emit(self.x, self._feet_y() - 2, (170, 160, 150), n=8, vx=(-20, 20), vy=(-14, -4), life=0.5)
            self._later(500, lambda: self._face("Surprised", fallback="!?", seconds=1.4))
        elif kind == "hum":
            self._enter("emote", anim="Nod" if "Nod" in self.sheets else "Idle", loop=True)
            self.until = now + 2.6
            for i in range(4):
                self._later(i * 600, self._note)
        elif kind == "grumble":
            self.grumble_until = now + 2.0
            self._enter("idle", 3.0)
            self.say("hmph", 1.6)
        elif kind == "raincloud":
            self.cloud_until = now + 9
            self._enter("idle", 9.0)
        elif kind == "stargaze":
            self._enter("idle", 9.0)
            self.row = ROW_UP
            self.stars_until = now + 8.5
        return True

    def _nap_spot(self):
        """The favourite nap spot: the right corner, just left of the mini GUI."""
        return max(14.0, self._wall_stop())

    def _into_ball(self, stay=None):
        def go():
            self.fx_from = self._centre()
            self._enter("capture", 0.85)
            self._ball_stay = stay
        self.walk_to(self.ball.x() + 16, then=go)

    def toggle_ball(self):
        """Double-clicking the mini GUI's Pokeball: recall it from wherever it
        is, or send it back out. Recalled, it stays in until sent out."""
        if self.state in ("capture", "release"):
            return
        self.last_touch = time.monotonic()
        if self.state == "ball":
            self.recalled = self.mem["recalled"] = False
            _save_state(self.mem)
            self._release()
            return
        self.recalled = self.mem["recalled"] = True  # stays in, even through battles, until sent out
        _save_state(self.mem)
        self.arc, self.after_walk, self.berry, self.y_off, self.zs = None, None, None, 0.0, []
        self.fx_from = self._centre()
        self._ball_stay = 6 * 3600
        self._enter("capture", 0.85)

    def _peek(self):
        """Peek up from the game's bottom edge, clear of the mini GUI."""
        hi = max(16.0, min(self.pill.left() - 30.0, self._wall_stop()))
        go = lambda: self._enter("peek", random.uniform(5.0, 8.0))
        if 14 <= self.x <= hi:
            go()
        else:
            self.walk_to(random.uniform(14, hi), then=go)

    def say(self, text, seconds=3.0, kind="text"):
        now = time.monotonic()
        self.bubble = (kind, text, now, now + seconds)

    def _hop(self, x1, dur=0.42, then=None):
        stop, edge = self._wall_stop(), self._pill_edge()
        if x1 == self.x and stop < self.x < edge:
            # a hop on the spot inside the wall's reach (a battle or a result
            # cut a climb short): first to the nearest clear spot
            self.x = x1 = edge if edge - self.x < self.x - stop else stop
            self.y_off = 0.0
        self.arc = (self.x, self.floor(self.x), x1, self.floor(x1), time.monotonic(), dur, then)

    # ── tick ──
    def _tick(self):
        now = time.monotonic()
        dt = TICK_MS / 1000.0
        if self.arc:
            x0, g0, x1, g1, t0, dur, then = self.arc
            t = min(1.0, (now - t0) / dur)
            self.x = x0 + (x1 - x0) * t
            # Up: rise early, so the body is above the ledge before it gets
            # there. Down: stay high until it's clear of the edge, then drop.
            k = 1 - (1 - t) ** 3 if g1 < g0 else t ** 3 if g1 > g0 else t
            ground = g0 + (g1 - g0) * k
            peak = 12 + max(0.0, g0 - g1) + (6 if g1 > g0 else 0)
            self.y_off = self.floor(self.x) - (ground - peak * 4 * t * (1 - t))
            if t >= 1.0:
                self.arc, self.y_off = None, 0.0
                if self.floor(self.x) >= WIN_H and self._wall_stop() < self.x < self._pill_edge():
                    self.x = self._wall_stop()  # the mini GUI moved mid-hop: land clear of its wall
                if then:
                    then()
        elif self.state == "walk":
            zoom = 1.7 if now < self.hyper_until else {"ok": 1.0, "sad": 0.8, "depressed": 0.65}[self.sadness()]
            step = WALK_SPEED.get(self.species, 24.0) * self.speed_mul * zoom * dt * (1 if self.target > self.x else -1)
            nxt = self.x + step
            if abs(self.target - self.x) <= abs(step):
                self.x = self.target
                done, self.after_walk = self.after_walk, None
                done() if done else self._next()
            elif step > 0 and self.floor(self.x) >= WIN_H and self.x < self._pill_edge() \
                    and nxt > self._wall_stop():
                self._hop(self._pill_edge() + 2, dur=0.5)  # the wall: up onto the mini GUI
            elif step < 0 and self.floor(self.x) < WIN_H and nxt < self._pill_edge() \
                    and self.x < self.pill.center().x():
                self._hop(self._wall_stop(), dur=0.5)  # off the mini GUI's left end, clear of the wall
            elif self.floor(nxt) != self.floor(self.x):
                self._hop(self.x + (16 if step > 0 else -16))  # a ledge: hop up / down
            else:
                self.x = nxt
        elif self.state == "capture":
            t = min(1.0, (now - self.started) / 0.85)
            if t < 0.3:
                self.tint, self.fx_pos = _ease(t / 0.3), None
            else:
                u = (t - 0.3) / 0.7
                e = u * u  # accelerates into the ball
                p0 = self.fx_from or self._centre()
                c = QPointF((p0.x() + self.ball.x()) / 2, min(p0.y(), self.ball.y()) - 26)
                self.tint, self.fx_pos, self.fx_scale = 1.0, _bezier(p0, c, self.ball, e), max(0.04, 1.0 - e)
            if t >= 1.0:
                self.fx_pos, self.flash = None, now
                stay = getattr(self, "_ball_stay", None)
                self._enter("ball", stay if stay else random.uniform(6, 15))
        elif self.state == "release":
            t = min(1.0, (now - self.started) / 0.7)
            u = min(1.0, t / 0.5)
            e = 1 - (1 - u) * (1 - u)  # shoots out, slows down
            land = self.fx_to or self._centre()
            c = QPointF((land.x() + self.ball.x()) / 2, min(land.y(), self.ball.y()) - 30)
            self.fx_pos, self.fx_scale = _bezier(self.ball, c, land, e), 0.04 + 0.96 * e
            self.tint = 1.0 if t < 0.5 else 1.0 - (t - 0.5) / 0.5
            if t >= 1.0:
                self.tint, self.fx_pos, self.fx_scale = 0.0, None, 1.0
                self._enter("emote", anim="Pose", loop=False) if "Pose" in self.sheets else self._enter("idle", 3.0)
                pending, self._pending_result = getattr(self, "_pending_result", None), None
                if pending:
                    QTimer.singleShot(400, lambda r=pending: self._show_result(r))
                if self.shiny:
                    self._shiny_burst()
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
                self._release()
            elif self.state == "sleep":
                self._enter("emote", anim="Nod", loop=False) if "Nod" in self.sheets else self._enter("idle")
            else:
                self._next()

        # never left standing on the floor where the mini GUI's wall reaches
        # (it moved during a release, a hop, a peek...): step clear
        if self.arc is None and self.fx_pos is None and self.state not in ("ball", "capture", "release", "peek") \
                and self.floor(self.x) >= WIN_H and self._wall_stop() < self.x < self._pill_edge():
            self.x = self._wall_stop()

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

        if getattr(self, "_pending_result", None) and self.state == "ball" and not self.recalled \
                and now - self._pending_since > 60:
            self._release()
        # needs: hungry, or ignored for a while -> a faint thought puff now and then
        if now >= self._next_thought and self.state in ("idle", "walk", "emote") and self.bubble is None:
            self._next_thought = now + random.uniform(25, 45)
            if self.mood() != "fed":
                self.thought = ("berry", now)
            elif now - self.last_touch > NEEDY_AFTER_S:
                self.thought = ("heart", now)
        if self.thought and (now - self.thought[1] > 2.6 or self.state in ("sleep", "ball", "capture", "peek")):
            self.thought = None

        # energy: drains while awake, refills while asleep or resting in the ball
        resting = self.state in ("sleep", "ball")
        self._meter("energy", dt / 60.0 * (4.0 if resting else -1.0))  # per minute: +4 resting, -1 awake
        self._meter("gloom", -dt / 60.0 * 1.5)  # gloom fades: ~1 point per 40 s
        self._tick_fx(now, dt)
        if now - self._saved_at > 30:
            self._saved_at = now
            _save_state(self.mem)

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

    def _tick_fx(self, now, dt):
        """Particles and the small things that come and go."""
        for q in self.particles:
            q[3] += q[8] * dt
            q[0] += q[2] * dt
            q[1] += q[3] * dt
        self.particles = [q for q in self.particles if now - q[4] < q[5]]
        hidden = self.state in ("ball", "capture", "release")
        top = self._top()
        if self.berry:  # a rarer berry shows off what it does
            kind = self.berry[4] if len(self.berry) > 4 else "Oran"
            fx = TREATS.get(kind, (0, 0, {}))[2].get("fx")
            bx, by = self.berry[0], self.berry[1] - 5
            if fx and random.random() < 0.13:
                if fx == "ember":
                    self._emit(bx + random.uniform(-3, 3), by - 4, random.choice(((255, 150, 40), (255, 90, 40))),
                               vx=(-4, 4), vy=(-32, -14), life=0.55)
                elif fx == "glint":
                    self._emit(bx + random.uniform(-7, 7), by + random.uniform(-6, 4), (255, 244, 170),
                               vx=(0, 0), vy=(-5, -1), life=0.45, size=random.choice((1, 2)))
                elif fx == "leaf":
                    self._emit(bx, by - 4, (130, 215, 100), vx=(-14, 14), vy=(-10, 2), life=0.9, grav=12)
                elif fx == "dusk":
                    self._emit(bx + random.uniform(-6, 6), by - 6, random.choice(((120, 90, 160), (70, 50, 95))),
                               vx=(-5, 5), vy=(3, 9), life=1.1)
                elif fx == "rainbow":
                    c = QColor.fromHsv(int(now * 140) % 360, 170, 255)
                    self._emit(bx + random.uniform(-6, 6), by - 2, (c.red(), c.green(), c.blue()),
                               vx=(-10, 10), vy=(-16, -4), life=0.7)
        if hidden:
            return
        if now < self.cloud_until and random.random() < 0.35:  # rain from its cloud
            self._emit(self.x + random.uniform(-8, 8), top - 14, (140, 170, 230), vx=(0, 0), vy=(50, 70),
                       life=0.32, size=1)
        if now < self.tears_until and random.random() < 0.3:
            self._emit(self.x + random.choice((-5, 5)), top + 9, (120, 180, 255), vx=(-6, 6), vy=(-8, 0),
                       life=0.6, grav=120, size=2)
        if now < self.grumble_until and random.random() < 0.3:  # disgruntled puffs off the head
            self._emit(self.x + random.uniform(-6, 6), top - 2, random.choice(((80, 80, 90), (110, 105, 115))),
                       vx=(-14, 14), vy=(-22, -10), life=0.7, size=3)
        if now < self.trail_until and self.state == "walk" and random.random() < 0.5:
            self._emit(self.x, self._feet_y() - 4, (255, 236, 140), vx=(-4, 4), vy=(-10, -2), life=0.5)
        if now < self.stars_until and random.random() < 0.08:
            self._shiny_burst(small=True)
        if self.critter:
            x0, x1, y, born, dur, _c = self.critter
            t = (now - born) / dur
            if t >= 1.0:
                self.critter = None
            elif self.state == "idle":
                cx = x0 + (x1 - x0) * t
                self.row = ROW_RIGHT if cx > self.x else ROW_LEFT  # watches it go by
        if self.pebble:
            px, vx, born = self.pebble
            if abs(vx) < 3 and abs(px - self.x) < 9 and self.state == "walk":
                vx = (1 if self.target > self.x else -1) * random.uniform(40, 55)  # kick
            vx *= max(0.0, 1 - 3.2 * dt)  # rolls to a stop
            px = max(4.0, min(self.width() - 4.0, px + vx * dt))
            self.pebble = [px, vx, born] if now - born < 14 else None

    def _release(self):
        """Out of the Pokeball: a white shape arcs out, lands left of the mini GUI."""
        self.flash = time.monotonic()
        self.x = max(14.0, self._wall_stop())
        self.anim = "Idle" if "Idle" in self.sheets else self.anim
        self.fx_to = QPointF(self.x, self.floor(self.x) - (self.sheets.get(self.anim) or
                                                           next(iter(self.sheets.values()))).foot * self.L)
        self._enter("release", 0.7)

    # ── battles (called by the overlay) ──
    def battle_start(self):
        """A quick cheer, then slowly off: into the Pokeball, or a nap on the right."""
        if self.battle or self.recalled:
            return
        self.battle, self.berry, self.after_walk, self.y_off = True, None, None, 0.0
        if self.state in ("ball", "capture", "release"):
            return  # already tucked away
        self._celebrate(jumps=2, face="Inspired")
        QTimer.singleShot(2400, self._battle_settle)

    def _battle_settle(self):
        if not self.battle or self.state in ("ball", "capture", "release"):
            return
        self.speed_mul = 0.45
        if random.random() < 0.5:
            self._into_ball(stay=1800)
        else:
            self.walk_to(self._wall_stop(), then=lambda: self._enter("sleep", 1800))

    def react(self, result):
        """A battle was saved. Win: one of several celebrations (bigger on a
        streak, relieved after a losing run). Loss: one of several sad
        reactions; losing runs build up gloom, and in time it gets depressed."""
        self.battle, self.speed_mul = False, 1.0
        self.mem["games"] += 1
        win, loss = str(result).lower().startswith("w"), str(result).lower().startswith("l")
        self._meter("happiness", 3 if win else -3)
        if self.mood() != "fed":
            self._meter("happiness", -8)
        before = int(self.mem.get("streak", 0))
        if win:
            self.mem["streak"] = before + 1 if before > 0 else 1
            self._meter("gloom", -(25 + (15 if before <= -3 else 0)))
        elif loss:
            self.mem["streak"] = before - 1 if before < 0 else -1
            self._meter("gloom", 10 + 4 * min(5, -self.mem["streak"]))
        self._streak_before = before
        _save_state(self.mem)
        if self.recalled:
            return  # recalled by the user: stays in the ball
        self._show_result(result)

    def _show_result(self, result):
        """The reaction only (the meters were updated once, in react)."""
        if self.state in ("ball", "capture", "release"):
            # played once it's back out: when the game reaches the main menu
            # (menu_seen), or after a minute if the menu is never reported
            self._pending_result = result
            self._pending_since = time.monotonic()
            return
        self.berry, self.after_walk, self.y_off, self.zs = None, None, 0.0, []
        result = str(result).lower()
        if result.startswith("w"):
            self._win_reaction(getattr(self, "_streak_before", 0))
        elif result.startswith("l"):
            self._loss_reaction()

    # ── win / loss reactions ──
    def _face(self, *names, fallback="(^_^)", seconds=2.5):
        """The first of these portraits this species has, else a text face."""
        face = next((n for n in names if n in self.portraits), None)
        self.say(face, seconds, kind="portrait") if face else self.say(fallback, seconds)

    def _top(self):
        return self._feet_y() - self.height_px

    def _win_reaction(self, before=0):
        kind = self._pick_fresh("win", WIN_REACTIONS)
        streak = int(self.mem.get("streak", 1))
        now = time.monotonic()
        if kind == "hops":
            self._celebrate()
        elif kind == "lap":  # a victory lap across the floor, sparkles trailing
            self._face("Joyous", "Happy", fallback="★ WIN! ★")
            self.hyper_until = self.trail_until = now + 9
            home = self.x
            self.walk_to(14, then=lambda: self.walk_to(
                home, then=lambda: self._enter("emote", anim="Pose" if "Pose" in self.sheets else "Idle", loop=False)))
        elif kind == "confetti":
            self._face("Inspired", "Joyous", fallback="\\(^o^)/")
            self._enter("emote", anim="Pose" if "Pose" in self.sheets else "Idle", loop=False)
            self._confetti(34)
        elif kind == "fireworks":
            self._face("Happy", "Joyous", fallback="★")
            self._enter("emote", anim="Rotate" if "Rotate" in self.sheets else "Nod", loop=False)
            for i in range(3):
                self._later(i * 420, lambda: self._firework(self.x + random.uniform(-40, 40),
                                                            self._top() - random.uniform(16, 34)))
        elif kind == "spin":
            spin = "Twirl" if "Twirl" in self.sheets else "Rotate" if "Rotate" in self.sheets else "Nod"
            self._enter("emote", anim=spin, loop=True)
            self.until = now + 2.4
            self.say("♪ ~", 2.2)
            for i in range(5):
                self._later(i * 380, self._note)
        else:  # hearts
            self._face("Joyous", "Happy", fallback="♥")
            self._love(8)
            self._hop(self.x, dur=0.34)
        if before <= -3:
            self._later(2800, lambda: self.say("Finally!", 2.2))
        elif streak >= 3:
            if kind != "confetti":
                self._confetti(18)
            self._later(2800, lambda s=streak: self.say(f"{s} in a row!", 2.2))
        if self.shiny:
            self._shiny_burst()

    def _loss_reaction(self):
        sad = self.sadness()
        weights = dict(LOSS_REACTIONS)
        if sad == "depressed":  # slumps more than it grumbles
            weights.update(away=1.8, tears=1.5, sigh=1.4, grumble=0.3)
        kind = self._pick_fresh("loss", weights)
        now = time.monotonic()
        nap = random.uniform(25, 40) * (1.4 if sad == "depressed" else 1.0)
        if kind == "mope":
            self._face("Sad", fallback="(._.)")
            self.walk_to(self._nap_spot(), then=lambda: (setattr(self, "row", ROW_DOWN), self._enter("sleep", nap)))
        elif kind == "sigh":  # a sigh under its own little rain cloud
            self._face("Sigh", "Sad", fallback="haa...")
            self.cloud_until = now + 7
            self._enter("idle", 7.0)
        elif kind == "away":  # sits facing the wall for a bit
            self._face("Sad", fallback="(._.)", seconds=1.8)

            def sulk():
                self._enter("idle", 7.0)
                self.row = ROW_UP
                self._later(1200, lambda: self.say("...", 2.4))
            self.walk_to(self._nap_spot(), then=sulk)
        elif kind == "pebble":  # trudges along kicking a pebble
            ahead = -1 if self.x > self.width() / 2 else 1
            self.pebble = [self.x + ahead * 12, 0.0, now]
            self.speed_mul = 0.55

            def stop():
                self.speed_mul = 1.0
                self._enter("idle", 3.0)
                self.say("(._.)", 2.0)
            self.walk_to(self.x + ahead * random.uniform(70, 110), then=stop)
        elif kind == "tears":
            self._face("Teary-Eyed", "Sad", fallback="(T_T)", seconds=3.2)
            self.tears_until = now + 3.2
            self._enter("idle", 4.0)
        else:  # grumble: a little fit, dark puffs
            self._face("Angry", fallback="hmph", seconds=2.0)
            self.grumble_until = now + 2.4
            self.shake_until = now + 0.5
            self._enter("emote", anim="Hurt" if "Hurt" in self.sheets else "Nod", loop=False)

    def _confetti(self, n=30):
        top = self._top()
        colors = ((255, 92, 128), (255, 214, 90), (110, 200, 255), (140, 230, 140), (200, 150, 255))
        for _ in range(n):
            self._emit(self.x + random.uniform(-30, 30), top - random.uniform(4, 26), random.choice(colors),
                       vx=(-25, 25), vy=(-70, -20), life=1.6, grav=90, size=2)

    def _firework(self, x, y):
        color = random.choice(((255, 214, 90), (255, 110, 140), (120, 200, 255), (170, 255, 170)))
        for i in range(14):
            a = i / 14 * math.tau
            speed = random.uniform(30, 42)
            self._emit(x, y, color, vx=(math.cos(a) * speed,) * 2, vy=(math.sin(a) * speed,) * 2,
                       life=0.75, grav=40, size=2)
        self._emit(x, y, (255, 255, 255), n=3, vx=(-4, 4), vy=(-4, 4), life=0.3, size=3)

    def _note(self):
        self._emit(self.x + random.uniform(-6, 10), self._top() - 4, (255, 236, 160), vx=(-6, 10), vy=(-26, -16),
                   life=1.4, size=9, glyph=random.choice("♪♫"))

    def menu_seen(self):
        """The game is back on the main menu (overlay): out of the ball after a battle."""
        if getattr(self, "_pending_result", None) and self.state == "ball" and not self.recalled:
            self._release()

    def _celebrate(self, jumps=3, face="Joyous"):
        face = face if face in self.portraits else "Joyous" if "Joyous" in self.portraits else "Happy"
        self.say(face, 2.6, kind="portrait") if face in self.portraits else self.say("★ WIN! ★", 2.6)
        self._love(4 if self.mood() == "fed" else 1)
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

    def _pick_treat(self):
        if random.random() < RARE_CANDY_ODDS and time.time() >= self.mem["candy_ready_at"]:
            return "Rare Candy"
        names = list(TREATS)
        return random.choices(names, weights=[TREATS[n][0] for n in names])[0]

    def _eat(self):
        self.row = ROW_DOWN
        self._enter("emote", anim="Eat" if "Eat" in self.sheets else "Nod", loop=True)
        self.until = time.monotonic() + 2.2
        QTimer.singleShot(1600, self._finish_eating)

    def _finish_eating(self):
        if self.berry is None:
            return
        kind = self.berry[4] if len(self.berry) > 4 else "Oran"
        self.berry = None
        self.mem["fed_game"] = self.mem["games"]
        if kind == "Rare Candy":
            self.mem["level"] += 1
            self.mem["happiness"], self.mem["energy"] = 100.0, 100.0
            self.mem["full_for"] = 6
            self.mem["candy_ready_at"] = time.time() + RARE_CANDY_COOLDOWN_S
            self.hyper_until = time.monotonic() + 45
            _save_state(self.mem)
            self.say(f"Lv. {self.mem['level']}!", 2.6)
            self._shiny_burst()
            self._love(4)
            self._celebrate(jumps=2)
            return
        _w, _c, fx = TREATS.get(kind, TREATS["Oran"])
        self.mem["full_for"] = fx.get("full", 3)
        self._meter("happiness", fx.get("happy", 0))
        self._meter("energy", fx.get("energy", 0))
        if fx.get("calm"):
            self.anger_at = self.shake_until = 0.0
            self.mem["happiness"] = max(self.mem["happiness"], 50.0)
        if fx.get("hyper"):
            self.hyper_until = time.monotonic() + fx["hyper"]
        self._meter("gloom", -8)  # a treat cheers it up a little
        if fx.get("cure"):
            self.mem["gloom"] = 0.0
            self.cloud_until = self.tears_until = self.grumble_until = 0.0
        surprise = random.choice(("zoomies", "sleepy", "party", "glow")) if fx.get("enigma") else None
        if surprise == "zoomies":
            self.hyper_until = time.monotonic() + 45
        elif surprise == "glow":
            self._meter("happiness", 20)
            self._meter("energy", 30)
        _save_state(self.mem)
        self._love(3 if self.mood() == "fed" else 1)
        if surprise:
            self.say("?!", 1.6)
            if surprise == "party":
                self._confetti(24)
            elif surprise == "glow":
                self._shiny_burst()
        else:
            face = {"Cheri": "Inspired", "Chesto": "Surprised", "Lum": "Happy", "Colbur": "Normal"}.get(kind, "Joyous")
            face = face if face in self.portraits else "Happy"
            self.say(face, 2.0, kind="portrait")
        if fx.get("sleepy") or surprise == "sleepy":  # drowsy: a nap right after
            self._later(900, lambda: self.state in ("emote", "idle") and not self.battle
                        and self._enter("sleep", random.uniform(25, 45)))

    def _angry(self):
        """Starving and poked: shakes, anger mark, angry face."""
        now = time.monotonic()
        self.shake_until = self.anger_at = now
        self.shake_until += 0.7
        self.say("Angry", 1.8, kind="portrait") if "Angry" in self.portraits else self.say("ò_ó", 1.8)

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
        through = self.state in ("ball", "capture", "release") or \
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
        self.last_touch, self.thought = time.monotonic(), None
        if event.button() == Qt.MouseButton.RightButton:
            if self.berry is None:
                bx = max(12.0, min(self.width() - 12.0, self.x + random.choice((-34, 34))))
                if self._wall_stop() - 12 < bx < self._pill_edge() + 4:  # not against the wall, half hidden
                    bx = self._wall_stop() - 14 if bx < self.pill.left() else self._pill_edge() + 12
                self.berry = [bx, -10.0, 0.0, False, self._pick_treat()]
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.zs, self.after_walk = [], None
        mood = self.mood()
        if self.state == "sleep" and self.battle:
            return  # let it nap through the battle
        self._enter("idle", 2.6)
        if mood == "angry":
            self._angry()
            return
        if time.monotonic() - getattr(self, "_petted_at", 0.0) > 30:
            self._petted_at = time.monotonic()
            self._meter("happiness", 4)
            self._meter("gloom", -3)
        self._love(3 if mood == "fed" else 1)
        if mood == "fed" and random.random() < 0.2:
            self.say("pet", 2.2, kind="pet")
        self._hop(self.x, dur=0.32, then=lambda: self._hop(self.x, dur=0.26) if mood == "fed" else None)

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
            sx = self.x + (math.sin(now * 70) * 2 if now < self.shake_until else 0)
            if self.state == "peek":  # hidden below the surface it peeks over
                p.setClipRect(QRect(0, 0, self.width(), int(floor)))
            if self.tint > 0:
                frame = self._tinted(frame, self.tint)
            if self.fx_pos is not None:
                s = max(0.01, self.fx_scale)
                p.save()
                p.translate(self.fx_pos)
                p.scale(s, s)
                p.drawPixmap(QPointF(-fw / 2, -fh / 2), frame)
                p.restore()
            else:
                p.drawPixmap(QPointF(sx - fw / 2, cy - fh / 2), frame)
            if now - self.anger_at < 1.2:
                self._pixel_art(p, ANGER, int(self.x + 12), int(feet - self.height_px - 4), 2, {},
                                QColor(235, 60, 60, int(255 * (1 - (now - self.anger_at) / 1.2))))
            p.setClipping(False)
        if self.flash:
            t = (now - self.flash) / 0.5
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, int(220 * (1 - t))))
            r = 4 + 16 * t
            p.drawEllipse(self.ball, r, r)
        if self.berry:
            kind = self.berry[4] if len(self.berry) > 4 else "Oran"
            bx, by = int(self.berry[0]), int(self.berry[1]) - 10
            if kind == "Rare Candy":
                self._pixel_art(p, CANDY, bx, by, 2, {(2, 3): QColor(255, 255, 255), (2, 2): QColor(255, 255, 255)},
                                QColor(80, 170, 240))
                if int(now * 4) % 2 == 0:
                    self._pixel_art(p, STAR, bx + 9, by - 9, 1, {}, QColor(255, 236, 120))
            else:
                r, g, b = TREATS.get(kind, TREATS["Oran"])[1]
                shine = QColor(min(255, r + 80), min(255, g + 80), min(255, b + 80))  # reads on dark scenes too
                self._pixel_art(p, BERRY, bx, by, 2, {(0, 2): QColor(90, 200, 90), (2, 1): shine}, QColor(r, g, b))
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
        self._paint_extras(p, now, feet)
        if self.thought and self.state != "ball":
            self._paint_thought(p, now)
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

    def _paint_extras(self, p, now, feet):
        """Particles, the rain cloud, the pebble and a passing butterfly."""
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, _vx, _vy, born, life, (r, g, b), size, _grav, glyph in self.particles:
            alpha = int(255 * max(0.0, 1 - (now - born) / life))
            if glyph:  # music notes etc.: symbol fonts (the pixel font has no ♪)
                font = QFont()
                font.setFamilies(["Segoe UI Symbol", "Segoe UI", "Yu Gothic UI", "MS Gothic"])
                font.setPixelSize(size + 3)
                font.setBold(True)
                p.setFont(font)
                p.setPen(QColor(r, g, b, alpha))
                p.drawText(QPointF(x, y), glyph)
                p.setPen(Qt.PenStyle.NoPen)
            else:
                p.setBrush(QColor(r, g, b, alpha))
                p.drawRect(QRectF(int(x), int(y), size, size))
        hidden = self.state in ("ball", "capture", "release")
        if not hidden and now < self.cloud_until:
            fade = min(1.0, (self.cloud_until - now) / 0.6)  # drifts away at the end
            drift = math.sin(now * 1.3) * 2
            self._pixel_art(p, CLOUD, int(self.x + drift), int(self._top() - 22), 3, {},
                            QColor(150, 158, 172, int(230 * max(0.0, fade))))
        if self.pebble:
            p.setBrush(QColor(150, 140, 130))
            p.drawRect(QRectF(int(self.pebble[0]) - 2, int(self.floor(self.pebble[0])) - 3, 4, 3))
        if self.critter:
            x0, x1, y, born, dur, (r, g, b) = self.critter
            t = min(1.0, (now - born) / dur)
            cx = x0 + (x1 - x0) * t
            cy = y + math.sin(now * 3.1) * 7 + math.sin(now * 7.3) * 2
            self._pixel_art(p, BUTTERFLY[int(now * 8) % 2], int(cx), int(cy), 2, {(3, 2): QColor(60, 50, 50)},
                            QColor(r, g, b, 235))

    @staticmethod
    def _tinted(frame, amount):
        """The sprite washed to white (a Pokemon turning to light for the ball)."""
        if amount <= 0:
            return frame
        out = QPixmap(frame.size())
        out.setDevicePixelRatio(frame.devicePixelRatio())
        out.fill(Qt.GlobalColor.transparent)
        q = QPainter(out)
        q.drawPixmap(0, 0, frame)
        q.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        q.fillRect(out.rect(), QColor(255, 255, 255, int(255 * min(1.0, amount))))
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
        font = QFont(theme.family("mono"), size)
        font.setBold(True)
        p.setFont(font)
        p.setPen(color)
        p.drawText(QPointF(x, y), text)

    def _paint_thought(self, p, now):
        """A small, faint thought puff up-right of the head: berry = hungry,
        heart outline = wants attention."""
        kind, born = self.thought
        age = now - born
        alpha = int(150 * min(1.0, age / 0.4) * min(1.0, (2.6 - age) / 0.4))
        if alpha <= 0:
            return
        hx, hy = self.x + 10, self._feet_y() - self.height_px
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(250, 250, 245, alpha))
        p.drawRect(QRectF(hx, hy - 2, 2, 2))
        p.drawRect(QRectF(hx + 4, hy - 7, 3, 3))
        p.drawRoundedRect(QRectF(hx + 7, hy - 21, 14, 12), 4, 4)
        if kind == "berry":
            r, g, b = TREATS["Oran"][1]
            self._pixel_art(p, BERRY, int(hx + 14), int(hy - 20), 2, {(0, 2): QColor(90, 200, 90, alpha)},
                            QColor(r, g, b, alpha))
        else:
            self._pixel_art(p, ("01010", "10101", "10001", "01010", "00100"), int(hx + 14), int(hy - 20), 2, {},
                            QColor(255, 92, 128, alpha))

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
