"""Round 3: the Card back direction, a ball as the eye's iris, in three
layouts and six colour themes.

    python branding/icon_concepts/make_icons_v3.py   ->  board_v3.png + v3_*.png
"""
import math
import os
import sys

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_icons_v2 import S, canvas, card_path, family, grain, shadow, to_np, to_qimage  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# base (card), deep (pattern ground), line (pattern), frame, sclera (eye white), ball top
THEMES = {
    "Midnight Gold": dict(base="#0C1424", deep="#16243D", line=(70, 118, 170), frame="#E2A83A",
                          sclera="#F1E7D0", top="#D8362F"),
    "Ember": dict(base="#2A0B10", deep="#4A121B", line=(150, 52, 60), frame="#F0B44A",
                  sclera="#F6E9D6", top="#E0412F"),
    "Forest": dict(base="#0A1C15", deep="#123326", line=(52, 128, 92), frame="#B9E27A",
                   sclera="#EEF2E2", top="#D8362F"),
    "Royal": dict(base="#170F2E", deep="#28194F", line=(120, 92, 190), frame="#E8C25A",
                  sclera="#F2ECF8", top="#D8362F"),
    "Lagoon": dict(base="#04222A", deep="#0A3842", line=(40, 150, 160), frame="#6FE3D6",
                   sclera="#EAF8F6", top="#E5483A"),
    "Graphite": dict(base="#121316", deep="#1E2026", line=(90, 94, 104), frame="#E2362F",
                     sclera="#F3F3F1", top="#E2362F"),
}


def ball(p, r, top):
    """The ball: coloured top, white bottom, dark band and button."""
    clip = QPainterPath()
    clip.addEllipse(QPointF(0, 0), r, r)
    p.save()
    p.setClipPath(clip)
    shade = QRadialGradient(QPointF(-r * 0.35, -r * 0.45), r * 1.4)
    shade.setColorAt(0, QColor(top).lighter(125))
    shade.setColorAt(1, QColor(top).darker(115))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(shade)
    p.drawRect(QRectF(-r, -r, 2 * r, r))
    low = QRadialGradient(QPointF(-r * 0.3, r * 0.2), r * 1.3)
    low.setColorAt(0, QColor("#FFFFFF"))
    low.setColorAt(1, QColor("#D9DCE2"))
    p.setBrush(low)
    p.drawRect(QRectF(-r, 0, 2 * r, r))
    p.setBrush(QColor("#15161A"))
    p.drawRect(QRectF(-r, -r * 0.11, 2 * r, r * 0.22))
    p.restore()
    p.setPen(QPen(QColor("#15161A"), r * 0.1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(0, 0), r, r)
    p.setBrush(QColor("#15161A"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(0, 0), r * 0.36, r * 0.36)
    p.setBrush(QColor("#F7F7F4"))
    p.drawEllipse(QPointF(0, 0), r * 0.22, r * 0.22)
    # a catch-light, so it reads as an eye looking at you
    p.setBrush(QColor(255, 255, 255, 190))
    p.drawEllipse(QPointF(-r * 0.42, -r * 0.5), r * 0.14, r * 0.1)


def eye(p, t, w, h, r_ball, lid=12):
    path = QPainterPath()
    path.moveTo(-w, 0)
    path.quadTo(0, -h, w, 0)
    path.quadTo(0, h, -w, 0)
    p.setPen(QPen(QColor(t["sclera"]), lid))
    p.setBrush(QColor(t["base"]))
    p.drawPath(path)
    p.save()
    p.setClipPath(path)
    ball(p, r_ball, t["top"])
    p.restore()


def weave(p, t, step=26):
    c = QColor(*t["line"], 120)
    p.setPen(QPen(c, 3))
    for k in range(-14, 15):
        p.drawLine(QPointF(k * step - 260, -260), QPointF(k * step + 260, 260))
        p.drawLine(QPointF(k * step + 260, -260), QPointF(k * step - 260, 260))


def hexes(p, t, r=24):
    c = QColor(*t["line"], 135)
    p.setPen(QPen(c, 3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    dx, dy = r * math.sqrt(3), r * 1.5
    for row in range(-10, 11):
        for col in range(-8, 9):
            cx = col * dx + (dx / 2 if row % 2 else 0)
            cy = row * dy
            hexagon = QPainterPath()
            for k in range(6):
                a = math.radians(60 * k - 30)
                pt = QPointF(cx + r * math.cos(a), cy + r * math.sin(a))
                hexagon.moveTo(pt) if k == 0 else hexagon.lineTo(pt)
            hexagon.closeSubpath()
            p.drawPath(hexagon)


def rays(p, t):
    """Sunburst from the eye: the watcher at the centre of the card."""
    c = QColor(*t["line"], 110)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    for k in range(24):
        if k % 2:
            continue
        a0, a1 = math.radians(k * 15), math.radians((k + 1) * 15)
        wedge = QPainterPath(QPointF(0, 0))
        wedge.lineTo(QPointF(400 * math.cos(a0), 400 * math.sin(a0)))
        wedge.lineTo(QPointF(400 * math.cos(a1), 400 * math.sin(a1)))
        wedge.closeSubpath()
        p.drawPath(wedge)


def card(t, layout):
    img, p = canvas()
    p.translate(S / 2, S / 2)
    p.rotate(6 if layout != "Bold" else 0)
    outer = card_path(-160, -215, 320, 430, 28)
    shadow(p, outer)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(t["base"]))
    p.drawPath(outer)
    inner = card_path(-138, -193, 276, 386, 16)
    p.save()
    p.setClipPath(inner)
    grad = QLinearGradient(0, -193, 0, 193)
    grad.setColorAt(0, QColor(t["deep"]).lighter(112))
    grad.setColorAt(1, QColor(t["deep"]))
    p.setBrush(grad)
    p.drawRect(QRectF(-160, -215, 320, 430))
    if layout == "Weave":
        weave(p, t)
    elif layout == "Hex":
        hexes(p, t)
    else:
        rays(p, t)
    p.restore()
    p.setPen(QPen(QColor(t["frame"]), 7 if layout != "Bold" else 12))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-138, -193, 276, 386), 16, 16)
    if layout == "Bold":
        # corner pips, like a card back's printed corners
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["frame"]))
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            p.drawEllipse(QPointF(sx * 108, sy * 163), 9, 9)
        eye(p, t, 134, 172, 72, lid=14)
    elif layout == "Hex":
        eye(p, t, 122, 150, 62)
    else:
        eye(p, t, 126, 146, 60)
    p.end()
    return grain(to_np(img), 5)


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    segoe = family("segoeui.ttf")
    family("seguisb.ttf")
    layouts = ["Weave", "Hex", "Bold"]
    tile, gap, pad, label_w = 176, 22, 46, 120
    width = pad * 2 + label_w + len(THEMES) * (tile + gap) - gap
    row_h = tile + 64 + gap * 2
    height = pad * 2 + 70 + 30 + len(layouts) * row_h
    board = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    board.fill(QColor("#141519"))
    p = QPainter(board)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setPen(QColor("#E8ECF2"))
    p.setFont(QFont(segoe, 20, QFont.Weight.DemiBold))
    p.drawText(pad, pad + 26, "Card back  ·  three layouts × six colour themes")
    p.setFont(QFont(segoe, 12, QFont.Weight.DemiBold))
    for c, name in enumerate(THEMES):
        p.drawText(QPointF(pad + label_w + c * (tile + gap), pad + 84), name)
    for r, layout in enumerate(layouts):
        y = pad + 100 + r * row_h
        p.setPen(QColor("#E8ECF2"))
        p.setFont(QFont(segoe, 15, QFont.Weight.DemiBold))
        p.drawText(QPointF(pad, y + tile / 2), layout)
        for c, (name, theme) in enumerate(THEMES.items()):
            img = to_qimage(card(theme, layout))
            img.save(os.path.join(HERE, f"v3_{layout.lower()}_{name.lower().replace(' ', '_')}.png"))
            x = pad + label_w + c * (tile + gap)
            p.fillRect(QRectF(x, y, tile, tile), QColor("#1E2027"))
            p.drawImage(QRectF(x + 10, y + 10, tile - 20, tile - 20), img)
            for k, (size, bg) in enumerate(((32, "#E9EBEF"), (16, "#E9EBEF"), (32, "#202227"), (16, "#202227"))):
                bx = x + k * (tile / 4)
                p.fillRect(QRectF(bx, y + tile + 8, tile / 4, 52), QColor(bg))
                small = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                p.drawImage(QPointF(bx + (tile / 4 - size) / 2, y + tile + 8 + (52 - size) / 2), small)
    p.end()
    out = os.path.join(HERE, "board_v3.png")
    board.save(out)
    print(out)


if __name__ == "__main__":
    main()
