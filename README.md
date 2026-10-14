# Pokemon TCG Live Monitor

A companion app for Pokemon TCG Live that keeps track of your games for you.

It runs quietly in the background while you play. After every match it grabs the battle log, works out what you and your opponent were playing and who won, and saves it. A small overlay sits in the corner of the game showing your rank and today's record, and there's a full dashboard when you want to dig into how your decks are actually doing.

## What it does

- Saves every game automatically: your deck, their deck, the result and your rank at the time.
- Figures out the opponent's deck from the cards they played. With an OpenAI key it uses AI for this; without one it works out the deck from public decklists.
- Shows your rank, highest rank and the day's wins and losses in a little overlay on the game window.
- Has a dashboard with your rank and win rate over time, how each deck performs, and your matchups.
- Compares your decks against the current meta using tournament data from Limitless, so you can see how they stack up beyond your own handful of games.
- Has extra tabs for replays, tournament tools and decklists, so you don't have to keep a browser open next to the game.

## Getting it

Download the setup file from the [latest release](https://github.com/lavahawk/Pokemon-TCG-Live-Monitor/releases/latest) and run it. Everything it needs comes with it, and it doesn't need admin rights.

Setup asks for your TCG Live username and, if you want, an OpenAI API key. You can skip the key; the app works fine without it. If you leave auto-start on, it starts hidden when you log in and only wakes up once the game is open.

Windows will probably show a SmartScreen warning because the installer isn't signed. Click **More info → Run anyway**.

If something seems off, there's a debug version under Start menu → Pokemon TCG Live Monitor → Tools, and everything is logged to the `Logs` folder.

New to it? The [quick start guide](QUICK_START_v2.0.md) walks through the basics.

## Running from source

1. Run `Install_Dependencies.bat`. It sets up a `.venv` with Python 3.10–3.12 and installs `requirements.txt`.
2. Install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki), or drop a `tesseract\` folder next to the code.
3. Run `Run_TCGLiveMonitor_Command_Prompt.bat` to start the monitor with a console.

To build the installer (needs Inno Setup 6 and Tesseract):
```
powershell -NoProfile -ExecutionPolicy Bypass -File installer\build_installer.ps1
```
The version comes from `version.py` and the files that ship are listed in `release_manifest.txt`.

Developer notes on how everything fits together are in `DevVault/`. Open it as an Obsidian vault and start with `00 Start Here.md`.

## Requirements

- Windows 10 or 11 (64-bit)
- Pokemon TCG Live
- An OpenAI API key, only if you want AI deck detection

## Feedback

Found a bug or have an idea? [Open an issue](https://github.com/lavahawk/Pokemon-TCG-Live-Monitor/issues).
