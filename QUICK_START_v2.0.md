# QUICK START - Pokemon TCG Live Monitor v2.3

## First Time Setup (5 minutes)

1. **Right-click** `Installers\INSTALL_COMPLETE_v2.3.bat`
2. Select **"Run as Administrator"**
3. Follow the installer prompts
4. Enter your OpenAI API key when asked (or choose Local-Only mode)
5. **Done!**

The monitor will now start automatically when you log in to Windows.

---

## What You'll See

When you play Pokemon TCG Live, you'll see a small overlay in the bottom-right:

```
[🔴] Elo:99 | Max:99 | 0-0
```

- **🔴 Pokeball** = Your current league tier (6 different icons)
- **Elo:99** = Your current Elo rating
- **Max:99** = Highest Elo you've achieved
- **0-0** = Today's wins-losses

The overlay:
- **Follows the game window**
- **Click-through** (won't block your clicks)
- **Updates automatically** after each battle
- **Runs in background** (no console windows)

---

## Daily Use

**You don't need to do anything!**

The monitor runs automatically on Windows login. Just play Pokemon TCG Live normally:

1. Battle ends
2. Game shows battle log
3. Monitor detects clipboard
4. AI analyzes the battle
5. Stats update in overlay
6. Database saves the battle

---

## Manual Control

### Start Manually
`Installers\Start_GUI_Mode_v2.0.bat`

### Disable Auto-Start
Right-click `Installers\Remove_AutoStart_v2.0.bat` → Run as Administrator

### View Battle History
Check `tcg_battles.db` (SQLite database)

---

## Troubleshooting

**Overlay not showing?**
- Make sure Pokemon TCG Live is running
- Check Task Manager for "pythonw.exe" process

**Battle not detected?**
- Make sure clipboard has the battle log
- Check `Logs/` folder for saved battle logs

**Need help?**
- See `Installers\README.md` for full documentation
- See `v2.0_RELEASE_NOTES.md` for technical details

---

## What Gets Installed

- Python 3.10+ (if not already installed)
- Tesseract OCR 5.5.0+ (for reading rank from screen)
- 20+ Python packages (PySide6, OpenAI, pandas, etc.)
- Windows Task Scheduler task (for auto-start)

Total install size: ~555 MB

---

## Features

**AI Battle Analysis** - GPT-4o identifies decks and winners  
**SQLite Database** - Fast statistics and history  
**OCR Rank Detection** - Reads your rank from the game screen  
**Live Overlay UI** - 8-bit pokeball icons for league tiers  
**Auto-Start** - Runs on login with no console window  
**Excel Integration** - Backup storage in spreadsheet  

---

## System Requirements

- Windows 10/11 (64-bit)
- Administrator access (for installation only)
- Internet connection (for OpenAI API)
- Pokemon TCG Live game

---

## Get Started Now!

**Right-click** `Installers\INSTALL_COMPLETE_v2.0.bat` → **Run as Administrator**

That's it! 🎉
