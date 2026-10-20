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
; ai = built-in AI through the hosted proxy; free = local predictor or your own model.
#ifndef Edition
  #define Edition "ai"
#endif
#ifndef EditionTag
  #define EditionTag ""
#endif

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
OutputBaseFilename=PokemonTCGLiveMonitor-{#AppVersion}-{#EditionTag}Setup
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
; Never ship user data, whatever ends up in the stage (an empty tcg_battles.db
; from the build's smoke test overwrote users' battles on upgrade, v2.4-2.6).
Source: "{#StageDir}\*"; DestDir: "{app}"; Excludes: "\screen_regions.json,\button_templates\*,\*.db,\*.db-journal,\.*,\Logs\*,\Backups\*"; Flags: ignoreversion recursesubdirs createallsubdirs
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
; In-app updates (silent) leave the desktop and auto-start choices exactly as the user has them now.
Name: "{autodesktop}\Pokemon TCG Live Stats"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\StatsUI.py"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon; Check: not WizardSilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#RunValue}"; ValueData: """{app}\runtime\pythonw.exe"" ""{app}\TCGLiveMonitor.py"" --headless"; Tasks: autostart; Check: not WizardSilent

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\TCGLiveMonitor.py"" --headless"; WorkingDir: "{app}"; Description: "Start the monitor now"; Flags: postinstall nowait skipifsilent
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\StatsUI.py"""; WorkingDir: "{app}"; Description: "Open the Stats Dashboard"; Flags: postinstall nowait skipifsilent unchecked
; In-app update (updater.py runs this installer with /VERYSILENT /RELAUNCH=1): start the monitor again.
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\TCGLiveMonitor.py"" --headless"; WorkingDir: "{app}"; Flags: nowait; Check: RelaunchAfterUpdate

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
  AIPage: TInputOptionWizardPage;
  KeyPage: TInputQueryWizardPage;
  CompatPage: TInputQueryWizardPage;
  AIPrefilled: Boolean;
  // AIPage index -> provider ("hosted" only in the AI edition).
  AIProviders: array of String;

// Stop every process running from the install folder (monitor, overlay,
// blocker, dashboard and Qt WebEngine helpers) so files can be replaced.
// Only Python / Qt processes: this Setup's own command line can contain the
// folder (/DIR=, /LOG=) and "TCGLiveMonitor" (its file name) - matching it
// made Setup kill itself (exit -1, found 2026-10-16).
procedure StopRunningCopies(Dir: String);
var
  ResultCode: Integer;
  Cmd: String;
begin
  StringChangeEx(Dir, '''', '''''', True);
  Cmd := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "' +
    '$d = ''' + Dir + '''; ' +
    'Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and ' +
    '$_.Name -match ''^(python|pythonw|QtWebEngineProcess|tesseract)\.exe$'' -and (' +
    '($_.ExecutablePath -and $_.ExecutablePath.StartsWith($d + ''\'', [StringComparison]::OrdinalIgnoreCase)) -or ' +
    '($_.CommandLine -and $_.CommandLine.IndexOf($d, [StringComparison]::OrdinalIgnoreCase) -ge 0 -and ' +
    '$_.CommandLine -match ''TCGLiveMonitor|OverlayUI|ContinueBlocker|StatsUI'')) } | ' +
    'ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"';
  Exec('powershell.exe', Cmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(800);
end;

// The auto-start value is shared by every copy (a dev checkout, another
// install folder). Only touch it when it points at THIS install.
function RunValueIsOurs(Dir: String): Boolean;
var
  Value: String;
begin
  Result := RegQueryStringValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#RunValue}', Value)
    and (Pos(Lowercase(AddBackslash(Dir)), Lowercase(Value)) > 0);
end;

function ReadTextFile(Path: String): String;
var
  S: AnsiString;
begin
  Result := '';
  if FileExists(Path) and LoadStringFromFile(Path, S) then
    Result := Trim(String(S));
end;

procedure AddProvider(Id, Caption: String);
begin
  SetArrayLength(AIProviders, GetArrayLength(AIProviders) + 1);
  AIProviders[GetArrayLength(AIProviders) - 1] := Id;
  AIPage.Add(Caption);
end;

function ChosenProvider: String;
begin
  Result := 'none';
  if (AIPage.SelectedValueIndex >= 0) and (AIPage.SelectedValueIndex < GetArrayLength(AIProviders)) then
    Result := AIProviders[AIPage.SelectedValueIndex];
end;

procedure SelectProvider(Id: String);
var
  I: Integer;
begin
  for I := 0 to GetArrayLength(AIProviders) - 1 do
    if AIProviders[I] = Id then
      AIPage.SelectedValueIndex := I;
end;

function JsonString(Value: String): String;
var
  I: Integer;
begin
  StringChangeEx(Value, '\', '\\', True);
  StringChangeEx(Value, '"', '\"', True);
  // Control characters (tabs, line breaks...) are invalid raw in JSON: \u-escape them.
  for I := 0 to 31 do
    StringChangeEx(Value, Chr(I), '\u00' + Copy('0123456789abcdef', (I div 16) + 1, 1) +
      Copy('0123456789abcdef', (I mod 16) + 1, 1), True);
  Result := '"' + Value + '"';
end;

procedure InitializeWizard;
begin
  AccountPage := CreateInputQueryPage(wpSelectTasks,
    'Your account', 'Optional; you can change it later in the dashboard.',
    'Your Pokemon TCG Live username lets the monitor tell your moves from your opponent''s in battle logs.');
  AccountPage.Add('Pokemon TCG Live username:', False);

  AIPage := CreateInputOptionPage(AccountPage.ID, 'AI deck detection',
    'How should the app name your opponent''s deck after each battle?',
    'You can change this any time in the dashboard (Settings, AI Parsing Mode).', True, False);
#if Edition == "ai"
  AddProvider('hosted', 'Built-in AI (recommended, nothing to set up)');
#endif
  AddProvider('openai', 'My own OpenAI API key');
  AddProvider('compatible', 'A local model or another provider (Ollama, LM Studio, OpenRouter, Groq...)');
  AddProvider('none', 'No AI: I pick the deck myself, helped by the local predictor');
  AIPage.SelectedValueIndex := 0;

  KeyPage := CreateInputQueryPage(AIPage.ID, 'Your OpenAI API key',
    'Stored encrypted for your Windows account only.',
    'Create a key at platform.openai.com/api-keys. Leave it empty to keep the key already saved by an earlier install.');
  KeyPage.Add('OpenAI API key:', True);

  CompatPage := CreateInputQueryPage(AIPage.ID, 'Your model',
    'Any server that speaks the OpenAI chat API.',
    'Examples: Ollama http://localhost:11434/v1 (model e.g. llama3.1), LM Studio http://localhost:1234/v1, ' +
    'OpenRouter https://openrouter.ai/api/v1. The key is optional for local servers.');
  CompatPage.Add('Base URL:', False);
  CompatPage.Add('Model name:', False);
  CompatPage.Add('API key (optional):', True);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := ((PageID = KeyPage.ID) and (ChosenProvider <> 'openai')) or
            ((PageID = CompatPage.ID) and (ChosenProvider <> 'compatible'));
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Dir: String;
begin
  Result := True;
  Dir := AddBackslash(WizardDirValue);
  if (CurPageID = KeyPage.ID) and (Trim(KeyPage.Values[0]) = '') and not FileExists(Dir + '.openai_key.dpapi') then
  begin
    MsgBox('Enter your OpenAI API key, or go back and choose another option.', mbError, MB_OK);
    Result := False;
  end
  else if (CurPageID = CompatPage.ID) and ((Trim(CompatPage.Values[0]) = '') or (Trim(CompatPage.Values[1]) = '')) then
  begin
    MsgBox('Enter the base URL and the model name.', mbError, MB_OK);
    Result := False;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Settings: String;
begin
  // Pre-fill from an existing install (the folder is known only by now).
  if (CurPageID = AccountPage.ID) and not AccountPrefilled then
  begin
    AccountPage.Values[0] := ReadTextFile(AddBackslash(WizardDirValue) + '.user_config');
    AccountPrefilled := True;
  end;
  // An earlier install's choice: keep it selected (keys stay encrypted on disk).
  if (CurPageID = AIPage.ID) and not AIPrefilled then
  begin
    Settings := ReadTextFile(AddBackslash(WizardDirValue) + '.app_settings.json');
    if Pos('"ai_provider": "compatible"', Settings) > 0 then
      SelectProvider('compatible')
    // local_only_mode alone was the old installers' default without a key.
    else if Pos('"ai_provider": "none"', Settings) > 0 then
      SelectProvider('none')
    else if FileExists(AddBackslash(WizardDirValue) + '.openai_key.dpapi') then
      SelectProvider('openai')
#if Edition == "free"
    else
      SelectProvider('none')
#endif
    ;
    AIPrefilled := True;
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

function RelaunchAfterUpdate: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RELAUNCH|0}') = '1');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Dir, User, Key, Provider, Choice: String;
  ResultCode: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;
  Dir := ExpandConstant('{app}');
  // Silent runs (in-app updates) never touch the account or the AI choice.
  if not WizardSilent then
  begin
    User := Trim(AccountPage.Values[0]);
    if User <> '' then
      SaveStringToFile(Dir + '\.user_config', User, False);
    // Plain-text keys are encrypted (DPAPI) and deleted by the app on its
    // first start (app_settings / ai_provider).
    Provider := ChosenProvider;
    Choice := '{"ai_provider": ' + JsonString(Provider);
    if Provider = 'openai' then
    begin
      Key := Trim(KeyPage.Values[0]);
      if Key <> '' then
        SaveStringToFile(Dir + '\.openai_key', Key, False);
    end
    else if Provider = 'compatible' then
    begin
      Choice := Choice + ', "ai_base_url": ' + JsonString(Trim(CompatPage.Values[0])) +
                ', "ai_model": ' + JsonString(Trim(CompatPage.Values[1]));
      Key := Trim(CompatPage.Values[2]);
      if Key <> '' then
        SaveStringToFile(Dir + '\.ai_compat_key', Key, False);
    end;
    SaveStringToFile(Dir + '\.ai_provider_install.json', Choice + '}', False);
    // Encrypt (DPAPI) and delete the plain-text keys right away instead of at
    // the app's first start: both loaders migrate on read (no DB is created).
    // The app folder comes from the working directory, so no path is quoted.
    if FileExists(Dir + '\.openai_key') or FileExists(Dir + '\.ai_compat_key') then
      Exec(Dir + '\runtime\python.exe',
        '-I -c "import os, sys; sys.path.insert(0, os.getcwd()); import app_settings, ai_provider; ' +
        'app_settings.load_api_key(); ai_provider.load_compat_key()"',
        Dir, SW_HIDE, ewWaitUntilTerminated, ResultCode);
  end;
  // Unticked on this run: remove an earlier auto-start entry of THIS install
  // (never one that launches another copy, e.g. a dev checkout).
  if not WizardSilent and not WizardIsTaskSelected('autostart') and RunValueIsOurs(Dir) then
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
    if RunValueIsOurs(Dir) then
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
