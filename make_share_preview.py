"""Draws docs/d/preview.png, the link-preview image of the share page
(Discord, WhatsApp, iMessage...): 1200x630, in the page's own terminal
style: the page's pixel-font logo, the pixel Pokeball, and what the
link is. Run it after changing the
look:  python make_share_preview.py
"""
import math
import os
import random
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

W, H = 1200, 630
BG, FG, DIM, RULE, ACCENT = "#0c0d0f", "#d8dbe0", "#6c7380", "#23262c", "#e8c547"
OUT = os.path.join(BASE_DIR, "docs", "d", "preview.png")

# the page's logo font (docs/d/index.html GLYPHS), 5x6 per letter
GLYPHS = {
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#...."], "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "C": [".###.", "#...#", "#....", "#....", "#...#", ".###."], "G": [".###.", "#....", "#....", "#..##", "#...#", ".###."],
    "L": ["#....", "#....", "#....", "#....", "#....", "#####"], "M": ["#...#", "##.##", "#.#.#", "#...#", "#...#", "#...#"],
    "O": [".###.", "#...#", "#...#", "#...#", "#...#", ".###."], "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"],
    "I": ["###", ".#.", ".#.", ".#.", ".#.", "###"], "R": ["####.", "#...#", "#...#", "####.", "#..#.", "#...#"],
    " ": ["..", "..", "..", "..", "..", ".."],
}
STRAY = "./\\|-_:;+*=~^`',<>[]{}()?!#%&$@"


def mono(size, bold=False):
    for family in ("Cascadia Mono", "Consolas"):
        if family in QFontDatabase.families():
            font = QFont(family)
            break
    else:
        font = QFont("monospace")
    font.setPixelSize(size)
    font.setBold(bold)
    return font


def logo_bits(text="PTCGL MONITOR"):
    rows = [[] for _ in range(6)]
    for ch in text:
        for y, line in enumerate(GLYPHS[ch]):
            rows[y].extend(b == "#" for b in line + ".")
    return rows


def _hash(a, b, c):
    """The page's hash (startLogo in docs/d/index.html), same doubles, same results."""
    v = math.sin(a * 127.1 + b * 311.7 + c * 74.7) * 43758.5453
    return v - math.floor(v)


def header_logo(t=1.5):
    """The site header's ASCII logo as rows of (character, colour), exactly as
    the page draws it with motion off: the pixel font in two characters per
    pixel, a light shadow, frayed strokes and stray ASCII around it. No beam:
    a still."""
    bits = logo_bits()
    width = (len(bits[0]) - 1) * 2
    ink = lambda sx, y: 0 <= y < 6 and 0 <= sx < width and bits[y][sx >> 1]  # noqa: E731
    rows = []
    for y in range(7):
        row = []
        for sx in range(width + 6):
            flick = math.floor(t * 9 + _hash(sx, y, 3) * 9)
            if ink(sx, y):
                if _hash(sx, y, math.floor(t * 2.5 + _hash(sx, y, 5) * 4)) < 0.07:  # frayed strokes
                    row.append((STRAY[math.floor(_hash(sx, y, flick) * len(STRAY))], FG))
                else:
                    row.append(("█", FG))
            elif ink(sx - 1, y - 1) or ink(sx - 2, y - 1):
                row.append(("░", DIM))  # drop shadow
            else:
                slow = math.floor(t * 0.7 + _hash(sx, y, 9) * 5)
                dense = 0.2 if sx < width + 4 else 0.26
                if _hash(sx, y, slow) < dense:
                    row.append((STRAY[math.floor(_hash(sx, y, slow + 7) * len(STRAY))], DIM))
                else:
                    row.append((" ", None))
        rows.append(row)
    return rows


def draw(p):
    rnd = random.Random(7)
    p.fillRect(0, 0, W, H, QColor(BG))
    # stray ASCII grain, faint, kept off the text
    clear = [QRectF(60, 40, 520, 50), QRectF(50, 120, 1100, 130), QRectF(60, 270, 800, 210),
             QRectF(60, 520, 820, 60)]
    p.setFont(mono(15))
    placed = 0
    while placed < 300:
        x, y = rnd.randint(0, W), rnd.randint(12, H)
        if any(r.contains(x, y) for r in clear):
            continue
        placed += 1
        p.setPen(QColor(RULE) if rnd.random() < 0.8 else QColor(DIM))
        p.drawText(x, y, rnd.choice(STRAY))

    # header line, like the page
    left = 72
    p.setFont(mono(22))
    p.setPen(QColor(DIM))
    p.drawText(left, 78, "> decklist")
    p.setPen(QColor(RULE))
    p.fillRect(left, 98, W - 2 * left, 2, QColor(RULE))

    # the logo: the site header's ASCII art, character for character
    logo = header_logo()
    size = 11  # font px, line height 1 like the header: the logo spans the banner
    p.setFont(mono(size))
    advance = p.fontMetrics().horizontalAdvance("█")
    for y, row in enumerate(logo):
        for x, (ch, color) in enumerate(row):
            if color:
                p.setPen(QColor(color))
                p.drawText(QRectF(left + x * advance, 140 + y * size, advance, size * 1.6),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, ch)

    # what the link is
    p.setPen(QColor(FG))
    p.setFont(mono(46, bold=True))
    p.drawText(left, 330, "Pokémon TCG Live decklist")
    p.setPen(QColor(ACCENT))
    p.setFont(mono(25))
    p.drawText(left, 396, "the whole list lives in the link.")

    # the pixel Pokeball, big, bottom right
    import OverlayUI
    ball = OverlayUI._ball_art("poke")
    scale = 22
    bx, by = W - left - ball.width() * scale, H - 72 - ball.height() * scale
    p.drawImage(QRectF(bx, by, ball.width() * scale, ball.height() * scale), ball)

    # footer
    p.fillRect(left, H - 96, W - 2 * left - ball.width() * scale - 40, 2, QColor(RULE))
    p.setFont(mono(22))
    p.setPen(QColor(DIM))
    p.drawText(left, H - 58, "PTCGL Monitor · lavahawk.github.io/Pokemon-TCG-Live-Monitor")


def main():
    if QApplication.instance() is None:  # fonts need an application
        main.app = QApplication([])
    img = QImage(W, H, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
    draw(p)
    p.end()
    img.save(OUT, "PNG", 9)
    print(f"wrote {OUT} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
