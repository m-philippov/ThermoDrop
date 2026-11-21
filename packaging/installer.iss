; Установщик ThermoDrop (Inno Setup 6.2+). Сборка: ISCC /DArch=x64 packaging\installer.iss
; Windows 7 SP1 / 10 / 11. Права администратора не нужны: установка в профиль пользователя,
; ярлык на рабочем столе создаётся по умолчанию.

#define AppName "ThermoDrop"
#define AppVersion "1.0.0"
#ifndef Arch
  #define Arch "x64"
#endif

[Setup]
AppId={{8C1B6E2A-4F3D-4C1E-9B7A-2D5E7F1A3C90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=ThermoDrop
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=ThermoDrop-{#AppVersion}-{#Arch}-setup
SetupIconFile=thermodrop.ico
UninstallDisplayIcon={app}\ThermoDrop.exe
Compression=lzma2/max
SolidCompression=yes
MinVersion=6.1sp1
WizardStyle=modern
#if Arch == "x64"
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
#endif

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#Arch}\ThermoDrop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\ThermoDrop.exe"
Name: "{autoprograms}\Руководство {#AppName}"; Filename: "{app}\doc\Руководство ThermoDrop.pdf"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ThermoDrop.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ThermoDrop.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
