; Inno Setup 스크립트: 포터블 앱 폴더(dist\MangaTranslator\, build\make_portable.py 가 만듦)를 설치 파일 하나로 만든다
;   1) python build\make_portable.py
;   2) "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" build\installer.iss
; 바로 가기는 python\pythonw.exe launch.py 를 실행한다 (첫 실행 때 torch 등을 사용자 PC 에 설치)
; 결과: build\out\MangaTranslator-Setup-<버전>.exe
; 설치 위치는 사용자 폴더(%LOCALAPPDATA%\MangaTranslator) 라 관리자 권한이 필요 없다. 프로젝트 데이터는 %LOCALAPPDATA%\MangaTranslator\projects

#define AppName "Manga Translator"
#define AppVersion "0.1.1"
#define AppExe "python\pythonw.exe"
#define AppArgs """{app}\launch.py"""

[Setup]
AppId={{7E3C1E2A-6B7F-4C3D-9F2A-5A1C0F9D3B11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Manga Translator
DefaultDirName={localappdata}\MangaTranslator\app
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=out
OutputBaseFilename=MangaTranslator-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\icon.ico
SetupIconFile=icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\MangaTranslator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: {#AppArgs}; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Parameters: {#AppArgs}; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Parameters: {#AppArgs}; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 앱 폴더만 지운다. 프로젝트·설치된 패키지·모델(%LOCALAPPDATA%\MangaTranslator\{projects,pylib,hf})은 남긴다
Type: filesandordirs; Name: "{app}"
