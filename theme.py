"""
UI themes (setting "ui_theme", Settings -> Appearance).

A theme is three parts, taken from the style picker's sources:
  type     the fonts:   legacy (Segoe UI / Consolas), geist (Geist / Geist Mono),
                        primer (Mona Sans / JetBrains Mono)
  palette  the colours: legacy, geist (Vercel Geist dark), primer (GitHub Primer dark)
  shape    the corners: legacy, geist (4/6/8 px), primer (3/6/12 px), valorant (square)

"legacy" is the original look and installs nothing. Any other theme is applied
in one place: install() wraps QWidget/QApplication.setStyleSheet so every
stylesheet the app sets is rewritten (colour roles, font families, corner
radii), and painted backgrounds go through qcolor(). The legacy colours are
grouped into roles (accent, text, muted, win, loss, ...) and each role maps to
the theme's colour, keeping the original alpha.

Fonts are bundled TTFs in fonts/ (OFL); a missing font falls back to Segoe UI.
A theme takes effect when the dashboard / overlay next starts.
"""

import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "fonts")

THEMES = {
    # key: (label, type, palette, shape)
    "legacy": ("Legacy", "legacy", "legacy", "legacy"),
    "geist_primer_geist": ("Graphite", "geist", "primer", "geist"),          # Geist type, Primer colours, Geist corners
    "primer_geist_valorant": ("Obsidian", "primer", "geist", "valorant"),   # Primer type, Geist black, square corners
    "primer": ("Harbor", "primer", "primer", "primer"),                     # GitHub Primer throughout
}
DEFAULT_THEME = "legacy"

TYPE = {
    "legacy": {"ui": "Segoe UI", "mono": "Consolas"},
    "geist": {"ui": "Geist", "mono": "Geist Mono"},
    "primer": {"ui": "Mona Sans", "mono": "JetBrains Mono"},
}

# Colour roles -> (r, g, b). bg/surface/raised are the dark backgrounds.
PALETTE = {
    "geist": {
        "bg": (0, 0, 0), "surface": (10, 10, 10), "raised": (23, 23, 23),
        "text": (237, 237, 237), "muted": (161, 161, 161),
        "accent": (0, 112, 243), "accent_light": (82, 168, 255),
        "win": (70, 167, 88), "loss": (229, 72, 77), "warn": (255, 178, 36), "purple": (142, 78, 198),
    },
    "primer": {
        "bg": (13, 17, 23), "surface": (21, 27, 35), "raised": (33, 40, 48),
        "text": (240, 246, 252), "muted": (145, 152, 161),
        "accent": (68, 147, 248), "accent_light": (121, 192, 255),
        "win": (63, 185, 80), "loss": (248, 81, 73), "warn": (210, 153, 34), "purple": (171, 125, 248),
    },
}

# Corner radius by size: (small <= 3 px, medium 4-7 px, large 8-13 px).
# 14 px and up are pills and circles: kept as they are.
SHAPE = {
    "geist": (4, 6, 8),
    "primer": (3, 6, 12),
    "valorant": (0, 0, 0),
}

# The legacy colours by role (from a survey of every stylesheet and paint call).
_LEGACY_ROLES = {
    "accent": ["#4a9fd8", (74, 159, 216)],
    "accent_light": ["#6bb6e8", "#7cc4f0"],
    "muted": ["#8a97aa", "#9aa5b1", "#8e959e", "#7d848d", "#9ba8bc", "#aab7cb", (168, 182, 204), (164, 181, 203)],
    "text": ["#e6ecf5", "#eef4ff", "#e6edf7", "#f4f9ff", "#f2f4f7", "#eef1f5", "#e8ebef", "#dcdcdc", "#d6dae0",
             "#e4eef5", "#f4f7fb", (236, 242, 252), (235, 242, 250), (245, 249, 255), (214, 225, 240),
             (238, 246, 255), (233, 240, 250), (220, 230, 244), (200, 212, 228)],
    "win": ["#66bb6a", "#81c784", "#9cc344"],
    "loss": ["#ef5350", "#e57373", "#ef9a9a", "#e53935", "#e66767", (239, 83, 80), (178, 34, 34)],
    "warn": ["#ffd54f", "#f9a825", "#f0b43c", "#ffb74d", "#f57f17", "#f0c674", (249, 168, 37), (240, 180, 60),
             (255, 221, 87), (255, 213, 79), (255, 193, 7), (230, 126, 34)],
    "purple": ["#b39ddb"],
    "bg": [(15, 15, 15), (10, 10, 10), (9, 14, 22), (10, 14, 22), (11, 14, 20), (12, 16, 24), (12, 17, 26),
           (12, 18, 28), (13, 20, 31), (20, 20, 20), "#141414"],
    "surface": [(16, 20, 28), (16, 24, 36), (18, 23, 33), (18, 25, 36), (20, 24, 30), (25, 25, 25)],
}


def _rgb(value):
    if isinstance(value, tuple):
        return value
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


_ROLE_OF = {_rgb(v): role for role, values in _LEGACY_ROLES.items() for v in values}

_current = None        # theme key once install() ran
_parts = THEMES[DEFAULT_THEME]
_seen = set()          # stylesheets already rewritten (re-setting one must not shift it again)


def theme_key(settings=None):
    if settings is None:
        try:
            from app_settings import load_app_settings
            settings = load_app_settings()
        except Exception:
            settings = {}
    key = settings.get("ui_theme") or DEFAULT_THEME
    return key if key in THEMES else DEFAULT_THEME


_FONT_PX = re.compile(r"(font-size\s*:\s*)(\d+(?:\.\d+)?)px")
_HEIGHT_PX = re.compile(r"((?<![\w-])(?:min-height|max-height|height)\s*:\s*)(\d+(?:\.\d+)?)px")
_text_scale = 1.0
# Code that sizes the in-game mini GUI and HUD buddy: it has its own size
# (hud_scale), so Text size leaves its fixed sizes alone.
_UNSCALED_MODULES = ("OverlayUI", "pet")


def _scale_font_px(text, factor):
    """Font sizes and box heights in a stylesheet, times `factor` (Text size):
    bigger text gets taller boxes instead of being cut off."""
    def times(m):
        return f"{m.group(1)}{max(1, round(float(m.group(2)) * factor))}px"
    return _HEIGHT_PX.sub(times, _FONT_PX.sub(times, text))


def _scale_fixed_sizes(factor):
    """setFixedHeight / setFixedWidth / setFixedSize grow with Text size, so a
    card or button sized for 100% text still fits its text at 125% or 200%.
    Calls from the mini GUI's code (_UNSCALED_MODULES) are left as they are."""
    import sys
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QWidget

    def caller_scales():
        return sys._getframe(2).f_globals.get("__name__") not in _UNSCALED_MODULES

    def grow(value):
        return max(1, round(value * factor)) if value > 1 else value

    fixed_h, fixed_w, fixed_size = QWidget.setFixedHeight, QWidget.setFixedWidth, QWidget.setFixedSize

    def set_fixed_height(self, h):
        fixed_h(self, grow(h) if caller_scales() else h)

    def set_fixed_width(self, w):
        fixed_w(self, grow(w) if caller_scales() else w)

    def set_fixed_size(self, *args):
        if not caller_scales():
            return fixed_size(self, *args)
        size = args[0] if len(args) == 1 else QSize(*args)
        return fixed_size(self, QSize(grow(size.width()), grow(size.height())))

    QWidget.setFixedHeight = set_fixed_height
    QWidget.setFixedWidth = set_fixed_width
    QWidget.setFixedSize = set_fixed_size


def _install_text_scale(app):
    """Settings -> Text size: every stylesheet font size and the default font
    grow by the saved factor. The mini GUI has its own size (hud_scale)."""
    global _text_scale
    from app_settings import get_scale
    _text_scale = get_scale("text_scale")
    if _text_scale == 1.0:
        return
    from PySide6.QtWidgets import QApplication, QWidget
    widget_set, app_set = QWidget.setStyleSheet, QApplication.setStyleSheet

    def widget_scaled(self, text):
        factor = 1.0 if type(self).__name__ == "MinimalOverlay" else _text_scale
        return widget_set(self, _scale_font_px(text, factor) if text and factor != 1.0 else text)

    QWidget.setStyleSheet = widget_scaled
    QApplication.setStyleSheet = lambda self, text: app_set(self, _scale_font_px(text, _text_scale) if text else text)
    _scale_fixed_sizes(_text_scale)
    if app is not None:
        font = app.font()
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * _text_scale)
            app.setFont(font)


def _palette():
    return PALETTE.get(_parts[2])


def family(kind="ui"):
    """The font family for "ui" or "mono" text in the current theme."""
    fam = TYPE[_parts[1]][kind]
    if fam in TYPE["legacy"].values() or fam in _loaded_families:
        return fam
    return TYPE["legacy"][kind]


_SATURATED = ("accent", "accent_light", "win", "loss", "warn", "purple")
_NEUTRAL = ("bg", "surface", "text", "muted")


def _nearest(rgb, roles, limit):
    best = None
    for role in roles:
        for value in _LEGACY_ROLES[role]:
            anchor = _rgb(value)
            d = sum((a - b) ** 2 for a, b in zip(rgb, anchor)) ** 0.5
            if d <= limit and (best is None or d < best[0]):
                best = (d, role, anchor)
    return best


def _map_rgb(rgb):
    """The theme colour for a legacy colour: exact role first, else a colour
    close to a role colour (shades, gradients, computed win-rate colours) moves
    with that role, keeping its offset. Unrelated colours are left alone."""
    pal = _palette()
    if not pal:
        return None
    rgb = tuple(rgb)
    role = _ROLE_OF.get(rgb)
    if role:
        return pal[role]
    hi, lo = max(rgb), min(rgb)
    saturated = hi > 60 and (hi - lo) / hi > 0.25
    near = _nearest(rgb, _SATURATED, 80) if saturated else _nearest(rgb, _NEUTRAL, 28)
    if not near:
        return None
    _d, role, anchor = near
    target = pal[role]
    return tuple(max(0, min(255, t + (c - a))) for t, c, a in zip(target, rgb, anchor))


def qcolor(r, g, b, a=255):
    """A painted colour in the current theme (QColor)."""
    from PySide6.QtGui import QColor
    mapped = _map_rgb((r, g, b))
    return QColor(*(mapped or (r, g, b)), a)


_HEX = re.compile(r"#([0-9a-fA-F]{6})\b")
_RGB = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(,[^)]*)?\)")
_RADIUS = re.compile(r"((?:border(?:-(?:top|bottom)-(?:left|right))?-radius)\s*:\s*)(\d+)px")
_FONT = re.compile(r"(font-family\s*:\s*)([^;}\n]+)")


def _radius(px):
    shape = SHAPE.get(_parts[3])
    if shape is None or px >= 14 or px == 0:
        return px
    small, medium, large = shape
    return small if px <= 3 else medium if px <= 7 else large


def _fonts(value):
    names = [n.strip().strip("'\"") for n in value.split(",")]
    out = []
    for name in names:
        low = name.lower()
        if low in ("segoe ui", "san francisco") and family("ui") != "Segoe UI":
            out.append(family("ui"))
        elif low == "consolas" and family("mono") != "Consolas":
            out.append(family("mono"))
        out.append(name)
    seen, uniq = set(), []
    for name in out:
        if name.lower() not in seen:
            seen.add(name.lower())
            uniq.append(name)
    return ", ".join(n if n in ("monospace", "sans-serif", "serif") else f"'{n}'" for n in uniq)


def css(text):
    """A stylesheet rewritten for the current theme (unchanged for legacy)."""
    if not text or _current in (None, "legacy") or text in _seen:
        return text
    pal = _palette()

    def hex_sub(m):
        mapped = _map_rgb(_rgb("#" + m.group(1).lower()))
        return "#%02x%02x%02x" % mapped if mapped else m.group(0)

    def rgb_sub(m):
        mapped = _map_rgb((int(m.group(1)), int(m.group(2)), int(m.group(3))))
        if not mapped:
            return m.group(0)
        alpha = m.group(4)
        return f"rgba({mapped[0]}, {mapped[1]}, {mapped[2]}{alpha})" if alpha else "rgb(%d, %d, %d)" % mapped

    out = text
    if pal:
        out = _RGB.sub(rgb_sub, _HEX.sub(hex_sub, out))
    out = _RADIUS.sub(lambda m: f"{m.group(1)}{_radius(int(m.group(2)))}px", out)
    out = _FONT.sub(lambda m: m.group(1) + _fonts(m.group(2)), out)
    if len(_seen) < 20000:
        _seen.add(out)
    return out


_loaded_families = set()


def _load_fonts():
    try:
        from PySide6.QtGui import QFontDatabase
    except Exception:
        return
    if not os.path.isdir(FONT_DIR):
        return
    for name in sorted(os.listdir(FONT_DIR)):
        if name.lower().endswith((".ttf", ".otf")):
            fid = QFontDatabase.addApplicationFont(os.path.join(FONT_DIR, name))
            if fid >= 0:
                _loaded_families.update(QFontDatabase.applicationFontFamilies(fid))


def _mapped_args(args):
    """QColor(...) arguments with a legacy colour swapped for the theme's."""
    if len(args) == 1 and isinstance(args[0], str):
        text = args[0].strip()
        if re.fullmatch(r"#[0-9a-fA-F]{6}", text):
            mapped = _map_rgb(_rgb(text.lower()))
            return ("#%02x%02x%02x" % mapped,) if mapped else args
        if re.fullmatch(r"#[0-9a-fA-F]{8}", text):  # Qt's #AARRGGBB
            mapped = _map_rgb(_rgb("#" + text[3:].lower()))
            return (text[:3] + "%02x%02x%02x" % mapped,) if mapped else args
        return args
    if len(args) in (3, 4) and all(isinstance(a, int) for a in args):
        mapped = _map_rgb(args[:3])
        return (*mapped, *args[3:]) if mapped else args
    return args


def _themed_qcolor():
    from PySide6.QtGui import QColor

    class ThemedColor(QColor):
        """QColor that swaps legacy colours for the theme's (painted UI)."""

        def __init__(self, *args):
            if len(args) == 1 and isinstance(args[0], QColor):
                # A copy (the subclass confuses PySide's copy constructor).
                super().__init__()
                self.setRgba64(args[0].rgba64())
                return
            super().__init__(*_mapped_args(args))

    return QColor, ThemedColor


def install(app=None, key=None):
    """Apply the saved theme to this process (call right after QApplication
    exists, before widgets are built). Legacy: nothing happens."""
    global _current, _parts
    if _current is not None:
        return _current
    try:
        from PySide6.QtWidgets import QApplication
        _install_text_scale(app or QApplication.instance())
    except Exception:
        pass
    key = key or theme_key()
    _current, _parts = key, THEMES[key]
    if key == "legacy":
        return key
    import sys
    from PySide6 import QtGui
    from PySide6.QtWidgets import QApplication, QWidget
    _load_fonts()
    widget_set, app_set = QWidget.setStyleSheet, QApplication.setStyleSheet
    QWidget.setStyleSheet = lambda self, text: widget_set(self, css(text))
    QApplication.setStyleSheet = lambda self, text: app_set(self, css(text))
    # Painted colours: the app's modules (already imported or imported later)
    # get a QColor that maps legacy colours. Qt's own QColor is untouched.
    base, themed = _themed_qcolor()
    QtGui.QColor = themed
    for name, module in list(sys.modules.items()):
        path = getattr(module, "__file__", None) or ""
        if not path or os.path.dirname(os.path.abspath(path)) != BASE_DIR:
            continue
        if getattr(module, "QColor", None) is base:
            module.QColor = themed
        # Colour constants built at import time, before the theme was known.
        for attr, value in list(vars(module).items()):
            if type(value) is base:
                setattr(module, attr, themed(value.red(), value.green(), value.blue(), value.alpha()))
    app = app or QApplication.instance()
    if app is not None:
        font = app.font()
        font.setFamily(family("ui"))
        app.setFont(font)
    return key
