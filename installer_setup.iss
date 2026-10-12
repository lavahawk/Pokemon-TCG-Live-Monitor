; Pokemon TCG Live Monitor v2.4 - Inno Setup installer (per-user, no admin)
; Build: iscc installer_setup.iss   (or Build_Inno_Installer.bat)

#define MyAppName "Pokemon TCG Live Monitor"
#define MyAppVersion "2.4.0"
#define MyAppPublisher "lavahawk"
#define MyAppURL "https://github.com/lavahawk/Pokemon-TCG-Live-Monitor"

[Setup]
AppId={{D8F9A4C3-7B2E-4F1A-9D3C-5E8F1A2B4C6D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
; Per-user, writable location (the app stores its DB/logs next to the code).
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
AllowNoIcons=yes
LicenseFile=LICENSE
InfoBeforeFile=RELEASE_NOTES_v2.4.md
OutputDir=Installers\Build
OutputBaseFilename=Pokemon-TCG-Live-Monitor-v{#MyAppVersion}-Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\icon.ico
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

#include "installer_common.iss"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\Run_Headless.bat"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{group}\{#MyAppName} (debug console)"; Filename: "{app}\Run_TCGLiveMonitor_Command_Prompt.bat"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Stats Dashboard"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\StatsUI.py"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\Run_Headless.bat"; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
