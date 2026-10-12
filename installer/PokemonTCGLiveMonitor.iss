; Pokemon TCG Live Monitor - Windows installer (Inno Setup 6)
;
; Built by installer\build_installer.ps1, which stages a self-contained bundle
; (Python runtime with all packages + Tesseract + app files) and passes:
;   /DAppVersion=x.y.z /DStageDir=... /DArtDir=... /DRootDir=...
;
; Design
;   * Per-user install, no admin prompt, nothing downloaded at install time.
;   * Same AppId as the v2.4 bootstrap installers, so it upgrades them in place
;     (and removes their .venv / batch-file leftovers).
;   * Battle history, settings and captured button images survive upgrades;
;     uninstall asks before deleting them.

#ifndef AppVersion
  #error Build with installer\build_installer.ps1 (AppVersion not defined)
#endif
#define AppName      "Pokemon TCG Live Monitor"
#define AppPublisher "lavahawk"
#define AppURL       "https://github.com/lavahawk/Pokemon-TCG-Live-Monitor"
#define RunValue     "PokemonTCGLiveMonitor"

[Setup]
AppId={{D8F9A4C3-7B2E-4F1A-9D3C-5E8F1A2B4C6D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoDescription={#AppName} Setup
; The app keeps its database and logs next to its code, so it must live in a
; folder the user can write to: per-user install, no admin rights.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputBaseFilename=PokemonTCGLiveMonitor-{#AppVersion}-Setup
SetupIconFile={#RootDir}\icon.ico
UninstallDisplayIcon={app}\icon.ico
UninstallDisplayName={#AppName}
LicenseFile={#RootDir}\LICENSE
WizardStyle=modern
WizardSizePercent=110
WizardImageFile={#ArtDir}\wizard-large-100.bmp,{#ArtDir}\wizard-large-200.bmp
WizardSmallImageFile={#ArtDir}\wizard-small-100.bmp,{#ArtDir}\wizard-small-200.bmp
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
; Running copies are stopped by [Code] (Python processes ignore Restart Manager).
CloseApplications=no
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nIt tracks your Pokemon TCG Live battles automatically: deck and rank detection, win rates, and a stats dashboard.%n%nEverything it needs is included - no Python, downloads or administrator rights required.

[Tasks]
Name: "autostart"; Description: "Start automatically when I sign in to Windows (stays hidden until Pokemon TCG Live is opened)"; GroupDescription: "Background monitor:"
Name: "desktopicon"; Description: "Create a desktop shortcut for the Stats Dashboard"; GroupDescription: "Shortcuts:"; Flags: unchecked

[InstallDelete]
; Always replace the runtime wholesale so no stale packages linger.
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\tesseract"
Type: filesandordirs; Name: "{app}\__pycache__"
; Leftovers of the v2.0-2.4 script-based installers.
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\Installers"
Type: files; Name: "{app}\bootstrap_setup.ps1"
Type: files; Name: "{app}\setup_install.py"
Type: files; Name: "{app}\Install_Dependencies.bat"
Type: files; Name: "{app}\Run_Headless.bat"
Type: files; Name: "{app}\Run_TCGLiveMonitor_Command_Prompt.bat"
Type: files; Name: "{app}\SetupStartup.py"
Type: files; Name: "{app}\SetupStartup.exe"
; Cached button positions from older builds could be wrong; they are re-learnt.
Type: files; Name: "{app}\button_templates\scale_cache.json"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Excludes: "\screen_regions.json,\button_templates\*"; Flags: ignoreversion recursesubdirs createallsubdirs
; User-calibrated files: install defaults only on first install.
Source: "{#StageDir}\screen_regions.json"; DestDir: "{app}"; Flags: onlyifdoesntexist
Source: "{#StageDir}\button_templates\*"; DestDir: "{app}\button_templates"; Flags: onlyifdoesntexist skipifsourcedoesntexist

[Dirs]
Name: "{app}\Logs"

[Icons]
Name: "{autoprograms}\{#AppName}\{#AppName}"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\TCGLiveMonitor.py"" --headless"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Comment: "Start the background monitor (the overlay appears when Pokemon TCG Live is running)"
Name: "{autoprograms}\{#AppName}\Stats Dashboard"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\StatsUI.py"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Comment: "Win rates, decks and battle history"
Name: "{autoprograms}\{#AppName}\Tools\Monitor (debug console)"; Filename: "{app}\runtime\python.exe"; Parameters: """{app}\TCGLiveMonitor.py"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Comment: "Run the monitor with a visible log window"
Name: "{autoprograms}\{#AppName}\Tools\Recapture auto-export buttons"; Filename: "{app}\runtime\python.exe"; Parameters: """{app}\SetupAutoClicker.py"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{autoprograms}\{#AppName}\Tools\Log files"; Filename: "{app}\Logs"
Name: "{autoprograms}\{#AppName}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Pokemon TCG Live Stats"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\StatsUI.py"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#RunValue}"; ValueData: """{app}\runtime\pythonw.exe"" ""{app}\TCGLiveMonitor.py"" --headless"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\TCGLiveMonitor.py"" --headless"; WorkingDir: "{app}"; Description: "Start the monitor now"; Flags: postinstall nowait skipifsilent
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\StatsUI.py"""; WorkingDir: "{app}"; Description: "Open the Stats Dashboard"; Flags: postinstall nowait skipifsilent unchecked

[UninstallDelete]
; Generated at runtime. Battle history, settings and logs are handled by the
; "delete my data?" question in [Code].
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\tesseract"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\.meta_icon_cache"
Type: files; Name: "{app}\.monitor_pid"
Type: files; Name: "{app}\.monitor_lock"
Type: files; Name: "{app}\button_templates\scale_cache.json"

[Code]
var
  AccountPage: TInputQueryWizardPage;
  AccountPrefilled: Boolean;

// Stop every process running from the install folder (monitor, overlay,
// blocker, dashboard and Qt WebEngine helpers) so files can be replaced.
procedure StopRunningCopies(Dir: String);
var
  ResultCode: Integer;
  Cmd: String;
begin
  StringChangeEx(Dir, '''', '''''', True);
  Cmd := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "' +
    '$d = ''' + Dir + '''; ' +
    'Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and (' +
    '($_.ExecutablePath -and $_.ExecutablePath.StartsWith($d + ''\'', [StringComparison]::OrdinalIgnoreCase)) -or ' +
    '($_.CommandLine -and $_.CommandLine.IndexOf($d, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and ' +
    '$_.CommandLine -match ''TCGLiveMonitor|OverlayUI|ContinueBlocker|StatsUI'')) } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"';
  Exec('powershell.exe', Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(800);
end;

function ReadTextFile(Path: String): String;
var
  S: AnsiString;
begin
  Result := '';
  if FileExists(Path) and LoadStringFromFile(Path, S) then
    Result := Trim(String(S));
end;

procedure InitializeWizard;
begin
  AccountPage := CreateInputQueryPage(wpSelectTasks,
    'Your account', 'Both fields are optional and can be changed later in the dashboard.',
    'Your Pokemon TCG Live username lets the monitor tell your moves from your opponent''s in battle logs.' + #13#10#13#10 +
    'An OpenAI API key enables AI deck detection. Without one the app runs in Local-Only mode (OCR and log parsing).');
  AccountPage.Add('Pokemon TCG Live username:', False);
  AccountPage.Add('OpenAI API key (optional):', True);
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  // Pre-fill from an existing install (the folder is known only by now).
  if (CurPageID = AccountPage.ID) and not AccountPrefilled then
  begin
    AccountPage.Values[0] := ReadTextFile(AddBackslash(WizardDirValue) + '.user_config');
    AccountPage.Values[1] := ReadTextFile(AddBackslash(WizardDirValue) + '.openai_key');
    AccountPrefilled := True;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Result := '';
  StopRunningCopies(ExpandConstant('{app}'));
  // Scheduled tasks created by v2.0-2.4 (per-user ones; elevated ones are
  // removed by the app itself when it next changes the auto-start setting).
  Exec('schtasks.exe', '/delete /tn "PokemonTCGLiveMonitor_v2.3" /f', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec('schtasks.exe', '/delete /tn "PokemonTCGLiveMonitor_v2.4" /f', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Dir, User, Key: String;
begin
  if CurStep <> ssPostInstall then
    Exit;
  Dir := ExpandConstant('{app}');
  if not WizardSilent then
  begin
    User := Trim(AccountPage.Values[0]);
    Key := Trim(AccountPage.Values[1]);
    if User <> '' then
      SaveStringToFile(Dir + '\.user_config', User, False);
    if Key <> '' then
      SaveStringToFile(Dir + '\.openai_key', Key, False)
    else
      DeleteFile(Dir + '\.openai_key');
  end;
  if not FileExists(Dir + '\.openai_key') and not FileExists(Dir + '\.app_settings.json') then
    SaveStringToFile(Dir + '\.app_settings.json', '{"local_only_mode": true}', False);
  // Unticked on this run: make sure an earlier auto-start entry is gone.
  if not WizardIsTaskSelected('autostart') then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#RunValue}');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Dir: String;
begin
  Dir := ExpandConstant('{app}');
  if CurUninstallStep = usUninstall then
  begin
    StopRunningCopies(Dir);
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#RunValue}');
  end
  else if CurUninstallStep = usPostUninstall then
  begin
    if DirExists(Dir) and not UninstallSilent and
       (MsgBox('Also delete your battle history, settings and logs?' + #13#10#13#10 +
               'Choose No to keep them for a future reinstall.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES) then
      DelTree(Dir, True, True, True);
  end;
end;
