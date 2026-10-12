"""
Interactive setup tool for AutoClicker button templates.

Lets you capture button templates directly from the screen by dragging a
rectangle around a button. Templates are saved to button_templates/<name>.png
and used by AutoClicker to find and click those buttons automatically.

Usage:
    python SetupAutoClicker.py                 # interactive capture
    python SetupAutoClicker.py --list          # list saved templates
    python SetupAutoClicker.py --delete NAME   # delete a template
"""

import os
import sys

import cv2
import numpy as np
import mss

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "button_templates")

# Default template suggestions for the battle-end flow.
SUGGESTED = {
    "battle_log": "Black 'BATTLE LOG' button (center bottom of the screen)",
    "battle_log_export": "Battle-log export button (top right, next to the X)",
}


def ensure_templates_dir():
    if not os.path.exists(TEMPLATES_DIR):
        os.makedirs(TEMPLATES_DIR)
        print(f"Created templates directory: {TEMPLATES_DIR}")


def grab_game_window():
    """Return (bgr ndarray, rect) of the game window (falls back to primary screen)."""
    rect = None
    try:
        from game_window import game_rect
        rect = game_rect()
    except Exception:
        rect = None
    with mss.mss() as sct:
        region = rect or sct.monitors[1]
        region = {k: region[k] for k in ("left", "top", "width", "height")}
        shot = sct.grab(region)
        img = np.array(shot)
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR), rect


def select_region(image_bgr):
    """Show the game screenshot (scaled to fit) and let the user drag a box.

    Works for a game window on ANY monitor. Uses OpenCV's built-in selector
    (no tkinter needed). Returns (x, y, w, h) in full-resolution pixels, or None.
    """
    import ctypes
    user32 = ctypes.windll.user32
    screen_w, screen_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    h, w = image_bgr.shape[:2]
    scale = min(1.0, (screen_w * 0.9) / w, (screen_h * 0.85) / h)
    disp = cv2.resize(image_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    title = "Drag a tight box around the button, then press ENTER (C = cancel)"
    x, y, sw, sh = cv2.selectROI(title, disp, showCrosshair=False)
    cv2.destroyAllWindows()
    if sw < 4 or sh < 4:
        return None
    return int(x / scale), int(y / scale), int(sw / scale), int(sh / scale)


def capture_template(name):
    """Capture a button template interactively and save it (+ window size)."""
    print(f"\nCapturing template: {name}")
    print("Make sure the button is visible in the game, then press Enter here.")
    input("Press Enter when ready...")

    image, rect = grab_game_window()
    if rect is None:
        print("Warning: game window not found - using the primary screen. "
              "Scaling to other window sizes will be less reliable.")
    sel = select_region(image)
    if not sel:
        print("Cancelled.")
        return False
    x, y, w, h = sel
    crop = image[y:y + h, x:x + w]
    ensure_templates_dir()
    path = os.path.join(TEMPLATES_DIR, f"{name}.png")
    cv2.imwrite(path, crop)
    try:
        from AutoClicker import save_template_meta
        save_template_meta(name, rect or {"width": image.shape[1], "height": image.shape[0]})
    except Exception as exc:
        print(f"(Could not save template metadata: {exc})")
    print(f"✓ Template saved: {path} ({w}x{h}) for a {image.shape[1]}x{image.shape[0]} game window")
    return True


def list_templates():
    ensure_templates_dir()
    files = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith(".png")]
    if not files:
        print("No templates saved yet.")
        return
    print("Saved templates:")
    for f in files:
        path = os.path.join(TEMPLATES_DIR, f)
        img = cv2.imread(path)
        size = f"{img.shape[1]}x{img.shape[0]}" if img is not None else "?"
        desc = SUGGESTED.get(f[:-4], "")
        extra = f"  # {desc}" if desc else ""
        print(f"  {f[:-4]} ({size}){extra}")


def delete_template(name):
    path = os.path.join(TEMPLATES_DIR, f"{name}.png")
    if os.path.exists(path):
        os.remove(path)
        print(f"Deleted: {path}")
    else:
        print(f"Not found: {path}")


def main():
    if "--list" in sys.argv:
        list_templates()
        return
    if "--delete" in sys.argv:
        idx = sys.argv.index("--delete")
        if idx + 1 < len(sys.argv):
            delete_template(sys.argv[idx + 1])
        else:
            print("Usage: --delete NAME")
        return

    print("=" * 56)
    print("  AutoClicker Button Template Setup")
    print("=" * 56)
    print()
    print("This tool captures button images the auto-clicker will look for")
    print("after a battle ends. Capture them while the game shows the button.")
    print()

    list_templates()

    todo = [k for k in SUGGESTED if not os.path.exists(os.path.join(TEMPLATES_DIR, f"{k}.png"))]
    if not todo:
        todo = list(SUGGESTED.keys())
        print("\nAll suggested templates already exist — recapturing anyway.")

    for name in todo:
        print(f"\n→ {name}: {SUGGESTED[name]}")
        capture_template(name)

    print("\n" + "=" * 56)
    print("Done! Templates are used automatically after each battle ends.")
    print("Re-run this tool any time to recapture (UI updates change buttons).")
    print("=" * 56)


if __name__ == "__main__":
    main()
