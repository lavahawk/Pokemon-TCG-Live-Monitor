import psutil
import pyperclip
import time
import re
import pygame
import sys
import os
import subprocess
import pyfiglet
from datetime import datetime
from colorama import init, Fore, Back, Style
import os
import sys
import tkinter as tk
from tkinter import simpledialog
import threading
from multiprocessing import Process
from BattleDatabase import BattleDatabase


###Version=2.0
# Get the script's directory (where the script is located)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define file path variables using relative paths
LOG_DIR = os.path.join(BASE_DIR, "Logs")  # Directory to save battle log files
SOUND_FILE = os.path.join(BASE_DIR, "ding.mp3")  # Path to the sound file
SCRIPT_TO_RUN = os.path.join(BASE_DIR, "AIParseBattleLog.py")  # Path to AIParseBattleLog.py

# Ensure the log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Initialize colorama
init(autoreset=True)

# Set a custom terminal window title
print("\033]0;TCG Live Monitor\007")

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

USER_CONFIG_FILE = os.path.join(BASE_DIR, ".user_config")  #  Username storage file directory
API_KEY_FILE = os.path.join(BASE_DIR, ".openai_key")  #  API key storage file directory

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

# Function to load stored data
def load_from_file(file_path):
    if os.path.exists(file_path):
        with open(file_path, "r") as file:
            return file.read().strip()
    return None

# Function to save data to a file
def save_to_file(file_path, data):
    with open(file_path, "w") as file:
        file.write(data)

# Load or prompt for username
username = load_from_file(USER_CONFIG_FILE)
if not username:
    username = get_input("First time setup \n----------------\nEnter your TCG Live username: ")
    while not username:
        print("Username cannot be empty. Please enter a valid username.")
        username = get_input("Enter your username: ")
    save_to_file(USER_CONFIG_FILE, username)

# Load or prompt for API key
API_KEY = load_from_file(API_KEY_FILE)
if not API_KEY:
    API_KEY = get_input(
        "Enter your OpenAI API Key:\n(Find or create one at https://platform.openai.com/signup)\n"
    )
    while not API_KEY:
        print("API key cannot be empty. Please enter a valid API key.")
        API_KEY = get_input("Enter your OpenAI API Key:")
    save_to_file(API_KEY_FILE, API_KEY)

def is_pokemon_tcg_live_running():
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] == "Pokemon TCG Live.exe":
            return True
    return False

def is_battle_log(clipboard_content):
    pattern = r"Turn # \d+ - .+'s Turn"
    return bool(re.search(pattern, clipboard_content))

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
    while True:
        if is_pokemon_tcg_live_running():
            clipboard_content = pyperclip.paste()
            time.sleep(2)
            if clipboard_content != previous_clipboard and is_battle_log(clipboard_content):
                save_battle_log(clipboard_content)
                play_sound()
                run_other_script()
                previous_clipboard = clipboard_content
        else:
            # If the game is not running, wait for it to start again
            print("Game closed. Waiting for Pokémon TCG Live to start...")
            wait_for_game_startup()
            print("Pokémon TCG Live is running. Monitoring clipboard...")
            previous_clipboard = ""  # Reset previous_clipboard if the game is restarted

def run_other_script():
    # Construct the absolute path to the other script
    script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), SCRIPT_TO_RUN))
    
    # Run the script using Python
    print(f"Running {script_path}...")
    subprocess.run(["python", script_path])
    
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
                            print(Fore.CYAN + f"   Database updated with rank: {rank}")
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
            # Run overlay in separate process so it doesn't block
            subprocess.Popen(["python", overlay_script], 
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
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
                    print(Fore.GREEN + f"✓ Initial Rank: {rank}")
                    rank_file = os.path.join(BASE_DIR, ".last_rank")
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
    # Start the overlay UI
    start_overlay()
    
    # Wait for game to be running
    wait_for_game_startup()
    
    # Detect initial rank and deck
    detect_initial_stats()
    
    # Start main monitoring loop
    monitor_clipboard()