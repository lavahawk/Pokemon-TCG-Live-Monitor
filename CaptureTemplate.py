"""
Template Capture Tool - Create validation templates for screen detection

Use this to capture small UI elements that only appear on specific screens
(main menu, post-battle, etc.) for precise screen validation.
"""

import tkinter as tk
from tkinter import messagebox, simpledialog
from PIL import Image, ImageTk
import mss
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")


class TemplateCaptureGUI:
    """Capture template images for screen validation"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Template Capture Tool")
        self.root.geometry("900x700")
        
        self.screenshot = None
        self.template_name = None
        
        # Ensure templates directory exists
        os.makedirs(TEMPLATES_DIR, exist_ok=True)
        
        self.setup_ui()
    
    def setup_ui(self):
        # Instructions
        instructions = tk.Label(
            self.root,
            text="Capture Template Images for Screen Validation\n" +
                 "1. Open Pokemon TCG Live to the screen you want to validate (main menu, post-battle, etc.)\n" +
                 "2. Click 'Take Screenshot'\n" +
                 "3. Click and drag to select a SMALL, UNIQUE UI element (logo, button, icon)\n" +
                 "4. Template will be saved for validation",
            justify=tk.LEFT,
            font=("Arial", 9)
        )
        instructions.pack(pady=10)
        
        # Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=5)
        
        tk.Button(btn_frame, text="📸 Take Screenshot", command=self.take_screenshot, 
                 font=("Arial", 10), bg="lightblue").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="💾 Save Template", command=self.save_template,
                 font=("Arial", 10), bg="lightgreen").pack(side=tk.LEFT, padx=5)
        
        # Canvas
        self.canvas = tk.Canvas(self.root, bg="gray", width=860, height=550)
        self.canvas.pack(pady=10)
        
        # Bind mouse events
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        
        self.selection_start = None
        self.selection_rect = None
        self.selected_region = None
    
    def take_screenshot(self):
        """Capture full screen"""
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            self.screenshot = img
            self.display_screenshot(img)
    
    def display_screenshot(self, img):
        """Display screenshot on canvas"""
        # Scale to fit
        img_width, img_height = img.size
        scale = min(860 / img_width, 550 / img_height, 1.0)
        
        new_width = int(img_width * scale)
        new_height = int(img_height * scale)
        
        resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(resized)
        self.scale = scale
        
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
    
    def on_click(self, event):
        """Start selection"""
        if not self.screenshot:
            messagebox.showwarning("No Screenshot", "Take a screenshot first!")
            return
        self.selection_start = (event.x, event.y)
    
    def on_drag(self, event):
        """Draw selection rectangle"""
        if self.selection_start:
            if self.selection_rect:
                self.canvas.delete(self.selection_rect)
            
            x1, y1 = self.selection_start
            self.selection_rect = self.canvas.create_rectangle(
                x1, y1, event.x, event.y, outline="red", width=2
            )
    
    def on_release(self, event):
        """Capture selected region"""
        if not self.selection_start:
            return
        
        x1, y1 = self.selection_start
        x2, y2 = event.x, event.y
        
        # Ensure correct order
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        
        # Convert to original image coordinates
        orig_x1 = int(x1 / self.scale)
        orig_y1 = int(y1 / self.scale)
        orig_x2 = int(x2 / self.scale)
        orig_y2 = int(y2 / self.scale)
        
        # Crop template
        template = self.screenshot.crop((orig_x1, orig_y1, orig_x2, orig_y2))
        self.selected_region = template
        
        width = orig_x2 - orig_x1
        height = orig_y2 - orig_y1
        
        messagebox.showinfo(
            "Template Selected",
            f"Template size: {width}x{height}\n\n" +
            f"Click 'Save Template' to save it.\n\n" +
            f"Good template sizes: 50x50 to 200x200 pixels"
        )
    
    def save_template(self):
        """Save template image"""
        if not self.selected_region:
            messagebox.showwarning("No Selection", "Select a region first!")
            return
        
        # Ask for template name
        name = simpledialog.askstring(
            "Template Name",
            "Enter template name:\n\n" +
            "Examples:\n" +
            "- main_menu_indicator\n" +
            "- post_battle_indicator\n" +
            "- deck_builder_indicator"
        )
        
        if not name:
            return
        
        # Save template
        if not name.endswith(".png"):
            name += ".png"
        
        path = os.path.join(TEMPLATES_DIR, name)
        self.selected_region.save(path)
        
        messagebox.showinfo(
            "Template Saved",
            f"Template saved to:\n{path}\n\n" +
            f"Size: {self.selected_region.size[0]}x{self.selected_region.size[1]}\n\n" +
            f"The system will now use this template\n" +
            f"to validate the screen before detection!"
        )
        
        print(f"✓ Template saved: {path}")
        print(f"  Size: {self.selected_region.size}")
    
    def run(self):
        """Start the application"""
        self.root.mainloop()


def main():
    print("\n" + "="*60)
    print("TEMPLATE CAPTURE TOOL")
    print("="*60)
    print("\nThis tool helps you create template images for screen validation.")
    print("\nBest Practices:")
    print("- Choose a UNIQUE UI element (logo, button, icon)")
    print("- Element should ONLY appear on the target screen")
    print("- Keep it small (50x50 to 200x200 pixels)")
    print("- Choose high-contrast elements")
    print("\nExamples of good templates:")
    print("- Game logo in corner of main menu")
    print("- PLAY button")
    print("- Specific icon or decoration")
    print("="*60)
    print()
    
    app = TemplateCaptureGUI()
    app.run()


if __name__ == "__main__":
    main()
