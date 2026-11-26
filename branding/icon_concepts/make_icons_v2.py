"""Round 2 of the app-icon directions: marks drawn from the game's own
objects (a scored card, the 60-card count, a logged stamp, a card back, a
scorekeeper's pencil mark), each with its own silhouette and some hand-made
texture - ink, grain, offset print - instead of a flat glyph on a tile.

    python branding/icon_concepts/make_icons_v2.py   ->  board_v2.png + one PNG per mark
"""
import math
import os
import random
import sys

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QFontDatabase, QGuiApplication, QImage,
                           QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
                           QTransform)

HERE = os.path.dirname(os.path.abspath(__file__))
S = 512                     # drawing size; scaled down for the board
FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

PAPER, PAPER_DK, INK, NAVY, NAVY_DK, GOLD, RED, TEAL = (
    "#EFE5CF", "#D9CBAA", "#1C2230", "#17263F", "#0D1626", "#E2A83A", "#C9413A", "#3E8FB8")


def family(file_name, fallback="Segoe UI"):
    fid = QFontDatabase.addApplicationFont(os.path.join(FONTS, file_name))
    names = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
    return names[0] if names else fallback


def canvas():
    img = QImage(S, S, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    return img, p


def to_np(img):
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    arr = np.frombuffer(img.constBits(), np.uint8).reshape(img.height(), img.width(), 4)
    return arr.copy()


def to_qimage(arr):
    arr = np.ascontiguousarray(arr)
    img = QImage(arr.data, arr.shape[1], arr.shape[0], arr.shape[1] * 4, QImage.Format.Format_RGBA8888)
    return img.copy()


def smooth_noise(shape, scale, seed):
    rng = np.random.default_rng(seed)
    small = rng.random((max(2, shape[0] // scale), max(2, shape[1] // scale))).astype(np.float32)
    return cv2.resize(small, (shape[1], shape[0]), interpolation=cv2.INTER_CUBIC)


def roughen(arr, amount=2.2, seed=1):
    """Wobble the edges a little, like ink on paper rather than vectors."""
    h, w = arr.shape[:2]
    dx = (smooth_noise((h, w), 9, seed) - 0.5) * 2 * amount
    dy = (smooth_noise((h, w), 9, seed + 7) - 0.5) * 2 * amount
    xs, ys = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return cv2.remap(arr, xs + dx, ys + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_TRANSPARENT,
                     dst=np.zeros_like(arr))


def grain(arr, strength=10, seed=3):
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, strength, arr.shape[:2]).astype(np.float32)
    out = arr.astype(np.float32)
    out[..., :3] += noise[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def ink_gaps(arr, seed=5, coverage=0.18):
    """Patchy rubber-stamp ink: knock holes in the alpha."""
    n = smooth_noise(arr.shape[:2], 6, seed) * 0.6 + smooth_noise(arr.shape[:2], 2, seed + 1) * 0.4
    cut = np.quantile(n, coverage)
    keep = np.clip((n - cut) / 0.05, 0, 1)
    out = arr.copy()
    out[..., 3] = (out[..., 3].astype(np.float32) * keep).astype(np.uint8)
    return out


def shadow(p, path, dy=10, blur_layers=6, alpha=26):
    for i in range(blur_layers, 0, -1):
        p.save()
        p.translate(0, dy)
        p.setPen(QPen(QColor(0, 0, 0, alpha), i * 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                      Qt.PenJoinStyle.RoundJoin))
        p.setBrush(QColor(0, 0, 0, alpha))
        p.drawPath(path)
        p.restore()


def card_path(x, y, w, h, r):
    path = QPainterPath()
    path.addRoundedRect(QRectF(x, y, w, h), r, r)
    return path


def brush_stroke(p, a, b, width, color, seed):
    """A tapered, slightly bent pencil/brush stroke from a to b."""
    rnd = random.Random(seed)
    (x0, y0), (x1, y1) = a, b
    length = math.hypot(x1 - x0, y1 - y0)
    nx, ny = -(y1 - y0) / length, (x1 - x0) / length
    bend = rnd.uniform(-0.06, 0.06) * length
    left, right = [], []
    steps = 24
    for i in range(steps + 1):
        t = i / steps
        cx = x0 + (x1 - x0) * t + nx * bend * math.sin(math.pi * t)
        cy = y0 + (y1 - y0) * t + ny * bend * math.sin(math.pi * t)
        half = width / 2 * (0.55 + 0.45 * math.sin(math.pi * min(1, t * 1.15))) * rnd.uniform(0.93, 1.07)
        left.append(QPointF(cx + nx * half, cy + ny * half))
        right.append(QPointF(cx - nx * half, cy - ny * half))
    path = QPainterPath(left[0])
    for pt in left[1:]:
        path.lineTo(pt)
    for pt in reversed(right):
        path.lineTo(pt)
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)


# ── 1. Scorecard: a cream card with your record scratched on it ─────────
def scorecard():
    img, p = canvas()
    p.translate(S / 2, S / 2)
    p.rotate(-7)
    card = card_path(-150, -205, 300, 410, 30)
    shadow(p, card)
    p.setPen(QPen(QColor(INK), 10))
    grad = QLinearGradient(0, -205, 0, 205)
    grad.setColorAt(0, QColor(PAPER))
    grad.setColorAt(1, QColor(PAPER_DK))
    p.setBrush(grad)
    p.drawPath(card)
    p.setPen(QPen(QColor(INK), 4))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-124, -179, 248, 358), 18, 18)
    # four strokes and the slash: five games logged
    for i, x in enumerate((-72, -26, 20, 66)):
        brush_stroke(p, (x + random.Random(i).uniform(-6, 6), -104), (x + 8, 108), 20, INK, i + 10)
    brush_stroke(p, (-116, 74), (112, -78), 22, RED, 99)
    p.end()
    return grain(roughen(to_np(img), 1.6, 11), 7)


# ── 2. Sixty: the deck count, printed slightly off-register ─────────────
def sixty(face):
    img, p = canvas()
    card = card_path(76, 36, 360, 440, 40)
    shadow(p, card)
    grad = QLinearGradient(0, 36, 0, 476)
    grad.setColorAt(0, QColor(NAVY))
    grad.setColorAt(1, QColor(NAVY_DK))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawPath(card)
    font = QFont(face)
    font.setPixelSize(250)
    p.setFont(font)
    box = QRectF(76, 40, 360, 400)
    p.setPen(QColor(TEAL))                       # the off-register plate
    p.drawText(box.translated(-8, 6), Qt.AlignmentFlag.AlignCenter, "60")
    p.setPen(QColor(GOLD))
    p.drawText(box, Qt.AlignmentFlag.AlignCenter, "60")
    # a deck-box edge: little card edges stacked at the bottom
    p.setPen(QPen(QColor(GOLD), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for i in range(6):
        p.drawLine(QPointF(150, 420 + i * 7.5), QPointF(362, 420 + i * 7.5))
    p.end()
    return grain(to_np(img), 8)


# ── 3. Logged: a rubber stamp, pressed a little crooked ─────────────────
def stamp(face):
    img, p = canvas()
    p.translate(S / 2, S / 2)
    p.rotate(-11)
    red = QColor(RED)
    p.setPen(QPen(red, 18))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(0, 0), 222, 222)
    p.setPen(QPen(red, 7))
    p.drawEllipse(QPointF(0, 0), 168, 168)
    font = QFont(face)
    font.setPixelSize(46)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
    p.setFont(font)
    p.setPen(red)
    text = "LOGGED \u2022 LOGGED \u2022 LOGGED \u2022 "
    metrics = p.fontMetrics()
    advances = [metrics.horizontalAdvance(ch) for ch in text]
    total = float(sum(advances))
    radius = 182
    angle = 0.0                      # degrees clockwise from the top
    for ch, adv in zip(text, advances):
        mid = angle + 360.0 * (adv / 2) / total
        p.save()
        p.rotate(mid)
        p.drawText(QPointF(-adv / 2, -radius + 14), ch)
        p.restore()
        angle += 360.0 * adv / total
    # the centre: a big check with a W
    big = QFont(face)
    big.setPixelSize(190)
    p.setFont(big)
    p.drawText(QRectF(-150, -120, 300, 230), Qt.AlignmentFlag.AlignCenter, "W")
    p.end()
    return ink_gaps(roughen(to_np(img), 1.4, 21), 23, 0.07)


# ── 4. Card back: the app's own card back, an eye woven into it ─────────
def card_back():
    img, p = canvas()
    p.translate(S / 2, S / 2)
    p.rotate(6)
    card = card_path(-160, -215, 320, 430, 26)
    shadow(p, card)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(NAVY_DK))
    p.drawPath(card)
    p.save()
    p.setClipPath(card_path(-138, -193, 276, 386, 14))
    p.setBrush(QColor(NAVY))
    p.drawRect(QRectF(-160, -215, 320, 430))
    p.setPen(QPen(QColor(62, 110, 160, 120), 3))
    for k in range(-14, 15):                   # diagonal weave
        p.drawLine(QPointF(k * 26 - 260, -260), QPointF(k * 26 + 260, 260))
        p.drawLine(QPointF(k * 26 + 260, -260), QPointF(k * 26 - 260, 260))
    p.restore()
    p.setPen(QPen(QColor(GOLD), 6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(-138, -193, 276, 386), 14, 14)
    # the eye: two arcs, a gold iris, a cut pupil shaped like a card
    eye = QPainterPath()
    eye.moveTo(-120, 0)
    eye.quadTo(0, -112, 120, 0)
    eye.quadTo(0, 112, -120, 0)
    p.setPen(QPen(QColor(PAPER), 12))
    p.setBrush(QColor(NAVY_DK))
    p.drawPath(eye)
    iris = QRadialGradient(QPointF(0, 0), 52)
    iris.setColorAt(0, QColor("#F6CF6E"))
    iris.setColorAt(1, QColor(GOLD))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(iris)
    p.drawEllipse(QPointF(0, 0), 50, 50)
    p.setBrush(QColor(NAVY_DK))
    p.drawRoundedRect(QRectF(-13, -22, 26, 44), 5, 5)
    p.end()
    return grain(to_np(img), 6)


# ── 5. Turn marker: a pencil tick on the corner of a card ───────────────
def corner_tick(face):
    img, p = canvas()
    card = card_path(70, 50, 372, 412, 44)
    shadow(p, card)
    grad = QLinearGradient(0, 50, 0, 462)
    grad.setColorAt(0, QColor(PAPER))
    grad.setColorAt(1, QColor(PAPER_DK))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawPath(card)
    # a navy band across the top, like a scoresheet header
    p.save()
    p.setClipPath(card)
    p.setBrush(QColor(NAVY))
    p.drawRect(QRectF(70, 50, 372, 118))
    p.restore()
    font = QFont(face)
    font.setPixelSize(74)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 4)
    p.setFont(font)
    p.setPen(QColor(PAPER))
    p.drawText(QRectF(70, 50, 372, 118), Qt.AlignmentFlag.AlignCenter, "W  L")
    # the result, ticked by hand under W
    brush_stroke(p, (150, 300), (206, 372), 34, RED, 7)
    brush_stroke(p, (204, 372), (330, 214), 34, RED, 8)
    p.end()
    return grain(roughen(to_np(img), 1.4, 31), 7)


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    rock = family("ROCKEB.TTF", "Rockwell")
    gill = family("GILLUBCD.TTF", "Impact")
    bahn = family("bahnschrift.ttf")
    marks = [
        ("Scorecard", "Your record, scratched on a card: four and the slash.", scorecard()),
        ("Sixty", "The deck count, printed a touch off-register.", sixty(gill)),
        ("Logged", "A rubber stamp, pressed crooked: battle recorded.", stamp(rock)),
        ("Card back", "The app's own card back, an eye woven in.", card_back()),
        ("W / L sheet", "A scoresheet corner with the win ticked by hand.", corner_tick(bahn)),
    ]
    segoe = family("segoeui.ttf")
    family("seguisb.ttf")
    tile, gap, pad = 230, 34, 46
    width = pad * 2 + len(marks) * (tile + gap) - gap
    height = 640
    board = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    board.fill(QColor("#141519"))
    p = QPainter(board)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setPen(QColor("#E8ECF2"))
    p.setFont(QFont(segoe, 20, QFont.Weight.DemiBold))
    p.drawText(pad, pad + 26, "PTCGL Monitor  ·  icon directions, round 2")
    for i, (name, idea, arr) in enumerate(marks):
        img = to_qimage(arr)
        img.save(os.path.join(HERE, f"v2_{i + 1}_{name.lower().replace(' / ', '_').replace(' ', '_')}.png"))
        x = pad + i * (tile + gap)
        y = pad + 64
        # on dark and on light, as a desktop or a light taskbar would show it
        p.fillRect(QRectF(x, y, tile, tile), QColor("#1E2027"))
        p.drawImage(QRectF(x + 15, y + 15, tile - 30, tile - 30), img)
        p.fillRect(QRectF(x, y + tile + 10, tile, 64), QColor("#E9EBEF"))
        p.fillRect(QRectF(x, y + tile + 74, tile, 64), QColor("#202227"))
        for row, bg_y in enumerate((y + tile + 10, y + tile + 74)):
            for k, size in enumerate((48, 32, 16)):
                small = img.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                p.drawImage(QPointF(x + 18 + k * 64, bg_y + (64 - size) / 2), small)
        p.setPen(QColor("#E8ECF2"))
        p.setFont(QFont(segoe, 14, QFont.Weight.DemiBold))
        p.drawText(QPointF(x, y + tile + 172), f"{i + 1}  {name}")
        p.setPen(QColor("#8A93A3"))
        p.setFont(QFont(segoe, 10))
        p.drawText(QRectF(x, y + tile + 182, tile, 60), Qt.TextFlag.TextWordWrap, idea)
    p.end()
    out = os.path.join(HERE, "board_v2.png")
    board.save(out)
    print(out)


if __name__ == "__main__":
    main()
