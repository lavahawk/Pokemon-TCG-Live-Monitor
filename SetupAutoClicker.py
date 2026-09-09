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
import tkinter as tk

import cv2
import numpy as np
import mss
from PIL import Image, ImageTk

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


def grab_screen():
    """Return (bgr ndarray, monitor dict) for the primary screen."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary screen
        shot = sct.grab(monitor)
        img = np.array(shot)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR), monitor


class RegionSelector:
    """Fullscreen overlay for dragging a selection rectangle."""

    def __init__(self, screen_bgr):
        self.screen_bgr = screen_bgr
        self.start_x = self.start_y = 0
        self.end_x = self.end_y = 0
        self.selection = None  # (x, y, w, h) in screen coordinates

        self.root = tk.Tk()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-alpha", 0.85)
        self.root.configure(cursor="crosshair", bg="black")
        self.root.title("Drag a rectangle around the button, then press Enter")

        self.cv_img = cv2.cvtColor(self.screen_bgr, cv2.COLOR_BGR2RGB)
        self.photo = ImageTk.PhotoImage(Image.fromarray(self.cv_img))

        self.canvas = tk.Canvas(self.root, cursor="crosshair", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_image(0, 0, image=self.photo, anchor=tk.NW)

        self.rect = None
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Return>", self.confirm)
        self.root.bind("<Escape>", lambda e: self.root.destroy())

        self.hint = self.canvas.create_text(
            20, 20, anchor=tk.NW,
            text="Drag around the BUTTON, release, then press ENTER to save (ESC to cancel)",
            fill="#FFD54F", font=("Segoe UI", 14, "bold"),
        )

    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#FF5252", width=2,
        )

    def on_drag(self, event):
        if self.rect:
            self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        self.end_x, self.end_y = event.x, event.y

    def confirm(self, event):
        x1, y1 = min(self.start_x, self.end_x), min(self.start_y, self.end_y)
        x2, y2 = max(self.start_x, self.end_x), max(self.start_y, self.end_y)
        if x2 - x1 < 4 or y2 - y1 < 4:
            print("Selection too small — try again.")
            return
        self.selection = (x1, y1, x2 - x1, y2 - y1)
        self.root.destroy()

    def run(self):
        self.root.mainloop()
        return self.selection


def capture_template(name):
    """Capture a button template interactively and save it."""
    print(f"\nCapturing template: {name}")
    print("A fullscreen screenshot will appear. Drag a tight rectangle around the button,")
    print("then press ENTER. Press ESC to cancel.")
    input("Press Enter when ready...")

    screen_bgr, monitor = grab_screen()
    selector = RegionSelector(screen_bgr)
    sel = selector.run()
    if not sel:
        print("Cancelled.")
        return False

    x, y, w, h = sel
    # Screen coords are relative to the captured monitor origin.
    abs_x = monitor["left"] + x
    abs_y = monitor["top"] + y

    crop = screen_bgr[y:y + h, x:x + w]
    ensure_templates_dir()
    path = os.path.join(TEMPLATES_DIR, f"{name}.png")
    cv2.imwrite(path, crop)
    print(f"✓ Template saved: {path}")
    print(f"  Screen region: ({abs_x}, {abs_y}) {w}x{h}")
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
