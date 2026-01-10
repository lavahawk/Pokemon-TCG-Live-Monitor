; Pokemon TCG Live Monitor v2.1.0 - Inno Setup Installer Script
; Creates a professional Windows installer (.exe)

#define MyAppName "Pokemon TCG Live Monitor"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "lavahawk"
#define MyAppURL "https://github.com/lavahawk/Pokemon-TCG-Live-Monitor"
#define MyAppExeName "TCGLiveMonitor.exe"

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
OutputBaseFilename=Pokemon-TCG-Live-Monitor-v2.1.0-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode
Name: "autostart"; Description: "Start automatically with Windows (Recommended)"; GroupDescription: "Auto-Start:"; Flags: checked

[Files]
; Core Python Files
Source: "TCGLiveMonitor.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "AIParseBattleLog.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "BattleDatabase.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "RankDetector.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "OverlayUI.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "StatsUI.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "SetupRegions.py"; DestDir: "{app}"; Flags: ignoreversion

; Utilities
Source: "AutoRun_Add.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "AutoRun_Remove.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "Run_Headless.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "AutoClicker.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "SetupAutoClicker.py"; DestDir: "{app}"; Flags: ignoreversion

; Batch Files
Source: "Run_Headless.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Run_TCGLiveMonitor_Command_Prompt.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Run_SetupRegions.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "Install_Dependencies.bat"; DestDir: "{app}"; Flags: ignoreversion

; Installers
Source: "Installers\*.bat"; DestDir: "{app}\Installers"; Flags: ignoreversion
Source: "Installers\README.md"; DestDir: "{app}\Installers"; Flags: ignoreversion

; Configuration
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "ding.mp3"; DestDir: "{app}"; Flags: ignoreversion

; Documentation
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "RELEASE_NOTES_v2.1.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "QUICK_START_v2.0.md"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
Name: "{app}\Logs"; Permissions: users-full

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\Run_Headless.bat"; IconFilename: "{app}\icon.ico"
Name: "{group}\Stats Dashboard"; Filename: "{sys}\cmd.exe"; Parameters: "/c """"{app}\.venv\Scripts\pythonw.exe"" ""{app}\StatsUI.py"""; IconFilename: "{app}\icon.ico"
Name: "{group}\Setup Screen Regions"; Filename: "{app}\Run_SetupRegions.bat"; IconFilename: "{app}\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Run_Headless.bat"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
; Run post-installation setup
Filename: "{app}\Installers\INSTALL_COMPLETE_v2.1.bat"; Description: "Complete Installation (Install Python, Tesseract, Dependencies)"; Flags: postinstall shellexec skipifsilent
Filename: "{app}\Run_SetupRegions.bat"; Description: "Configure Screen Regions"; Flags: postinstall nowait skipifsilent unchecked
Filename: "{app}\README.md"; Description: "View Documentation"; Flags: postinstall shellexec skipifsilent unchecked

[Code]
var
  PythonPage: TInputOptionWizardPage;
  TesseractPage: TInputOptionWizardPage;
  APIKeyPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  // Python check page
  PythonPage := CreateInputOptionPage(wpWelcome,
    'Python Installation', 'Python 3.10+ is required',
    'The installer will check for Python and guide you through installation if needed.',
    True, False);
  PythonPage.Add('I have Python 3.10 or later installed');
  PythonPage.Add('I need to install Python (installer will guide me)');
  PythonPage.SelectedValueIndex := 0;

  // Tesseract check page
  TesseractPage := CreateInputOptionPage(PythonPage.ID,
    'Tesseract OCR', 'Tesseract OCR is required for rank detection',
    'The installer will check for Tesseract and guide you through installation if needed.',
    True, False);
  TesseractPage.Add('I have Tesseract OCR installed');
  TesseractPage.Add('I need to install Tesseract (installer will guide me)');
  TesseractPage.SelectedValueIndex := 0;

  // API Key page
  APIKeyPage := CreateInputQueryPage(TesseractPage.ID,
    'OpenAI API Key (Optional)', 'Configure AI Battle Analysis',
    'Enter your OpenAI API key to enable AI-powered deck detection. You can skip this and add it later.');
  APIKeyPage.Add('OpenAI API Key:', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  APIKeyFile: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Save API key if provided
    if APIKeyPage.Values[0] <> '' then
    begin
      APIKeyFile := ExpandConstant('{app}\.openai_key');
      SaveStringToFile(APIKeyFile, APIKeyPage.Values[0], False);
    end;
    
    // Create auto-start task if selected
    if WizardIsTaskSelected('autostart') then
    begin
      // Task will be created by INSTALL_COMPLETE_v2.1.bat
    end;
  end;
end;

[UninstallRun]
Filename: "schtasks"; Parameters: "/delete /tn ""PokemonTCGLiveMonitor_v2.1"" /f"; Flags: runhidden
Filename: "{sys}\cmd.exe"; Parameters: "/c rmdir /s /q ""{app}\.venv"""; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\Logs"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\.openai_key"
Type: files; Name: "{app}\.user_config"
Type: files; Name: "{app}\.last_rank"
Type: files; Name: "{app}\.last_deck"
Type: files; Name: "{app}\.max_rank"
Type: files; Name: "{app}\.monitor_pid"
Type: files; Name: "{app}\.console_pref"
Type: files; Name: "{app}\tcg_battles.db"
Type: files; Name: "{app}\screen_regions.json"
