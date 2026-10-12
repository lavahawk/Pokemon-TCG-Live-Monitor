"""
Generate the Inno Setup wizard artwork from icon.ico.

    python make_wizard_art.py <icon.ico> <out_dir>

Writes wizard-large-{100,200}.bmp (welcome/finish side panel, 164x314 base)
and wizard-small-{100,200}.bmp (header icon, 55x55 base). Two sizes each so
the wizard stays sharp on high-DPI screens.
"""

import os
import sys

from PIL import Image, ImageDraw, ImageFont

TOP = (24, 28, 40)
BOTTOM = (46, 58, 96)
ACCENT = (255, 203, 5)      # Pokemon yellow
TEXT = (235, 239, 247)


def _font(size, bold=False):
    names = ["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    for name in names:
        try:
            return ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def _icon(path, size):
    ico = Image.open(path)
    sizes = sorted(ico.info.get("sizes", [(ico.width, ico.height)]), key=lambda s: s[0])
    best = next((s for s in sizes if s[0] >= size), sizes[-1])
    try:
        ico.size = best
    except Exception:
        pass
    return ico.convert("RGBA").resize((size, size), Image.LANCZOS)


def large(icon_path, scale):
    w, h = 164 * scale, 314 * scale
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        row = tuple(int(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = row
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, w, 4 * scale], fill=ACCENT)
    icon = _icon(icon_path, 92 * scale)
    img.paste(icon, ((w - icon.width) // 2, 64 * scale), icon)
    y = 64 * scale + icon.height + 22 * scale
    for text, font, color in (("Pokemon TCG Live", _font(15 * scale, True), TEXT),
                              ("Monitor", _font(15 * scale, True), ACCENT),
                              ("Battle tracking & stats", _font(10 * scale), (170, 180, 200))):
        tw = draw.textlength(text, font=font)
        draw.text(((w - tw) / 2, y), text, font=font, fill=color)
        y += int(font.size * 1.45)
    return img


def small(icon_path, scale):
    s = 55 * scale
    img = Image.new("RGB", (s, s), (255, 255, 255))
    icon = _icon(icon_path, int(s * 0.9))
    img.paste(icon, ((s - icon.width) // 2, (s - icon.height) // 2), icon)
    return img


def main():
    icon_path, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for scale, pct in ((1, 100), (2, 200)):
        large(icon_path, scale).save(os.path.join(out, f"wizard-large-{pct}.bmp"))
        small(icon_path, scale).save(os.path.join(out, f"wizard-small-{pct}.bmp"))
    print(f"    Wizard artwork written to {out}")


if __name__ == "__main__":
    main()
