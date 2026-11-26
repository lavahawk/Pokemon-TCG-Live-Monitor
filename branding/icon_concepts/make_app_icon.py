"""Build the app's icon.ico from the chosen design: the Hex card back in
red & black (Graphite), textured, for 24-256 px, and the hand-placed pixel
version at 16 px (the tray), where the texture would turn to mush.

    python branding/icon_concepts/make_app_icon.py   ->  icon.ico (repo root) + icon_preview.png
"""
import io
import os
import struct
import sys

import cv2
import numpy as np
from PIL import Image
from PySide6.QtGui import QGuiApplication

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_icons_v3 import THEMES, card  # noqa: E402
from make_icons_v4 import pixel16  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
THEME = THEMES["Graphite"]
SIZES = (256, 128, 64, 48, 40, 32, 24)


def square_crop(rgba, margin=0.03):
    """Trim the empty canvas around the card (shadow kept), centred in a square."""
    ys, xs = np.nonzero(rgba[..., 3] > 8)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    side = int(max(y1 - y0, x1 - x0) * (1 + 2 * margin))
    out = np.zeros((side, side, 4), np.uint8)
    oy, ox = (side - (y1 - y0)) // 2, (side - (x1 - x0)) // 2
    out[oy:oy + y1 - y0, ox:ox + x1 - x0] = rgba[y0:y1, x0:x1]
    return out


def resized(rgba, size):
    # premultiply so the transparent edge doesn't bleed dark fringes
    a = rgba[..., 3:4].astype(np.float32) / 255
    pre = rgba.astype(np.float32)
    pre[..., :3] *= a
    small = cv2.resize(pre, (size, size), interpolation=cv2.INTER_AREA)
    alpha = small[..., 3:4] / 255
    small[..., :3] = np.where(alpha > 0, small[..., :3] / np.maximum(alpha, 1e-6), 0)
    return Image.fromarray(np.clip(small, 0, 255).astype(np.uint8), "RGBA")


def write_ico(path, images):
    """An .ico holding one PNG per size (Windows Vista and later read these)."""
    blobs = []
    for img in images:
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        blobs.append(buf.getvalue())
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for img, blob in zip(images, blobs):
        w, h = img.size
        entries += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    with open(path, "wb") as fh:
        fh.write(header + entries + b"".join(blobs))


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    big = square_crop(card(THEME, "Hex"))
    images = [resized(big, s) for s in SIZES]
    tray = cv2.resize(pixel16(THEME), (16, 16), interpolation=cv2.INTER_NEAREST)
    images.append(Image.fromarray(tray, "RGBA"))
    out = os.path.join(ROOT, "icon.ico")
    write_ico(out, images)
    # a preview strip of every size inside the .ico
    strip = Image.new("RGBA", (sum(i.size[0] for i in images) + 12 * len(images) + 12, 280), (30, 32, 39, 255))
    x = 12
    for img in images:
        strip.alpha_composite(img, (x, 140 - img.size[1] // 2))
        x += img.size[0] + 12
    strip.save(os.path.join(HERE, "icon_preview.png"))
    print(out, [i.size[0] for i in images])


if __name__ == "__main__":
    main()
