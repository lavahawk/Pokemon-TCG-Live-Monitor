"""
Setup Regions Tool - Interactive GUI for defining OCR scan regions
Allows user to define screen regions for rank and other text detection
Uses WINDOW-RELATIVE coordinates - works regardless of window position!
"""

import tkinter as tk
from tkinter import messagebox, ttk
import mss
from PIL import Image, ImageTk, ImageDraw, ImageFont
import json
import os
import win32gui
import win32process
import psutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REGIONS_CONFIG = os.path.join(BASE_DIR, "screen_regions.json")


class RegionSetupTool:
    """Interactive tool to define screen regions for OCR"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TCG Live Monitor - Region Setup Tool")
        self.root.geometry("900x700")
        
        self.regions = self.load_regions()
        self.current_screenshot = None
        self.screenshot_display = None
        self.canvas_image = None
        self.game_window = None
        self.zoom_level = 1.0
        
        self.setup_ui()
    
    def load_regions(self):
        """Load existing regions from config"""
        if os.path.exists(REGIONS_CONFIG):
            with open(REGIONS_CONFIG, 'r') as f:
                return json.load(f)
        return {}
    
    def save_regions(self):
        """Save regions to config file"""
        with open(REGIONS_CONFIG, 'w') as f:
            json.dump(self.regions, f, indent=4)
        messagebox.showinfo("Success", "Regions saved successfully!")
    
    def find_game_window(self):
        """Find the Pokemon TCG Live game window"""
        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                window_title = win32gui.GetWindowText(hwnd)
                if "Pokémon TCG Live" in window_title or "Pokemon TCG Live" in window_title:
                    rect = win32gui.GetWindowRect(hwnd)
                    left, top, right, bottom = rect
                    windows.append({
                        'hwnd': hwnd,
                        'title': window_title,
                        'left': left,
                        'top': top,
                        'width': right - left,
                        'height': bottom - top
                    })
            return True
        
        windows = []
        win32gui.EnumWindows(callback, windows)
        
        if windows:
            return windows[0]
        
        # Try by process name
        for proc in psutil.process_iter(['name', 'pid']):
            if proc.info['name'] == "Pokemon TCG Live.exe":
                def find_by_pid(hwnd, result):
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid == proc.info['pid'] and win32gui.IsWindowVisible(hwnd):
                        rect = win32gui.GetWindowRect(hwnd)
                        left, top, right, bottom = rect
                        result.append({
                            'hwnd': hwnd,
                            'title': win32gui.GetWindowText(hwnd),
                            'left': left,
                            'top': top,
                            'width': right - left,
                            'height': bottom - top
                        })
                    return True
                
                result = []
                win32gui.EnumWindows(find_by_pid, result)
                if result:
                    return result[0]
        
        return None
    
    def setup_ui(self):
        """Create the UI"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Instructions
        instructions = tk.Label(
            main_frame,
            text="Region Setup Tool - Define screen areas for OCR detection\n" +
                 "1. Click 'Detect Game Window' | 2. Take Screenshot | 3. Define regions | 4. Save",
            justify=tk.LEFT,
            font=("Arial", 9),
            fg="darkblue"
        )
        instructions.grid(row=0, column=0, columnspan=4, pady=10, sticky=tk.W)
        
        # Window detection button
        detect_btn = ttk.Button(
            main_frame,
            text="🎮 Detect Game Window",
            command=self.detect_window
        )
        detect_btn.grid(row=1, column=0, pady=5, padx=5, sticky=tk.W)
        
        # Window status label
        self.window_status = tk.Label(main_frame, text="Game window: Not detected", fg="red")
        self.window_status.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=5)
        
        # Screenshot button
        screenshot_btn = ttk.Button(
            main_frame,
            text="📸 Take Screenshot",
            command=self.take_screenshot
        )
        screenshot_btn.grid(row=2, column=0, pady=5, padx=5, sticky=tk.W)
        
        # Region selector
        ttk.Label(main_frame, text="Region Name:").grid(row=2, column=1, padx=5)
        self.region_name_var = tk.StringVar(value="rank")
        region_combo = ttk.Combobox(
            main_frame,
            textvariable=self.region_name_var,
            values=["rank", "my_deck_name", "menu_text", "username", "custom"],
            width=15
        )
        region_combo.grid(row=2, column=2, padx=5)
        
        # Zoom controls
        ttk.Label(main_frame, text="Zoom:").grid(row=2, column=3, padx=5)
        zoom_frame = ttk.Frame(main_frame)
        zoom_frame.grid(row=2, column=4, padx=5)
        ttk.Button(zoom_frame, text="-", command=self.zoom_out, width=3).pack(side=tk.LEFT)
        self.zoom_label = ttk.Label(zoom_frame, text="100%", width=5)
        self.zoom_label.pack(side=tk.LEFT, padx=2)
        ttk.Button(zoom_frame, text="+", command=self.zoom_in, width=3).pack(side=tk.LEFT)
        
        # Canvas for screenshot
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.grid(row=3, column=0, columnspan=5, pady=10, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Add scrollbars for zoomed images
        self.h_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        self.v_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        
        self.canvas = tk.Canvas(
            canvas_frame, 
            bg="gray", 
            width=860, 
            height=450,
            xscrollcommand=self.h_scrollbar.set,
            yscrollcommand=self.v_scrollbar.set
        )
        
        self.h_scrollbar.config(command=self.canvas.xview)
        self.v_scrollbar.config(command=self.canvas.yview)
        
        self.canvas.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.h_scrollbar.grid(row=1, column=0, sticky=(tk.E, tk.W))
        self.v_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        
        # Selection state
        self.selection_start = None
        self.selection_rect = None
        
        # Defined regions list
        regions_frame = ttk.LabelFrame(main_frame, text="Defined Regions", padding="5")
        regions_frame.grid(row=4, column=0, columnspan=5, pady=10, sticky=(tk.W, tk.E))
        
        self.regions_listbox = tk.Listbox(regions_frame, height=5, selectmode=tk.SINGLE)
        self.regions_listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        listbox_scroll = ttk.Scrollbar(regions_frame, orient=tk.VERTICAL, command=self.regions_listbox.yview)
        listbox_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.regions_listbox.config(yscrollcommand=listbox_scroll.set)
        
        # Update regions list
        self.update_regions_list()
        
        # Button frame
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=5, column=0, columnspan=5, pady=10)
        
        ttk.Button(btn_frame, text="Delete Selected Region", 
                  command=self.delete_region).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="💾 Save Configuration", 
                  command=self.save_regions, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Test Rank Detection", 
                  command=self.test_detection).pack(side=tk.LEFT, padx=5)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
    
    def detect_window(self):
        """Detect and display game window information"""
        self.game_window = self.find_game_window()
        
        if self.game_window:
            self.window_status.config(
                text=f"✓ Game found: {self.game_window['width']}x{self.game_window['height']}",
                fg="green"
            )
            messagebox.showinfo(
                "Game Window Found",
                f"Window: {self.game_window['title']}\n" +
                f"Size: {self.game_window['width']} x {self.game_window['height']}"
            )
        else:
            self.window_status.config(
                text="✗ Game window not found",
                fg="red"
            )
            messagebox.showwarning(
                "Game Not Found",
                "Could not find Pokemon TCG Live window.\n\n" +
                "Make sure the game is running and visible."
            )
    
    def zoom_in(self):
        """Zoom in on the screenshot"""
        if not self.current_screenshot:
            return
        
        self.zoom_level = min(self.zoom_level + 0.25, 3.0)  # Max 3x zoom
        self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
        self.display_screenshot(self.current_screenshot)
    
    def zoom_out(self):
        """Zoom out on the screenshot"""
        if not self.current_screenshot:
            return
        
        self.zoom_level = max(self.zoom_level - 0.25, 0.5)  # Min 0.5x zoom
        self.zoom_label.config(text=f"{int(self.zoom_level * 100)}%")
        self.display_screenshot(self.current_screenshot)
    
    def take_screenshot(self):
        """Capture the game window"""
        # Make sure we have window info
        if not self.game_window:
            messagebox.showwarning(
                "No Window Detected",
                "Please click 'Detect Game Window' first!"
            )
            return
        
        with mss.mss() as sct:
            # Capture just the game window
            monitor = {
                "top": self.game_window['top'],
                "left": self.game_window['left'],
                "width": self.game_window['width'],
                "height": self.game_window['height']
            }
            screenshot = sct.grab(monitor)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            
            # Store original screenshot and window info
            self.current_screenshot = img
            
            # Display on canvas
            self.display_screenshot(img)
    
    def display_screenshot(self, img):
        """Display screenshot on canvas with scaling"""
        # Calculate scaling with zoom
        img_width, img_height = img.size
        scale_x = 860 / img_width
        scale_y = 450 / img_height
        base_scale = min(scale_x, scale_y, 1.0)
        self.scale_factor = base_scale * self.zoom_level
        
        # Resize image
        new_width = int(img_width * self.scale_factor)
        new_height = int(img_height * self.scale_factor)
        resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Convert to PhotoImage
        self.screenshot_display = ImageTk.PhotoImage(resized_img)
        
        # Update canvas scroll region
        self.canvas.config(scrollregion=(0, 0, new_width, new_height))
        
        # Display on canvas
        self.canvas.delete("all")
        self.canvas_image = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.screenshot_display)
        
        # Draw existing regions
        self.draw_existing_regions()
    
    def draw_existing_regions(self):
        """Draw existing regions on the canvas"""
        if not self.current_screenshot:
            return
        
        for name, region in self.regions.items():
            # Handle both old (absolute) and new (relative) format
            if region.get('relative', False):
                # Check if it has percentage values (v2.0) or pixel offsets (old)
                if 'percent_x' in region:
                    # Calculate pixel position from percentages
                    if not self.game_window:
                        continue  # Can't display without window info
                    
                    offset_x = int(self.game_window['width'] * region['percent_x'])
                    offset_y = int(self.game_window['height'] * region['percent_y'])
                    width = int(self.game_window['width'] * region['percent_width'])
                    height = int(self.game_window['height'] * region['percent_height'])
                    
                    x1 = int(offset_x * self.scale_factor)
                    y1 = int(offset_y * self.scale_factor)
                    x2 = int((offset_x + width) * self.scale_factor)
                    y2 = int((offset_y + height) * self.scale_factor)
                    color = "lime"
                    tag_text = f"{name} (scaled)"
                elif 'offset_x' in region:
                    # Old pixel-based format
                    x1 = int(region["offset_x"] * self.scale_factor)
                    y1 = int(region["offset_y"] * self.scale_factor)
                    x2 = int((region["offset_x"] + region["width"]) * self.scale_factor)
                    y2 = int((region["offset_y"] + region["height"]) * self.scale_factor)
                    color = "yellow"
                    tag_text = f"{name} (fixed)"
                else:
                    continue
            else:
                # Old format: skip (won't display correctly in window view)
                continue
            
            # Draw rectangle
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, tags="region")
            self.canvas.create_text(x1 + 5, y1 + 5, text=tag_text, anchor=tk.NW, 
                                   fill=color, font=("Arial", 10, "bold"), tags="region")
    
    def on_canvas_click(self, event):
        """Handle mouse click on canvas"""
        if not self.current_screenshot:
            messagebox.showwarning("No Screenshot", "Please take a screenshot first!")
            return
        
        # Convert screen coordinates to canvas coordinates (accounts for scrolling)
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        self.selection_start = (canvas_x, canvas_y)
    
    def on_canvas_drag(self, event):
        """Handle mouse drag to draw selection rectangle"""
        if self.selection_start:
            # Remove previous selection rectangle
            if self.selection_rect:
                self.canvas.delete(self.selection_rect)
            
            # Convert screen coordinates to canvas coordinates (accounts for scrolling)
            canvas_x = self.canvas.canvasx(event.x)
            canvas_y = self.canvas.canvasy(event.y)
            
            # Draw new selection rectangle
            x1, y1 = self.selection_start
            x2, y2 = canvas_x, canvas_y
            self.selection_rect = self.canvas.create_rectangle(
                x1, y1, x2, y2, outline="red", width=2, dash=(5, 5)
            )
    
    def on_canvas_release(self, event):
        """Handle mouse release to save region"""
        if not self.selection_start:
            return
        
        if not self.game_window:
            messagebox.showwarning("No Window", "Game window not detected!")
            self.canvas.delete(self.selection_rect)
            self.selection_start = None
            self.selection_rect = None
            return
        
        # Convert screen coordinates to canvas coordinates (accounts for scrolling)
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        
        # Calculate region in window-relative coordinates
        x1, y1 = self.selection_start
        x2, y2 = canvas_x, canvas_y
        
        # Ensure x1 < x2 and y1 < y2
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        
        # Convert canvas coords to window-relative coords (pixels from window top-left)
        offset_x = int(x1 / self.scale_factor)
        offset_y = int(y1 / self.scale_factor)
        width = int((x2 - x1) / self.scale_factor)
        height = int((y2 - y1) / self.scale_factor)
        
        # Check minimum size
        if width < 20 or height < 10:
            messagebox.showwarning("Region Too Small", "Please select a larger region.")
            self.canvas.delete(self.selection_rect)
            self.selection_start = None
            self.selection_rect = None
            return
        
        # Get region name
        region_name = self.region_name_var.get()
        if not region_name:
            messagebox.showwarning("No Name", "Please enter a region name.")
            return
        
        # Calculate percentages for resolution-independent scaling (v2.0)
        percent_x = offset_x / self.game_window['width']
        percent_y = offset_y / self.game_window['height']
        percent_width = width / self.game_window['width']
        percent_height = height / self.game_window['height']
        
        # Save region with BOTH pixel and percentage values
        # Percentages used for scaling, pixels for backwards compatibility
        self.regions[region_name] = {
            "relative": True,  # Flag indicating window-relative coordinates
            "offset_x": offset_x,  # Pixels from window left (backwards compat)
            "offset_y": offset_y,  # Pixels from window top (backwards compat)
            "width": width,  # Pixel width (backwards compat)
            "height": height,  # Pixel height (backwards compat)
            "percent_x": round(percent_x, 4),  # Percentage from left (v2.0 - scales!)
            "percent_y": round(percent_y, 4),  # Percentage from top (v2.0 - scales!)
            "percent_width": round(percent_width, 4),  # Width as percentage (v2.0 - scales!)
            "percent_height": round(percent_height, 4),  # Height as percentage (v2.0 - scales!)
            "comment": f"Calibrated at {self.game_window['width']}x{self.game_window['height']}"
        }
        
        # Update UI
        self.update_regions_list()
        self.canvas.delete(self.selection_rect)
        self.draw_existing_regions()
        
        # Reset selection
        self.selection_start = None
        self.selection_rect = None
        
        messagebox.showinfo("Region Added", 
                           f"Region '{region_name}' defined: {width}x{height}")
    
    def update_regions_list(self):
        """Update the regions listbox"""
        self.regions_listbox.delete(0, tk.END)
        for name, region in self.regions.items():
            if region.get('relative', False):
                # Show percentage info if available (v2.0)
                if 'percent_x' in region:
                    # Percentage-based (v2.0) - may or may not have pixel values
                    if 'width' in region and 'height' in region:
                        self.regions_listbox.insert(
                            tk.END,
                            f"{name}: {region['width']}x{region['height']} ({region['percent_x']:.1%},{region['percent_y']:.1%})"
                        )
                    else:
                        # Percentage-only (calculate pixel size if window available)
                        if self.game_window:
                            w = int(self.game_window['width'] * region['percent_width'])
                            h = int(self.game_window['height'] * region['percent_height'])
                            self.regions_listbox.insert(
                                tk.END,
                                f"{name}: {w}x{h} ({region['percent_x']:.1%},{region['percent_y']:.1%})"
                            )
                        else:
                            self.regions_listbox.insert(
                                tk.END,
                                f"{name}: {region['percent_x']:.1%},{region['percent_y']:.1%} (percentage-based)"
                            )
                else:
                    # Old pixel-based without percentages
                    self.regions_listbox.insert(
                        tk.END,
                        f"{name}: {region.get('width', '?')}x{region.get('height', '?')} (fixed pixels)"
                    )
            else:
                # Old absolute format
                self.regions_listbox.insert(
                    tk.END,
                    f"{name}: {region.get('width', '?')}x{region.get('height', '?')} (old)"
                )
    
    def delete_region(self):
        """Delete selected region"""
        selection = self.regions_listbox.curselection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a region to delete.")
            return
        
        # Get the selected index
        index = selection[0]
        
        # Get region names list (in same order as listbox)
        region_names = list(self.regions.keys())
        
        if index >= len(region_names):
            messagebox.showerror("Error", "Invalid selection.")
            return
        
        region_name = region_names[index]
        
        # Confirm deletion
        if messagebox.askyesno("Delete Region", f"Delete region '{region_name}'?"):
            del self.regions[region_name]
            self.update_regions_list()
            
            # Redraw
            if self.current_screenshot:
                self.display_screenshot(self.current_screenshot)
            
            messagebox.showinfo("Deleted", f"Region '{region_name}' deleted successfully.")
    
    def test_detection(self):
        """Test the rank detection with current configuration"""
        if not self.regions:
            messagebox.showwarning("No Regions", "Please define at least one region first.")
            return
        
        # Save current regions
        self.save_regions()
        
        # Import and test
        try:
            from RankDetector import RankDetector
            detector = RankDetector()
            
            messagebox.showinfo("Testing", 
                               "Testing rank detection...\n" +
                               "Make sure Pokemon TCG Live is showing the rank on screen.")
            
            rank = detector.extract_rank(debug=True)
            
            if rank:
                messagebox.showinfo("Success", f"Detected Rank: {rank}\n\nCheck debug_rank.png for details.")
            else:
                messagebox.showwarning("Detection Failed", 
                                      "Could not detect rank.\n" +
                                      "Check debug_rank.png to see what was captured.\n" +
                                      "You may need to adjust the region.")
        except Exception as e:
            messagebox.showerror("Error", f"Error testing detection:\n{str(e)}")
    
    def run(self):
        """Start the application"""
        self.root.mainloop()


def main():
    """Main entry point"""
    print("Starting Region Setup Tool...")
    print("=" * 50)
    print("Instructions:")
    print("1. Make sure Pokemon TCG Live is running")
    print("2. Click 'Detect Game Window'")
    print("3. Click 'Take Screenshot'")
    print("4. Click and drag to select regions")
    print("5. Use zoom +/- for precise selection")
    print("6. Click 'Save Configuration'")
    print("=" * 50)
    
    app = RegionSetupTool()
    app.run()


if __name__ == "__main__":
    main()
