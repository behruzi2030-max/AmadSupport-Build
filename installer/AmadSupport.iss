#define MyAppName "سامانه آماد و پشتیبانی پایگاه شهید صیاد شیرازی"
#define MyAppVersion "5.0.1"
#define MyAppExeName "AmadSupport.exe"

[Setup]
AppId={{B4E4B57A-9F32-48CF-9D38-5C2D5DCE7A10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=پایگاه شهید صیاد شیرازی
DefaultDirName={autopf}\AmadSupport
DefaultGroupName={#MyAppName}
OutputDir=..\dist-installer
OutputBaseFilename=AmadSupport-Setup-x64
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "persian"; MessagesFile: "compiler:Languages\Persian.isl"

[Tasks]
Name: "desktopicon"; Description: "ایجاد میانبر روی دسکتاپ"; GroupDescription: "میانبرها:"; Flags: unchecked

[Files]
Source: "..\dist\AmadSupport\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "اجرای سامانه"; Flags: postinstall nowait skipifsilent
