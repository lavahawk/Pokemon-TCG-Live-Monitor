; Pokemon TCG Live Monitor v2.3.0 - Inno Setup Installer Script
; Creates a professional Windows installer (.exe)
; Requires: Inno Setup 6 (https://jrsoftware.org/isinfo.php)
; Build:   iscc installer_setup.iss

#define MyAppName "Pokemon TCG Live Monitor"
#define MyAppVersion "2.3.0"
#define MyAppPublisher "lavahawk"
#define MyAppURL "https://github.com/lavahawk/Pokemon-TCG-Live-Monitor"
#define MyAppExeName "TCGLiveMonitor.py"

[Setup]
; Basic Information
AppId={{D8F9A4C3-7B2E-4F1A-9D3C-5E8F1A2B4C6D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
LicenseFile=LICENSE
OutputDir=Installers\Build
OutputBaseFilename=Pokemon-TCG-Live-Monitor-v{#MyAppVersion}-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\icon.ico
; Show a "What's New" page
InfoBeforeFile=RELEASE_NOTES_v2.3.md

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start automatically with Windows (Recommended)"; GroupDescription: "Auto-Start:"; Flags: checked

[Files]
; Core Python Files
Source: "TCGLiveMonitor.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "AIParseBattleLog.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "BattleDatabase.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "RankDetector.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "OverlayUI.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "StatsUI.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "app_settings.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "deck_analytics.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "startup_utils.py"; DestDir: "{app}"; Flags: ignoreversion

; Utilities
Source: "AutoRun_Add.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "AutoRun_Remove.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "Run_Headless.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "AutoClicker.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "SetupStartup.py"; DestDir: "{app}"; Flags: ignoreversion

; Batch Files
Source: "Run_Headless.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Run_TCGLiveMonitor_Command_Prompt.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Install_Dependencies.bat"; DestDir: "{app}"; Flags: ignoreversion

; Installers
Source: "Installers\INSTALL_COMPLETE_v2.3.bat"; DestDir: "{app}\Installers"; Flags: ignoreversion
Source: "Installers\Start_GUI_Mode_v2.3.bat"; DestDir: "{app}\Installers"; Flags: ignoreversion
Source: "Installers\Remove_AutoStart_v2.3.bat"; DestDir: "{app}\Installers"; Flags: ignoreversion
Source: "Installers\README.md"; DestDir: "{app}\Installers"; Flags: ignoreversion

; Configuration
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "ding.mp3"; DestDir: "{app}"; Flags: ignoreversion
Source: "screen_regions.json"; DestDir: "{app}"; Flags: ignoreversion

; Documentation
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "RELEASE_NOTES_v2.3.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "QUICK_START_v2.0.md"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\Logs"; Permissions: users-full

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\Run_Headless.bat"; IconFilename: "{app}\icon.ico"
Name: "{group}\Stats Dashboard"; Filename: "{sys}\cmd.exe"; Parameters: "/c """"{app}\.venv\Scripts\pythonw.exe"" ""{app}\StatsUI.py"""; IconFilename: "{app}\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Run_Headless.bat"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
; Run post-installation setup (installs Python deps, Tesseract, configures startup)
Filename: "{app}\Installers\INSTALL_COMPLETE_v2.3.bat"; Description: "Complete Installation (Install Python, Tesseract, Dependencies)"; Flags: postinstall shellexec skipifsilent
Filename: "{app}\README.md"; Description: "View Documentation"; Flags: postinstall shellexec skipifsilent unchecked

[Code]
var
  APIKeyPage: TInputQueryWizardPage;
  LocalOnlyPage: TInputOptionWizardPage;

procedure InitializeWizard;
begin
  // API Key page - optional, with clear guidance
  APIKeyPage := CreateInputQueryPage(wpSelectTasks,
    'OpenAI API Key (Optional)', 'Configure AI Battle Analysis',
    'Enter your OpenAI API key to enable AI-powered deck detection.' + #13#10 +
    'You can skip this and use Local-Only mode instead.' + #13#10 + #13#10 +
    'Get a free API key at: https://platform.openai.com/api-keys' + #13#10 +
    'Approximate cost: $0.01 per battle analyzed.');
  APIKeyPage.Add('OpenAI API Key:', False);

  // Local-only mode explanation page
  LocalOnlyPage := CreateInputOptionPage(APIKeyPage.ID,
    'Analysis Mode', 'Choose how battles are analyzed',
    'If you skipped the API key, the app will run in Local-Only mode.' + #13#10 +
    'This still tracks your battles, rank, and deck via OCR - it just asks you' + #13#10 +
    'to enter the opponent deck name manually instead of using AI.',
    True, False);
  LocalOnlyPage.Add('Use AI analysis (I entered an API key)');
  LocalOnlyPage.Add('Use Local-Only mode (no API key needed)');
  LocalOnlyPage.SelectedValueIndex := 0;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  APIKeyFile: String;
  SettingsFile: String;
  apiKey: String;
  localOnly: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Save API key if provided
    apiKey := APIKeyPage.Values[0];
    if apiKey <> '' then
    begin
      APIKeyFile := ExpandConstant('{app}\.openai_key');
      SaveStringToFile(APIKeyFile, apiKey, False);
    end;

    // If user chose local-only mode, write the setting
    if LocalOnlyPage.SelectedValueIndex = 1 then
    begin
      SettingsFile := ExpandConstant('{app}\.app_settings.json');
      localOnly := '{"local_only_mode": true}';
      SaveStringToFile(SettingsFile, localOnly, False);
    end;
  end;
end;

[UninstallRun]
Filename: "schtasks"; Parameters: "/delete /tn ""PokemonTCGLiveMonitor_v2.3"" /f"; Flags: runhidden
Filename: "{sys}\cmd.exe"; Parameters: "/c rmdir /s /q ""{app}\.venv"""; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\Logs"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\.openai_key"
Type: files; Name: "{app}\.user_config"
Type: files; Name: "{app}\.app_settings.json"
Type: files; Name: "{app}\.last_rank"
Type: files; Name: "{app}\.last_deck"
Type: files; Name: "{app}\.max_rank"
Type: files; Name: "{app}\.monitor_pid"
Type: files; Name: "{app}\.console_pref"
Type: files; Name: "{app}\tcg_battles.db"
Type: files; Name: "{app}\screen_regions.json"