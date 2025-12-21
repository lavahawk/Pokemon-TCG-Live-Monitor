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

# Get the script's directory (where the script is located)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Define file path variables using relative paths
LOG_DIR = os.path.join(BASE_DIR, "dist", "Logs")  # Directory to save battle log files
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
    filename = get_new_filename()  # Generate a new filename for each clipboard copy
    os.makedirs(LOG_DIR, exist_ok=True)  # Ensure the directory exists
    with open(filename, "w") as file:
        file.write(log + "\n\n")

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

if __name__ == "__main__":
    wait_for_game_startup()
    monitor_clipboard()