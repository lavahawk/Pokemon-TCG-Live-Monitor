"""Round 4: the Hex card back in red (Ember) and purple (Royal), redrawn in
other art styles: the textured original, flat 2D, pixel art (32 and 16),
3D, ASCII and neon line.

    python branding/icon_concepts/make_icons_v4.py   ->  board_v4.png + v4_*.png
"""
import math
import os
import sys

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_icons_v2 import S, canvas, card_path, family, shadow, to_np, to_qimage  # noqa: E402
from make_icons_v3 import THEMES, card, hexes  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DARK = "#15161A"
PICKS = {"Red & black": THEMES["Graphite"], "Purple": THEMES["Royal"]}


# ── flat 2D: same shapes, solid fills, no grain or gradients ────────────
def flat_ball(p, r, top, outline=True):
    clip = QPainterPath()
    clip.addEllipse(QPointF(0, 0), r, r)
    p.save()
    p.setClipPath(clip)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(top))
    p.drawRect(QRectF(-r, -r, 2 * r, r))
    p.setBrush(QColor("#FFFFFF"))
    p.drawRect(QRectF(-r, 0, 2 * r, r))
    p.setBrush(QColor(DARK))
    p.drawRect(QRectF(-r, -r * 0.12, 2 * r, r * 0.24))
    p.restore()
    if outline:
        p.setPen(QPen(QColor(DARK), r * 0.12))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(0, 0), r, r)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(DARK))
    p.drawEllipse(QPointF(0, 0), r * 0.38, r * 0.38)
    p.setBrush(QColor("#FFFFFF"))
    p.drawEllipse(QPointF(0, 0), r * 0.22, r * 0.22)


def eye_path(w, h):
    path = QPainterPath()
    path.moveTo(-w, 0)
    path.quadTo(0, -h, w, 0)
    path.quadTo(0, h, -w, 0)
    return path


def flat(t, with_ball=True, hex_r=30, line_w=6):
    img, p = canvas()
    p.translate(S / 2, S / 2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(t["base"]))
    p.drawPath(card_path(-170, -225, 340, 450, 30))
    inner = card_path(-146, -201, 292, 402, 18)
    p.save()
    p.setClipPath(inner)
    p.setBrush(QColor(t["deep"]))
    p.drawRect(QRectF(-170, -225, 340, 450))
    p.setPen(QPen(QColor(*t["line"]), line_w))
    p.setBrush(Qt.BrushStyle.NoBrush)
    dx, dy = hex_r * math.sqrt(3), hex_r * 1.5
    for row in range(-9, 10):
        for col in range(-6, 7):
            cx, cy = col * dx + (dx / 2 if row % 2 else 0), row * dy
            hexagon = QPainterPath()
            for k in range(6):
                a = math.radians(60 * k - 30)
                pt = QPointF(cx + hex_r * math.cos(a), cy + hex_r * math.sin(a))
                hexagon.moveTo(pt) if k == 0 else hexagon.lineTo(pt)
            hexagon.closeSubpath()
            p.drawPath(hexagon)
    p.restore()
    p.setPen(QPen(QColor(t["frame"]), 12))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-146, -201, 292, 402), 18, 18)
    eye = eye_path(136, 168)
    p.setPen(QPen(QColor(t["sclera"]), 16))
    p.setBrush(QColor(t["base"]))
    p.drawPath(eye)
    if with_ball:
        p.save()
        p.setClipPath(eye)
        flat_ball(p, 68, t["top"])
        p.restore()
    p.end()
    return to_np(img)


# ── pixel art: drawn on the grid itself, not a shrunk picture ──────────
def pixel(t, grid):
    """Every shape placed on whole pixels with no anti-aliasing: card,
    frame, a sparse dot pattern for the hexes, the eye and the ball."""
    img = QImage(grid, grid, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    u = grid / 32.0                                   # one "pixel" at 32
    def rect(x, y, w, h, c):
        p.fillRect(int(x * u), int(y * u), max(1, int(w * u)), max(1, int(h * u)), QColor(c))
    dark = QColor(t["base"]).darker(160).name()
    rect(5, 1, 22, 30, DARK)                          # outline
    rect(6, 2, 20, 28, t["base"])
    rect(7, 3, 18, 26, t["frame"])                   # frame
    rect(8, 4, 16, 24, t["deep"])
    line = QColor(*t["line"]).name()
    step = 3 if grid == 32 else 4
    for yy in range(5, 27, step):                    # the hex weave, as dots
        for xx in range(9 + (yy // step) % 2, 23, step):
            rect(xx, yy, 1, 1, line)
    # the eye: a lens of sclera rows, then the ball over its middle
    lens = [(10, 13, 12), (9, 14, 14), (8, 15, 16), (8, 16, 16), (8, 17, 16), (9, 18, 14), (10, 19, 12)]
    if grid == 16:
        lens = [(10, 12, 12), (8, 14, 16), (8, 16, 16), (8, 18, 16), (10, 20, 12)]
    for x0, y0, w0 in lens:
        rect(x0, y0 - 1, w0, 1 if grid == 32 else 2, t["sclera"])
    for x0, y0, w0 in lens[1:-1]:
        rect(x0 + 2, y0 - 1, w0 - 4, 1 if grid == 32 else 2, t["base"])
    if grid == 32:
        ball_rows = [(14, 12, 4), (13, 13, 6), (12, 14, 8), (12, 15, 8), (12, 16, 8), (12, 17, 8), (13, 18, 6), (14, 19, 4)]
        for i, (x0, y0, w0) in enumerate(ball_rows):
            rect(x0, y0, w0, 1, t["top"] if i < 3 else "#FFFFFF")
        rect(12, 15, 8, 1, DARK)                     # the band
        rect(15, 15, 2, 2, DARK)
        rect(15, 15, 2, 1, "#FFFFFF")                # the button
        rect(14, 13, 1, 1, "#FFFFFF")                # catch-light
    else:
        rect(12, 12, 8, 4, t["top"])
        rect(12, 16, 8, 4, "#FFFFFF")
        rect(12, 15, 8, 2, DARK)
        rect(14, 14, 4, 4, DARK)
        rect(15, 15, 2, 2, "#FFFFFF")
    p.end()
    arr = to_np(img)
    return cv2.resize(arr, (S, S), interpolation=cv2.INTER_NEAREST)


def pixel16(t):
    """16 px laid out on its own grid: at this size every pixel is placed."""
    img = QImage(16, 16, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    def px(x, y, c, w=1, h=1):
        p.fillRect(x, y, w, h, QColor(c))
    px(2, 0, DARK, 12, 16)
    px(3, 1, t["frame"], 10, 14)
    px(4, 2, t["deep"], 8, 12)
    line = QColor(*t["line"]).lighter(120).name()
    for x, y in ((5, 3), (10, 3), (7, 3), (5, 12), (8, 12), (10, 12)):
        px(x, y, line)
    sc, base = t["sclera"], t["base"]
    px(5, 5, sc, 6)                               # upper lid
    for y in (6, 7, 8):
        px(4, y, sc)
        px(11, y, sc)
        px(5, y, base)
        px(10, y, base)
    px(6, 6, t["top"], 4)                         # the ball
    px(6, 7, DARK, 4)
    px(7, 7, "#FFFFFF", 2)
    px(6, 8, "#FFFFFF", 4)
    px(5, 9, sc, 6)                               # lower lid
    p.end()
    return cv2.resize(to_np(img), (S, S), interpolation=cv2.INTER_NEAREST)


# ── 3D: the card tilted in space, with thickness and a raised glossy ball ──
def three_d(t):
    face = flat(t, with_ball=False)
    h, w = face.shape[:2]
    src = np.float32([[86, 31], [426, 31], [426, 481], [86, 481]])
    dst = np.float32([[132, 52], [420, 86], [400, 470], [104, 436]])
    m = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(face, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT)
    img, p = canvas()
    # thickness: the card's edge, stacked below and to the left
    edge = warped.copy()
    edge[..., :3] = (np.array(QColor(t["base"]).darker(170).getRgb()[:3])).astype(np.uint8)
    for k in range(14, 0, -1):
        layer = np.roll(np.roll(edge, k, axis=0), -k // 2, axis=1)
        p.drawImage(0, 0, to_qimage(layer))
    # soft ground shadow
    shade = np.zeros_like(warped)
    shade[..., 3] = cv2.GaussianBlur(warped[..., 3], (0, 0), 14) * 0.45
    p.drawImage(10, 34, to_qimage(shade))
    for k in range(14, 0, -1):
        layer = np.roll(np.roll(edge, k, axis=0), -k // 2, axis=1)
        p.drawImage(0, 0, to_qimage(layer))
    # lit face: brighter at the top-left
    lit = warped.astype(np.float32)
    ys, xs = np.mgrid[0:h, 0:w]
    light = 1.18 - 0.0009 * (xs + ys)
    lit[..., :3] *= np.clip(light, 0.8, 1.25)[..., None]
    p.drawImage(0, 0, to_qimage(np.clip(lit, 0, 255).astype(np.uint8)))
    # the ball, raised off the card: a shaded sphere with its own shadow
    cx, cy = cv2.perspectiveTransform(np.float32([[[256, 256]]]), m)[0, 0]
    r = 74
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 90))
    p.drawEllipse(QPointF(cx + 14, cy + 22), r * 1.02, r * 0.9)
    p.translate(cx, cy - 10)
    clip = QPainterPath()
    clip.addEllipse(QPointF(0, 0), r, r)
    p.save()
    p.setClipPath(clip)
    topg = QRadialGradient(QPointF(-r * 0.35, -r * 0.55), r * 1.5)
    topg.setColorAt(0, QColor(t["top"]).lighter(140))
    topg.setColorAt(0.6, QColor(t["top"]))
    topg.setColorAt(1, QColor(t["top"]).darker(170))
    p.setBrush(topg)
    p.drawRect(QRectF(-r, -r, 2 * r, r))
    botg = QRadialGradient(QPointF(-r * 0.35, -r * 0.2), r * 1.6)
    botg.setColorAt(0, QColor("#FFFFFF"))
    botg.setColorAt(1, QColor("#9EA3AD"))
    p.setBrush(botg)
    p.drawRect(QRectF(-r, 0, 2 * r, r))
    p.setBrush(QColor(DARK))
    p.drawRect(QRectF(-r, -r * 0.1, 2 * r, r * 0.2))
    p.restore()
    p.setPen(QPen(QColor(DARK), 7))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(0, 0), r, r)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(DARK))
    p.drawEllipse(QPointF(0, 0), r * 0.36, r * 0.36)
    btn = QRadialGradient(QPointF(-6, -6), r * 0.3)
    btn.setColorAt(0, QColor("#FFFFFF"))
    btn.setColorAt(1, QColor("#C9CDD4"))
    p.setBrush(btn)
    p.drawEllipse(QPointF(0, 0), r * 0.22, r * 0.22)
    p.setBrush(QColor(255, 255, 255, 200))       # specular highlight
    p.drawEllipse(QPointF(-r * 0.4, -r * 0.55), r * 0.24, r * 0.13)
    p.end()
    return to_np(img)


# ── ASCII: a character per cell, chosen by what part of the icon it is ──
def ascii_art(t, face):
    cols, rows = 18, 20
    src = flat(t)
    cells = cv2.resize(src, (cols, rows), interpolation=cv2.INTER_AREA)
    palette = {
        "frame": (QColor(t["frame"]), "#"), "base": (QColor(t["base"]).lighter(250), "%"),
        "deep": (QColor(*t["line"]).lighter(130), "."), "line": (QColor(*t["line"]).lighter(150), ":"),
        "sclera": (QColor(t["sclera"]), "="), "top": (QColor(t["top"]), "@"),
        "white": (QColor("#FFFFFF"), "O"), "dark": (QColor("#8A8F9A"), "-"),
    }
    refs = {"frame": t["frame"], "base": t["base"], "deep": t["deep"], "line": QColor(*t["line"]).name(),
            "sclera": t["sclera"], "top": t["top"], "white": "#FFFFFF", "dark": DARK}
    keys = list(refs)
    ref = np.array([QColor(refs[k]).getRgb()[:3] for k in keys], np.float32)
    img, p = canvas()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#0B0C0F"))
    p.drawRoundedRect(QRectF(12, 12, S - 24, S - 24), 44, 44)
    font = QFont(face)
    font.setPixelSize(30)
    font.setBold(True)
    p.setFont(font)
    cw, ch = (S - 72) / cols, (S - 72) / rows
    for y in range(rows):
        for x in range(cols):
            r, g, b, a = (float(v) for v in cells[y, x])
            if a < 90:
                continue
            k = keys[int(np.argmin(((ref - np.array([r, g, b])) ** 2).sum(1)))]
            color, char = palette[k]
            p.setPen(color)
            p.drawText(QRectF(36 + x * cw, 36 + y * ch, cw, ch), Qt.AlignmentFlag.AlignCenter, char)
    p.end()
    return to_np(img)


# ── neon: line art with a glow, like a sign ─────────────────────────────
def neon(t):
    img, p = canvas()
    p.translate(S / 2, S / 2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#0B0C10"))
    p.drawRoundedRect(QRectF(-240, -240, 480, 480), 60, 60)
    frame, ball_top = QColor(t["frame"]), QColor(t["top"])

    def lines(pen_w, alpha):
        def pen(c, wmul=1.0):
            c = QColor(c)
            c.setAlpha(alpha)
            return QPen(c, pen_w * wmul, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen(frame))
        p.drawRoundedRect(QRectF(-150, -205, 300, 410), 26, 26)
        p.setPen(pen(QColor(*t["line"]).lighter(150), 0.6))
        for (hx, hy) in ((-90, -140), (90, 140)):
            hexagon = QPainterPath()
            for k in range(6):
                a = math.radians(60 * k - 30)
                pt = QPointF(hx + 26 * math.cos(a), hy + 26 * math.sin(a))
                hexagon.moveTo(pt) if k == 0 else hexagon.lineTo(pt)
            hexagon.closeSubpath()
            p.drawPath(hexagon)
        p.setPen(pen(t["sclera"]))
        p.drawPath(eye_path(128, 160))
        p.setPen(pen(ball_top))
        p.drawEllipse(QPointF(0, 0), 60, 60)
        p.drawLine(QPointF(-60, 0), QPointF(-20, 0))
        p.drawLine(QPointF(20, 0), QPointF(60, 0))
        p.drawEllipse(QPointF(0, 0), 20, 20)

    for width, alpha in ((40, 18), (26, 30), (16, 60), (6, 255)):
        lines(width, alpha)
    p.setPen(QPen(QColor(255, 255, 255, 170), 2))   # hot white core
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-150, -205, 300, 410), 26, 26)
    p.end()
    return to_np(img)


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    segoe = family("segoeui.ttf")
    family("seguisb.ttf")
    mono = family("consolab.ttf", "Consolas")
    styles = [
        ("Textured", lambda t: card(t, "Hex")),
        ("Flat 2D", flat),
        ("Pixel 32", lambda t: pixel(t, 32)),
        ("Pixel 16", pixel16),
        ("3D", three_d),
        ("ASCII", lambda t: ascii_art(t, mono)),
        ("Neon", neon),
    ]
    tile, gap, pad, label_w = 168, 18, 46, 138
    width = pad * 2 + label_w + len(styles) * (tile + gap) - gap
    row_h = tile + 60 + gap * 2
    height = pad * 2 + 100 + len(PICKS) * row_h
    board = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    board.fill(QColor("#141519"))
    p = QPainter(board)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor("#E8ECF2"))
    p.setFont(QFont(segoe, 20, QFont.Weight.DemiBold))
    p.drawText(pad, pad + 26, "Hex card back  ·  red & black and purple, seven art styles")
    p.setFont(QFont(segoe, 12, QFont.Weight.DemiBold))
    for c, (name, _) in enumerate(styles):
        p.drawText(QPointF(pad + label_w + c * (tile + gap), pad + 84), name)
    for r, (theme_name, theme) in enumerate(PICKS.items()):
        y = pad + 100 + r * row_h
        p.setPen(QColor("#E8ECF2"))
        p.setFont(QFont(segoe, 15, QFont.Weight.DemiBold))
        p.drawText(QPointF(pad, y + tile / 2), theme_name)
        for c, (style, make) in enumerate(styles):
            img = to_qimage(make(theme))
            img.save(os.path.join(HERE, f"v4_{theme_name.lower().replace(' & ', '_')}_{style.lower().replace(' ', '')}.png"))
            x = pad + label_w + c * (tile + gap)
            p.fillRect(QRectF(x, y, tile, tile), QColor("#1E2027"))
            smooth = Qt.TransformationMode.FastTransformation if style.startswith("Pixel") \
                else Qt.TransformationMode.SmoothTransformation
            p.drawImage(QPointF(x + 8, y + 8),
                        img.scaled(tile - 16, tile - 16, Qt.AspectRatioMode.KeepAspectRatio, smooth))
            for k, (size, bg) in enumerate(((32, "#E9EBEF"), (16, "#E9EBEF"), (32, "#202227"), (16, "#202227"))):
                bx = x + k * (tile / 4)
                p.fillRect(QRectF(bx, y + tile + 8, tile / 4, 48), QColor(bg))
                small = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                p.drawImage(QPointF(bx + (tile / 4 - size) / 2, y + tile + 8 + (48 - size) / 2), small)
    p.end()
    out = os.path.join(HERE, "board_v4.png")
    board.save(out)
    print(out)


if __name__ == "__main__":
    main()
