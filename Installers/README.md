# Pokemon TCG Live Monitor v2.4 - Installers

None of these need administrator rights.

| File | What it does |
|---|---|
| `INSTALL_COMPLETE_v2.4.bat` | Full setup. Finds or installs Python 3.12, builds the `.venv`, installs packages and Tesseract, asks for an optional OpenAI key, enables auto-start and launches the monitor. All the work is done by `..\bootstrap_setup.ps1` + `..\setup_install.py`; the log is in `..\Logs\setup.log`. |
| `Start_GUI_Mode_v2.4.bat` | Runs the monitor in a visible console (debug mode). If the background copy is already running, this one exits; close the app from Dashboard → Advanced first. |
| `Remove_AutoStart_v2.4.bat` | Turns off auto-start (registry Run key + any old scheduled tasks). |

## How auto-start works
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run\PokemonTCGLiveMonitor` =
`"<app>\.venv\Scripts\pythonw.exe" "<app>\TCGLiveMonitor.py" --headless`

At login the monitor runs hidden at below-normal priority and checks every 5 s whether Pokemon TCG Live is running. Once the game is up, it starts the overlay and the battle-end auto-export watcher. Output goes to `Logs\monitor.log`.

## Release builds (maintainers)
- `Build_Release_Package.bat`: ZIP built from `release_manifest.txt`.
- `Build_Inno_Installer.bat`: `installer_setup.iss` (per-user Setup.exe). `installer_portable.iss` is the same without Start Menu entries. Both include `installer_common.iss`.
- `Create_Portable_Installer.py`: self-extracting Tk wizard (PyInstaller).

The old `*_v2.0`–`*_v2.3` scripts in this folder are obsolete. The v2.3 complete installer pinned `openai==1.12.0` and created an elevated scheduled task, so don't use it.
