---
tags: [module, ops]
files: [startup_utils.py, SetupStartup.py, Run_Headless.*, AutoRun_*.py, setup_install.py, installer_*.iss, Create_Portable_Installer.py, Build_*.bat, Installers/*.bat]
---
# Startup, launchers and installers

## Launch paths
| Path | Command | Notes |
|---|---|---|
| Console | `Run_TCGLiveMonitor_Command_Prompt.bat` → venv `python TCGLiveMonitor.py` | safest today |
| Headless | `Run_Headless.bat` → hidden cmd → `pythonw Run_Headless.py` → `startup_utils.launch_monitor(headless)` → `pythonw TCGLiveMonitor.py --headless` | BUG-009 |
| Auto-start (current) | HKCU `Run\PokemonTCGLiveMonitor` = `"pythonw" "TCGLiveMonitor.py" --headless` | via `startup_utils.add_registry`, `setup_install.configure_startup` |
| Auto-start (bat installer) | schtasks `PokemonTCGLiveMonitor_v2.3` `/rl highest` onlogon | SEC-11 |
| Frozen | `BackgroundRun/dist/TCGLiveMonitorNOCONSOLE.exe` (57 MB, old PyInstaller build) | stale |

`startup_utils.enable_startup()`: registry first; if that fails, create a task, but then `remove_task()` deletes `TASK_NAME` along with the legacy ones (BUG-016).

## Installers (4 separate file lists, all stale; BUG-003)
- `Installers/INSTALL_COMPLETE_v2.3.bat`: admin; Python check; Tesseract 5.5.0 download + silent install; venv; hand-written pip list (BUG-013); API key prompt; schtasks.
- `installer_setup.iss` (Program Files, admin) / `installer_portable.iss` (LocalAppData, no admin) → `[Run] {sys}\python.exe setup_install.py` (broken path).
- `setup_install.py`: venv → `pip -r requirements.txt` (fallback list) → Tesseract via 7-Zip extract or silent install (SEC-06) → Run key.
- `Create_Portable_Installer.py`: builds a Tk wizard with the app zipped as base64 (`Installers/Build/wizard_installer_script.py`, 12 MB).
- `Build_Release_Package.bat`, `Build_Inno_Installer.bat`.

Recommendation: one `release_manifest.txt` used by all builders, plus a smoke test that imports every module from the built folder.

## 2026-10-12 release build (current)
The offline Inno installer (`installer\build_installer.ps1` → `installer\PokemonTCGLiveMonitor.iss`) replaces the old installers above.
- Silent install verified (exit 0). Auto-start `Run` value is only removed when it points at the install folder being changed (`RunValueIsOurs`).
- Hidden monitor: `runtime\pythonw.exe TCGLiveMonitor.py --headless`. No dialogs before the game is detected. Idle cost ~0.3% CPU (Toolhelp32 process snapshot in `game_window.py`).
- Single instance: a second `--headless` launch logs "Another monitor instance is already running - exiting." and exits 0.
