; ============================================================
;  PDF 工具 安装程序脚本（中文向导版，用 Inno Setup 编译）
;  用法：把本文件和 ChineseSimplified.isl 一起放到
;        PDF2Word_卡密版 文件夹里（和 dist 文件夹同级），
;        右键 setup.iss → Compile（或双击打开点 ▶）。
;        生成的中文安装包在同目录 Output\ 里。
;  前提：dist\PDF2Word.exe 已存在（先双击 build.bat 打包好）。
; ============================================================

#define MyAppName "PDF工具"
#define MyAppVersion "1.0"
#define MyAppPublisher "婷肥出品"
#define MyAppExeName "PDF2Word.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\PDF2Word
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=PDF工具_安装程序
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 安装程序自身的图标（本文件夹里放 icon_64.ico）
SetupIconFile=icon_64.ico
; 免管理员、按当前用户安装：这样就【不会】再弹那个英文“选择安装方式”的框
PrivilegesRequired=lowest

[Languages]
; 只用简体中文，向导全程中文，也不会再问选哪种语言
Name: "chs"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Files]
; 文件夹版(onedir)打包：把整个 dist\PDF2Word 文件夹装进去
Source: "dist\PDF2Word\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 把图标文件也装进去，供快捷方式使用
Source: "icon_64.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon_64.ico"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon_64.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent
