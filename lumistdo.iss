; LumistDo(览明贴)安装脚本(Inno Setup 6)
;
; 编译: "<Inno Setup 6>\ISCC.exe" lumistdo.iss
; 产物: release\LumistDo-Setup-v{版本号}.exe
;
; 安装位置由用户在向导的「选择安装位置」页自己定:
;   默认「仅为我安装」→ %LOCALAPPDATA%\Programs\LumistDo,全程不弹 UAC;
;   想装到 C:\Program Files 之类需要管理员权限的地方,就在向导第一页选
;   「为所有用户安装」,Setup 会提权,默认目录随之变成 Program Files。
; 用户数据始终在 %APPDATA%\LumistDo,安装/更新/卸载均不触碰。
; 发新版时只改 MyAppVersion;AppId 是升级/卸载的注册表标识,改了会被当成另一个软件。
;
; AppId 是本软件独有的:GUID 与其他软件都不同,
; 所以本安装包不会覆盖别的软件,也有自己的卸载项。

#define MyAppName "LumistDo"
#define MyAppNameZh "览明贴"
#define MyAppVersion "1.3.2"
#define MyAppPublisher "1TRhez"
#define MyAppURL "https://github.com/1TRhez/LumistDo"

[Setup]
AppId={{A5588A1E-0E39-46FA-B7A7-E64F4D82E8CC}
AppName={#MyAppName}
AppVersion=v{#MyAppVersion}
AppVerName={#MyAppName} {#MyAppNameZh} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
; {autopf} 会跟着安装模式走:仅当前用户 → %LOCALAPPDATA%\Programs,所有用户 → Program Files
DefaultDirName={autopf}\{#MyAppName}
PrivilegesRequired=lowest
; 允许在向导里选「为所有用户安装」提权,否则用户改到 Program Files 会因权限不足失败
PrivilegesRequiredOverridesAllowed=dialog
; 连更新时也保留「选择安装位置」页,想换目录随时换
DisableDirPage=no
DisableProgramGroupPage=yes
OutputDir=release
OutputBaseFilename=LumistDo-Setup-v{#MyAppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\LumistDo.exe
UninstallDisplayName={#MyAppName} {#MyAppNameZh}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
; 简体中文放第一位,安装向导默认选中
Name: "chinesesimplified"; MessagesFile: "installer\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller onedir 产物整目录安装
Source: "dist\LumistDo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\LumistDo.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\LumistDo.exe"; Tasks: desktopicon

[Run]
; runasoriginaluser:「为所有用户安装」时也用当前用户身份启动,别把程序拉起来当管理员跑
Filename: "{app}\LumistDo.exe"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[CustomMessages]
DeleteUserDataPrompt=是否同时删除用户数据（任务与设置）？数据位于 %APPDATA%\LumistDo。
english.DeleteUserDataPrompt=Also delete user data (tasks and settings)? Data is stored in %APPDATA%\LumistDo.

[Code]
// 卸载完成后询问是否一并删除用户数据(静默卸载不打扰)
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
  begin
    DataDir := ExpandConstant('{userappdata}\LumistDo');
    if DirExists(DataDir) then
    begin
      if MsgBox(CustomMessage('DeleteUserDataPrompt'), mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
