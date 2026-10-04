# AGENTS.md

本文件是给 AI 编码助手看的项目指南，每次会话都应先读它。

## 项目概述

**LumistDo（览明贴）**——一个**桌面任务便签软件**（本地运行，Windows 自用，MIT）。

- 半透明、无边框、默认普通窗口层级（非置顶），能看到壁纸
- 点加号创建任务，双击任务文字就地编辑
- 点任务左侧小圆点 → 任务从桌面消失并标记完成 → 进入底部「已完成」栏
- 已完成栏可展开，点圆点把任务恢复回主列表
- 删除任务进入历史任务，可批量恢复或永久删除
- 外观可自定义（6 套预设 + 真·毛玻璃 + 独立的「自定义配色」窗口：单独调背景色/字体颜色）
- 顶部栏三按钮：图钉（层级三态）→ 固定窗口位置 → 缩略模式
- 快捷键可改键（`Ctrl+N` 新建固定不可改，其余三项在快捷键窗口里改）
- 可选：不在任务栏显示图标（用托盘图标找回窗口）、开机自启动
- 中英文双语，改语言后重启生效
- 数据持久化到 `%APPDATA%\LumistDo` 下的 JSON，关掉重开任务还在（不过夜刷新）
- 不需要用户管理、不需要每日重置、不联网

- **状态**：可用（v1.3.1）
- **维护**：一人项目

## 技术栈

- 语言：Python 3.13
- GUI 框架：PySide6（Qt for Python）6.11
- 数据持久化：JSON（`%APPDATA%\LumistDo\tasks.json` / `settings.json`，原子写入）
- 版本与名称：`lumistdo/__init__.py` 的 `APP_NAME` / `APP_NAME_ZH` / `APP_VERSION`（发 Release 时 tag 用 `v{版本号}`，四处版本号要一起改：该文件、`version_info.txt`、`lumistdo.iss` 的 `MyAppVersion`）
- 打包：PyInstaller（onedir，`lumistdo.spec`）+ Inno Setup 6（`lumistdo.iss`）
- 测试：pytest
- 包管理：pip + requirements.txt

## 目录结构

```
LumistDo-src/
├── AGENTS.md            # 本文件
├── README.md            # 功能与使用说明（用户视角）
├── LICENSE              # MIT
├── requirements.txt
├── main.py              # 入口：QApplication + MainWindow（含崩溃日志钩子）
├── lumistdo.spec        # PyInstaller 配置
├── lumistdo.iss         # Inno Setup 安装脚本
├── version_info.txt     # exe 版本资源
├── assets/icon.ico
├── docs/                # README 用的截图 + 介绍页
├── installer/           # Inno Setup 简体中文语言文件
├── lumistdo/        # 应用包（import 名 lumistdo，与产品名一致）
│   ├── __init__.py          # APP_NAME / APP_NAME_ZH / APP_VERSION
│   ├── app_paths.py         # 数据/日志路径解析 + 旧数据迁移
│   ├── app_settings.py      # 设置模型、预设、快捷键解析
│   ├── blur_behind.py       # 真·毛玻璃（DWM blur-behind，未公开 API，失败静默）
│   ├── json_io.py           # 原子写入
│   ├── task_store.py        # 数据层：Task / TaskStore
│   ├── task_item.py         # UI：单条任务（圆点 + 编辑框，高度自适应）
│   ├── completed_panel.py   # UI：已完成面板
│   ├── history_window.py    # UI：历史任务窗口
│   ├── settings_dialog.py   # UI：设置窗口 + 自定义配色窗口
│   ├── keybind_window.py    # UI：编辑快捷键窗口
│   ├── floating_window.py   # 浮动窗口共享件（羽化边缘/关闭按钮/色块/容器背景）
│   ├── tray_icon.py         # 托盘图标
│   ├── autostart.py         # 开机自启动（注册表 Run 项）
│   ├── single_instance.py   # 单实例锁（QLockFile）
│   ├── dialogs.py           # 消息框（切断父窗口深色样式继承）
│   ├── i18n.py              # 中英文文案表 + product_name()
│   └── main_window.py       # UI：主窗口（拖动/缩放/渐隐/快捷键/落盘）
└── tests/
    ├── test_app_paths.py    # 路径解析与旧数据迁移
    ├── test_app_settings.py # 设置模型
    ├── test_task_store.py   # 数据层
    └── test_gui_smoke.py    # GUI 冒烟测试（offscreen 平台）
```

## 常用命令

```powershell
# 安装依赖
python -m pip install -r requirements.txt

# 运行（开发模式）
python main.py

# 跑测试（GUI 用 offscreen，不弹真窗口）
$env:QT_QPA_PLATFORM="offscreen"; python -m pytest tests/ -q

# 打包 exe 目录 → dist\LumistDo\LumistDo.exe
python -m PyInstaller lumistdo.spec --noconfirm

# 打安装包 → release\LumistDo-Setup-v{版本号}.exe
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" lumistdo.iss
```

## 架构要点

- **数据与 UI 分离**：`TaskStore` 只管数据和持久化，不依赖 Qt UI；`MainWindow` 持有 store 并在 UI 交互时调用它。这使数据层可单独单测。
- **任务对象同一引用**：`TaskItem.task` 与 `store.tasks` 中的对象是同一个，UI 改文本时本地与 store 同步。
- **完成动作的边界**：空任务被点完成时直接删除，不进已完成栏（避免空任务堆积）。
- **圆点不抢焦点**：`TaskItem.dot` 设 `Qt.NoFocus`，点完成时不会触发文本框的 `editingFinished`，避免完成与保存逻辑冲突。
- **半透明 + 圆角**：窗口 `WA_TranslucentBackground` + 容器 `rgba` 背景，文字保持不透明清晰；圆角外区域透明。
- **毛玻璃只有一种做法真的有效**：要"糊掉背后"必须调未公开的 `SetWindowCompositionAttribute` + `ACCENT_ENABLE_BLURBEHIND`(3)（`blur_behind.py`）。实测这台 Win11 上 `ACCENT_ENABLE_ACRYLICBLURBEHIND`(4) 与 `ACCENT_ENABLE_HOSTBACKDROP`(5) 都**返回成功但毫无效果**，已废弃的 `DwmEnableBlurBehindWindow` 同样不生效——判断有没有效只能看画面，不能看返回值。`GradientColor` 是 ABGR（低字节 alpha），不是 ARGB。窗口标志重建（最小化还原、改任务栏样式）会丢掉效果，所以 `showEvent` / `changeEvent` 里都要补一次 `_apply_blur_behind()`。模糊是 DWM 合成的，`PrintWindow` / `grab()` 都抓不到，验收必须整屏抓图。
- **快捷键默认走系统级热键,不是 QShortcut**：`QShortcut` 是窗口级绑定,主窗口没被选中就完全不响应,而「层级/固定/缩略」这三个动作天生是"在别的窗口里顺手拨一下"的操作,所以走 `RegisterHotKey`(`lumistdo/global_hotkeys.py`)。五条必须记住的：
  1. **`UnregisterHotKey` 必须传注册时那个 hwnd**。它是按"(窗口, id)"登记的,传 `None` 只对"注册时也没传窗口"的热键有效;传错会**静默失败并留下孤儿热键**——系统照样投 `WM_HOTKEY`(id 是我们发的),但 `_ids` 已清空,于是"按键有反应"变成"什么都没发生"。真踩过:窗口被 Qt 重建后重新 `apply()`,先注销失败、再注册失败(1409),最后只剩一个没人认领的热键。
  2. **一次按键系统会投两条 `WM_HOTKEY`**,所以 `handle_hotkey` 里有一层 `_REPEAT_GUARD_SECONDS = 0.3` 去抖。不去抖的话层级这种循环动作连切两下正好回到原位,用户看到的就是"按了没反应"。（实测脚本:`lumistdo-dev/probe_hotkey_downup.py`,只注入"按下"就收到 2 条、"抬起"0 条。）
  3. **`QAbstractNativeEventFilter` 必须自己强引用**(`app.installNativeEventFilter()` 不保活),所以挂在 `MainWindow._hotkeys` 上。
  4. **注册用具体 hwnd,窗口标志重建后要重挂**:`showEvent` 里 `QTimer.singleShot(0, self._ensure_hotkeys)`,hwnd 变了才 `apply()`。
  5. **热键是独占的,出厂值要挑没人占的组合**:实测本机 `Ctrl+Alt+O/L/C/S/T`、`Ctrl+Win+O` 都被别的软件占着,所以默认值是 `Ctrl+Alt+1/2/3`(`DEFAULT_SHORTCUTS`),并保留 `LEGACY_DEFAULT_SHORTCUTS` 做**只升级出厂值**的迁移。注册失败的动作**只退回该动作的 QShortcut**,不影响其他两个。
- **验收"全局热键真生效"只能看落盘设置**,别依赖 UIA:顶部栏按钮是自绘 `QWidget`,UIA 里只有 AutomationId(`...HeaderBar.PinButton`),**Qt 也不把 tooltip 暴露成 HelpText**,而且缩略模式**故意不改窗口尺寸**。`lumistdo-dev/probe_global_hotkeys.py` 用的是"读程序自己写的 `settings.json` 里的 `always_on_top/always_on_bottom/compact_mode/position_fixed`",它既能证明动作跑了,又能区分"触发一次"和"触发两次"。另外注入按键要用 **`keybd_event`**——这台机器上 `SendInput` 稳定返回 0 / `err=87`。
- **窗口层级回传的是层级名，不是"要不要置底"的布尔值**：`SettingsWindow.z_order_changed` 发 `"top"/"bottom"/"normal"`，主窗口 `set_layer(name)` 接。早先发的是 `name == "bottom"` 的布尔值，选「置于最上层」时回传 `False` 被主窗口当成"回到普通层级"，`set_always_on_bottom(False)` 随即将单选弹回「普通层级」——用户看到的就是"置顶点了没反应"（设置其实已经写进去了，只有界面被弹回）。同步单选项一律走 `MainWindow._sync_layer_checks()`（按当前 `_always_on_top/_always_on_bottom` 算模式），不要在置顶/置底分支里各写死一个模式。
- **单选圆点要用 `qradialgradient` 画，别用 border**：`QRadioButton::indicator` 给 15px 方块配 `border-radius:8px`，四角各差半像素，量化出来是个圆角方框；靠加粗 border 做"环"会让底色从环里透出来，像方块套方块。现由 `app_settings.radio_qss(theme)` 按明暗主题生成（浅色背景下白环等于看不见），在 `SettingsWindow.apply_theme()` 里拼到 `WINDOW_QSS` 后面。
- **拖动/缩放**：无边框窗口重写鼠标事件，顶栏空白处拖动、边缘缩放；`position_fixed` 打开后 `_edge()` 返回 None 且不再拖动。
- **渐隐**：只有缩略模式会让顶栏渐隐。`_chrome_wanted()` 是唯一判定入口；`_reveal_until` 让"点窗口临时唤回 3 秒"在没有鼠标贴边时也能点到图标。
- **清单区绝不能用 `setVisible(False)` 隐藏**：`QScrollArea` 不可见后不再重算几何，内部 widget 会卡在 `sizeHint` 宽度（638）把任务行撑出窗口；要折叠就走 `setMaximumHeight`（`_set_widget_shown`）。
- **透明度特效必须丢引用**：Qt 的 `widget.setGraphicsEffect(None)` 会**直接 delete** 那个 `QGraphicsOpacityEffect`，缓存的引用立刻变成野指针（`Internal C++ object already deleted`）。每次摘掉特效后都要 `_forget_effect(name)` 清缓存，下次重建。
- **任务栏图标重登记要推迟**：`_apply_taskbar_style()` 里的 `hide()`+`show()` 若同步执行，会被 `showEvent` 排的同一个回调再触发，把 Qt 的可见性状态搞乱（表现为"窗口再也显示不出来"）。所以走 `QTimer.singleShot(0, self._reregister_for_taskbar)`。
- **自绘图标按钮要设 `accessibleName`**：否则 UI 自动化/无障碍工具读到空名字，按名字点不到（`_reset_btn` 就踩过）。
- **数据目录可迁移**：`app_paths.data_dir()` 每次取用都跑一次迁移——先搬早期版本用过的 `%APPDATA%\LumistDo`（新目录已有同名文件则不覆盖，搬完删旧文件），再搬便携版的程序目录内 `.lumistdo`（只复制不删）。迁移失败静默，绝不能挡住启动。
- **背景用三档垂直渐变**：容器背景由 `app_settings.container_qss()` 统一生成（三个窗口共用）。两档渐变要把色差摊满整个窗口高度，8bit 量化下会出现一条条水平色带，所以用上/中/下三档停靠点把色差压小。
- **预设是"名字"不是颜色值**：`settings_dialog.PRESETS` 的 `name`（中文原名）同时是持久化标识，界面显示走 `i18n.preset_name()`；`AppSettings.appearance_preset` 只用于设置窗口高亮，不影响渲染。
- **固定灰也要跟着明暗走**：`Theme.fixed_title_color` / `fixed_footer_color` 以前是硬编码常量，浅色主题下等于看不见；现在由 `Theme._derive()` 按 `is_dark` 给出（深色 `#9a9aa5`/`#8a8a94`，浅色 `#5c5c66`/`#63636d`），所以不要再往 `PRESETS` 字典里塞这两个键。
- **界面产品名走 `i18n.product_name()`**：中文显示"览明贴"，英文显示"LumistDo"；需要显示软件名的地方（窗口标题、消息框标题、托盘 tooltip）都用它，不要硬编码。

## 开发约定

- **语言**：与用户交流用中文，代码、命令、标识符用英文。
- **代码风格**：匹配现有文件风格（4 空格缩进、双引号字符串、模块级 docstring）。
- **改动前先看**：修改既有代码前先读取相关文件，匹配周围风格。
- **不过度工程**：优先简单可读的实现；这是自用小工具，不引入非必要依赖。
- **验证再报告**：说"完成"前实际运行过测试；失败就如实说明，不粉饰。

## 环境备注

- 操作系统：Windows 11。命令在 PowerShell（`pwsh`）里跑：路径带空格要引号，环境变量用 `$env:VAR`。
- GUI 测试在无头环境用 `$env:QT_QPA_PLATFORM="offscreen"`，不弹真实窗口；中文输出建议同时设 `$env:PYTHONIOENCODING="utf-8"` 与 `$env:PYTHONUTF8="1"`。
- 测试必须给 `MainWindow` 传 `settings_path`（临时目录），否则会去读开发机真实的 `%APPDATA%\LumistDo\settings.json`，结果随本机状态漂移。
- **不要为了"试探"而运行 Inno Setup 卸载器**：它不弹确认就直接卸载并删除用户数据（本项目历史上真的丢过一次用户任务）。
- 需要渲染界面截图时可用工作区里的 `lumistdo-dev/preview_ui.py`（不在本仓库内）：`python preview_ui.py zh normal|compact|keys|custom|frost`。

## AI 工作约定

- 优先使用专用工具（Read/Edit/Glob/Grep）而非等价的 shell 命令。
- 路径引用用 `file_path:line_number` 格式，便于点击跳转。
- 涉及不可逆或对外的操作前先确认，除非已获明确授权。
- 不确定时先给建议再行动，不要罗列不会采用的方案。
