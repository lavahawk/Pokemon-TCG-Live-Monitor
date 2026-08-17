"""
Pokemon TCG Live Monitor v2.3 - Startup Manager
Compiles to SetupStartup.exe  (pyinstaller --onefile --windowed)
Manages Windows startup registration and provides quick-launch buttons.
"""
import os
import sys
import tkinter as tk
from tkinter import messagebox

import startup_utils

VERSION  = startup_utils.VERSION
APP_NAME = f"Pokemon TCG Live Monitor v{VERSION}"

# ── Colour palette (matches installer wizard) ───────────────────────────────
C_HDR    = "#1a1a2e"
C_ACCENT = "#e94560"
C_BODY   = "#f5f5f5"
C_BTN    = "#e94560"
C_BTN_H  = "#c73652"
C_BTN_FG = "#ffffff"
C_GREEN  = "#27ae60"
C_ORANGE = "#e67e22"
C_GRAY   = "#888888"
C_BORDER = "#cccccc"

FB = ("Segoe UI", 10)
FS = ("Segoe UI", 9)
FT = ("Segoe UI", 13, "bold")


def _btn(parent, text, cmd, color=C_BTN, width=18):
    b = tk.Button(parent, text=text, command=cmd,
                  bg=color, fg=C_BTN_FG, activebackground=C_BTN_H,
                  activeforeground=C_BTN_FG, font=FB, relief="flat",
                  cursor="hand2", width=width, padx=6, pady=5)
    b.bind("<Enter>", lambda e, c=color: b.config(bg=_darken(c)))
    b.bind("<Leave>", lambda e, c=color: b.config(bg=c))
    return b


def _darken(hex_col):
    r, g, bl = int(hex_col[1:3],16), int(hex_col[3:5],16), int(hex_col[5:7],16)
    return f"#{max(r-30,0):02x}{max(g-30,0):02x}{max(bl-30,0):02x}"

class StartupManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} – Startup Manager")
        self.resizable(False, False)
        self.configure(bg=C_BODY)
        W, H = 500, 460
        self.geometry(f"{W}x{H}")
        self.update_idletasks()
        self.geometry(f"{W}x{H}+{(self.winfo_screenwidth()-W)//2}+{(self.winfo_screenheight()-H)//2}")

        self.root_path = startup_utils.find_install_root()
        self._build_header()
        self._build_body()
        self.refresh_status()

    # ── Chrome ─────────────────────────────────────────────────────────────
    def _build_header(self):
        h = tk.Frame(self, bg=C_HDR, height=65)
        h.place(x=0, y=0, relwidth=1)
        tk.Label(h, text=APP_NAME, font=FT, bg=C_HDR, fg="white").place(x=16, y=10)
        tk.Label(h, text="Startup & Launch Manager", font=FS, bg=C_HDR,
                 fg="#aaaaaa").place(x=17, y=38)
        tk.Frame(self, bg=C_ACCENT, height=3).place(x=0, y=65, relwidth=1)

    def _build_body(self):
        body = tk.Frame(self, bg=C_BODY)
        body.place(x=0, y=68, relwidth=1, relheight=1)

        # Install path info
        path_row = tk.Frame(body, bg=C_BODY)
        path_row.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(path_row, text="Install location:", font=FS, bg=C_BODY,
                 fg=C_GRAY).pack(side="left")
        self._path_lbl = tk.Label(path_row, text=str(self.root_path),
                                   font=("Consolas", 8), bg=C_BODY,
                                   fg="#333333", wraplength=350, anchor="w")
        self._path_lbl.pack(side="left", padx=6)

        tk.Frame(body, bg=C_BORDER, height=1).pack(fill="x", padx=16, pady=4)

        # ── Status card ────────────────────────────────────────────────────
        status_card = tk.Frame(body, bg="#eef2f7", relief="flat", bd=1)
        status_card.pack(fill="x", padx=16, pady=4)
        tk.Label(status_card, text="Startup Status", font=("Segoe UI",10,"bold"),
                 bg="#eef2f7").pack(anchor="w", padx=12, pady=(10,4))

        row1 = tk.Frame(status_card, bg="#eef2f7")
        row1.pack(fill="x", padx=12, pady=2)
        tk.Label(row1, text="Windows Registry (Run on login):", font=FS,
                 bg="#eef2f7", width=32, anchor="w").pack(side="left")
        self._reg_lbl = tk.Label(row1, text="Checking...", font=("Segoe UI",9,"bold"),
                                  bg="#eef2f7")
        self._reg_lbl.pack(side="left")

        row2 = tk.Frame(status_card, bg="#eef2f7")
        row2.pack(fill="x", padx=12, pady=(2,10))
        tk.Label(row2, text="Scheduled Task (on logon, elevated):", font=FS,
                 bg="#eef2f7", width=32, anchor="w").pack(side="left")
        self._task_lbl = tk.Label(row2, text="Checking...", font=("Segoe UI",9,"bold"),
                                   bg="#eef2f7")
        self._task_lbl.pack(side="left")

        # ── Startup buttons ────────────────────────────────────────────────
        tk.Frame(body, bg=C_BORDER, height=1).pack(fill="x", padx=16, pady=(8,4))
        tk.Label(body, text="Startup Registration", font=("Segoe UI",10,"bold"),
                 bg=C_BODY).pack(anchor="w", padx=16)

        btn_row1 = tk.Frame(body, bg=C_BODY)
        btn_row1.pack(pady=6)
        _btn(btn_row1, "Enable Startup (Recommended)", self.enable_startup,
             color=C_GREEN).pack(side="left", padx=6)
        _btn(btn_row1, "Disable Startup", self.disable_startup,
             color="#95a5a6").pack(side="left", padx=6)

        # ── Launch buttons ─────────────────────────────────────────────────
        tk.Frame(body, bg=C_BORDER, height=1).pack(fill="x", padx=16, pady=(8,4))
        tk.Label(body, text="Launch Monitor Now", font=("Segoe UI",10,"bold"),
                 bg=C_BODY).pack(anchor="w", padx=16)

        btn_row2 = tk.Frame(body, bg=C_BODY)
        btn_row2.pack(pady=6)
        _btn(btn_row2, "Start  (GUI / Visible)", self.launch_gui,
             color=C_ACCENT).pack(side="left", padx=6)
        _btn(btn_row2, "Start  (Headless / No Console)", self.launch_headless,
             color="#2980b9").pack(side="left", padx=6)

        # ── Status bar ─────────────────────────────────────────────────────
        sb = tk.Frame(self, bg=C_BORDER, height=1)
        sb.place(x=0, y=420, relwidth=1)
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self._status_var, font=FS, bg=C_BODY,
                 fg=C_GRAY, anchor="w").place(x=16, y=424)
        _btn(self, "Refresh Status", self.refresh_status,
             color="#7f8c8d", width=14).place(x=340, y=418)

    # ── Status refresh ──────────────────────────────────────────────────────
    def refresh_status(self):
        self._path_lbl.config(text=str(self.root_path))
        reg = startup_utils.is_registry_registered()
        task = startup_utils.is_task_registered()
        self._reg_lbl.config(
            text="ENABLED" if reg else "disabled",
            fg=C_GREEN if reg else C_ORANGE
        )
        self._task_lbl.config(
            text="ENABLED" if task else "disabled",
            fg=C_GREEN if task else C_ORANGE
        )
        self._status_var.set("Status refreshed")

    # ── Startup actions ─────────────────────────────────────────────────────
    def enable_startup(self):
        report = startup_utils.enable_startup(self.root_path)
        self.refresh_status()
        if report["registry_ok"] or report["task_ok"]:
            methods = []
            if report["registry_ok"]:
                methods.append("Registry Run key (primary)")
            if report["task_ok"]:
                methods.append("Scheduled Task (backup)")
            msg = (
                f"Monitor will start automatically on Windows login.\n\n"
                f"Methods registered:\n" + "\n".join(f"  + {m}" for m in methods) +
                f"\n\nInstall path: {report['root']}"
            )
            if report.get("removed_tasks"):
                msg += "\n\nRemoved old scheduled tasks:\n" + "\n".join(
                    f"  - {task}" for task in report["removed_tasks"]
                )
            messagebox.showinfo("Startup Enabled", msg)
        else:
            errors = [msg for msg in (report["registry_error"], report["task_error"]) if msg]
            messagebox.showwarning(
                "Startup Failed",
                "Windows startup could not be enabled.\n\n" + "\n".join(errors)
            )

    def disable_startup(self):
        report = startup_utils.disable_startup()
        self.refresh_status()
        if report["registry_ok"] and report["task_ok"]:
            messagebox.showinfo("Startup Disabled",
                "Autostart has been removed.\n"
                "You can re-enable it at any time from this tool."
                + (
                    "\n\nRemoved tasks:\n" + "\n".join(f"  + {task}" for task in report["removed_tasks"])
                    if report["removed_tasks"] else ""
                ))
            return

        errors = []
        if report["registry_error"]:
            errors.append(report["registry_error"])
        errors.extend(report["task_errors"])
        messagebox.showwarning(
            "Startup Removal Failed",
            "Autostart could not be fully removed.\n\n" + "\n".join(errors)
        )

    # ── Launch actions ──────────────────────────────────────────────────────
    def launch_gui(self):
        """Launch with visible console window — shows all output."""
        result = startup_utils.launch_monitor(self.root_path, headless=False)
        if not result["ok"]:
            messagebox.showerror("Launch Failed", result["error"])
            return
        self._status_var.set("Monitor launched in visible console mode")

    def launch_headless(self):
        """Launch silently in background — no console window."""
        result = startup_utils.launch_monitor(self.root_path, headless=True)
        if not result["ok"]:
            messagebox.showerror("Launch Failed", result["error"])
            return
        self._status_var.set("Monitor launched headless (no console)")


if __name__ == "__main__":
    try:
        StartupManager().mainloop()
    except Exception as e:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Error", f"Startup Manager error:\n\n{e}")
        root.destroy()
        sys.exit(1)
