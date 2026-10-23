; Kridwinn Orbit Pro installer script for Inno Setup
[Setup]
AppId={{b5e77c56-7e9a-4a67-b9c5-de3caa5aab24}}
AppName=Kridwinn Orbit Pro
AppVersion=25.11.001Beta
AppVerName=Kridwinn Orbit Pro 25.11.001Beta
AppPublisher=Kridwinn Innovations Private Limited
AppPublisherURL=https://www.kridwinn.com
AppSupportURL=https://www.kridwinn.com/support
AppUpdatesURL=https://www.kridwinn.com/downloads
DefaultDirName={localappdata}\Kridwinn Orbit Pro
DefaultGroupName=Kridwinn Orbit Pro
AllowNoIcons=yes
; LicenseFile=LICENSE.txt
OutputDir=dist\installer
OutputBaseFilename=KridwinnOrbitPro-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Kridwinn Orbit Pro.exe
UninstallDisplayName=Kridwinn Orbit Pro
VersionInfoProductName=Kridwinn Orbit Pro
VersionInfoProductVersion=25.11.001.0
VersionInfoVersion=25.11.001.0
VersionInfoCompany=Kridwinn Innovations Private Limited
VersionInfoDescription=Kridwinn Orbit Pro Installation
VersionInfoCopyright=Copyright (C) 2025 Kridwinn Innovations Private Limited

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; Standalone build - copy entire app.dist folder
Source: "dist\app.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Kridwinn Orbit Pro"; Filename: "{app}\Kridwinn Orbit Pro.exe"; WorkingDir: "{app}"
Name: "{group}\Uninstall Kridwinn Orbit Pro"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Kridwinn Orbit Pro"; Filename: "{app}\Kridwinn Orbit Pro.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Registry]
; Store installation path in registry so the app can find it
Root: HKCU; Subkey: "Software\Kridwinn Orbit Pro"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\Kridwinn Orbit Pro.exe"; Description: "Launch Kridwinn Orbit Pro"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
; Also clean up user data if desired (optional - comment out to preserve user data)
; Type: filesandordirs; Name: "{localappdata}\Kridwinn Orbit Pro"