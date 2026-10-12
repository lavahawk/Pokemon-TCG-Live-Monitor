; Pokemon TCG Live Monitor v2.4 - portable-style installer (no Start Menu group)
; Build: iscc installer_portable.iss

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
DefaultDirName={localappdata}\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
LicenseFile=LICENSE
OutputDir=Installers\Build
OutputBaseFilename=Pokemon-TCG-Live-Monitor-v{#MyAppVersion}-Portable
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\icon.ico
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

#include "installer_common.iss"
