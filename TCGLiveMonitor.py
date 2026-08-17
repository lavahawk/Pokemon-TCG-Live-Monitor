import psutil
import pyperclip
import time
import re
import pygame
import sys
import os
import subprocess
import pyfiglet
import argparse
from datetime import datetime
from colorama import init, Fore, Back, Style
import os
import sys
import tkinter as tk
from tkinter import simpledialog
import threading
from multiprocessing import Process
from BattleDatabase import BattleDatabase
from app_settings import load_username, save_username, load_api_key, is_local_only_mode


###Version=2.3
# Get the script's directory (where the script is located)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define file path variables using relative paths
LOG_DIR = os.path.join(BASE_DIR, "Logs")  # Directory to save battle log files
SOUND_FILE = os.path.join(BASE_DIR, "ding.mp3")  # Path to the sound file
SCRIPT_TO_RUN = os.path.join(BASE_DIR, "AIParseBattleLog.py")  # Path to AIParseBattleLog.py
PID_FILE = os.path.join(BASE_DIR, ".monitor_pid")  # PID file for process management

# Ensure the log directory exists
os.makedirs(LOG_DIR, exist_ok=True)


def _pid_is_running(pid):
    """Return True if a process with the given PID is alive and is a monitor."""
    if not pid:
        return False
    try:
        proc = psutil.Process(pid)
        if not proc.is_running():
            return False
        # Confirm it's actually a TCGLiveMonitor process (not a recycled PID).
        cmdline = " ".join(proc.cmdline() or [])
        return "TCGLiveMonitor.py" in cmdline
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


# A separate lock file used for atomic single-instance mutual exclusion.
# Using an OS file lock (msvcrt.locking) avoids the race where two instances
# launched at the same time both read the PID file before either writes it.
LOCK_FILE = os.path.join(BASE_DIR, ".monitor_lock")

# Kept open for the lifetime of the process so the lock is held.
_global_lock_handle = None


def _acquire_single_instance():
    """Ensure only one monitor instance runs at a time (race-free).

    Uses an OS-level file lock so that even if two instances start at the
    exact same moment, only one can acquire the lock. The loser exits
    immediately instead of creating a duplicate monitor + overlay.
    Returns True if this instance should continue.
    """
    global _global_lock_handle

    if os.name == "nt":
        try:
            import msvcrt

            handle = open(LOCK_FILE, "a+")
            try:
                # Try to lock the first byte. If another process holds it,
                # this raises immediately (LK_NBLCK = non-blocking).
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                handle.close()
                # Another instance holds the lock — read its PID for the message.
                existing_pid = None
                try:
                    if os.path.exists(PID_FILE):
                        with open(PID_FILE, "r") as fh:
                            existing_pid = int(fh.read().strip() or 0)
                except Exception:
                    existing_pid = None
                print(Fore.YELLOW + f"[Monitor] Another instance is already running (PID {existing_pid or 'unknown'}).")
                print(Fore.YELLOW + "[Monitor] Exiting to avoid duplicate monitors/overlays.")
                return False

            # We hold the lock. Write our PID and keep the handle open.
            handle.seek(0)
            handle.truncate()
            handle.write(str(os.getpid()))
            handle.flush()
            _global_lock_handle = handle
            return True
        except Exception:
            # Fall back to the PID-file check if locking is unavailable.
            pass

    # Non-Windows or lock unavailable: fall back to PID-file check.
    existing_pid = None
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, "r") as handle:
                existing_pid = int(handle.read().strip() or 0)
    except Exception:
        existing_pid = None

    if existing_pid and existing_pid != os.getpid() and _pid_is_running(existing_pid):
        print(Fore.YELLOW + f"[Monitor] Another instance is already running (PID {existing_pid}).")
        print(Fore.YELLOW + "[Monitor] Exiting to avoid duplicate monitors/overlays.")
        return False

    try:
        with open(PID_FILE, "w") as handle:
            handle.write(str(os.getpid()))
    except Exception:
        pass
    return True


# Initialize colorama
init(autoreset=True)

# Reconfigure stdout/stderr to UTF-8 so emoji (🎮, ✗, ✓, 🏆) don't crash the
# console with a UnicodeEncodeError on Windows (cp1252 default).
try:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Set a custom terminal window title that never resembles the game window
print("\033]0;PTCGL Monitor Console\007")

# Function to clear the terminal window
def clear_terminal():
    if os.name == 'nt':
        os.system('cls')
    else:
        os.system('clear')

# Clear the terminal
clear_terminal()

# Create and display an ASCII art banner
def display_banner(text):
    ascii_banner = pyfiglet.figlet_format(text)
    print(Fore.CYAN + Style.BRIGHT + ascii_banner)

# Set terminal colors
def set_terminal_theme():
    # Background color (not supported in all terminals)
    print(Back.BLACK, end="")

    # Main foreground text color
    print(Fore.CYAN + Style.BRIGHT, end="")

# Apply the theme
set_terminal_theme()

# Display the banner
display_banner("TCG Live Monitor \(^ v ^)/")
# Counts number of files in the specified Log Directory
def count_logs_in_directory(log_dir):
    # Count the number of files in the specified directory
    try:
        files = [f for f in os.listdir(log_dir) if os.path.isfile(os.path.join(log_dir, f))]
        return len(files)
    except FileNotFoundError:
        return 0
log_count = count_logs_in_directory(LOG_DIR)

# Sample sections with headers and content
print(Fore.BLUE + Style.BRIGHT + "========================================")
print(Fore.CYAN + "Monitoring Status: " + Fore.GREEN + "Active")
print(Fore.CYAN + "Logs Saved: " + Fore.GREEN + f"{log_count}")
print(Fore.BLUE + Style.BRIGHT + "========================================")

# Display another section with a banner
display_banner("Game Status")
print(Fore.BLUE + Style.BRIGHT + "========================================")

###################################################
# ALL FUNCTIONAL STUFF BELOW THIS POINT
###################################################

# Detect if script is running in a terminal
IS_TERMINAL = sys.stdin.isatty()

# Function to get user input based on environment
def get_input(prompt):
    """Prompt user for input using CLI (if in terminal) or GUI (if in background)."""
    if IS_TERMINAL:
        return input(prompt)
    else:
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        return simpledialog.askstring("Input Required", prompt)

# Load or prompt for username
username = load_username()
if not username:
    username = get_input("First time setup \n----------------\nEnter your TCG Live username: ")
    while not username:
        print("Username cannot be empty. Please enter a valid username.")
        username = get_input("Enter your username: ")
    save_username(username)

if is_local_only_mode():
    print(Fore.CYAN + "[Monitor] Local-only mode is enabled. AI parsing will use manual opponent deck entry.")
elif not load_api_key():
    print(Fore.YELLOW + "[Monitor] No OpenAI API key found. The parser will fall back to local-only mode.")

def is_pokemon_tcg_live_running():
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and 'pokemon tcg live' in proc.info['name'].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

def is_battle_log(clipboard_content):
    if not clipboard_content:
        return False

    normalized = clipboard_content.replace("\r\n", "\n").strip()
    if len(normalized) < 120:
        return False

    old_format_turn = re.search(r"Turn #\s*\d+\s*-\s*.+?'s Turn", normalized, flags=re.IGNORECASE)
    new_format_turn = re.search(r"(?m)^[^\n]{1,40}'s Turn\s*$", normalized)
    has_setup = normalized.startswith("Setup") or "\nSetup\n" in f"\n{normalized}\n"
    has_result = re.search(
        r"(?im)(all prize cards taken\..+? wins\.|opponent conceded\..+? wins\.|^.+? wins\.$)",
        normalized,
    )
    action_hits = len(
        re.findall(r"\b(played|drew|attached|used|retreated|evolved|was Knocked Out|took a Prize card)\b", normalized)
    )

    if old_format_turn and has_result:
        return True
    if has_setup and new_format_turn and has_result and action_hits >= 3:
        return True
    return False


def read_stable_clipboard(max_reads=4, delay=0.25):
    """Read clipboard a few times and keep the most complete stable snapshot."""
    best_value = ""
    previous_value = None

    for _ in range(max_reads):
        try:
            current_value = pyperclip.paste() or ""
        except Exception:
            current_value = ""

        if len(current_value) > len(best_value):
            best_value = current_value

        if current_value and current_value == previous_value:
            return current_value

        previous_value = current_value
        time.sleep(delay)

    return best_value

def get_new_filename():
    # Generate a filename with a timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(LOG_DIR, f"battle_log_{timestamp}.txt")

def save_battle_log(log):
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)
        print(f"Created logs directory: {LOG_DIR}")  # Optional logging

    filename = os.path.join(LOG_DIR, get_new_filename())  # Ensure filename is inside LOG_DIR
    with open(filename, "w") as file:
        file.write(log + "\n\n")
    print(f"Log saved: {filename}")
    return filename

def play_sound():
    pygame.mixer.init()
    pygame.mixer.music.load(SOUND_FILE)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():  # Wait until the sound has finished playing
        pygame.time.Clock().tick(10)

def wait_for_game_startup():
    print("Waiting for Pokémon TCG Live to start...")
    while not is_pokemon_tcg_live_running():
        time.sleep(10)  # Check every 10 seconds
    print("Pokémon TCG Live is running. Monitoring clipboard...")
    pyperclip.copy('') # Clear the clipboard on launch

def monitor_clipboard():
    previous_clipboard = ""
    tick = 0
    while True:
        if is_pokemon_tcg_live_running():
            clipboard_content = read_stable_clipboard()
            time.sleep(1.25)
            tick += 1
            # Print status every 15 ticks (~30s)
            if tick % 15 == 0:
                clip_preview = clipboard_content[:60].replace('\n', ' ') if clipboard_content else '(empty)'
                print(Fore.CYAN + f"[Monitor] Watching clipboard... (tick {tick}) | clip: {clip_preview}")
            if clipboard_content != previous_clipboard and is_battle_log(clipboard_content):
                print(Fore.GREEN + "[Monitor] Battle log detected! Saving...")
                log_path = save_battle_log(clipboard_content)
                play_sound()
                run_other_script(log_path)
                previous_clipboard = clipboard_content
            elif clipboard_content != previous_clipboard and clipboard_content:
                clip_preview = clipboard_content[:60].replace('\n', ' ')
                print(Fore.YELLOW + f"[Monitor] Clipboard changed (not a battle log): {clip_preview}")
                previous_clipboard = clipboard_content
        else:
            # If the game is not running, wait for it to start again
            print(Fore.RED + "[Monitor] Game closed. Waiting for Pokémon TCG Live to start...")
            wait_for_game_startup()
            print(Fore.GREEN + "[Monitor] Pokémon TCG Live is running. Monitoring clipboard...")
            previous_clipboard = ""  # Reset previous_clipboard if the game is restarted

def run_other_script(log_file_path=None):
    # Construct the absolute path to the other script
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), SCRIPT_TO_RUN))
    
    # Run the script using the same Python interpreter (ensures venv packages are available)
    print(f"Running {script_path}...")
    command = [sys.executable, script_path]
    if log_file_path:
        command.append(os.path.abspath(log_file_path))
    subprocess.run(command)
    
    # After AI parsing, wait for user to return to main menu
    wait_for_main_menu_and_detect()

def wait_for_main_menu_and_detect():
    """Wait for user to return to main menu, then detect rank and deck name with OCR."""
    print(Fore.YELLOW + "\n" + "="*50)
    print(Fore.YELLOW + "⏳ Waiting for you to return to the main menu...")
    print(Fore.CYAN + "   OCR will auto-detect your rank and deck name")
    print(Fore.YELLOW + "="*50)
    
    try:
        from RankDetector import RankDetector
        
        detector = RankDetector()
        max_attempts = 60  # Wait up to 2 minutes (60 * 2 seconds)
        attempt = 0
        
        while attempt < max_attempts:
            # First check if menu text is detected (quick check)
            menu_text_found = False
            if "menu_text" in detector.regions:
                menu_text_found = detector.validate_screen_by_text(
                    "menu_text", 
                    ["PLAY", "SHOP", "CARDS", "BATTLE PASS", "DECK", "RANKED"]
                )
            
            if menu_text_found:
                print(Fore.GREEN + "\n✓ Main menu text detected!")
                
                # Wait 4 seconds for the rank to fully populate on screen
                print(Fore.CYAN + "   Waiting 4 seconds for rank to populate...")
                time.sleep(4)
                
                # Now verify full menu detection (rank + deck + menu text)
                if detector.is_on_main_menu(validation_method="auto", debug=False):
                    print(Fore.GREEN + "✓ Full menu validation complete!")
                    
                    # Detect deck name first
                    deck_name = detector.extract_text("my_deck_name")
                    if deck_name:
                        # Clean up the deck name (remove extra whitespace, etc.)
                        deck_name = " ".join(deck_name.split())
                        print(Fore.GREEN + f"✓ Deck detected: {deck_name}")
                        # Save deck name to a file for AIParseBattleLog to use
                        deck_file = os.path.join(BASE_DIR, ".last_deck")
                        with open(deck_file, "w") as f:
                            f.write(deck_name)
                    else:
                        print(Fore.YELLOW + "⚠ Could not detect deck name")
                        deck_name = None
                    
                    # Detect rank
                    rank = detector.extract_rank_safe(validate_screen=True, debug=False)
                    if rank:
                        print(Fore.GREEN + f"✓ Rank detected: {rank}")
                        # Save rank to a file for AIParseBattleLog to use
                        rank_file = os.path.join(BASE_DIR, ".last_rank")
                        with open(rank_file, "w") as f:
                            f.write(str(rank))
                        
                        # Update database so overlay refreshes immediately
                        try:
                            db = BattleDatabase()
                            db.add_rank_update(rank, deck_name)
                            
                            # ALSO update the most recent battle with this rank and OCR deck name
                            import sqlite3
                            conn = sqlite3.connect(db.db_path)
                            cursor = conn.cursor()
                            if deck_name:
                                cursor.execute("""
                                    UPDATE battles 
                                    SET my_rank = ?, my_deck = ?
                                    WHERE id = (SELECT MAX(id) FROM battles)
                                """, (rank, deck_name))
                                print(Fore.CYAN + f"   ✓ Most recent battle deck overridden with OCR: {deck_name}")
                            else:
                                cursor.execute("""
                                    UPDATE battles 
                                    SET my_rank = ? 
                                    WHERE id = (SELECT MAX(id) FROM battles)
                                """, (rank,))
                            conn.commit()
                            conn.close()
                            
                            print(Fore.CYAN + f"   Database updated with rank: {rank}")
                            print(Fore.GREEN + f"   ✓ Most recent battle updated with rank: {rank}")
                        except Exception as e:
                            print(Fore.YELLOW + f"   Warning: Could not update database: {e}")
                    else:
                        print(Fore.YELLOW + "⚠ Could not detect rank number")
                    
                    print(Fore.GREEN + "\n✓ OCR detection complete!")
                    print(Fore.YELLOW + "="*50 + "\n")
                    break
            
            # Not on menu yet, wait and try again
            time.sleep(2)
            attempt += 1
            
            # Show progress every 10 attempts (20 seconds)
            if attempt % 10 == 0:
                print(Fore.CYAN + f"   Still waiting... ({attempt * 2}s elapsed)")
        
        if attempt >= max_attempts:
            print(Fore.RED + "\n✗ Timeout: Did not detect main menu within 2 minutes")
            print(Fore.YELLOW + "   Continuing without OCR data...")
            print(Fore.YELLOW + "="*50 + "\n")
    
    except Exception as e:
        print(Fore.RED + f"\n✗ Error during OCR detection: {e}")
        print(Fore.YELLOW + "   Continuing without OCR data...")
        print(Fore.YELLOW + "="*50 + "\n")
        import traceback
        traceback.print_exc()

def start_overlay():
    """Start the overlay UI in a separate process"""
    try:
        overlay_script = os.path.join(BASE_DIR, "OverlayUI.py")
        if os.path.exists(overlay_script):
            print(Fore.CYAN + "🎮 Starting overlay UI...")
            # Use sys.executable to get current Python (venv-aware)
            # Use pythonw to run GUI without console window
            python_exe = sys.executable
            if os.name == 'nt' and python_exe.endswith('python.exe'):
                pythonw_exe = python_exe.replace('python.exe', 'pythonw.exe')
                if os.path.exists(pythonw_exe):
                    python_exe = pythonw_exe
            subprocess.Popen([python_exe, overlay_script])
            time.sleep(1)  # Give it a moment to start
            print(Fore.GREEN + "✓ Overlay UI started!\n")
        else:
            print(Fore.YELLOW + "⚠ Overlay UI not found, skipping...\n")
    except Exception as e:
        print(Fore.RED + f"✗ Could not start overlay: {e}\n")

def detect_initial_stats():
    """Detect rank and deck on startup"""
    print(Fore.YELLOW + "\n" + "="*50)
    print(Fore.CYAN + "📊 Detecting initial rank and deck...")
    print(Fore.YELLOW + "   Make sure you're on the main menu!")
    print(Fore.YELLOW + "="*50)
    
    try:
        from RankDetector import RankDetector
        detector = RankDetector()
        
        # Wait up to 1 minute for main menu (30 attempts x 2 seconds)
        max_attempts = 30
        attempt = 0
        
        while attempt < max_attempts:
            if detector.is_on_main_menu(validation_method="auto", debug=False):
                print(Fore.GREEN + "\n✓ Main menu detected!")
                
                # Detect deck first
                deck_name = detector.extract_text("my_deck_name")
                if deck_name:
                    deck_name = " ".join(deck_name.split())
                    print(Fore.GREEN + f"✓ Initial Deck: {deck_name}")
                    deck_file = os.path.join(BASE_DIR, ".last_deck")
                    with open(deck_file, "w") as f:
                        f.write(deck_name)
                else:
                    print(Fore.YELLOW + "⚠ Could not detect deck")
                    deck_name = None
                
                # Detect rank
                rank = detector.extract_rank_safe(validate_screen=True, debug=False)
                if rank:
                    # Check if we have a previous rank to compare against
                    previous_rank = None
                    rank_file = os.path.join(BASE_DIR, ".last_rank")
                    if os.path.exists(rank_file):
                        try:
                            with open(rank_file, "r") as f:
                                previous_rank = int(f.read().strip())
                        except:
                            pass
                    
                    # Validate: if previous rank exists, validate based on game rules
                    # Can lose infinite rank, but can only gain max 30 points
                    # Or if no previous rank, accept any value (first time setup)
                    is_valid = False
                    if previous_rank:
                        rank_change = rank - previous_rank
                        if rank_change <= 30:  # Allow any loss, but only +30 gain
                            is_valid = True
                        else:
                            print(Fore.YELLOW + f"⚠ Detected rank {rank} is +{rank_change} from previous {previous_rank} (max gain is +30, OCR error, ignoring)")
                    else:
                        # No previous rank - accept any value (first time setup)
                        is_valid = True
                    
                    if is_valid:
                        print(Fore.GREEN + f"✓ Initial Rank: {rank}")
                        with open(rank_file, "w") as f:
                            f.write(str(rank))
                        
                        # Update database so overlay shows correct rank immediately
                        try:
                            db = BattleDatabase()
                            db.add_rank_update(rank, deck_name)
                            print(Fore.CYAN + f"   Database updated with rank: {rank}")
                        except Exception as e:
                            print(Fore.YELLOW + f"   Warning: Could not update database: {e}")
                else:
                    print(Fore.YELLOW + "⚠ Could not detect rank")
                
                print(Fore.GREEN + "\n✓ Initial detection complete!")
                print(Fore.YELLOW + "="*50 + "\n")
                return
            
            # Not on menu yet, wait and try again
            time.sleep(2)
            attempt += 1
            
            # Show progress every 10 attempts (20 seconds)
            if attempt % 10 == 0:
                print(Fore.CYAN + f"   Still waiting for main menu... ({attempt * 2}s elapsed)")
        
        # Timeout reached
        print(Fore.YELLOW + "\n⚠ Timeout: Main menu not detected within 1 minute")
        print(Fore.CYAN + "   (You may be in a battle or logging in)")
        print(Fore.CYAN + "   Stats will update after first battle")
        print(Fore.YELLOW + "="*50 + "\n")
    
    except Exception as e:
        print(Fore.RED + f"\n✗ Error during initial detection: {e}")
        print(Fore.YELLOW + "   Stats will update after first battle")
        print(Fore.YELLOW + "="*50 + "\n")

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Pokemon TCG Live Monitor')
    parser.add_argument('--headless', action='store_true', help='Run without console window')
    parser.add_argument('--no-overlay', action='store_true', help='Run without overlay UI')
    args = parser.parse_args()

    # Single-instance guard: if a monitor is already running, exit now so we
    # don't create a duplicate monitor + duplicate overlay.
    if not _acquire_single_instance():
        sys.exit(0)

    # Write PID file for process management
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        if not args.headless:
            print(Fore.CYAN + f"Process ID: {os.getpid()} (saved to {PID_FILE})")
    except Exception as e:
        if not args.headless:
            print(Fore.YELLOW + f"Warning: Could not write PID file: {e}")
    
    try:
        # Start the overlay UI (unless disabled)
        if not args.no_overlay:
            start_overlay()
        
        # Wait for game to be running
        wait_for_game_startup()
        
        # Detect initial rank and deck
        detect_initial_stats()
        
        # Start main monitoring loop
        monitor_clipboard()
    finally:
        # Release the single-instance lock and clean up PID file on exit.
        try:
            if _global_lock_handle is not None:
                try:
                    import msvcrt
                    _global_lock_handle.seek(0)
                    msvcrt.locking(_global_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
                try:
                    _global_lock_handle.close()
                except Exception:
                    pass
                _global_lock_handle = None
        except Exception:
            pass
        try:
            if os.path.exists(LOCK_FILE):
                os.remove(LOCK_FILE)
        except Exception:
            pass
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
                if not args.headless:
                    print(Fore.CYAN + "Cleaned up PID file")
        except:
            pass
