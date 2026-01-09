import os
import tkinter as tk
from tkinter import simpledialog
from openai import OpenAI
import pandas as pd
import pyperclip
import openpyxl
from openpyxl import load_workbook
from pydantic import BaseModel
import xlwings as xw
import json
import time
from BattleDatabase import BattleDatabase

# Get the script's directory (where the script is running)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(BASE_DIR, "TCGExampleSheet.xlsx")
deck_sheet = "Limitless Meta"

# Initialize database
db = BattleDatabase()

# Define API key storage file
API_KEY_FILE = os.path.join(BASE_DIR, ".openai_key")
USER_CONFIG_FILE = os.path.join(BASE_DIR, ".user_config")  # Stores username

# Function to load stored username
def load_username():
    if os.path.exists(USER_CONFIG_FILE):
        with open(USER_CONFIG_FILE, "r") as file:
            return file.read().strip()
    return None

# Function to save username
def save_username(user):
    with open(USER_CONFIG_FILE, "w") as file:
        file.write(user)
    print(f"Username saved to {USER_CONFIG_FILE}")


# Function to load API key from the file
def load_api_key():
    if os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, "r") as file:
            return file.read().strip()
    return None

# Function to save API key to a file
def save_api_key(key):
    with open(API_KEY_FILE, "w") as file:
        file.write(key)
    print(f"API key saved to {API_KEY_FILE}")

# Check for stored username
username = load_username()

if not username:
    root = tk.Tk()
    root.withdraw()  # Hide the root window

    username = simpledialog.askstring(
        "Enter Your TCG Live Username",
        "No username found.\n\n"
        "Please enter your username to continue:",
    )

    if username:
        save_username(username)

# Load or prompt for API key
API_KEY = load_api_key()

if not API_KEY:
    root = tk.Tk()
    root.withdraw()  # Hide the root window

    API_KEY = simpledialog.askstring(
        "Enter OpenAI API Key",
        "No OpenAI API key found.\n\n"
        "You can create and find your API key at: https://platform.openai.com/api-keys\n\n"
        "Enter your OpenAI API Key:",
        show="*"
    )

    if API_KEY:
        save_api_key(API_KEY)

#Change API key for your own setup or use automated prompt as of v1.2

client = OpenAI(
    api_key=API_KEY
)

# Get battle log from clipboard
battlelog = pyperclip.paste()

# Load the deck lists from the Excel file
deck_df = pd.read_excel(file_path, deck_sheet, usecols="B", skiprows=0, nrows=40)
#print(f'{deck_df}')  #for debugging decks
possibledecks = deck_df

# Debugging: Print the variables to ensure they're being populated correctly
#print(f"Possible Decks: {possibledecks}")
#print(f"Battle Log: {battlelog}")
    
# Define the prompt before using it in the API call
prompt = f"""
Here is a list of the most popular Pokemon TCG deck names pick from these primarily: {possibledecks}. The main attacker of each deck is usually the deck name but not always. Sometimes a deck is named for its engine rather than attacker.
Below is a battle log. Determine the winner and the decks used by each player based on the cards used and held. If no battlelog was provided return blank. Please include a confidence value that you got the each deck correctly 0-100. Please be accurate with your confidence value considering you should need to see a lot of cards played out of the 60 total in each deck to have an understanding of what each player is fully playing and also your lack of knowledge of current deck name meanings.
My username is {username}. Report if I won or lost the battle. 
Export the data as JSON with these fields: My_deck, OpponentsDeck, Win_or_Loss, Confidence
Battlelog:
"{battlelog}"
"""
#print(f'{prompt}) for debugging prompt

class BattleLogOutput(BaseModel):
    My_deck: str
    OpponentsDeck: str
    Win_or_Loss: str
    Confidence: int
 
completion = client.chat.completions.create(
        model="gpt-5",
        messages=[
            {"role": "system", "content": "You are an assistant that parses Pokemon TCG battle logs and outputs JSON format data."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"}
    )

# print(completion.choices[0].message.content) # For Debugging
response = completion.choices[0].message.content

# print(type(response))  # Debugging: Print the type of the response
# print(response)  


# Example response
#response = {"My_deck":"Dragapult Charizard","OpponentsDeck":"Dragapult LZ Box","Win_or_Loss":"Win"}


# Parse the JSON string into a dictionary
response_dict = json.loads(response)

# Extract values from the dictionary
my_deck = response_dict.get('My_deck')
opponents_deck = response_dict.get('OpponentsDeck')
win_or_loss = response_dict.get('Win_or_Loss')
confidence = response_dict.get('Confidence')
#cards_seen = response_dict.get('Cards_Seen')

# Print the The Information for console viewers
print(f"-------------------------- ")
print(f"My Deck: {my_deck}  |  Opponent's Deck: {opponents_deck}  |  Result: {win_or_loss}  |  Confidence: {confidence}%" )
# print(f"Opponent's Deck: {opponents_deck}")
# print(f"Result: {win_or_loss}")
print(f"--------------------------")

# Load the workbook
workbook = openpyxl.load_workbook(file_path)

# Select the sheet with the name of my deck, or create it if it doesn't exist
if my_deck in workbook.sheetnames:
    sheet = workbook[my_deck]
else:
    if len(my_deck) > 31:
        sheet = workbook.create_sheet(title=my_deck[:31])  # Truncate to 31 characters
    else:
        sheet = workbook.create_sheet(title=my_deck)


# Find the first truly empty row in column A
next_row = 1
while sheet.cell(row=next_row, column=1).value is not None:
    next_row += 1

# Write the win/loss information and deck name to the sheet
sheet.cell(row=next_row, column=1).value = win_or_loss
sheet.cell(row=next_row, column=2).value = opponents_deck
# Save the workbook

workbook.save(file_path)
print("Saved Succesfully!^v^")

# Save to database
try:
    # Get current rank from file if it exists
    rank_file = os.path.join(BASE_DIR, ".last_rank")
    current_rank = None
    if os.path.exists(rank_file):
        with open(rank_file, "r") as f:
            try:
                current_rank = int(f.read().strip())
            except:
                pass
    
    # Get the most recent log file
    log_dir = os.path.join(BASE_DIR, "Logs")
    log_files = [f for f in os.listdir(log_dir) if f.startswith("battle_log_") and f.endswith(".txt")]
    if log_files:
        log_files.sort(reverse=True)
        latest_log = os.path.join(log_dir, log_files[0])
    else:
        latest_log = None
    
    # Save battle to database
    db.add_battle(
        my_deck=my_deck,
        opponent_deck=opponents_deck,
        result=win_or_loss,
        my_rank=current_rank,
        confidence=confidence,
        deck_source="AI",
        log_file=latest_log
    )
    print(f"✓ Battle saved to database (Rank: {current_rank if current_rank else 'N/A'})")
except Exception as e:
    print(f"Warning: Could not save to database: {e}")

time.sleep(5)