; ISWM Plant installer (Inno Setup 6). Built by .github/workflows/build-exe.yml:
;   iscc /DMyAppVersion=1.1.0 installer\ISWM.iss
; Expects the PyInstaller output in dist\ISWM and the WebView2 bootstrapper
; in installer\MicrosoftEdgeWebview2Setup.exe.

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
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\ISWM.exe"
Name: "{group}\ISWM data folder"; Filename: "{commonappdata}\ISWM"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\ISWM.exe"; Tasks: desktopicon
Name: "{commonstartup}\{#MyAppName}"; Filename: "{app}\ISWM.exe"; Tasks: startup

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2 (needed to show the screens)..."; Check: NeedsWebView2; Flags: waituntilterminated
; Live view (off until the admin turns it on) needs incoming connections on private networks only.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""ISWM live view"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""ISWM live view"" dir=in action=allow program=""{app}\ISWM.exe"" enable=yes profile=private"; Flags: runhidden
Filename: "{app}\ISWM.exe"; Description: "Open ISWM now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""ISWM live view"""; Flags: runhidden; RunOnceId: "DelFwRule"

[Code]
const
  WV2 = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';

function HasWV2(Root: Integer; Key: String): Boolean;
var
  V: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', V) and (V <> '') and (V <> '0.0.0.0');
end;

function NeedsWebView2: Boolean;
begin
  Result := not (HasWV2(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\' + WV2) or
                 HasWV2(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\' + WV2) or
                 HasWV2(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\' + WV2));
end;
