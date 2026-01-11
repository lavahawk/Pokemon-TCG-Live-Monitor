"""
Pokemon TCG Live Monitor v2.1.0 - Portable Installer Creator
Creates a single EXE installer that extracts and runs the installation
"""
import os
import sys
import zipfile
import base64
import shutil
from pathlib import Path

INSTALLER_TEMPLATE = '''
import os
import sys
import zipfile
import tempfile
import subprocess
from pathlib import Path
import base64
import io
import tkinter as tk
from tkinter import messagebox, filedialog

# Embedded ZIP data (base64 encoded)
PACKAGE_DATA = """
{package_data}
"""

def select_installation_path():
    """Show GUI dialog to select installation path"""
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    
    default_path = os.path.join(os.environ.get("USERPROFILE", "C:\\\\"), "PokemonTCGLiveMonitor")
    
    # Show message box with installation info
    result = messagebox.askokcancel(
        "Pokemon TCG Live Monitor v2.1.0",
        f"Welcome to Pokemon TCG Live Monitor v2.1.0 Installation!\\n\\n"
        f"Default installation path:\\n{{default_path}}\\n\\n"
        f"Click OK to use default path, or Cancel to choose a custom location."
    )
    
    if result:
        # User clicked OK - use default
        install_path = default_path
    else:
        # User clicked Cancel - show folder browser
        install_path = filedialog.askdirectory(
            title="Choose Installation Directory",
            initialdir=os.path.dirname(default_path)
        )
        
        if not install_path:
            # User cancelled folder selection
            messagebox.showinfo("Installation Cancelled", "Installation has been cancelled.")
            root.destroy()
            return None
    
    root.destroy()
    return install_path

def show_progress(title, message):
    """Show a simple progress window"""
    root = tk.Tk()
    root.title(title)
    root.geometry("500x150")
    root.resizable(False, False)
    
    # Center the window
    root.update_idletasks()
    x = (root.winfo_screenwidth() // 2) - (500 // 2)
    y = (root.winfo_screenheight() // 2) - (150 // 2)
    root.geometry(f"+{{x}}+{{y}}")
    
    label = tk.Label(root, text=message, font=("Arial", 10), wraplength=450, justify="left")
    label.pack(pady=20, padx=20)
    
    return root

def main():
    # Select installation path
    install_path = select_installation_path()
    
    if not install_path:
        sys.exit(0)  # User cancelled
    
    # Create installation directory
    install_path = Path(install_path)
    try:
        install_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Installation Error",
            f"Failed to create installation directory:\\n{{install_path}}\\n\\nError: {{e}}"
        )
        root.destroy()
        sys.exit(1)
    
    # Show progress window
    progress_window = show_progress(
        "Installing Pokemon TCG Live Monitor",
        "Extracting files...\\nThis may take a moment."
    )
    progress_window.update()
    
    # Decode and extract ZIP
    try:
        package_bytes = base64.b64decode(PACKAGE_DATA)
        with zipfile.ZipFile(io.BytesIO(package_bytes), 'r') as zip_ref:
            zip_ref.extractall(install_path)
    except Exception as e:
        progress_window.destroy()
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Extraction Error",
            f"Failed to extract files:\\n\\n{{e}}"
        )
        root.destroy()
        sys.exit(1)
    
    progress_window.destroy()
    
    # Find and run the installer
    installer_path = install_path / "Installers" / "INSTALL_COMPLETE_v2.1.bat"
    
    if not installer_path.exists():
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Installer Not Found",
            f"Installer not found at:\\n{{installer_path}}"
        )
        root.destroy()
        sys.exit(1)
    
    # Ask if user wants to run installer now
    root = tk.Tk()
    root.withdraw()
    run_now = messagebox.askyesno(
        "Files Extracted Successfully",
        f"Files extracted to:\\n{{install_path}}\\n\\n"
        f"Run the installer now?\\n\\n"
        f"The installer will:\\n"
        f"  • Check for Python 3.10+\\n"
        f"  • Auto-install Tesseract OCR\\n"
        f"  • Install dependencies\\n"
        f"  • Configure auto-start\\n\\n"
        f"Click Yes to run installer, or No to exit."
    )
    root.destroy()
    
    if run_now:
        # Change to installation directory and run installer
        os.chdir(install_path)
        
        # Run the installer as administrator
        try:
            import ctypes
            if ctypes.windll.shell32.IsUserAnAdmin():
                # Already admin, run directly
                subprocess.Popen([str(installer_path)], shell=True)
            else:
                # Request admin elevation
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", str(installer_path), "", str(install_path), 1
                )
        except Exception as e:
            root = tk.Tk()
            root.withdraw()
            result = messagebox.askyesno(
                "Administrator Rights Required",
                f"Could not run installer with administrator rights.\\n\\n"
                f"Error: {{e}}\\n\\n"
                f"Open the installation folder to run manually?"
            )
            root.destroy()
            
            if result:
                os.startfile(install_path)
    else:
        # User chose not to run installer - ask if they want to open folder
        root = tk.Tk()
        root.withdraw()
        open_folder = messagebox.askyesno(
            "Installation Complete",
            f"Files extracted successfully!\\n\\n"
            f"To complete installation later, navigate to:\\n"
            f"{{install_path}}\\\\Installers\\n\\n"
            f"Right-click INSTALL_COMPLETE_v2.1.bat and\\n"
            f"select \\"Run as Administrator\\"\\n\\n"
            f"Open installation folder now?"
        )
        root.destroy()
        
        if open_folder:
            os.startfile(install_path)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Unexpected Error",
            f"An unexpected error occurred:\\n\\n{{e}}\\n\\n"
            f"Please report this issue on GitHub."
        )
        root.destroy()
        sys.exit(1)
'''

def create_portable_installer():
    """Create a portable installer EXE"""
    print("=" * 70)
    print("    Pokemon TCG Live Monitor v2.1.0")
    print("    Portable Installer Creator")
    print("=" * 70)
    print()
    
    # Step 1: Build release package
    print("[1/5] Building release package...")
    zip_path = Path("Installers/Build/Pokemon-TCG-Live-Monitor-v2.1.0.zip")
    
    if zip_path.exists():
        print("      [OK] Release package already exists")
    else:
        if os.system("Build_Release_Package.bat > nul") != 0:
            print("      [ERROR] Failed to build release package")
            return False
        print("      [OK] Release package built")
    print()
    
    # Step 2: Read and encode ZIP
    print("[2/5] Encoding package data...")
    zip_path = Path("Installers/Build/Pokemon-TCG-Live-Monitor-v2.1.0.zip")
    
    if not zip_path.exists():
        print(f"      [ERROR] ZIP file not found: {zip_path}")
        return False
    
    with open(zip_path, 'rb') as f:
        package_data = base64.b64encode(f.read()).decode('ascii')
    
    # Split into lines for readability
    package_data_lines = [package_data[i:i+76] for i in range(0, len(package_data), 76)]
    package_data_formatted = '\n'.join(package_data_lines)
    
    print(f"      [OK] Package encoded ({len(package_data)} characters)")
    print()
    
    # Step 3: Create installer script
    print("[3/5] Creating installer script...")
    installer_script = INSTALLER_TEMPLATE.format(package_data=package_data_formatted)
    
    script_path = Path("Installers/Build/portable_installer_script.py")
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(installer_script)
    
    print("      [OK] Installer script created")
    print()
    
    # Step 4: Check PyInstaller
    print("[4/5] Checking PyInstaller...")
    try:
        import PyInstaller.__main__
        print("      [OK] PyInstaller available")
    except ImportError:
        print("      [!] PyInstaller not found, installing...")
        if os.system("pip install pyinstaller --quiet") != 0:
            print("      [ERROR] Failed to install PyInstaller")
            return False
        print("      [OK] PyInstaller installed")
    print()
    
    # Step 5: Build EXE
    print("[5/5] Building portable installer EXE...")
    print("      This may take a few minutes...")
    print()
    
    # Use absolute icon path
    icon_path = (Path.cwd() / "icon.ico").absolute()
    
    pyinstaller_args = [
        str(script_path),
        '--onefile',
        '--windowed',
        '--name=Pokemon-TCG-Live-Monitor-v2.1.0-Installer',
        '--distpath=Installers/Build',
        '--workpath=Installers/Build/build_temp',
        '--specpath=Installers/Build',
        '--clean',
        '--noconfirm',
        '--hidden-import=tkinter'
    ]
    
    if icon_path.exists():
        pyinstaller_args.append(f'--icon={icon_path}')
    
    PyInstaller.__main__.run(pyinstaller_args)
    
    exe_path = Path("Installers/Build/Pokemon-TCG-Live-Monitor-v2.1.0-Installer.exe")
    
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print()
        print("      [OK] Portable installer created!")
        print()
        print("=" * 70)
        print("                 BUILD COMPLETE!")
        print("=" * 70)
        print()
        print("Portable installer created:")
        print(f"  Location: {exe_path}")
        print(f"  Size: {size_mb:.2f} MB")
        print()
        print("FEATURES:")
        print("  [+] Single portable EXE file")
        print("  [+] No extraction needed")
        print("  [+] Auto-extracts and installs")
        print("  [+] Asks for installation path")
        print("  [+] Runs installer automatically")
        print()
        print("HOW TO USE:")
        print("  1. Share the .exe file")
        print("  2. User double-clicks it")
        print("  3. Chooses installation path")
        print("  4. Application auto-installs")
        print()
        print("NEXT STEPS:")
        print("  1. Test the installer")
        print("  2. Upload to GitHub Release")
        print("  3. Share with users!")
        print()
        print("=" * 70)
        
        # Clean up temp files
        shutil.rmtree("Installers/Build/build_temp", ignore_errors=True)
        
        return True
    else:
        print("      [ERROR] Failed to create installer EXE")
        return False

if __name__ == "__main__":
    try:
        success = create_portable_installer()
        input("\nPress ENTER to exit...")
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        input("\nPress ENTER to exit...")
        sys.exit(1)
