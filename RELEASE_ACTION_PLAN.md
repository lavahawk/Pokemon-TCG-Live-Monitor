# v2.1 Release Action Plan

## Current Situation
We have many files mixed together - production code, test scripts, debug files, and documentation. We need to clean this up for a professional release.

## Goal
Create a clean, professional release with:
1. Only production-ready files in main branch
2. Proper installer that works on any Windows PC
3. Auto-start headless mode by default
4. API key setup during installation (optional)

---

## Immediate Actions

### Step 1: Unstage Current Changes
```powershell
git reset
```
We need to be selective about what goes into v2.1.

### Step 2: Update Installer to v2.1
- Update INSTALL_COMPLETE_v2.0.bat → v2.1
- Add headless mode as default
- Improve API key setup prompts
- Better error handling

### Step 3: Clean Up Test/Debug Files
Move to separate Dev folder or delete:
- Test_*.py files (11 files)
- Test_*.bat files
- fix_rank_data.py
- debug_rank.png
- Legacy documentation files

### Step 4: Update Core Files
- Ensure all version numbers say v2.1
- Verify all imports and paths work
- Test each core script independently

### Step 5: Selective Git Add
Only add production files:
```powershell
# Core application
git add TCGLiveMonitor.py
git add AIParseBattleLog.py
git add BattleDatabase.py
git add RankDetector.py
git add OverlayUI.py
git add StatsUI.py
git add SetupRegions.py

# Utilities
git add AutoRun_Add.py
git add AutoRun_Remove.py
git add Run_Headless.py

# Launchers
git add Run_Headless.bat
git add Run_TCGLiveMonitor_Command_Prompt.bat
git add Run_SetupRegions.bat
git add Install_Dependencies.bat

# Experimental (beta features)
git add AutoClicker.py
git add SetupAutoClicker.py

# Configuration
git add requirements.txt
git add .gitignore
git add .gitattributes

# Assets
git add ding.mp3
git add icon.ico

# Installers
git add Installers/INSTALL_COMPLETE_v2.1.bat  (after creating)
git add Installers/Start_GUI_Mode_v2.1.bat    (after creating)
git add Installers/Remove_AutoStart_v2.1.bat  (after creating)
git add Installers/README.md

# Documentation
git add README.md
git add RELEASE_NOTES_v2.1.md
git add QUICK_START_v2.0.md
git add FILE_ORGANIZATION.md
```

### Step 6: Commit and Release
```powershell
git commit -m "Release v2.1.0: Production-Ready with Headless Auto-Start"
git tag -a v2.1.0 -m "Version 2.1.0 - Production Release"
git push origin main
git push origin v2.1.0
```

---

## Files to Keep (Production)

### Essential Core (7 files)
1. TCGLiveMonitor.py - Main monitor
2. AIParseBattleLog.py - AI parser
3. BattleDatabase.py - Database
4. RankDetector.py - OCR detection
5. OverlayUI.py - Overlay UI
6. StatsUI.py - Stats dashboard
7. SetupRegions.py - Region setup

### Utilities (3 files)
8. AutoRun_Add.py - Add to startup
9. AutoRun_Remove.py - Remove from startup
10. Run_Headless.py - Headless launcher

### Launchers (4 files)
11. Run_Headless.bat - Headless mode
12. Run_TCGLiveMonitor_Command_Prompt.bat - Console mode
13. Run_SetupRegions.bat - Setup regions
14. Install_Dependencies.bat - Manual install

### Experimental (2 files)
15. AutoClicker.py - Button automation
16. SetupAutoClicker.py - AutoClicker setup

### Config/Assets (5 files)
17. requirements.txt - Dependencies
18. .gitignore - Git ignore
19. .gitattributes - Git attributes
20. ding.mp3 - Sound file
21. icon.ico - App icon

### Installers (3-4 files)
22. INSTALL_COMPLETE_v2.1.bat - Main installer
23. Start_GUI_Mode_v2.1.bat - Quick launcher
24. Remove_AutoStart_v2.1.bat - Remove startup
25. Installers/README.md - Installation docs

### Documentation (4 files)
26. README.md - Main readme
27. RELEASE_NOTES_v2.1.md - Release notes
28. QUICK_START_v2.0.md - Quick start
29. FILE_ORGANIZATION.md - This file

**Total: ~29 core files** (plus BackgroundRun/ legacy folder)

---

## Files to Remove/Ignore

### Test Scripts (13 files) - DELETE or move to dev branch
- Test_AllRegions.py
- Test_ConsoleDetection.py
- Test_ConsolePreference.bat
- Test_ConsoleToggle.bat
- Test_ConsoleToggle.py
- Test_MaxRank.py
- Test_MenuValidation.py
- Test_RankDetection.py
- Test_SimulateBattle.py
- Test_StatsUI.py
- Test_Validation.py
- Run_TestRankDetection.bat
- Run_AI_ParseScript.bat

### Debug/One-time Scripts (4 files) - DELETE
- fix_rank_data.py
- debug_rank.png
- IntegrateOCR_Example.py
- CaptureTemplate.py

### Redundant Scripts (5 files) - DELETE
- Start_Complete_System.bat
- Start_Overlay.bat
- Stop_Overlay.bat
- ViewStats.py (replaced by StatsUI.py)
- README.txt (use README.md)

### Old Documentation (20+ files) - DELETE or consolidate
- ANSWER_WINDOW_RELATIVE.md
- CONSOLE_MANAGEMENT.md (move to docs/)
- CRITICAL_FIXES.md
- INTEGRATION_COMPLETE.md
- LEAGUE_ICONS.md
- OCR_INTEGRATION_COMPLETE.md
- OCR_README.md
- OCR_RESOLUTION_FIX.md
- OVERLAY_COMPLETE.md
- OVERLAY_DESIGN.md
- OVERLAY_FIXES.md
- OVERLAY_GUIDE.md
- PROCESS_MANAGEMENT.md (move to docs/)
- PROJECT_SUMMARY.md
- QUICKSTART_OCR.md
- QUICK_START_VALIDATION.md
- SCREEN_VALIDATION_GUIDE.md
- STATS_DASHBOARD.md (move to docs/)
- v2.0_RELEASE_NOTES.md
- WHATS_NEW.md
- WINDOW_RELATIVE_UPDATE.md

### Shortcuts (2 files) - DELETE
- TCGLiveMonitorCONSOLE.lnk
- TCGLiveMonitorNOCONSOLE.exe - Shortcut.lnk

---

## Next Steps

1. **Review this plan** - Confirm approach
2. **Unstage all changes** - Start fresh
3. **Update installer** - Create v2.1 installer
4. **Test installer** - Verify it works
5. **Selective commit** - Only production files
6. **Create release** - GitHub release with proper notes

Ready to proceed?
