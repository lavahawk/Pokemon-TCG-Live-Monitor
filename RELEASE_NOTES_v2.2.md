# Pokemon TCG Live Monitor v2.2 - Release Notes

**Release Date:** April 21, 2026

## Overview

v2.2 ships a targeted accuracy improvement: after every battle, OCR scans the main menu and **overrides the AI-assumed deck name with the real deck name detected on-screen**. This ensures the battle database always reflects the correct deck, even when GPT guesses wrong.

---

## What's New in v2.2

### Deck Name Auto-Override
- **OCR Deck Override** — After returning to the main menu, the detected deck name now replaces the AI-assumed deck in the most recent battle record
- **Database Accuracy** — `my_deck` column in `battles` table is updated with the verified OCR name alongside rank
- **Confirmation log** — Console prints `✓ Most recent battle deck overridden with OCR: <deck>` when override occurs
- **Graceful fallback** — If OCR cannot detect a deck, the AI name is preserved unchanged

### Installer
- **Professional 5-step wizard** — Welcome → License → Install Location → Installing (live progress bar + log) → Finish
- **Real-time progress bar** — Shows per-file extraction progress and step status
- **Installation log pane** — Dark-themed console inside the wizard shows every step
- **License Agreement page** — Must accept MIT license before proceeding
- **Path selection** — Browse dialog with default path and space/requirement notes
- **Finish page** — Option to open installation folder after setup

---

## Bug Fixes
- AI-assumed deck no longer persists in DB when OCR provides a better name

---

## Upgrade from v2.1
1. Stop the current monitor (Stats Dashboard → Advanced → Close Application)
2. Replace all `.py` files and `Installers\` batch files with v2.2 versions
3. Re-run `Installers\INSTALL_COMPLETE_v2.2.bat` as Administrator to update the scheduled task

---

## System Requirements
- Windows 10 / 11
- Python 3.10+
- Tesseract OCR 5.x (auto-installed)
- ~500 MB disk space
