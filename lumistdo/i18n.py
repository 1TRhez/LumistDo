"""多语言支持:中文 / English。

极简方案:查表翻译,不走 Qt Linguist。界面文案在启动时按
当前语言构建,改语言后提示重启生效。
"""

from . import APP_NAME, APP_NAME_ZH

LANG_ZH = "zh"
LANG_EN = "en"
SUPPORTED = (LANG_ZH, LANG_EN)

_current = LANG_ZH


def set_language(lang: str):
    """设置当前语言;不支持的值回退到中文。"""
    global _current
    _current = lang if lang in SUPPORTED else LANG_ZH


def get_language() -> str:
    return _current


def product_name() -> str:
    """界面/对话框标题里显示的软件名:跟随语言(中文显示"览明贴")。"""
    return APP_NAME_ZH if _current == LANG_ZH else APP_NAME


def t(key: str, **fmt) -> str:
    """按 key 取当前语言文案,可用关键字参数填充占位符。

    缺 key 时直接返回 key 本身,保证永不崩。
    """
    table = _TRANSLATIONS.get(_current) or _TRANSLATIONS[LANG_ZH]
    text = table.get(key)
    if text is None:
        text = (_TRANSLATIONS[LANG_ZH].get(key) or key)
    if fmt:
        try:
            text = text.format(**fmt)
        except (KeyError, IndexError):
            pass
    return text


# 注:"已完成  {n}" 的双空格是排版设计,两种语言均保留。
_TRANSLATIONS = {
    LANG_ZH: {
        # ---- 通用 ----
        "common.confirm": "确认",
        "common.cancel": "取消",
        "common.restart_now": "立即重启",
        "common.later": "稍后",
        # ---- 主窗口 ----
        "app.running": "{name} 已在运行,请勿重复打开。",
        "app.crash": "程序遇到了意外错误。\n错误详情已记录到 .lumistdo/crash.log，反馈问题时请附带该文件。",
        "app.data_warning": "本地数据提示",
        "main.new_tooltip": "新建任务 (Ctrl+N)",
        "main.empty_hint": "暂无任务 —— 点击上方 + 或按 Ctrl+N 新建",
        "main.completed_count": "已完成  {n}",
        "main.settings_tooltip": "设置",
        "main.lock_tooltip": "快捷键",
        "main.menu_quit": "退出",
        "main.menu_minimize": "最小化",
        "main.pin_tooltip_on": "置于最上层 -> 最底层{sc}",
        "main.pin_tooltip_off": "置于最底层 -> 普通层级{sc}",
        "main.pin_tooltip_mid": "普通层级 -> 置于最上层{sc}",
        "main.fixed_tooltip_on": "解除固定{sc}",
        "main.fixed_tooltip_off": "固定窗口位置,禁止拖动与缩放{sc}",
        "main.compact_action_on": "退出缩略模式",
        "main.compact_action_off": "缩略模式（只留任务列表）",
        # ---- 任务项 ----
        "task.mark_done": "标记为完成",
        "task.edit": "编辑",
        "task.delete": "删除",
        "task.edit_placeholder": "输入任务…",
        # ---- 设置窗口 ----
        "settings.title": "设置",
        "settings.presets": "预设",
        "settings.bg_color": "背景颜色",
        "settings.text_color": "字体颜色",
        "settings.font": "字体",
        "settings.font_search": "搜索字体",
        "settings.font_size": "字号",
        "settings.bg_opacity": "背景透明度",
        "settings.language": "界面语言",
        "settings.z_order": "窗口层级",
        "settings.always_on_top": "置于最上层",
        "settings.always_on_bottom": "置于最底层",
        "settings.always_on_normal": "普通层级",
        "settings.layer_bottom": "置于最底层",
        "settings.layer_normal": "普通层级",
        "settings.layer_top": "置于最上层",
        "settings.position_fixed": "固定窗口位置（禁止拖动与缩放）",
        "settings.hide_from_taskbar": "不在任务栏显示图标（用托盘图标找回）",
        # ---- 顶部栏标题 ----
        "main.title_default": "JUST DO IT.",
        "settings.title_text": "顶部栏文字",
        "settings.title_placeholder": "留空则不显示文字",
        "settings.autostart": "开机自启动",
        "settings.autostart_failed": "写入开机自启动失败,请检查系统权限",
        # ---- 系统托盘 ----
        "tray.toggle": "显示 / 隐藏窗口",
        "tray.quit": "退出",
        "settings.history_btn": "查看历史任务",
        "settings.keybind_btn": "编辑快捷键",
        "settings.reset_btn": "恢复默认设置",
        "settings.reset_confirm": "把外观和功能开关都恢复成默认吗？\n（颜色、字体、透明度、顶部栏文字、快捷键；窗口层级、固定窗口位置、缩略模式、不在任务栏显示图标一律关闭。「开机自启动」不受影响）",
        "settings.reset_done": "已恢复默认设置。",
        # ---- 快捷键设置窗口 ----
        "keys.title": "编辑快捷键",
        "keys.hint": "点一下输入框,再按要绑定的组合键（如 Ctrl+O）",
        "keys.action_z_order": "切换窗口层级",
        "keys.action_fixed": "固定窗口位置",
        "keys.action_compact": "缩略模式",
        "keys.cleared": "未绑定",
        "keys.hint_cleared": "退格键清空绑定",
        "keys.taken": "已从「{other}」移过来",
        "keys.empty": "该项未绑定快捷键",
        "keys.reset_btn": "恢复默认快捷键",
        "keys.done": "快捷键已恢复默认。",
        "settings.pick_bg": "选择背景颜色",
        "settings.pick_text": "选择字体颜色",
        "settings.lang_confirm": "界面语言将切换为{lang}，确定吗？",
        "settings.lang_restart": "语言已切换，将在重启后生效。",
        "settings.close": "关闭",
    },
    LANG_EN: {
        # ---- Common ----
        "common.confirm": "Confirm",
        "common.cancel": "Cancel",
        "common.restart_now": "Restart now",
        "common.later": "Later",
        # ---- Main window ----
        "app.running": "{name} is already running.",
        "app.crash": "An unexpected error occurred.\nDetails were saved to .lumistdo/crash.log — please attach it when reporting.",
        "app.data_warning": "Local Data Notice",
        "main.new_tooltip": "New task (Ctrl+N)",
        "main.empty_hint": "No tasks — click + above or press Ctrl+N",
        "main.completed_count": "Completed  {n}",
        "main.settings_tooltip": "Settings",
        "main.lock_tooltip": "Shortcuts",
        "main.menu_quit": "Quit",
        "main.menu_minimize": "Minimize",
        "main.pin_tooltip_on": "Keep on top -> bottom{sc}",
        "main.pin_tooltip_off": "Keep at bottom -> normal layer{sc}",
        "main.pin_tooltip_mid": "Normal layer -> keep on top{sc}",
        "main.fixed_tooltip_on": "Unfix window{sc}",
        "main.fixed_tooltip_off": "Fix window position (no drag or resize){sc}",
        "main.compact_action_on": "Leave compact mode",
        "main.compact_action_off": "Compact mode (list only)",
        # ---- Task item ----
        "task.mark_done": "Mark as done",
        "task.edit": "Edit",
        "task.delete": "Delete",
        "task.edit_placeholder": "Type a task…",
        # ---- Settings window ----
        "settings.title": "Settings",
        "settings.presets": "Presets",
        "settings.bg_color": "Background color",
        "settings.text_color": "Text color",
        "settings.font": "Font",
        "settings.font_search": "Search fonts",
        "settings.font_size": "Font size",
        "settings.bg_opacity": "Background opacity",
        "settings.language": "Interface language",
        "settings.z_order": "Window layer",
        "settings.always_on_top": "Keep on top",
        "settings.always_on_bottom": "Keep at bottom",
        "settings.always_on_normal": "Normal layer",
        "settings.layer_bottom": "Keep at bottom",
        "settings.layer_normal": "Normal layer",
        "settings.layer_top": "Keep on top",
        "settings.position_fixed": "Fix window position (no drag or resize)",
        "settings.hide_from_taskbar": "Hide from taskbar (use tray icon to restore)",
        # ---- Header title ----
        "main.title_default": "JUST DO IT.",
        "settings.title_text": "Header text",
        "settings.title_placeholder": "Leave empty for no text",
        "settings.autostart": "Start with Windows",
        "settings.autostart_failed": "Could not write the autostart entry (check permissions)",
        # ---- System tray ----
        "tray.toggle": "Show / hide window",
        "tray.quit": "Quit",
        "settings.history_btn": "View history",
        "settings.keybind_btn": "Edit shortcuts",
        "settings.reset_btn": "Reset to defaults",
        "settings.reset_confirm": "Reset the appearance and feature switches to defaults?\n(colors, font, opacity, header text, shortcuts; window layer, fix position, compact mode and hide-from-taskbar all turn off. \"Start with Windows\" is left alone)",
        "settings.reset_done": "Reset to defaults.",
        # ---- Shortcut editor window ----
        "keys.title": "Edit shortcuts",
        "keys.hint": "Click a field, then press the combination (e.g. Ctrl+O)",
        "keys.action_z_order": "Cycle window layer",
        "keys.action_fixed": "Fix window position",
        "keys.action_compact": "Compact mode",
        "keys.cleared": "Not bound",
        "keys.hint_cleared": "Backspace clears the binding",
        "keys.taken": "Moved over from \"{other}\"",
        "keys.empty": "This action has no shortcut",
        "keys.reset_btn": "Restore default shortcuts",
        "keys.done": "Default shortcuts restored.",
        "settings.pick_bg": "Pick background color",
        "settings.pick_text": "Pick text color",
        "settings.lang_confirm": "Switch interface language to {lang}?",
        "settings.lang_restart": "Language switched. It will take effect after a restart.",
        "settings.close": "Close",
    },
}
