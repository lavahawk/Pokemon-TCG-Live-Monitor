"""Five app-icon directions for PTCGL Monitor, three variations each.

Writes one SVG per icon next to this file, renders them with Qt, and lays
out a review board (board.png): every icon at 256 px plus 32 and 16 px.
Original marks only: cards, charts, reticles, letterforms. No game IP.

    python branding/icon_concepts/make_icons.py
"""
import os
import sys

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

HERE = os.path.dirname(os.path.abspath(__file__))

# One disciplined palette: the app's blue, rank gold, near-black navy.
NAVY, NAVY2, BLUE, BLUE2, GOLD, WHITE, INK = ("#0E1726", "#16243A", "#4A9FD8", "#7CC4F2",
                                             "#F2B83D", "#F4F7FB", "#0B1220")

PALETTES = {
    "Night": dict(bg1=NAVY2, bg2=NAVY, main=BLUE, alt=GOLD, line=WHITE),
    "Gold": dict(bg1="#F6C453", bg2="#E0A126", main=INK, alt=NAVY2, line=INK),
    "Ice": dict(bg1="#FFFFFF", bg2="#E6EEF7", main="#2F7FBF", alt=GOLD, line=NAVY),
}


def tile(p, body):
    """A Windows-style rounded square tile with a soft vertical gradient."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{p['bg1']}"/><stop offset="1" stop-color="{p['bg2']}"/></linearGradient></defs>
<rect x="8" y="8" width="240" height="240" rx="54" fill="url(#g)"/>
{body}
</svg>"""


def pulse_card(p):
    """1 · Pulse Card - product action: the app watches every battle. A card
    with a live signal line running through it (monitor + stats)."""
    return tile(p, f"""
<rect x="66" y="40" width="124" height="176" rx="18" fill="none" stroke="{p['main']}" stroke-width="14"/>
<polyline points="34,140 92,140 112,104 136,172 156,124 168,140 222,140" fill="none"
 stroke="{p['alt']}" stroke-width="16" stroke-linecap="round" stroke-linejoin="round"/>""")


def ascent_stack(p):
    """2 · Ascent - construction: three cards stand as a rising bar chart;
    the last one is tallest and notched with an up-chevron (rank climbing)."""
    return tile(p, f"""
<g fill="none" stroke-width="11" stroke-linejoin="round">
<rect x="42" y="136" width="50" height="78" rx="9" stroke="{p['main']}" opacity="0.5"/>
<rect x="103" y="102" width="50" height="112" rx="9" stroke="{p['main']}" opacity="0.75"/></g>
<rect x="158" y="56" width="58" height="160" rx="11" fill="{p['main']}"/>
<path d="M170 108 L187 88 L204 108" fill="none" stroke="{p['alt']}" stroke-width="11"
 stroke-linecap="round" stroke-linejoin="round"/>""")


def scope(p):
    """3 · Scope - metaphor fusion: the HUD's reticle locked on a card.
    The overlay that sits on the game, read as one mark."""
    return tile(p, f"""
<circle cx="128" cy="128" r="84" fill="none" stroke="{p['main']}" stroke-width="12"/>
<g stroke="{p['main']}" stroke-width="12" stroke-linecap="round">
<line x1="128" y1="26" x2="128" y2="52"/><line x1="128" y1="204" x2="128" y2="230"/>
<line x1="26" y1="128" x2="52" y2="128"/><line x1="204" y1="128" x2="230" y2="128"/></g>
<rect x="100" y="88" width="56" height="80" rx="9" fill="{p['alt']}" transform="rotate(-12 128 128)"/>""")


def m_fold(p):
    """4 · Fold M - monogram + meaning: two tilted cards lean on each other
    and the gap between them draws the M of Monitor."""
    return tile(p, f"""
<g transform="translate(128 132)">
<rect x="-92" y="-70" width="62" height="136" rx="11" fill="{p['main']}" transform="rotate(-8 -61 -2)"/>
<rect x="30" y="-70" width="62" height="136" rx="11" fill="{p['main']}" transform="rotate(8 61 -2)"/>
<path d="M-40 -58 L0 16 L40 -58" fill="none" stroke="{p['alt']}" stroke-width="18"
 stroke-linecap="round" stroke-linejoin="round"/></g>""")


def hex_log(p):
    """5 · Logbook - negative space: a hex badge with a card cut out of it,
    the card's folded corner pointing up-right like an export arrow."""
    return tile(p, f"""
<polygon points="128,30 213,79 213,177 128,226 43,177 43,79" fill="{p['main']}"/>
<path d="M98 82 H146 L166 102 V172 Q166 178 160 178 H98 Q92 178 92 172 V88 Q92 82 98 82 Z" fill="{p['bg2']}"/>
<path d="M146 82 V102 H166" fill="none" stroke="{p['main']}" stroke-width="6" stroke-linejoin="round"/>
<g stroke="{p['alt']}" stroke-width="9" stroke-linecap="round">
<line x1="106" y1="124" x2="150" y2="124"/><line x1="106" y1="144" x2="140" y2="144"/>
<line x1="106" y1="164" x2="146" y2="164"/></g>""")


CONCEPTS = [
    ("1  Pulse Card", "Live signal through a card: it watches every battle.", pulse_card),
    ("2  Ascent", "Cards as a rising bar chart: your rank, climbing.", ascent_stack),
    ("3  Scope", "The HUD's reticle on a card: the overlay as a mark.", scope),
    ("4  Fold M", "Two leaning cards draw the M of Monitor.", m_fold),
    ("5  Logbook", "A battle log cut out of a badge, corner folded up.", hex_log),
]


def render(svg, size):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return img


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in ("segoeui.ttf", "seguisb.ttf"):
        QFontDatabase.addApplicationFont(os.path.join(fonts, name))
    big, gap, label_w, pad = 200, 28, 300, 48
    cols = len(PALETTES)
    cell = big + 34 + 16 + 3 * gap
    width = pad * 2 + label_w + cols * cell
    height = pad * 2 + 70 + len(CONCEPTS) * (big + gap * 2)
    board = QImage(width, height, QImage.Format.Format_ARGB32)
    board.fill(QColor("#101114"))
    p = QPainter(board)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor("#E8ECF2"))
    p.setFont(QFont("Segoe UI", 22, QFont.Weight.DemiBold))
    p.drawText(pad, pad + 30, "PTCGL Monitor  ·  app icon directions")
    p.setPen(QColor("#7D8594"))
    p.setFont(QFont("Segoe UI", 11))
    p.drawText(pad, pad + 56, "Each at 200 px, then 32 and 16 px (taskbar / tray size).   "
                              "Variations:  " + "  ·  ".join(PALETTES))
    for row, (title, idea, make) in enumerate(CONCEPTS):
        y = pad + 70 + row * (big + gap * 2) + gap
        p.setPen(QColor("#E8ECF2"))
        p.setFont(QFont("Segoe UI", 16, QFont.Weight.DemiBold))
        p.drawText(pad, y + 60, title)
        p.setPen(QColor("#8A93A3"))
        p.setFont(QFont("Segoe UI", 10))
        p.drawText(QRectF(pad, y + 76, label_w - 30, 80), Qt.TextFlag.TextWordWrap, idea)
        for col, (pal_name, pal) in enumerate(PALETTES.items()):
            svg = make(pal)
            slug = f"{row + 1}_{make.__name__}_{pal_name.lower()}"
            with open(os.path.join(HERE, slug + ".svg"), "w", encoding="utf-8") as fh:
                fh.write(svg)
            x = pad + label_w + col * cell
            p.drawImage(x, y, render(svg, big))
            p.drawImage(x + big + gap, y + big - 32 - 24, render(svg, 32))
            p.drawImage(x + big + gap + 34 + gap // 2, y + big - 16 - 24, render(svg, 16))
    p.end()
    out = os.path.join(HERE, "board.png")
    board.save(out)
    print(out)


if __name__ == "__main__":
    main()
