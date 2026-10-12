; Shared parts of the Inno Setup installers (included by installer_setup.iss
; and installer_portable.iss). v2.4
;
; Everything installs PER USER (no admin): the app keeps its database, logs
; and caches next to the code, so it must live in a user-writable folder.
; After copying files, bootstrap_setup.ps1 finds or installs Python 3.12,
; builds the venv, installs dependencies + Tesseract, registers auto-start
; and launches the monitor.

[Files]
; All application modules (wildcard so new modules can never be forgotten
; again - v2.3 shipped without japan_data.py / BattleState.py / ContinueBlocker.py).
Source: "*.py"; DestDir: "{app}"; Excludes: "Create_Portable_Installer.py,Fix_MaxRank.py,test_*.py,*_installer_script.py"; Flags: ignoreversion
Source: "bootstrap_setup.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "Run_Headless.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Run_TCGLiveMonitor_Command_Prompt.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Install_Dependencies.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Installers\Start_GUI_Mode_v2.4.bat"; DestDir: "{app}\Installers"; Flags: ignoreversion
Source: "Installers\Remove_AutoStart_v2.4.bat"; DestDir: "{app}\Installers"; Flags: ignoreversion
Source: "Installers\README.md"; DestDir: "{app}\Installers"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "release_manifest.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "ding.mp3"; DestDir: "{app}"; Flags: ignoreversion
; Don't overwrite a user's re-calibrated OCR regions on upgrade.
Source: "screen_regions.json"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "button_templates\*.png"; DestDir: "{app}\button_templates"; Flags: onlyifdoesntexist skipifsourcedoesntexist
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "RELEASE_NOTES_v2.4.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "QUICK_START_v2.0.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\Logs"
Name: "{app}\button_templates"

[Tasks]
Name: "autostart"; Description: "Start automatically with Windows (runs hidden until Pokemon TCG Live opens - recommended)"; GroupDescription: "Auto-Start:"

[Run]
; The real setup. Shown in a console window so the (long) pip install is visible.
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\bootstrap_setup.ps1"" {code:SetupArgs}"; StatusMsg: "Installing Python packages and OCR (this can take several minutes)..."; BeforeInstall: SaveUserSettings; Flags: waituntilterminated

[Code]
var
  APIKeyPage: TInputQueryWizardPage;

function SetupArgs(Param: String): String;
begin
  Result := '-Launch -NoPause';
  if WizardIsTaskSelected('autostart') then
    Result := Result + ' -AutoStart'
  else
    Result := Result + ' -NoAutoStart';
end;

procedure InitializeWizard;
begin
  APIKeyPage := CreateInputQueryPage(wpSelectTasks,
    'OpenAI API Key (Optional)', 'AI deck detection',
    'Paste an OpenAI API key to let the app identify both decks with AI.' + #13#10 +
    'Leave it empty to use Local-Only mode (OCR + log parsing, no AI). You can change this later in the dashboard.');
  APIKeyPage.Add('OpenAI API Key:', True);
end;

// Runs right before bootstrap_setup.ps1 (BeforeInstall of the [Run] entry),
// so the key/settings exist before the monitor is first launched.
procedure SaveUserSettings;
var
  ResultCode: Integer;
begin
  begin
    if Trim(APIKeyPage.Values[0]) <> '' then
      SaveStringToFile(ExpandConstant('{app}\.openai_key'), Trim(APIKeyPage.Values[0]), False)
    else if not FileExists(ExpandConstant('{app}\.openai_key')) and not FileExists(ExpandConstant('{app}\.app_settings.json')) then
      SaveStringToFile(ExpandConstant('{app}\.app_settings.json'), '{"local_only_mode": true}', False);
    // Old v2.0-2.3 per-user tasks (elevated ones are removed by the app later).
    Exec('schtasks.exe', '/delete /tn "PokemonTCGLiveMonitor_v2.3" /f', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Stop running instances so their files can be removed.
    Exec('powershell.exe', '-NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match ''TCGLiveMonitor|OverlayUI|ContinueBlocker'' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'PokemonTCGLiveMonitor');
    Exec('schtasks.exe', '/delete /tn "PokemonTCGLiveMonitor_v2.4" /f', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
end;

[UninstallDelete]
; Program-generated files. The battle database, logs and settings are KEPT so a
; reinstall/upgrade doesn't lose history; delete the folder manually to wipe.
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\tesseract"
Type: filesandordirs; Name: "{app}\.meta_icon_cache"
Type: files; Name: "{app}\.monitor_pid"
Type: files; Name: "{app}\.monitor_lock"
