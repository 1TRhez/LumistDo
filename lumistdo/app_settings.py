"""应用设置:用户自定义外观 + 自动对比色派生。

持久化到软件目录下的 .lumistdo/settings.json,与 tasks.json 同目录。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from PySide6.QtGui import QColor, QKeySequence

from .json_io import atomic_write_text


MIN_BG_OPACITY = 3  # 约 1%（内部透明度范围为 0~255）
MAX_TITLE_LENGTH = 40  # 顶部栏标题最大长度,再长会顶掉右侧图标按钮
DEFAULT_TITLE_TEXT = "LumistDo"  # 顶部栏默认文字;留空则由用户主动清掉
# 出厂外观预设名(与 settings_dialog.PRESETS 里的 name 对应)与"自定义配色"标记
DEFAULT_PRESET = "深空"
CUSTOM_PRESET = "custom"

# 顶部栏三个功能按钮的快捷键动作名
SHORTCUT_ACTIONS = ("z_order", "fixed", "compact")
# 出厂快捷键:在设置窗口的「编辑快捷键」里改,恢复默认设置时回到这一组
DEFAULT_SHORTCUTS = {
    "z_order": "Ctrl+O",   # 循环切换 置顶 / 普通 / 置底
    "fixed": "Ctrl+K",     # 固定窗口位置(禁止拖动与缩放)
    "compact": "Ctrl+L",   # 缩略模式
}
# 禁止绑定的按键:tab 会打断焦点遍历,方向键/空格/回车留给界面本身,
# esc 用作取消编辑,退格/删除用作清空绑定。
FORBIDDEN_SEQUENCES = {
    "", "Tab", "Backtab", "Space", "Return", "Enter", "Escape",
    "Backspace", "Delete", "Del",
    "Up", "Down", "Left", "Right",
}

_MOD_KEYS = {"ctrl", "shift", "alt", "meta"}
_KEY_ALIASES = {
    "pgup": "PgUp", "pgdown": "PgDown", "pageup": "PgUp", "pagedown": "PgDown",
    "ins": "Ins", "insert": "Ins", "del": "Delete", "delkey": "Delete",
}


def normalize_sequence(text: str) -> str:
    """把快捷键文本规整成 Qt 认识的形式,不合法或禁止绑定则返回空串。

    用可移植文本解析(QKeySequence.PortableText),这样无论系统怎么设置
    修饰键显示名(Ctrl / ⌘ / Strg 等),界面里显示的都是同一套写法。
    """
    parts = [p.strip() for p in str(text).split("+")]
    if not parts or any(not p for p in parts):
        return ""
    keys = []
    for index, part in enumerate(parts):
        low = part.lower()
        if low in _MOD_KEYS:
            if index == len(parts) - 1:
                return ""  # 只有修饰键,没按实际按键
            keys.append(low.capitalize())
            continue
        key = _KEY_ALIASES.get(low, part)
        if len(key) != 1 and not key.startswith("F"):
            key = key[:1].upper() + key[1:]
        keys.append(key)
    sequence = QKeySequence.fromString("+".join(keys), QKeySequence.PortableText)
    if sequence.isEmpty():
        return ""
    text = sequence.toString(QKeySequence.PortableText)
    if text in FORBIDDEN_SEQUENCES:
        return ""
    return text


def _luminance(c: QColor) -> float:
    """相对亮度(0~255),用于判断背景明暗。"""
    return 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()


def _mix(base: QColor, overlay: QColor, alpha: int) -> QColor:
    """将 overlay 以 alpha(0~255)叠加到 base 上,返回混合色。"""
    a = alpha / 255.0
    return QColor(
        int(base.red() * (1 - a) + overlay.red() * a),
        int(base.green() * (1 - a) + overlay.green() * a),
        int(base.blue() * (1 - a) + overlay.blue() * a),
    )


def _parse_shortcuts(raw) -> dict:
    """校验并补齐快捷键表;缺失或非法的项回落到出厂快捷键。"""
    result = dict(DEFAULT_SHORTCUTS)
    if not isinstance(raw, dict):
        return result
    for action in SHORTCUT_ACTIONS:
        value = raw.get(action)
        if not isinstance(value, str):
            continue
        # 空串是合法值,表示用户主动解绑了这个功能
        result[action] = normalize_sequence(value) if value.strip() else ""
    return result


@dataclass
class Theme:
    """从用户设置派生的完整配色方案。

    fixed_* 系列:软件自身标识(标题、已完成标签),不随用户自定义改变。
    其余颜色:根据背景明暗自动派生,始终保持与背景可区分。
    """

    # ---- 用户可自定义 ----
    bg_color: QColor = field(default_factory=lambda: QColor("#25262c"))
    text_color: QColor = field(default_factory=lambda: QColor("#e9e9ef"))
    font_family: str = "Segoe UI Variable"
    font_size: int = 13
    bg_opacity: int = 240  # 0~255

    # ---- 固定(软件标识,不随自定义变;明暗跟着背景走,见 _derive) ----
    fixed_title_color: QColor = field(init=False)
    fixed_footer_color: QColor = field(init=False)

    # ---- 自动派生 ----
    sep_color: QColor = field(init=False)
    icon_color: QColor = field(init=False)
    icon_hover_color: QColor = field(init=False)
    highlight_color: QColor = field(init=False)
    scrollbar_color: QColor = field(init=False)
    scrollbar_hover_color: QColor = field(init=False)
    accent_color: QColor = field(init=False)
    edge_fade_color: QColor = field(init=False)
    # 背景渐变两端(毛玻璃质感):上端被"打亮"、下端略沉,alpha 与 bg_opacity 一致
    bg_top_color: QColor = field(init=False)
    bg_bottom_color: QColor = field(init=False)
    is_dark: bool = field(init=False)

    def __post_init__(self):
        self._derive()

    def _derive(self):
        bg = self.bg_color
        lum = _luminance(bg)
        self.is_dark = lum < 128

        # 渐变两端:只做很小的色差。跨满窗口高度时 8bit 量化会出水平色带,
        # 所以亮度差控制在 ~20 个灰阶以内,再靠 render 时的抖动掩盖。
        highlight = QColor(255, 255, 255) if self.is_dark else QColor(0, 0, 0)
        shade = QColor(0, 0, 0) if self.is_dark else QColor(255, 255, 255)
        top = _mix(bg, highlight, 26)
        bottom = _mix(bg, shade, 26)
        op = self.bg_opacity
        self.bg_top_color = QColor(top.red(), top.green(), top.blue(), op)
        self.bg_bottom_color = QColor(bottom.red(), bottom.green(), bottom.blue(), op)

        if self.is_dark:
            # 深色背景 → 用白色低透明度做线条/图标/高亮
            white = QColor(255, 255, 255)
            self.sep_color = QColor(255, 255, 255, 10)
            self.icon_color = _mix(bg, white, 110)
            self.icon_hover_color = _mix(bg, white, 200)
            self.highlight_color = QColor(255, 255, 255, 7)
            self.scrollbar_color = QColor(255, 255, 255, 36)
            self.scrollbar_hover_color = QColor(255, 255, 255, 58)
            self.accent_color = QColor("#5ea0ff")
            self.edge_fade_color = QColor(bg.red(), bg.green(), bg.blue())
        else:
            # 浅色背景 → 用黑色低透明度
            black = QColor(0, 0, 0)
            self.sep_color = QColor(0, 0, 0, 18)
            self.icon_color = _mix(bg, black, 100)
            self.icon_hover_color = _mix(bg, black, 180)
            self.highlight_color = QColor(0, 0, 0, 10)
            self.scrollbar_color = QColor(0, 0, 0, 40)
            self.scrollbar_hover_color = QColor(0, 0, 0, 70)
            self.accent_color = QColor("#2b7de9")
            self.edge_fade_color = QColor(bg.red(), bg.green(), bg.blue())

        # 标题与页脚的灰也要跟着明暗走:浅色背景上用原来的浅灰等于看不见。
        if self.is_dark:
            self.fixed_title_color = QColor("#9a9aa5")
            self.fixed_footer_color = QColor("#8a8a94")
        else:
            self.fixed_title_color = QColor("#5c5c66")
            self.fixed_footer_color = QColor("#63636d")


def container_qss(theme: Theme, selector: str, radius: float) -> str:
    """主窗口/设置窗口/快捷键窗口共用的容器背景样式。

    用垂直渐变而不是纯色:上端混一点反差色、下端略沉,做出玻璃面板的厚度感。
    三档停靠点(0% / 45% / 100%)而不是两档——两档时色差要跨满整个窗口高度,
    8bit 量化下会看到一条条水平色带。
    """
    top = theme.bg_top_color
    mid = theme.bg_color
    bottom = theme.bg_bottom_color
    r = radius
    return (
        f"{selector} {{"
        f"  background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f"    stop:0 rgba({top.red()}, {top.green()}, {top.blue()}, {top.alpha()}),"
        f"    stop:0.45 rgba({mid.red()}, {mid.green()}, {mid.blue()}, {theme.bg_opacity}),"
        f"    stop:1 rgba({bottom.red()}, {bottom.green()}, {bottom.blue()},"
        f" {bottom.alpha()}));"
        f"  border: none;"
        f"  border-radius: {r:g}px;"
        f"}}"
    )


@dataclass
class AppSettings:
    """用户设置,持久化到 JSON。默认外观为预设「深空」。"""

    bg_color: str = "#25262c"
    text_color: str = "#e9e9ef"
    font_family: str = "Segoe UI Variable"
    font_size: int = 13
    bg_opacity: int = 240
    language: str = "zh"  # zh / en,界面语言,重启后生效
    always_on_top: bool = False  # 图钉置顶状态,重启后保持
    always_on_bottom: bool = False  # 置底状态,与置顶互斥
    position_fixed: bool = False  # 固定窗口位置:禁止拖动与缩放,重启后保持
    hide_from_taskbar: bool = False  # 不在任务栏显示图标:此时常驻托盘图标
    autostart: bool = False  # 开机自启动(HKCU Run),重启后保持
    compact_mode: bool = False  # 缩略模式:只留任务列表,顶栏渐隐,重启后保持
    title_text: str = DEFAULT_TITLE_TEXT  # 顶部栏标题,留空则不显示文字
    shortcuts: dict = field(default_factory=lambda: dict(DEFAULT_SHORTCUTS))
    window_x: int | None = None
    window_y: int | None = None
    window_width: int | None = None
    window_height: int | None = None
    custom_colors: list[str] = field(default_factory=list)
    # 当前外观来自哪套预设(PRESETS 里的名字,custom = 自定义配色)。
    # 只用于设置窗口里高亮选中的预设,不影响渲染。
    appearance_preset: str = DEFAULT_PRESET

    def to_theme(self) -> Theme:
        return Theme(
            bg_color=QColor(self.bg_color),
            text_color=QColor(self.text_color),
            font_family=self.font_family,
            font_size=self.font_size,
            bg_opacity=self.bg_opacity,
        )

    def save(self, path: Path):
        atomic_write_text(
            path,
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
        )

    @classmethod
    def load(cls, path: Path) -> "AppSettings":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        s = cls()
        for key in ("bg_color", "text_color", "font_family"):
            if key in data and isinstance(data[key], str):
                setattr(s, key, data[key])
        lang = data.get("language")
        if isinstance(lang, str) and lang in ("zh", "en"):
            s.language = lang
        if type(data.get("always_on_top")) is bool:
            s.always_on_top = data["always_on_top"]
        if type(data.get("always_on_bottom")) is bool:
            s.always_on_bottom = data["always_on_bottom"]
        if type(data.get("position_fixed")) is bool:
            s.position_fixed = data["position_fixed"]
        if type(data.get("hide_from_taskbar")) is bool:
            s.hide_from_taskbar = data["hide_from_taskbar"]
        if type(data.get("autostart")) is bool:
            s.autostart = data["autostart"]
        if type(data.get("compact_mode")) is bool:
            s.compact_mode = data["compact_mode"]
        title = data.get("title_text")
        if isinstance(title, str):
            # 去掉换行等控制字符,再按长度上限截断(与输入框的 maxLength 一致)
            s.title_text = " ".join(title.split())[:MAX_TITLE_LENGTH]
        elif title is None:
            # 老版本设置文件里没有这个键 → 显示默认标语
            s.title_text = DEFAULT_TITLE_TEXT
        s.shortcuts = _parse_shortcuts(data.get("shortcuts"))
        # 置顶与置底互斥:置底开启时以置底为准,避免同时存在两个相反的层级要求
        if s.always_on_bottom:
            s.always_on_top = False
        for key in ("font_size", "bg_opacity"):
            if key in data and type(data[key]) is int:
                setattr(s, key, data[key])
        for key in ("window_x", "window_y", "window_width", "window_height"):
            if key in data and type(data[key]) is int:
                setattr(s, key, data[key])
        if isinstance(data.get("custom_colors"), list):
            s.custom_colors = [
                color for color in data["custom_colors"]
                if isinstance(color, str) and QColor(color).isValid()
            ][:16]
        preset = data.get("appearance_preset")
        if isinstance(preset, str) and preset.strip():
            s.appearance_preset = preset.strip()[:24]
        # 校验颜色合法性
        if not QColor(s.bg_color).isValid():
            s.bg_color = "#25262c"
        if not QColor(s.text_color).isValid():
            s.text_color = "#e9e9ef"
        s.font_size = max(9, min(24, s.font_size))
        s.bg_opacity = max(MIN_BG_OPACITY, min(255, s.bg_opacity))
        if s.window_width is not None:
            s.window_width = max(220, s.window_width)
        if s.window_height is not None:
            s.window_height = max(200, s.window_height)
        return s
