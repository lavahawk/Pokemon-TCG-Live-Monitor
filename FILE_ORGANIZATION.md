# File Organization - Pokemon TCG Live Monitor v2.1

## PRODUCTION FILES (For Release)

### Core Application Files
```
✅ TCGLiveMonitor.py          - Main monitoring script (v2.1)
✅ AIParseBattleLog.py         - AI battle log parser
✅ BattleDatabase.py           - SQLite database module
✅ RankDetector.py             - OCR rank detection system
✅ OverlayUI.py                - Minimal overlay window (v2.1)
✅ StatsUI.py                  - Stats dashboard UI (v2.1)
✅ SetupRegions.py             - Screen region configuration tool
```

### Launcher Scripts
```
✅ Run_Headless.bat            - Launch headless (no console)
✅ Run_Headless.py             - Headless launcher script
✅ Run_TCGLiveMonitor_Command_Prompt.bat - Launch with console
✅ Run_SetupRegions.bat        - Launch region setup tool
```

### Installer & Setup
```
✅ Installers/INSTALL_COMPLETE_v2.0.bat  - Main installer (needs update to v2.1)
✅ Installers/Start_GUI_Mode_v2.0.bat    - Quick start launcher
✅ Installers/Remove_AutoStart_v2.0.bat  - Remove from startup
✅ Install_Dependencies.bat              - Manual dependency installer
✅ AutoRun_Add.py                        - Add to Windows startup
✅ AutoRun_Remove.py                     - Remove from Windows startup
```

### Configuration & Data
```
✅ requirements.txt            - Python dependencies
✅ screen_regions.json         - OCR region configuration
✅ ding.mp3                    - Notification sound
✅ icon.ico                    - Application icon
✅ .gitignore                  - Git ignore rules
✅ .gitattributes              - Git attributes
```

### Documentation (User-Facing)
```
✅ README.md                   - Main project README
✅ RELEASE_NOTES_v2.1.md       - v2.1 release notes
✅ QUICK_START_v2.0.md         - Quick start guide
✅ Installers/README.md        - Installer documentation
```

### Generated Files (User Data - Not in Repo)
```
⚠️ .openai_key                - OpenAI API key (gitignored)
⚠️ .user_config               - Username config (gitignored)
⚠️ .last_rank                 - Last detected rank (gitignored)
⚠️ .last_deck                 - Last detected deck (gitignored)
⚠️ .max_rank                  - Maximum rank achieved (gitignored)
⚠️ .monitor_pid               - Process ID file (gitignored)
⚠️ .console_pref              - Console preference (gitignored)
⚠️ TCGExampleSheet.xlsx       - Excel data export (gitignored)
⚠️ tcg_battles.db             - SQLite database (gitignored)
⚠️ Logs/                      - Battle log directory (gitignored)
```

---

## DEVELOPMENT/DEBUG FILES (Move to Dev folder or Delete)

### Test Scripts
```
❌ Test_AllRegions.py
❌ Test_ConsoleDetection.py
❌ Test_ConsolePreference.bat
❌ Test_ConsoleToggle.bat
❌ Test_ConsoleToggle.py
❌ Test_MaxRank.py
❌ Test_MenuValidation.py
❌ Test_RankDetection.py
❌ Test_SimulateBattle.py
❌ Test_StatsUI.py
❌ Test_Validation.py
❌ Run_TestRankDetection.bat
```

### Debug/Development Files
```
❌ fix_rank_data.py           - One-time database fix script
❌ debug_rank.png             - Debug screenshot
❌ IntegrateOCR_Example.py    - OCR integration example
❌ CaptureTemplate.py         - Template capture utility
❌ ViewStats.py               - Standalone stats viewer (replaced by StatsUI.py)
```

### Redundant Batch Files
```
❌ Start_Complete_System.bat  - Redundant (use Run_TCGLiveMonitor_Command_Prompt.bat)
❌ Start_Overlay.bat          - Redundant (overlay auto-starts)
❌ Stop_Overlay.bat           - Redundant (use Stats UI close button)
❌ Run_AI_ParseScript.bat     - Redundant (AI parser auto-runs)
❌ Create Build Script.bat    - Build script (development only)
❌ Create Build Script - NoGUI.bat - Build script (development only)
```

### Documentation (Development/Archive)
```
❌ ANSWER_WINDOW_RELATIVE.md
❌ CONSOLE_MANAGEMENT.md      - Keep but move to docs/
❌ CRITICAL_FIXES.md
❌ INTEGRATION_COMPLETE.md
❌ LEAGUE_ICONS.md
❌ OCR_INTEGRATION_COMPLETE.md
❌ OCR_README.md              - Merge into main README
❌ OCR_RESOLUTION_FIX.md
❌ OVERLAY_COMPLETE.md
❌ OVERLAY_DESIGN.md
❌ OVERLAY_FIXES.md
❌ OVERLAY_GUIDE.md           - Merge into main README
❌ PROCESS_MANAGEMENT.md      - Keep but move to docs/
❌ PROJECT_SUMMARY.md
❌ QUICKSTART_OCR.md          - Merge into QUICK_START
❌ QUICK_START_VALIDATION.md
❌ SCREEN_VALIDATION_GUIDE.md
❌ STATS_DASHBOARD.md         - Keep but move to docs/
❌ v2.0_RELEASE_NOTES.md      - Archive
❌ WHATS_NEW.md
❌ WINDOW_RELATIVE_UPDATE.md
❌ README.txt                 - Redundant (use README.md)
```

### Shortcuts (Not Needed in Release)
```
❌ TCGLiveMonitorCONSOLE.lnk
❌ TCGLiveMonitorNOCONSOLE.exe - Shortcut.lnk
```

### Archived/Legacy Folders
```
⚠️ _Archive/                  - Keep but exclude from release
⚠️ BackgroundRun/             - Legacy executables (may be useful)
⚠️ Testing New Stuff/         - Development experiments
⚠️ __pycache__/               - Python cache (gitignored)
⚠️ .venv/                     - Virtual environment (gitignored)
```

---

## EXPERIMENTAL/FUTURE FEATURES (Keep but Document)

```
⚠️ AutoClicker.py             - Button automation (experimental)
⚠️ SetupAutoClicker.py        - AutoClicker setup tool (experimental)
```

**Decision:** Keep these but add a notice that they're experimental/beta features.

---

## RECOMMENDED ACTIONS

### 1. Create Clean Release Structure
```
Pokemon-TCG-Live-Monitor-v2.1/
├── Core/                     # Main application files
│   ├── TCGLiveMonitor.py
│   ├── AIParseBattleLog.py
│   ├── BattleDatabase.py
│   ├── RankDetector.py
│   ├── OverlayUI.py
│   ├── StatsUI.py
│   └── SetupRegions.py
├── Installers/               # Installation scripts
│   ├── INSTALL_COMPLETE_v2.1.bat  (UPDATE FROM v2.0)
│   ├── Start_GUI_Mode_v2.1.bat
│   ├── Remove_AutoStart_v2.1.bat
│   └── README.md
├── Launchers/                # Quick launch scripts
│   ├── Run_Headless.bat
│   ├── Run_Headless.py
│   ├── Run_With_Console.bat
│   └── Run_SetupRegions.bat
├── Utils/                    # Utility scripts
│   ├── AutoRun_Add.py
│   ├── AutoRun_Remove.py
│   └── Install_Dependencies.bat
├── Experimental/             # Beta features
│   ├── AutoClicker.py
│   └── SetupAutoClicker.py
├── Docs/                     # Documentation
│   ├── README.md (main)
│   ├── RELEASE_NOTES_v2.1.md
│   ├── QUICK_START.md
│   ├── CONSOLE_MANAGEMENT.md
│   ├── PROCESS_MANAGEMENT.md
│   └── STATS_DASHBOARD.md
├── Assets/                   # Resources
│   ├── ding.mp3
│   └── icon.ico
├── requirements.txt
├── .gitignore
└── .gitattributes
```

### 2. Files to DELETE from Repository
- All Test_*.py and Test_*.bat files
- All markdown files documenting old fixes/updates
- Legacy batch files (Start_Complete_System.bat, etc.)
- Debug files (fix_rank_data.py, debug_rank.png)
- Redundant documentation
- Shortcuts (.lnk files)

### 3. Files to GITIGNORE (if not already)
- .openai_key
- .user_config
- .env
- .last_*
- .monitor_pid
- .console_pref
- *.db
- *.xlsx (except template if any)
- Logs/
- __pycache__/
- .venv/
- *.pyc
- *.pyo

### 4. Update for v2.1 Release
- Update INSTALL_COMPLETE_v2.0.bat → INSTALL_COMPLETE_v2.1.bat
- Update Start_GUI_Mode_v2.0.bat → Start_GUI_Mode_v2.1.bat
- Update Remove_AutoStart_v2.0.bat → Remove_AutoStart_v2.1.bat
- Consolidate documentation into main README.md
- Create concise QUICK_START.md
- Update version numbers in all scripts

---

## PRODUCTION RELEASE CHECKLIST

### Phase 1: Clean Repository
- [ ] Move all Test_* files to dev branch or delete
- [ ] Delete redundant documentation files
- [ ] Delete debug/one-time scripts
- [ ] Delete legacy shortcuts
- [ ] Update .gitignore for all user data files

### Phase 2: Reorganize Structure
- [ ] Create Core/ folder with main scripts
- [ ] Move installers to Installers/ (already done)
- [ ] Create Launchers/ folder for batch scripts
- [ ] Create Docs/ folder for documentation
- [ ] Create Assets/ folder for media files
- [ ] Move experimental features to Experimental/

### Phase 3: Update Installer
- [ ] Update INSTALL_COMPLETE to v2.1
- [ ] Update all references from v2.0 to v2.1
- [ ] Test installer on clean Windows machine
- [ ] Verify all paths work with new structure

### Phase 4: Documentation
- [ ] Consolidate README.md (comprehensive)
- [ ] Create QUICK_START.md (simple 5-minute guide)
- [ ] Update RELEASE_NOTES_v2.1.md
- [ ] Create CHANGELOG.md for version history

### Phase 5: Testing
- [ ] Test fresh install with new installer
- [ ] Test headless mode
- [ ] Test console mode
- [ ] Test stats dashboard
- [ ] Test AutoRun add/remove
- [ ] Verify all dependencies install correctly

### Phase 6: Release
- [ ] Commit cleaned repository
- [ ] Tag as v2.1.0
- [ ] Create GitHub release
- [ ] Upload installer package
- [ ] Add release notes
- [ ] Update README with installation instructions

---

## NOTES

- **BackgroundRun/** folder contains legacy .exe files - Keep for now but mark as deprecated
- **_Archive/** folder - Keep but exclude from release package
- **Testing New Stuff/** - Keep in dev branch only
- Consider creating a separate `dev` branch for all test/debug files
- Main branch should only have production-ready code

