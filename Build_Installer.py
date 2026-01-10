"""
Build Standalone Windows Installer for Pokemon TCG Live Monitor v2.1.0
This creates a self-contained executable installer using PyInstaller
"""

import os
import sys
import shutil
import subprocess

VERSION = "2.1.0"
APP_NAME = "Pokemon TCG Live Monitor"

def build_installer():
    """Build the standalone installer"""
    print("="*70)
    print(f"Building {APP_NAME} v{VERSION} Installer")
    print("="*70)
    print()
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print("[OK] PyInstaller is installed")
    except ImportError:
        print("[!] PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)
        print("[OK] PyInstaller installed")
    
    print()
    print("[1/5] Cleaning old builds...")
    
    # Clean old builds
    for dir_name in ["build", "dist", "Installers/Build"]:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"    Removed {dir_name}/")
    
    os.makedirs("Installers/Build", exist_ok=True)
    
    print("[OK] Cleaned")
    print()
    print("[2/5] Creating installer script...")
    
    # Create a simple installer launcher
    installer_script = """
# Pokemon TCG Live Monitor Installer Launcher
import os
import sys
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Show welcome message
print("="*70)
print("    Pokemon TCG Live Monitor v2.1.0 - Installation")
print("="*70)
print()
print("This will install the Pokemon TCG Live Monitor on your system.")
print()
input("Press Enter to continue...")

# Run the main installer
installer_path = os.path.join(BASE_DIR, "Installers", "INSTALL_COMPLETE_v2.1.bat")
subprocess.run([installer_path], shell=True, cwd=BASE_DIR)
"""
    
    with open("installer_launcher.py", "w") as f:
        f.write(installer_script)
    
    print("[OK] Installer script created")
    print()
    print("[3/5] Building executable with PyInstaller...")
    print("    This may take a few minutes...")
    print()
    
    # PyInstaller command
    pyinstaller_cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", f"Pokemon-TCG-Live-Monitor-v{VERSION}-Installer",
        "--icon", "icon.ico",
        "--add-data", "Installers;Installers",
        "--add-data", "*.py;.",
        "--add-data", "*.bat;.",
        "--add-data", "*.md;.",
        "--add-data", "*.txt;.",
        "--add-data", "*.mp3;.",
        "--add-data", "*.ico;.",
        "--hidden-import", "pkg_resources.py2_warn",
        "installer_launcher.py"
    ]
    
    result = subprocess.run(pyinstaller_cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print("[ERROR] PyInstaller failed!")
        print(result.stderr)
        return False
    
    print("[OK] Executable built")
    print()
    print("[4/5] Moving installer to release folder...")
    
    # Move the exe to Installers/Build
    exe_name = f"Pokemon-TCG-Live-Monitor-v{VERSION}-Installer.exe"
    src = os.path.join("dist", exe_name)
    dst = os.path.join("Installers", "Build", exe_name)
    
    if os.path.exists(src):
        shutil.move(src, dst)
        print(f"[OK] Installer moved to: Installers/Build/{exe_name}")
    else:
        print("[ERROR] Installer executable not found!")
        return False
    
    print()
    print("[5/5] Creating portable ZIP package...")
    
    # Create ZIP with all files
    zip_name = f"Pokemon-TCG-Live-Monitor-v{VERSION}-Portable"
    zip_path = os.path.join("Installers", "Build", zip_name)
    
    # Files to include in portable ZIP
    files_to_zip = [
        "*.py",
        "*.bat", 
        "*.md",
        "*.txt",
        "*.mp3",
        "*.ico",
        "Installers/"
    ]
    
    shutil.make_archive(zip_path, 'zip', '.', )
    print(f"[OK] Portable ZIP created: Installers/Build/{zip_name}.zip")
    
    print()
    print("="*70)
    print("BUILD COMPLETE!")
    print("="*70)
    print()
    print("Output files:")
    print(f"  - Installers/Build/{exe_name}")
    print(f"  - Installers/Build/{zip_name}.zip")
    print()
    print("To release:")
    print("  1. Test the installer on a clean machine")
    print("  2. Upload both files to GitHub release")
    print("  3. Mark the EXE as the main installer")
    print("  4. Provide the ZIP as 'Portable Version'")
    print()
    
    return True


if __name__ == "__main__":
    try:
        success = build_installer()
        if success:
            print("[✓] Build successful!")
            input("\nPress Enter to exit...")
        else:
            print("[✗] Build failed!")
            input("\nPress Enter to exit...")
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
        sys.exit(1)
