"""
Pokemon TCG Live Monitor v2.3.0 - Professional Installer Creator
Wizard pages:
  1 - Welcome
  2 - License Agreement
  3 - Choose Install Location
  4 - OpenAI API Key (optional)
  5 - Installing  (live progress bar + log)
  6 - Finish
"""
import os
import sys
import zipfile
import base64
import shutil
from pathlib import Path

INSTALLER_TEMPLATE = r'''
import os
import sys
import zipfile
import subprocess
import threading
import io
import base64
import ctypes
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

VERSION     = "2.3.0"
APP_NAME    = f"Pokemon TCG Live Monitor v{VERSION}"
DEFAULT_DIR = os.path.join(os.environ.get("USERPROFILE", "C:\\"), "PokemonTCGLiveMonitor")

PACKAGE_DATA = """\
{package_data}
"""

# ── Palette ────────────────────────────────────────────────────────────────
C_HDR_BG = "#1a1a2e"
C_HDR_FG = "#e0e0e0"
C_ACCENT  = "#e94560"
C_BODY    = "#f5f5f5"
C_BTN     = "#e94560"
C_BTN_FG  = "#ffffff"
C_BTN_HOV = "#c73652"
C_BORDER  = "#cccccc"
C_LOG_BG  = "#1e1e1e"
C_LOG_FG  = "#d4d4d4"

FT = ("Segoe UI", 14, "bold")   # title
FB = ("Segoe UI", 10)            # body
FS = ("Segoe UI", 8)             # small
FM = ("Consolas", 9)             # mono


# ── Helpers ────────────────────────────────────────────────────────────────
def btn(parent, text, cmd, width=12, state="normal"):
    b = tk.Button(parent, text=text, command=cmd,
                  bg=C_BTN, fg=C_BTN_FG, activebackground=C_BTN_HOV,
                  activeforeground=C_BTN_FG, font=FB, relief="flat",
                  cursor="hand2", width=width, padx=8, pady=4, state=state)
    b.bind("<Enter>", lambda e: b.config(bg=C_BTN_HOV))
    b.bind("<Leave>", lambda e: b.config(bg=C_BTN if b["state"] == "normal" else C_BORDER))
    return b


# ── Wizard ─────────────────────────────────────────────────────────────────
class Wizard(tk.Tk):
    # Page indices
    P_WELCOME  = 0
    P_LICENSE  = 1
    P_PATH     = 2
    P_APIKEY   = 3
    P_INSTALL  = 4
    P_FINISH   = 5
    LAST       = 5

    STEPS = ["Welcome", "License", "Location", "API Key", "Installing", "Finish"]

    def __init__(self):
        super().__init__()
        self.title(APP_NAME + " Setup")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._close)
        W, H = 640, 500
        self.geometry(f"{W}x{H}")
        self.update_idletasks()
        self.geometry(f"{W}x{H}+{(self.winfo_screenwidth()-W)//2}+{(self.winfo_screenheight()-H)//2}")
        self.configure(bg=C_BODY)

        # State
        self.install_path     = tk.StringVar(value=DEFAULT_DIR)
        self._accept_var      = tk.BooleanVar(value=False)
        self._api_key_var     = tk.StringVar()
        self._api_skip_var    = tk.BooleanVar(value=False)
        self._open_folder_var = tk.BooleanVar(value=True)
        self._install_done    = False
        self._install_ok      = False

        self._build_header()
        self._build_sidebar()
        self._content = tk.Frame(self, bg=C_BODY)
        self._content.place(x=160, y=73, width=480, height=357)
        self._build_nav()

        self._pages = [
            self._pg_welcome,
            self._pg_license,
            self._pg_path,
            self._pg_apikey,
            self._pg_install,
            self._pg_finish,
        ]
        self._cur = 0
        self._show(0)

    # ── Chrome ─────────────────────────────────────────────────────────────
    def _build_header(self):
        h = tk.Frame(self, bg=C_HDR_BG, height=70)
        h.place(x=0, y=0, relwidth=1)
        tk.Label(h, text=APP_NAME + " Setup", font=FT,
                 bg=C_HDR_BG, fg=C_HDR_FG).place(x=170, y=12)
        tk.Label(h, text="Follow the steps below to complete installation.",
                 font=FS, bg=C_HDR_BG, fg="#aaaaaa").place(x=171, y=42)
        tk.Frame(self, bg=C_ACCENT, height=3).place(x=0, y=70, relwidth=1)

    def _build_sidebar(self):
        sb = tk.Frame(self, bg=C_HDR_BG)
        sb.place(x=0, y=73, width=157, height=357)
        tk.Frame(sb, bg=C_ACCENT, width=3).place(x=154, y=0, height=357)
        self._slbls = []
        for i, name in enumerate(self.STEPS):
            row = tk.Frame(sb, bg=C_HDR_BG)
            row.pack(fill="x", pady=5, padx=8)
            num = tk.Label(row, text=str(i+1), width=2, bg=C_ACCENT,
                           fg="white", font=("Segoe UI", 9, "bold"))
            num.pack(side="left")
            lbl = tk.Label(row, text=f"  {name}", font=FS, bg=C_HDR_BG,
                           fg="#888888", anchor="w")
            lbl.pack(side="left")
            self._slbls.append((num, lbl))

    def _hi(self, idx):
        for i, (num, lbl) in enumerate(self._slbls):
            if i == idx:
                num.config(bg=C_ACCENT);      lbl.config(fg="#ffffff", font=("Segoe UI", 9, "bold"))
            elif i < idx:
                num.config(bg="#2ecc71");     lbl.config(fg="#aaaaaa", font=("Segoe UI", 9))
            else:
                num.config(bg="#555555");     lbl.config(fg="#666666", font=("Segoe UI", 9))

    def _build_nav(self):
        nav = tk.Frame(self, bg=C_BODY)
        nav.place(x=0, y=430, relwidth=1, height=70)
        tk.Frame(nav, bg=C_BORDER, height=1).pack(fill="x")
        row = tk.Frame(nav, bg=C_BODY)
        row.pack(side="right", padx=16, pady=14)
        self._btn_cancel = btn(row, "Cancel", self._close, width=10)
        self._btn_cancel.pack(side="right", padx=4)
        self._btn_next = btn(row, "Next  >", self._next, width=12)
        self._btn_next.pack(side="right", padx=4)
        self._btn_back = btn(row, "<  Back", self._back, width=10)
        self._btn_back.pack(side="right", padx=4)
        self._btn_back.config(state="disabled", bg=C_BORDER, cursor="arrow")

    # ── Navigation ──────────────────────────────────────────────────────────
    def _show(self, idx):
        for w in self._content.winfo_children():
            w.destroy()
        self._cur = idx
        self._hi(idx)
        self._pages[idx]()

        can_back = 0 < idx < self.P_INSTALL
        self._btn_back.config(
            state="normal" if can_back else "disabled",
            bg=C_BTN if can_back else C_BORDER,
            cursor="hand2" if can_back else "arrow"
        )

        if idx == self.P_FINISH:
            self._btn_next.config(text="Finish", command=self._finish,
                                  state="normal", bg=C_BTN, cursor="hand2")
            self._btn_back.config(state="disabled", bg=C_BORDER, cursor="arrow")
            self._btn_cancel.config(state="disabled", bg=C_BORDER, cursor="arrow")
        elif idx == self.P_INSTALL:
            self._btn_next.config(state="disabled", text="Next  >",
                                  bg=C_BORDER, cursor="arrow", command=self._next)
        elif idx == self.P_LICENSE:
            ok = self._accept_var.get()
            self._btn_next.config(state="normal" if ok else "disabled",
                                  bg=C_BTN if ok else C_BORDER,
                                  cursor="hand2" if ok else "arrow",
                                  command=self._next, text="Next  >")
        else:
            self._btn_next.config(state="normal", text="Next  >",
                                  bg=C_BTN, cursor="hand2", command=self._next)

    def _next(self):
        if self._cur == self.P_PATH:
            if not self.install_path.get().strip():
                messagebox.showwarning("No Path", "Please choose an installation path.")
                return
        if self._cur < self.LAST:
            self._show(self._cur + 1)
            if self._cur == self.P_INSTALL:
                self._start_install()

    def _back(self):
        if self._cur > 0:
            self._show(self._cur - 1)

    def _close(self):
        if self._install_done and self._install_ok:
            self.destroy(); return
        if messagebox.askyesno("Cancel Setup", "Are you sure you want to cancel the installation?"):
            self.destroy()

    # ── Pages ───────────────────────────────────────────────────────────────
    def _pg_welcome(self):
        f = tk.Frame(self._content, bg=C_BODY)
        f.pack(fill="both", expand=True, padx=24, pady=14)
        tk.Label(f, text="Welcome!", font=FT, bg=C_BODY, fg=C_HDR_BG).pack(anchor="w")
        tk.Label(f, text=f"This wizard will install {APP_NAME} on your computer.",
                 font=FB, bg=C_BODY, wraplength=420, justify="left").pack(anchor="w", pady=(6,14))
        card = tk.Frame(f, bg="#e8f4fd", relief="flat", bd=1)
        card.pack(fill="x")
        tk.Label(card, text="What will be installed:", font=("Segoe UI",10,"bold"), bg="#e8f4fd").pack(anchor="w", padx=12, pady=(10,4))
        for feat in [
            "  +  AI-Powered Battle Analysis (GPT-4o, optional)",
            "  +  OCR Rank & Deck Detection with Auto-Override",
            "  +  Live Overlay UI with League Icons",
            "  +  SQLite Battle Statistics Database",
            "  +  Automatic Headless Startup",
            "  +  Modern Stats Dashboard",
        ]:
            tk.Label(card, text=feat, font=FB, bg="#e8f4fd", anchor="w").pack(anchor="w", padx=12)
        tk.Label(card, text="", bg="#e8f4fd").pack()
        tk.Label(f, text="Click Next to continue, or Cancel to exit Setup.",
                 font=FS, bg=C_BODY, fg="#777777").pack(anchor="w", pady=(14,0))

    def _pg_license(self):
        f = tk.Frame(self._content, bg=C_BODY)
        f.pack(fill="both", expand=True, padx=24, pady=14)
        tk.Label(f, text="License Agreement", font=FT, bg=C_BODY, fg=C_HDR_BG).pack(anchor="w")
        tk.Label(f, text="Please review and accept the terms to continue.",
                 font=FB, bg=C_BODY).pack(anchor="w", pady=(4,8))
        tf = tk.Frame(f, bg=C_BODY)
        tf.pack(fill="both", expand=True)
        sb = tk.Scrollbar(tf); sb.pack(side="right", fill="y")
        txt = tk.Text(tf, wrap="word", font=FS, relief="sunken", yscrollcommand=sb.set,
                      bg="#fdfdfd", bd=1, height=10)
        txt.pack(side="left", fill="both", expand=True)
        sb.config(command=txt.yview)
        txt.insert("1.0",
            "MIT License\n\nCopyright (c) 2026 lavahawk\n\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy "
            "of this software and associated documentation files (the \"Software\"), to deal "
            "in the Software without restriction, including without limitation the rights "
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell "
            "copies of the Software, and to permit persons to whom the Software is furnished "
            "to do so, subject to the following conditions:\n\n"
            "The above copyright notice and this permission notice shall be included in all "
            "copies or substantial portions of the Software.\n\n"
            "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR "
            "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, "
            "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE "
            "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER "
            "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, "
            "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE "
            "SOFTWARE.\n\nThird-party components are subject to their own respective licenses.")
        txt.config(state="disabled")
        tk.Checkbutton(f, text="I accept the terms of the License Agreement",
                       variable=self._accept_var, font=FB, bg=C_BODY,
                       command=lambda: self._show(self._cur)).pack(anchor="w", pady=(8,0))

    def _pg_path(self):
        f = tk.Frame(self._content, bg=C_BODY)
        f.pack(fill="both", expand=True, padx=24, pady=14)
        tk.Label(f, text="Choose Install Location", font=FT, bg=C_BODY, fg=C_HDR_BG).pack(anchor="w")
        tk.Label(f, text="Select the folder where the monitor will be installed.",
                 font=FB, bg=C_BODY).pack(anchor="w", pady=(4,14))
        tk.Label(f, text="Destination Folder:", font=FB, bg=C_BODY).pack(anchor="w")
        row = tk.Frame(f, bg=C_BODY)
        row.pack(fill="x", pady=4)
        tk.Entry(row, textvariable=self.install_path, font=FB, relief="sunken", bd=1).pack(
            side="left", fill="x", expand=True, ipady=4)
        btn(row, "Browse...", self._browse, width=9).pack(side="left", padx=(8,0))
        info = tk.Frame(f, bg="#fff8dc", relief="flat", bd=1)
        info.pack(fill="x", pady=(18,0))
        tk.Label(info,
                 text=(
                     "  i  Space required: ~500 MB (includes Python virtual environment)\n"
                     "  i  Tesseract OCR will be auto-downloaded if not present\n"
                     "  i  Python 3.10+ required (download page opens if missing)"
                 ),
                 font=FS, bg="#fff8dc", justify="left", anchor="w").pack(padx=8, pady=8, anchor="w")

    def _browse(self):
        p = filedialog.askdirectory(title="Choose Installation Folder",
                                    initialdir=os.path.dirname(self.install_path.get()))
        if p:
            self.install_path.set(p)

    def _pg_apikey(self):
        f = tk.Frame(self._content, bg=C_BODY)
        f.pack(fill="both", expand=True, padx=24, pady=14)
        tk.Label(f, text="OpenAI API Key  (Optional)", font=FT, bg=C_BODY, fg=C_HDR_BG).pack(anchor="w")
        tk.Label(f,
                 text="The AI battle analyser uses GPT-4o to identify decks from battle logs.\n"
                      "This step is optional — you can add or change the key later from the Stats Dashboard.",
                 font=FB, bg=C_BODY, wraplength=420, justify="left").pack(anchor="w", pady=(6,16))

        card = tk.Frame(f, bg="#e8f4fd", relief="flat", bd=1)
        card.pack(fill="x", pady=(0,12))
        tk.Label(card, text="  Where to get a key:",
                 font=("Segoe UI",10,"bold"), bg="#e8f4fd").pack(anchor="w", padx=12, pady=(10,2))
        tk.Label(card,
                 text=(
                     "  1.  Visit  https://platform.openai.com/api-keys\n"
                     "  2.  Sign in and click \"Create new secret key\"\n"
                     "  3.  Copy the key and paste it below\n"
                     "  Approximate cost: ~$0.01 per battle"
                 ),
                 font=FS, bg="#e8f4fd", justify="left").pack(anchor="w", padx=12, pady=(0,10))

        tk.Label(f, text="Paste your API key here:", font=FB, bg=C_BODY).pack(anchor="w")

        key_row = tk.Frame(f, bg=C_BODY)
        key_row.pack(fill="x", pady=4)
        self._key_entry = tk.Entry(key_row, textvariable=self._api_key_var,
                                   font=("Consolas",10), relief="sunken", bd=1, show="*")
        self._key_entry.pack(side="left", fill="x", expand=True, ipady=5)

        self._show_key_btn = btn(key_row, "Show", self._toggle_key, width=6)
        self._show_key_btn.pack(side="left", padx=(8,0))

        tk.Checkbutton(f, text="Skip this step (add key later in Stats Dashboard)",
                       variable=self._api_skip_var, font=FB, bg=C_BODY,
                       command=self._toggle_skip).pack(anchor="w", pady=(10,0))

    def _toggle_key(self):
        cur = self._key_entry.cget("show")
        if cur == "*":
            self._key_entry.config(show="")
            self._show_key_btn.config(text="Hide")
        else:
            self._key_entry.config(show="*")
            self._show_key_btn.config(text="Show")

    def _toggle_skip(self):
        if self._api_skip_var.get():
            self._key_entry.config(state="disabled", bg="#eeeeee")
        else:
            self._key_entry.config(state="normal", bg="white")

    def _pg_install(self):
        f = tk.Frame(self._content, bg=C_BODY)
        f.pack(fill="both", expand=True, padx=24, pady=14)
        tk.Label(f, text="Installing...", font=FT, bg=C_BODY, fg=C_HDR_BG).pack(anchor="w")
        self._status_var = tk.StringVar(value="Preparing...")
        tk.Label(f, textvariable=self._status_var, font=FB, bg=C_BODY, fg=C_HDR_BG).pack(anchor="w", pady=(4,8))
        self._progress = ttk.Progressbar(f, orient="horizontal", length=420,
                                         mode="determinate", maximum=100)
        self._progress.pack(fill="x", pady=(0,2))
        self._pct_var = tk.StringVar(value="0%")
        tk.Label(f, textvariable=self._pct_var, font=FS, bg=C_BODY, fg="#555555").pack(anchor="e")
        lf = tk.Frame(f, bg=C_LOG_BG, relief="sunken", bd=1)
        lf.pack(fill="both", expand=True, pady=(4,0))
        self._log = tk.Text(lf, bg=C_LOG_BG, fg=C_LOG_FG, font=FM,
                            state="disabled", relief="flat", bd=0, height=9)
        self._log.pack(side="left", fill="both", expand=True)
        sb2 = tk.Scrollbar(lf, command=self._log.yview)
        sb2.pack(side="right", fill="y")
        self._log.config(yscrollcommand=sb2.set)
        for tag, col in [("ok","#2ecc71"),("warn","#f39c12"),("err","#e74c3c"),
                          ("info","#3498db"),("plain",C_LOG_FG)]:
            self._log.tag_config(tag, foreground=col)

    def _log_write(self, msg, tag="plain"):
        self._log.config(state="normal")
        self._log.insert("end", msg+"\n", tag)
        self._log.see("end")
        self._log.config(state="disabled")
        self.update_idletasks()

    def _set_pct(self, pct, status=None):
        self._progress["value"] = pct
        self._pct_var.set(f"{pct:.0f}%")
        if status:
            self._status_var.set(status)
        self.update_idletasks()

    def _start_install(self):
        threading.Thread(target=self._do_install, daemon=True).start()

    def _do_install(self):
        install_path = Path(self.install_path.get().strip())
        api_key = self._api_key_var.get().strip()
        skip_key = self._api_skip_var.get()
        try:
            # Step 1 – Create directory
            self._set_pct(5, "Creating installation directory...")
            self._log_write(f"[1/5] Target: {install_path}", "info")
            install_path.mkdir(parents=True, exist_ok=True)
            self._log_write("      OK", "ok")

            # Step 2 – Decode & extract
            self._set_pct(10, "Decoding embedded package...")
            self._log_write("[2/5] Decoding package...", "info")
            package_bytes = base64.b64decode(PACKAGE_DATA)
            self._log_write(f"      {len(package_bytes)//1024} KB", "plain")
            self._set_pct(15, "Extracting files...")
            self._log_write("      Extracting files...", "info")
            with zipfile.ZipFile(io.BytesIO(package_bytes), "r") as zf:
                members = zf.namelist()
                total = len(members)
                for i, member in enumerate(members):
                    zf.extract(member, install_path)
                    self._set_pct(15 + int((i+1)/total*50),
                                  f"Extracting: {os.path.basename(member)}")
            self._log_write(f"      {total} files extracted", "ok")

            # Step 3 – Save API key
            self._set_pct(68, "Saving configuration...")
            self._log_write("[3/5] Saving API key...", "info")
            key_file = install_path / ".openai_key"
            if not skip_key and api_key.startswith("sk-"):
                key_file.write_text(api_key, encoding="utf-8")
                self._log_write("      API key saved  (AI analysis enabled)", "ok")
            elif not skip_key and api_key and not api_key.startswith("sk-"):
                key_file.write_text(api_key, encoding="utf-8")
                self._log_write("      API key saved (verify it is correct at platform.openai.com)", "warn")
            else:
                self._log_write("      Skipped — add key later in Stats Dashboard", "warn")

            # Step 4 – Run INSTALL_COMPLETE bat
            self._set_pct(72, "Running setup script...")
            self._log_write("[4/5] Running INSTALL_COMPLETE_v2.3.bat...", "info")
            bat = install_path / "Installers" / "INSTALL_COMPLETE_v2.3.bat"
            if not bat.exists():
                cands = list(install_path.rglob("INSTALL_COMPLETE*.bat"))
                bat = cands[0] if cands else None
            if bat:
                if ctypes.windll.shell32.IsUserAnAdmin():
                    subprocess.Popen([str(bat)], shell=True, cwd=str(install_path))
                else:
                    ctypes.windll.shell32.ShellExecuteW(None, "runas", str(bat), "", str(install_path), 1)
                self._log_write(f"      Launched: {bat.name}", "ok")
                self._log_write("      (running in a separate window)", "plain")
            else:
                self._log_write("      [WARN] INSTALL_COMPLETE bat not found", "warn")

            # Step 5 – Done
            self._set_pct(100, "Installation complete!")
            self._log_write("[5/5] Setup finished successfully!", "ok")
            self._log_write(f"      Installed to: {install_path}", "plain")
            if not skip_key and api_key:
                self._log_write("      AI battle analysis: ENABLED", "ok")
            else:
                self._log_write("      AI battle analysis: disabled (no key)", "warn")
            self._install_done = True
            self._install_ok   = True
            self.after(1400, lambda: self._show(self.P_FINISH))

        except Exception as exc:
            self._log_write(f"[ERROR] {exc}", "err")
            self._set_pct(self._progress["value"], "Error during installation")
            self._install_done = True
            self._install_ok   = False
            self.after(0, lambda: messagebox.showerror("Installation Error",
                f"An error occurred:\n\n{exc}\n\nSee the log for details."))

    def _pg_finish(self):
        f = tk.Frame(self._content, bg=C_BODY)
        f.pack(fill="both", expand=True, padx=24, pady=14)
        ai_enabled = bool(self._api_key_var.get().strip()) and not self._api_skip_var.get()
        tk.Label(f, text="Installation Complete!", font=FT, bg=C_BODY, fg="#27ae60").pack(anchor="w")
        tk.Label(f, text=f"{APP_NAME} has been successfully installed.",
                 font=FB, bg=C_BODY).pack(anchor="w", pady=(6,16))
        card = tk.Frame(f, bg="#eafaf1", relief="flat", bd=1)
        card.pack(fill="x")
        tk.Label(card, text="Quick Start:", font=("Segoe UI",10,"bold"), bg="#eafaf1").pack(anchor="w", padx=12, pady=(10,4))
        for s in [
            "1.  Monitor auto-starts on next Windows login.",
            "2.  Open Pokemon TCG Live — the overlay will appear.",
            "3.  Click the overlay arrow (^) to open Stats Dashboard.",
            "4.  Battles are tracked and analysed automatically.",
        ]:
            tk.Label(card, text=f"  {s}", font=FB, bg="#eafaf1", anchor="w").pack(anchor="w", padx=12)
        tk.Label(card, text="", bg="#eafaf1").pack()
        ai_color = "#27ae60" if ai_enabled else "#e67e22"
        ai_text  = "AI analysis:  ENABLED  (GPT-4o)" if ai_enabled else "AI analysis:  disabled  (add key in Stats Dashboard)"
        tk.Label(f, text=f"  {ai_text}", font=FS, bg=C_BODY, fg=ai_color).pack(anchor="w", pady=(10,0))
        tk.Label(f, text=f"  Installed to: {self.install_path.get()}",
                 font=FS, bg=C_BODY, fg="#555555", wraplength=420, justify="left").pack(anchor="w", pady=(4,0))
        tk.Checkbutton(f, text="Open installation folder",
                       variable=self._open_folder_var, font=FB, bg=C_BODY).pack(anchor="w", pady=(12,0))

    def _finish(self):
        if self._open_folder_var.get():
            try: os.startfile(self.install_path.get())
            except Exception: pass
        self.destroy()


if __name__ == "__main__":
    try:
        Wizard().mainloop()
    except Exception as e:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Installer Error",
            f"A fatal error occurred:\n\n{e}\n\nPlease report this on GitHub.")
        root.destroy(); sys.exit(1)
'''

# ── Builder ─────────────────────────────────────────────────────────────────
VERSION   = "2.3.0"
BUILD_DIR = Path("Installers/Build")
ZIP_NAME  = f"Pokemon-TCG-Live-Monitor-v{VERSION}.zip"
EXE_NAME  = f"Pokemon-TCG-Live-Monitor-v{VERSION}-Installer"


def _build_zip_python(zip_path: Path):
    """Fallback ZIP builder when Build_Release_Package.bat is unavailable."""
    files = [
        "TCGLiveMonitor.py", "AIParseBattleLog.py", "BattleDatabase.py",
        "RankDetector.py", "OverlayUI.py", "StatsUI.py",
        "app_settings.py", "deck_analytics.py", "startup_utils.py",
        "AutoRun_Add.py", "AutoRun_Remove.py", "Run_Headless.py", "AutoClicker.py",
        "Run_Headless.bat", "Run_TCGLiveMonitor_Command_Prompt.bat",
        "Install_Dependencies.bat", "requirements.txt", "screen_regions.json",
        "README.md", "QUICK_START_v2.0.md", "GITHUB_RELEASE_NOTES.md",
        f"RELEASE_NOTES_v{VERSION[:3]}.md",
    ]
    optional = ["icon.ico", "ding.mp3", ".gitignore"]
    installer_files = [
        f"Installers/INSTALL_COMPLETE_v{VERSION[:3]}.bat",
        f"Installers/Start_GUI_Mode_v{VERSION[:3]}.bat",
        f"Installers/Remove_AutoStart_v{VERSION[:3]}.bat",
        "Installers/README.md",
    ]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in files + optional + installer_files:
            p = Path(name)
            if p.exists():
                zf.write(p, name)
                print(f"      + {name}")
            else:
                print(f"      - SKIP (not found): {name}")


def build_zip() -> Path:
    zip_path = BUILD_DIR / ZIP_NAME
    print("[1/5] Building release ZIP...")
    if zip_path.exists():
        print(f"      [OK] Reusing existing ZIP  ({zip_path.stat().st_size // 1024} KB)")
        return zip_path
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    import subprocess
    r = subprocess.run(["cmd", "/c", "Build_Release_Package.bat"], capture_output=True)
    if r.returncode != 0 or not zip_path.exists():
        print("      Build_Release_Package.bat unavailable — building ZIP from Python")
        _build_zip_python(zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP not created: {zip_path}")
    print(f"      [OK] {zip_path.stat().st_size // 1024} KB")
    return zip_path


def create_installer():
    print("=" * 70)
    print(f"    Pokemon TCG Live Monitor v{VERSION}")
    print("    Professional Installer Builder  (6-step wizard)")
    print("=" * 70)
    print()
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # 1 – ZIP
    zip_path = build_zip()
    print()

    # 2 – Encode
    print("[2/5] Encoding package data...")
    raw = zip_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    lines = [b64[i:i+76] for i in range(0, len(b64), 76)]
    print(f"      [OK] {len(raw)//1024} KB  ({len(b64)} base64 chars)")
    print()

    # 3 – Generate script
    print("[3/5] Generating installer script...")
    script = INSTALLER_TEMPLATE.replace("{package_data}", "\n".join(lines))
    script_path = BUILD_DIR / "wizard_installer_script.py"
    script_path.write_text(script, encoding="utf-8")
    print(f"      [OK] {script_path}")
    print()

    # 4 – Check PyInstaller
    print("[4/5] Checking PyInstaller...")
    try:
        import PyInstaller.__main__ as pyi
    except ImportError:
        print("      Not found — installing...")
        os.system(".venv\\Scripts\\pip install pyinstaller --quiet")
        import PyInstaller.__main__ as pyi
    print("      [OK] PyInstaller ready")
    print()

    # 5 – Compile
    print("[5/5] Compiling EXE  (1-3 minutes)...")
    print()
    icon_path = Path("icon.ico").absolute()
    args = [
        str(script_path),
        "--onefile", "--windowed",
        f"--name={EXE_NAME}",
        f"--distpath={BUILD_DIR}",
        f"--workpath={BUILD_DIR / 'build_temp'}",
        f"--specpath={BUILD_DIR}",
        "--clean", "--noconfirm",
        "--hidden-import=tkinter",
        "--hidden-import=tkinter.ttk",
        "--hidden-import=tkinter.messagebox",
        "--hidden-import=tkinter.filedialog",
    ]
    if icon_path.exists():
        args.append(f"--icon={icon_path}")
    pyi.run(args)

    exe_path = BUILD_DIR / f"{EXE_NAME}.exe"
    if exe_path.exists():
        mb = exe_path.stat().st_size / 1024 / 1024
        shutil.rmtree(BUILD_DIR / "build_temp", ignore_errors=True)
        print()
        print("=" * 70)
        print("                   BUILD COMPLETE!")
        print("=" * 70)
        print()
        print(f"  Installer EXE : {exe_path}")
        print(f"  Release ZIP   : {zip_path}")
        print(f"  EXE size      : {mb:.1f} MB")
        print()
        print("  WIZARD STEPS:")
        print("  [1] Welcome          [2] License Agreement")
        print("  [3] Install Location [4] OpenAI API Key")
        print("  [5] Installing       [6] Finish")
        print()
        print("  UPLOAD TO GITHUB RELEASE:")
        print(f"  - {ZIP_NAME}")
        print(f"  - {EXE_NAME}.exe")
        print()
        print("=" * 70)
        return True
    else:
        print("      [ERROR] EXE was not created — check PyInstaller output above")
        return False


if __name__ == "__main__":
    try:
        ok = create_installer()
        input("\nPress ENTER to exit...")
        sys.exit(0 if ok else 1)
    except Exception as exc:
        print(f"\n[FATAL] {exc}")
        import traceback; traceback.print_exc()
        input("\nPress ENTER to exit...")
        sys.exit(1)
