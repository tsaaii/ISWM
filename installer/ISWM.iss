; ISWM Plant installer (Inno Setup 6). Built by .github/workflows/build-exe.yml:
;   iscc /DMyAppVersion=1.1.0 installer\ISWM.iss
; Expects the PyInstaller output in dist\ISWM. The window uses Microsoft Edge,
; which is part of Windows 10/11, so nothing else is installed.

#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif
#define MyAppName "ISWM Plant"

[Setup]
AppId={{7C1B3F0E-5E52-4C4B-9C0B-1D2A6E9F4B21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=ISWM
DefaultDirName={autopf}\ISWM
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=ISWM-Setup
SetupIconFile=..\assets\iswm.ico
UninstallDisplayIcon={app}\ISWM.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Put an ISWM icon on the desktop"; Flags: checkedonce
Name: "startup"; Description: "Start ISWM when Windows starts"; Flags: unchecked

[Dirs]
; Data (database, photos, settings) lives here and is kept on uninstall.
Name: "{commonappdata}\ISWM"; Permissions: users-modify; Flags: uninsneveruninstall

[Files]
Source: "..\dist\ISWM\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "installed.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\ISWM.exe"
Name: "{group}\ISWM data folder"; Filename: "{commonappdata}\ISWM"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\ISWM.exe"; Tasks: desktopicon
Name: "{commonstartup}\{#MyAppName}"; Filename: "{app}\ISWM.exe"; Tasks: startup

[Run]
; Live view (off until the admin turns it on) needs incoming connections on private networks only.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""ISWM live view"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""ISWM live view"" dir=in action=allow program=""{app}\ISWM.exe"" enable=yes profile=private"; Flags: runhidden
Filename: "{app}\ISWM.exe"; Description: "Open ISWM now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""ISWM live view"""; Flags: runhidden; RunOnceId: "DelFwRule"
