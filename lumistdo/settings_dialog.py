"""设置窗口:外观、语言、数据管理与关于。

独立非模态窗口,不遮挡主界面;任何修改即时生效(实时预览)。
颜色使用系统选择器，字体直接在设置窗口的下拉框中选择。
窗口自绘外观(无系统边框):与主界面同一套圆角、羽化边缘与背景透明度,
右上角是自绘的关闭按钮。
"""

import math

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame,
    QColorDialog, QComboBox, QSlider, QSpinBox, QCompleter,
    QAbstractSpinBox, QLineEdit, QMessageBox, QCheckBox, QRadioButton,
    QButtonGroup, QSizePolicy,
)
# 注:QCompleter 仅用其枚举常量配置 combo 内置补全器,不另建实例
from PySide6.QtCore import Qt, Signal, QEvent, QPoint, QPointF, QRectF, QSize
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontDatabase, QFontMetrics, QIcon, QPainter, QPen,
    QPixmap, QPolygonF,
)

from . import dialogs
from .app_settings import (
    AppSettings, CUSTOM_PRESET, DEFAULT_PRESET, MAX_TITLE_LENGTH, MIN_BG_OPACITY,
    Theme, container_qss, radio_qss,
)
from .floating_window import (
    CONTAINER_RADIUS, OUTER_MARGIN, CloseButton, custom_preset_glyph,
    make_color_btn, paint_color_btn, paint_edge_fade,
)
from .i18n import (
    LANG_EN, LANG_ZH, preset_name, product_name, set_language, t,
)
from .restart import restart_app

# 设置窗口的内容区宽度:底部三个按钮(编辑快捷键/恢复默认/查看历史任务)
# 要放得下,300px 会把文字挤成省略号,这里留足 340px
CONTENT_WIDTH = 340


def pick_color(initial: QColor, title: str, parent=None) -> QColor:
    """弹系统非原生取色器,返回选中的颜色;取消时返回无效 QColor。

    非原生(不走 Windows 自带对话框)才能沿用 Qt 的自定义色板,
    也才能跟着应用的中文字体与深色配色。
    """
    dialog = QColorDialog(initial, parent)
    dialog.setWindowTitle(title)
    dialog.setOption(QColorDialog.DontUseNativeDialog, True)
    accepted = dialog.exec()
    return dialog.selectedColor() if accepted else QColor()

WINDOW_QSS = """
QLabel { color: #c8c8d2; }QLabel#sectionTitle {
    color: #9a9aa5;
    font-weight: 700;
    letter-spacing: 1.5px;
}
QLabel#windowTitle {
    color: #9a9aa5;
    font-weight: 700;
    letter-spacing: 2.0px;
}
QPushButton#colorBtn {
    border: 1px solid rgba(255,255,255,30);
    border-radius: 6px;
    min-width: 60px;
    min-height: 26px;
}
QPushButton#actionBtn {
    background: rgba(255,255,255,8);
    border: 1px solid rgba(255,255,255,16);
    border-radius: 7px;
    color: #d0d0d8;
    padding: 6px 16px;
}
QPushButton#actionBtn:hover {
    background: rgba(255,255,255,14);
}
QPushButton#iconBtn {
    background: rgba(255,255,255,8);
    border: 1px solid rgba(255,255,255,16);
    border-radius: 7px;
    color: #d0d0d8;
    padding: 0;
}
QPushButton#iconBtn:hover {
    background: rgba(255,255,255,16);
}
QSlider::groove:horizontal {
    height: 4px;
    background: rgba(255,255,255,20);
    border-radius: 2px;
}
QSlider::handle:horizontal {
    width: 14px;
    height: 14px;
    margin: -5px 0;
    background: #5ea0ff;
    border-radius: 7px;
}
QSpinBox {
    background: rgba(255,255,255,8);
    border: 1px solid rgba(255,255,255,20);
    border-radius: 6px;
    color: #e0e0e8;
    padding: 3px 6px;
}
QSpinBox::up-button, QSpinBox::down-button { width: 16px; }
QCheckBox {
    color: #c8c8d2;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid rgba(255,255,255,40);
    border-radius: 4px;
    background: rgba(255,255,255,8);
}
QCheckBox::indicator:hover {
    border-color: #5ea0ff;
}
QCheckBox::indicator:checked {
    background: #5ea0ff;
    border-color: #5ea0ff;
}
QRadioButton {
    color: #c8c8d2;
    spacing: 8px;
}
/* 圆点本体由 radio_qss(theme) 在 apply_theme 里按明暗主题给,不写死在这里 */
QComboBox {
    background: rgba(255,255,255,8);
    border: 1px solid rgba(255,255,255,20);
    border-radius: 6px;
    color: #e0e0e8;
    min-height: 28px;
    padding: 2px 8px;
}
QComboBox QAbstractItemView {
    background: #282930;
    border: 1px solid rgba(255,255,255,20);
    color: #e0e0e8;
    selection-background-color: #3d6599;
}
QLineEdit {
    background: rgba(255,255,255,8);
    border: 1px solid rgba(255,255,255,20);
    border-radius: 6px;
    color: #e0e0e8;
    min-height: 28px;
    padding: 2px 8px;
}
QLineEdit:focus {
    border-color: #5ea0ff;
}
"""

# 预设主题:每套包含 bg_color, text_color, font_family, font_size, bg_opacity, blur。
# name 同时是持久化用的标识(settings.appearance_preset),不要跟着界面语言改。
# blur = 真·毛玻璃(让 Windows 把背后的桌面内容模糊掉,见 lumistdo/blur_behind.py);
# 只有毛玻璃预设默认开,其余预设都是实底,开了也看不出来。
PRESETS = [
    {"name": "深空",   "bg": "#25262c", "text": "#e9e9ef", "font": "Segoe UI Variable", "size": 13, "opacity": 240, "blur": False},
    {"name": "暖夜",   "bg": "#2c2420", "text": "#f0e6dc", "font": "Microsoft YaHei UI", "size": 13, "opacity": 235, "blur": False},
    # 毛玻璃:背景几乎全透明(alpha 22/255 ≈ 9%),靠 blur_behind 把背后的桌面糊掉。
    # 不是"半透明能看见壁纸",而是"像透过磨砂玻璃看"——背后是糊的,只剩色块。
    # 那点 alpha 用来托住右上角图标与顶栏文字的对比度,全 0 会让浅色壁纸上的白字看不清。
    {"name": "毛玻璃", "bg": "#333a47", "text": "#f4f6fa", "font": "Segoe UI Variable", "size": 13, "opacity": 22, "blur": True},
    {"name": "海洋",   "bg": "#1a2432", "text": "#dce8f4", "font": "Segoe UI Variable", "size": 13, "opacity": 240, "blur": False},
    {"name": "薰衣草", "bg": "#282430", "text": "#ece6f4", "font": "Microsoft YaHei UI", "size": 13, "opacity": 236, "blur": False},
    {"name": "素白",   "bg": "#f2f2f4", "text": "#2c2c32", "font": "Microsoft YaHei UI", "size": 13, "opacity": 248, "blur": False},
]


class _NoWheelComboBox(QComboBox):
    """禁用滚轮换字体:悬停/聚焦时滚轮一动就换字体,太容易误触。"""

    def wheelEvent(self, event):
        event.ignore()  # 交给父级(页面滚动等)


class _NoWheelSpinBox(QSpinBox):
    """禁用滚轮改字号,理由同上。"""

    def wheelEvent(self, event):
        event.ignore()


class _NoWheelSlider(QSlider):
    """禁用滚轮调透明度:悬停时滚轮一动就改值,太容易误触。"""

    def wheelEvent(self, event):
        event.ignore()


def reset_glyph(size, color, hover=False):
    """画一个「恢复默认」圆形箭头位图(留口圆环 + 加粗箭头)。

    独立成函数:底部按钮条上的按钮要把同一个图形当图标用,
    自绘控件和图标两条路都从这一份画法出来,不会长成两个样子。
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    scale = size / 30.0
    p.scale(scale, scale)
    center = 15.0
    radius = 6.6
    start_deg, span_deg = 60.0, 230.0
    p.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawArc(
        QRectF(center - radius, center - radius, radius * 2, radius * 2),
        int(start_deg * 16), int(span_deg * 16),
    )
    # 箭头:33px 下必须比弧线粗得多才认得出是箭头而不是字母 C
    tip = _polar(center, radius, start_deg)
    head = 6.4
    tangent = math.radians(start_deg + 90.0)
    tx, ty = math.cos(tangent), -math.sin(tangent)
    nx, ny = -ty, tx
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawPolygon(QPolygonF([
        QPointF(tip.x() - tx * head * 0.5, tip.y() - ty * head * 0.5),
        QPointF(tip.x() + tx * head * 0.8 + nx * head * 0.55,
                tip.y() + ty * head * 0.8 + ny * head * 0.55),
        QPointF(tip.x() + tx * head * 0.8 - nx * head * 0.55,
                tip.y() + ty * head * 0.8 - ny * head * 0.55),
    ]))
    p.end()
    return pm


def _polar(center, radius, angle_deg):
    """极坐标取点:角度按数学惯例(0 度在右,逆时针为正)。"""
    rad = math.radians(angle_deg)
    return QPointF(
        center + radius * math.cos(rad), center - radius * math.sin(rad),
    )


class SettingsHeader(QWidget):
    """设置窗口顶部条:标题 + 自绘关闭按钮,空白处可拖动整个窗口。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self._drag_pos = None
        self.setCursor(QCursor(Qt.ArrowCursor))

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self.title_label = QLabel()
        self.title_label.setObjectName("windowTitle")
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.title_label.setMinimumWidth(0)
        row.addWidget(self.title_label, 1)

        self.close_btn = CloseButton(self)
        self.close_btn.clicked.connect(self._window.close)
        row.addWidget(self.close_btn, 0)

        self.set_title(t("settings.title"))

    def set_title(self, text):
        """写入标题;空字符串表示不显示标题。"""
        self._raw_title = (text or "").upper()
        self.title_label.setText(self._raw_title)
        self.title_label.setVisible(bool(self._raw_title))
        self._elide_title()

    def _elide_title(self):
        """按标签实际宽度省略,避免标题顶掉右侧关闭按钮。"""
        if not self._raw_title or self.title_label.width() <= 0:
            return
        metrics = QFontMetrics(self.title_label.font())
        self.title_label.setText(
            metrics.elidedText(self._raw_title, Qt.ElideRight, self.title_label.width()),
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide_title()

    # ---- 空白处按住可拖动窗口 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)


class CustomColorHeader(QWidget):
    """自定义配色窗口顶部条:标题 + 自绘关闭按钮,空白处可拖动窗口。"""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(7)
        self.setFixedHeight(26)

        self.title_label = QLabel(t("custom.title"))
        self.title_label.setObjectName("windowTitle")
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row.addWidget(self.title_label, 1)
        self.close_btn = CloseButton(self)
        row.addWidget(self.close_btn)

        self._drag_offset = None

    def _elide_title(self):
        width = self.title_label.width()
        if width <= 0:
            return
        metrics = QFontMetrics(self.title_label.font())
        self.title_label.setText(
            metrics.elidedText(t("custom.title").upper(), Qt.ElideRight, width),
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide_title()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint()
                - self._window.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            self._window.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class CustomColorWindow(QWidget):
    """自定义配色窗口:单独调背景色与字体颜色(与设置窗口同一套自绘外观)。

    改色即写进 settings 并发 changed,主窗口与设置窗口实时跟随。
    只暴露两个颜色,因为「毛玻璃」那种层次感来自派生色,不靠用户手调。
    """

    changed = Signal(QColor, QColor)   # (背景色, 字体颜色)

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        set_language(settings.language)
        self._settings = settings
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle(f"{product_name()} - {t('custom.title')}")
        self.setStyleSheet(WINDOW_QSS)
        self.setFixedWidth(CONTENT_WIDTH + OUTER_MARGIN * 2)
        self._fade_pixmap = None
        self._fade_key = None
        self._build_ui()
        self.apply_theme()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN,
        )
        self.container = QFrame()
        self.container.setObjectName("settingsContainer")
        outer.addWidget(self.container)

        root = QVBoxLayout(self.container)
        root.setContentsMargins(20, 8, 20, 16)
        root.setSpacing(10)

        self.header = CustomColorHeader(self)
        self.header.close_btn.clicked.connect(self.close)
        root.addWidget(self.header)

        hint = QLabel(t("custom.hint"))
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8a8a94;")
        root.addWidget(hint)

        self._bg_btn = make_color_btn(QColor(self._settings.bg_color))
        root.addWidget(self._row(t("custom.bg"), self._bg_btn, self._pick_bg))

        self._txt_btn = make_color_btn(QColor(self._settings.text_color))
        root.addWidget(self._row(t("custom.text"), self._txt_btn, self._pick_text))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        reset_btn = QPushButton()
        reset_btn.setObjectName("actionBtn")
        reset_btn.setCursor(QCursor(Qt.PointingHandCursor))
        reset_btn.setToolTip(t("custom.reset_btn"))
        reset_btn.setAccessibleName(t("custom.reset_btn"))
        reset_btn.setIconSize(QSize(16, 16))
        reset_btn.clicked.connect(self.restore_defaults)
        self.reset_btn = reset_btn
        btn_row.addWidget(reset_btn, 1)
        confirm_btn = QPushButton(t("custom.confirm"))
        confirm_btn.setObjectName("actionBtn")
        confirm_btn.setCursor(QCursor(Qt.PointingHandCursor))
        confirm_btn.clicked.connect(self.close)
        btn_row.addWidget(confirm_btn, 1)
        root.addLayout(btn_row)

    def _row(self, label_text, btn, slot):
        """一行:标签在上、色块在下(与设置窗口的颜色行同一版式)。"""
        col = QVBoxLayout()
        col.setSpacing(6)
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color: #8a8a94;")
        lbl.setFixedHeight(18)
        col.addWidget(lbl)
        btn.clicked.connect(slot)
        col.addWidget(btn)
        wrap = QWidget()
        wrap.setLayout(col)
        return wrap

    # ---- 改色 ----
    def _pick_bg(self):
        color = pick_color(QColor(self._settings.bg_color), t("custom.pick_bg"), self)
        if color.isValid():
            self._settings.bg_color = color.name()
            paint_color_btn(self._bg_btn, color)
            self._emit()

    def _pick_text(self):
        color = pick_color(
            QColor(self._settings.text_color), t("custom.pick_text"), self,
        )
        if color.isValid():
            self._settings.text_color = color.name()
            paint_color_btn(self._txt_btn, color)
            self._emit()

    def restore_defaults(self):
        """恢复出厂配色:回到默认预设(深空)的颜色。"""
        defaults = AppSettings()
        self._settings.bg_color = defaults.bg_color
        self._settings.text_color = defaults.text_color
        self._settings.appearance_preset = DEFAULT_PRESET
        self.refresh()
        self._emit()

    def refresh(self):
        """把 settings 里的颜色重新画到色块上(外观被别处改动时调用)。"""
        bg = QColor(self._settings.bg_color)
        text = QColor(self._settings.text_color)
        paint_color_btn(self._bg_btn, bg)
        paint_color_btn(self._txt_btn, text)
        self.reset_btn.setIcon(QIcon(reset_glyph(16, text)))
        self._fade_pixmap = None
        self._fade_key = None
        self.update()

    def _emit(self):
        self.changed.emit(
            QColor(self._settings.bg_color), QColor(self._settings.text_color),
        )

    # ---- 外观:与设置窗口同一套(背景/透明度/字体/羽化) ----
    def apply_theme(self):
        theme = self._settings.to_theme()
        self.container.setStyleSheet(
            container_qss(theme, "QFrame#settingsContainer", CONTAINER_RADIUS),
        )
        self.setFont(QFont(theme.font_family, 10))
        self.reset_btn.setIcon(QIcon(reset_glyph(16, QColor(theme.text_color))))
        self._fade_pixmap = None
        self._fade_key = None
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fade_pixmap = None
        self._fade_key = None

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.width() <= 0 or self.height() <= 0:
            return
        p = QPainter(self)
        p.drawPixmap(0, 0, self._edge_fade_pixmap())
        p.end()

    def _edge_fade_pixmap(self):
        key = (self.width(), self.height(), id(self._settings))
        if self._fade_pixmap is not None and self._fade_key == key:
            return self._fade_pixmap
        theme = self._settings.to_theme()
        pm = QPixmap(self.width(), self.height())
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        paint_edge_fade(p, QRectF(self.container.geometry()), theme)
        p.end()
        self._fade_pixmap = pm
        self._fade_key = key
        return pm


class SettingsWindow(QWidget):
    """外观设置独立窗口(非模态,实时预览)。"""
    changed = Signal()  # 任何设置变动时发出,主窗口据此实时刷新
    z_order_changed = Signal(str)        # 窗口层级:回传 "top"/"bottom"/"normal"
    position_fixed_changed = Signal(bool)  # 固定开关:同样需即时生效
    taskbar_changed = Signal(bool)       # 任务栏图标开关:需即时改扩展样式
    autostart_changed = Signal(bool)     # 开机自启动:需即时写注册表
    title_changed = Signal(str)          # 顶部栏文字:需即时重排标题
    keybind_requested = Signal()         # 打开快捷键设置窗口
    global_shortcuts_changed = Signal(bool)  # 全局快捷键开关:需重挂 RegisterHotKey
    reset_requested = Signal()           # 恢复默认设置:主窗口收掉缩略/隐藏清单等界面状态
    history_requested = Signal()

    def __init__(self, settings: AppSettings, parent=None):
        super().__init__(parent)
        # 窗口文案跟随 settings 里的语言(启动时 main.py 已全局同步,
        # 这里再确保窗口自身始终与自己的 settings 一致)
        set_language(settings.language)
        self.setWindowTitle(t("settings.title"))
        # 自绘外观:无系统边框 → 与主界面同一套圆角与羽化边缘
        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet(WINDOW_QSS)
        self.setFixedWidth(CONTENT_WIDTH + OUTER_MARGIN * 2)
        self._settings = settings
        self._fade_pixmap = None
        self._fade_key = None
        # 自定义配色窗口正在「恢复默认配色」:此时不要把它标记成自定义预设
        self._restoring_custom = False
        self._build_ui()
        self.apply_theme()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN,
        )
        self.container = QFrame()
        self.container.setObjectName("settingsContainer")
        outer.addWidget(self.container)

        root = QVBoxLayout(self.container)
        root.setContentsMargins(20, 8, 20, 16)
        root.setSpacing(10)

        # ---- 顶部条:标题 + 自绘关闭按钮,空白处可拖动窗口 ----
        self.header = SettingsHeader(self)
        self.header.setFixedHeight(26)
        root.addWidget(self.header)

        # ---- 预设主题 ----
        root.addWidget(self._row_label(t("settings.presets")))
        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        self._preset_btns = {}
        for p in PRESETS:
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setToolTip(preset_name(p["name"]))
            btn.setAccessibleName(preset_name(p["name"]))
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background: {p['bg']};"
                f"  border: 2px solid rgba(255,255,255,40);"
                f"  border-radius: 14px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  border-color: #5ea0ff;"
                f"}}"
                f"QPushButton[selected=\"true\"] {{"
                f"  border-color: #5ea0ff;"
                f"}}"
            )
            btn.clicked.connect(lambda checked=False, preset=p: self._apply_preset(preset))
            preset_row.addWidget(btn)
            self._preset_btns[p["name"]] = btn

        # 最右边的自定义配色入口:同样大小的圆,里面是四色小方块
        self._custom_btn = QPushButton()
        self._custom_btn.setFixedSize(28, 28)
        self._custom_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._custom_btn.setToolTip(t("preset.custom_tip"))
        self._custom_btn.setAccessibleName(t("preset.custom"))
        self._custom_btn.setIcon(QIcon(custom_preset_glyph(16)))
        self._custom_btn.setIconSize(QSize(16, 16))
        self._custom_btn.setStyleSheet(
            "QPushButton {"
            "  background: rgba(255,255,255,12);"
            "  border: 2px dashed rgba(255,255,255,45);"
            "  border-radius: 14px;"
            "}"
            "QPushButton:hover {"
            "  border-color: #5ea0ff;"
            "}"
            "QPushButton[selected=\"true\"] {"
            "  border-style: solid;"
            "  border-color: #5ea0ff;"
            "}"
        )
        self._custom_btn.clicked.connect(self.open_custom_colors)
        preset_row.addWidget(self._custom_btn)
        preset_row.addStretch()
        root.addLayout(preset_row)
        self._refresh_preset_selection()

        # ---- 背景颜色 / 字体颜色(并列两列) ----
        color_row = QHBoxLayout()
        color_row.setSpacing(14)
        bg_col = QVBoxLayout()
        bg_col.setSpacing(6)
        bg_col.addWidget(self._row_label(t("settings.bg_color")))
        self._bg_btn = self._make_color_btn(QColor(self._settings.bg_color))
        self._bg_btn.clicked.connect(self._pick_bg_color)
        bg_col.addWidget(self._bg_btn)
        color_row.addLayout(bg_col, 1)
        txt_col = QVBoxLayout()
        txt_col.setSpacing(6)
        txt_col.addWidget(self._row_label(t("settings.text_color")))
        self._txt_btn = self._make_color_btn(QColor(self._settings.text_color))
        self._txt_btn.clicked.connect(self._pick_text_color)
        txt_col.addWidget(self._txt_btn)
        color_row.addLayout(txt_col, 1)
        root.addLayout(color_row)

        # ---- 字体 ----
        root.addWidget(self._row_label(t("settings.font")))
        self._font_families = sorted(QFontDatabase.families(), key=str.casefold)
        self._font_combo = _NoWheelComboBox()
        self._font_combo.setEditable(True)
        self._font_combo.setInsertPolicy(QComboBox.NoInsert)
        self._font_combo.addItems(self._font_families)
        self._font_combo.setCurrentText(self._settings.font_family)
        self._font_combo.lineEdit().setPlaceholderText(t("settings.font_search"))
        # 直接配置内置补全器(可编辑 combo 自带),不再另建 QCompleter:
        # 少一份 500+ 字体项的补全模型,打开设置窗口更快。
        completer = self._font_combo.completer()
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self._font_combo.textActivated.connect(self._on_font_activated)
        self._font_combo.lineEdit().editingFinished.connect(self._commit_font_text)
        root.addWidget(self._font_combo)

        # ---- 字号 ----
        root.addWidget(self._row_label(t("settings.font_size")))
        size_row = QHBoxLayout()
        self._size_spin = _NoWheelSpinBox()
        self._size_spin.setRange(9, 24)
        self._size_spin.setValue(self._settings.font_size)
        self._size_spin.setSuffix(" px")
        self._size_spin.valueChanged.connect(self._on_size_changed)
        size_row.addWidget(self._size_spin)
        size_row.addStretch()
        root.addLayout(size_row)

        # ---- 背景透明度 ----
        root.addWidget(self._row_label(t("settings.bg_opacity")))
        op_row = QHBoxLayout()
        self._op_slider = _NoWheelSlider(Qt.Horizontal)
        self._op_slider.setRange(MIN_BG_OPACITY, 255)
        self._op_slider.setValue(self._settings.bg_opacity)
        op_row.addWidget(self._op_slider, 1)
        self._op_label = QLabel(f"{int(self._settings.bg_opacity / 255 * 100)}%")
        self._op_label.setFixedWidth(36)
        self._op_slider.valueChanged.connect(self._on_opacity_changed)
        op_row.addWidget(self._op_label)
        root.addLayout(op_row)

        # ---- 真·毛玻璃(把背后的桌面内容模糊掉,需要背景足够透明才看得出) ----
        self._blur_check = QCheckBox(t("settings.blur_behind"))
        self._blur_check.setCursor(QCursor(Qt.PointingHandCursor))
        self._blur_check.setChecked(self._settings.blur_behind)
        self._blur_check.toggled.connect(self._on_blur_toggled)
        root.addWidget(self._blur_check)

        # ---- 顶部栏文字(外观的一部分,留空则不显示文字) ----
        root.addWidget(self._row_label(t("settings.title_text")))
        self._title_edit = QLineEdit(self._settings.title_text)
        self._title_edit.setPlaceholderText(t("settings.title_placeholder"))
        self._title_edit.setMaxLength(MAX_TITLE_LENGTH)
        self._title_edit.textChanged.connect(self._on_title_text_changed)
        root.addWidget(self._title_edit)

        root.addWidget(self._separator())

        # ---- 窗口层级:三选一(置底 / 普通 / 置顶),与顶部栏图钉的三态同步 ----
        root.addWidget(self._row_label(t("settings.z_order")))
        self._layer_group = QButtonGroup(self)
        self._layer_group.setExclusive(True)
        self._layer_radios = {}
        for key, text in (
            ("bottom", t("settings.layer_bottom")),
            ("normal", t("settings.layer_normal")),
            ("top", t("settings.layer_top")),
        ):
            radio = QRadioButton(text)
            radio.setCursor(QCursor(Qt.PointingHandCursor))
            radio.toggled.connect(
                lambda checked, name=key: self._on_layer_selected(name, checked),
            )
            self._layer_group.addButton(radio)
            self._layer_radios[key] = radio
            root.addWidget(radio)
        layer = "top" if self._settings.always_on_top else (
            "bottom" if self._settings.always_on_bottom else "normal"
        )
        self._layer_radios[layer].setChecked(True)
        self._fixed_check = QCheckBox(t("settings.position_fixed"))
        self._fixed_check.setCursor(QCursor(Qt.PointingHandCursor))
        self._fixed_check.setChecked(self._settings.position_fixed)
        self._fixed_check.toggled.connect(self._on_position_fixed_toggled)
        root.addWidget(self._fixed_check)
        self._taskbar_check = QCheckBox(t("settings.hide_from_taskbar"))
        self._taskbar_check.setCursor(QCursor(Qt.PointingHandCursor))
        self._taskbar_check.setChecked(self._settings.hide_from_taskbar)
        self._taskbar_check.toggled.connect(self._on_hide_from_taskbar_toggled)
        root.addWidget(self._taskbar_check)

        self._autostart_check = QCheckBox(t("settings.autostart"))
        self._autostart_check.setCursor(QCursor(Qt.PointingHandCursor))
        self._autostart_check.setChecked(self._settings.autostart)
        self._autostart_check.toggled.connect(self._on_autostart_toggled)
        root.addWidget(self._autostart_check)

        root.addWidget(self._separator())

        # ---- 语言 ----
        lang_row = QHBoxLayout()
        lang_row.addWidget(self._row_label(t("settings.language")))
        self._lang_combo = _NoWheelComboBox()
        self._lang_combo.addItem("中文", LANG_ZH)
        self._lang_combo.addItem("English", LANG_EN)
        self._lang_combo.setCurrentIndex(
            1 if self._settings.language == LANG_EN else 0,
        )
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        lang_row.addWidget(self._lang_combo)
        lang_row.addStretch()
        root.addLayout(lang_row)

        root.addWidget(self._separator())

        # ---- 快捷键:是否注册成系统级热键(不选中窗口也能触发) ----
        self._global_keys_check = QCheckBox(t("settings.global_shortcuts"))
        self._global_keys_check.setCursor(QCursor(Qt.PointingHandCursor))
        self._global_keys_check.setChecked(bool(self._settings.global_shortcuts))
        self._global_keys_check.toggled.connect(self._on_global_shortcuts_toggled)
        root.addWidget(self._global_keys_check)

        root.addWidget(self._separator())

        # ---- 底部按钮条:编辑快捷键 / 恢复默认 / 查看历史任务(三格等宽等距) ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        keybind_btn = QPushButton(t("settings.keybind_btn"))
        keybind_btn.setObjectName("actionBtn")
        keybind_btn.setCursor(QCursor(Qt.PointingHandCursor))
        keybind_btn.clicked.connect(self.keybind_requested)
        btn_row.addWidget(keybind_btn, 1)
        self._keybind_btn = keybind_btn
        self._reset_btn = QPushButton()
        self._reset_btn.setObjectName("actionBtn")
        self._reset_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._reset_btn.setToolTip(t("settings.reset_btn"))
        self._reset_btn.setAccessibleName(t("settings.reset_btn"))
        self._reset_btn.setIconSize(QSize(16, 16))
        self._reset_btn.clicked.connect(self._reset_appearance)
        btn_row.addWidget(self._reset_btn, 1)
        history_btn = QPushButton(t("settings.history_btn"))
        history_btn.setObjectName("actionBtn")
        history_btn.setCursor(QCursor(Qt.PointingHandCursor))
        history_btn.clicked.connect(self.history_requested)
        btn_row.addWidget(history_btn, 1)
        self._history_btn = history_btn
        root.addLayout(btn_row)

        self._install_click_blank_clear_focus()

    # ---- 自绘外观:背景色/透明度/字体跟随设置,与主界面一致 ----
    def apply_theme(self):
        """重新套用主题(背景色、透明度、字体、边缘羽化)。"""
        theme = self._settings.to_theme()
        self.container.setStyleSheet(
            container_qss(theme, "QFrame#settingsContainer", CONTAINER_RADIUS),
        )
        # 单选圆点:按明暗主题重算(浅色背景下白环等于看不见)
        self.setStyleSheet(WINDOW_QSS + radio_qss(theme))
        self.setFont(QFont(theme.font_family, 10))
        self._reset_btn.setIcon(QIcon(reset_glyph(16, QColor(theme.text_color))))
        self._fade_pixmap = None
        self._fade_key = None
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 尺寸变了羽化位图作废(画法与主界面一致:缓存按 尺寸+主题 命中)
        self._fade_pixmap = None
        self._fade_key = None

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.width() <= 0 or self.height() <= 0:
            return
        p = QPainter(self)
        p.drawPixmap(0, 0, self._edge_fade_pixmap())
        p.end()

    def _edge_fade_pixmap(self):
        """返回当前尺寸+主题下的羽化位图(与主界面同一套画法)。"""
        key = (self.width(), self.height(), id(self._settings))
        if self._fade_pixmap is not None and self._fade_key == key:
            return self._fade_pixmap
        theme = self._settings.to_theme()
        pm = QPixmap(self.width(), self.height())
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        paint_edge_fade(p, QRectF(self.container.geometry()), theme)
        p.end()
        self._fade_pixmap = pm
        self._fade_key = key
        return pm

    # ---- 窗口层级(三选一,回传主窗口即时改层级)与固定 ----
    def _on_layer_selected(self, name, checked):
        """层级单选项被选中:写设置并把层级回传主窗口。

        传的是**具体层级名**而不是"要不要置底"的布尔值:主窗口收到后
        按同一个名字回同步单选项,才不会把用户刚点的「置于最上层」弹回「普通层级」。
        """
        if not checked:
            return
        self._settings.always_on_top = name == "top"
        self._settings.always_on_bottom = name == "bottom"
        self.z_order_changed.emit(name)
        self.changed.emit()

    def set_z_order_checks(self, layer):
        """主窗口改动层级后回同步单选项(仅主窗口调用,防止回环)。"""
        if layer is None:
            return
        radio = self._layer_radios.get(layer)
        if radio is not None and not radio.isChecked():
            radio.blockSignals(True)
            radio.setChecked(True)
            radio.blockSignals(False)

    def set_fixed_check(self, fixed):
        """主窗口改「固定窗口位置」后回同步勾选框(仅主窗口调用)。"""
        if self._fixed_check.isChecked() == fixed:
            return
        self._fixed_check.blockSignals(True)
        self._fixed_check.setChecked(fixed)
        self._fixed_check.blockSignals(False)

    def _on_position_fixed_toggled(self, checked):
        self._settings.position_fixed = checked
        self.position_fixed_changed.emit(checked)
        self.changed.emit()

    def _on_hide_from_taskbar_toggled(self, checked):
        self._settings.hide_from_taskbar = checked
        self.taskbar_changed.emit(checked)
        self.changed.emit()

    def _on_blur_toggled(self, checked):
        self._settings.blur_behind = checked
        # 只是开关一件效果,颜色没变,不该把预设高亮改成"自定义配色"
        self._emit_changed()

    def set_taskbar_check(self, hidden):
        """主窗口改动任务栏开关后回同步勾选(仅主窗口调用)。"""
        if self._taskbar_check.isChecked() == hidden:
            return
        self._taskbar_check.blockSignals(True)
        self._taskbar_check.setChecked(hidden)
        self._taskbar_check.blockSignals(False)

    def _on_autostart_toggled(self, checked):
        self._settings.autostart = checked
        self.autostart_changed.emit(checked)
        self.changed.emit()

    def _on_global_shortcuts_toggled(self, checked):
        """全局快捷键开关:写设置并让主窗口重挂(或注销)系统级热键。"""
        self._settings.global_shortcuts = bool(checked)
        self.global_shortcuts_changed.emit(bool(checked))
        self.changed.emit()

    def set_global_shortcuts_check(self, enabled):
        """主窗口改动该开关后回同步勾选(仅主窗口调用)。"""
        if self._global_keys_check.isChecked() == enabled:
            return
        self._global_keys_check.blockSignals(True)
        self._global_keys_check.setChecked(enabled)
        self._global_keys_check.blockSignals(False)

    def set_autostart_check(self, enabled, ok=True):
        """主窗口写注册表后回同步勾选;写失败时把勾选退回真实状态。"""
        if self._autostart_check.isChecked() != enabled:
            self._autostart_check.blockSignals(True)
            self._autostart_check.setChecked(enabled)
            self._autostart_check.blockSignals(False)
        self._autostart_check.setToolTip("" if ok else t("settings.autostart_failed"))

    def _on_title_text_changed(self, text):
        self._settings.title_text = text
        self.title_changed.emit(text)
        self.changed.emit()

    # ---- 恢复默认设置(外观 + 快捷键 + 除任务列表外的所有功能开关) ----
    def _reset_appearance(self):
        """把外观、快捷键和功能开关全部恢复出厂默认。

        外观 = 颜色/字体/字号/透明度/顶部栏文字/快捷键;
        功能 = 窗口层级(回普通层级)、固定窗口位置、缩略模式、
               不在任务栏显示图标 —— 一律回到关闭状态。
        唯一不动的是"开机自启动":它写的是注册表 Run 项,属于系统侧设置,
        点一下外观重置就悄悄关掉用户的开机启动不合适。
        """
        box = dialogs.message_box(self)
        box.setWindowTitle(product_name())
        box.setText(t("settings.reset_confirm"))
        confirm_btn = box.addButton(t("common.confirm"), QMessageBox.AcceptRole)
        box.addButton(t("common.cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not confirm_btn:
            return

        defaults = AppSettings()
        s = self._settings
        s.bg_color = defaults.bg_color
        s.text_color = defaults.text_color
        s.font_family = defaults.font_family
        s.font_size = defaults.font_size
        s.bg_opacity = defaults.bg_opacity
        s.title_text = defaults.title_text
        s.shortcuts = dict(defaults.shortcuts)
        s.always_on_top = defaults.always_on_top
        s.always_on_bottom = defaults.always_on_bottom
        s.position_fixed = defaults.position_fixed
        s.compact_mode = defaults.compact_mode
        s.hide_from_taskbar = defaults.hide_from_taskbar
        s.blur_behind = defaults.blur_behind
        s.global_shortcuts = defaults.global_shortcuts
        # 预设高亮一并回到默认「深空」,否则色块变了高亮还停在自定义上
        s.appearance_preset = defaults.appearance_preset

        # 控件同步(全部 blockSignals,避免中途触发一串 changed)
        self._bg_color = QColor(s.bg_color)
        self._txt_color = QColor(s.text_color)
        self._paint_color_btn(self._bg_btn, self._bg_color)
        self._paint_color_btn(self._txt_btn, self._txt_color)
        for widget, value in (
            (self._font_combo, s.font_family),
            (self._size_spin, s.font_size),
            (self._op_slider, s.bg_opacity),
            (self._title_edit, s.title_text),
        ):
            widget.blockSignals(True)
            if isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(value)
            else:
                widget.setValue(value)
            widget.blockSignals(False)
        self._op_label.setText(f"{int(s.bg_opacity / 255 * 100)}%")
        self._refresh_preset_selection()
        self.refresh_custom_colors()
        self.set_z_order_checks("normal")
        self.set_fixed_check(False)
        self.set_taskbar_check(False)
        # 全局快捷键是 AppSettings 的字段(不是 settings.<x> 交换),单独同步;
        # emit 让主窗口把系统级热键重新挂一遍
        self.set_global_shortcuts_check(s.global_shortcuts)
        self.global_shortcuts_changed.emit(s.global_shortcuts)
        self.title_changed.emit(s.title_text)
        self.changed.emit()
        # 交给主窗口把缩略模式/托盘图标这些界面状态一起收掉
        self.reset_requested.emit()
        dialogs.information(self, product_name(), t("settings.reset_done"))

    # ---- 点击空白处清除焦点(消掉字号框的蓝色选中高亮)----
    _FOCUS_KEEPERS = (QComboBox, QAbstractSpinBox, QLineEdit, QSlider)

    def _install_click_blank_clear_focus(self):
        self.installEventFilter(self)
        for child in self.findChildren(QWidget):
            child.installEventFilter(self)

    def eventFilter(self, obj, event):
        if (
            event.type() == QEvent.MouseButtonPress
            and not isinstance(obj, self._FOCUS_KEEPERS)
        ):
            focused = self.focusWidget()
            if focused is not None:
                focused.clearFocus()
        return super().eventFilter(obj, event)

    # ---- 语言(两段式确认:确认切换 → 提示重启) ----
    def _on_language_changed(self, index):
        lang = self._lang_combo.itemData(index)
        if lang == self._settings.language:
            return
        old_index = 1 if self._settings.language == LANG_EN else 0
        lang_name = "English" if lang == LANG_EN else "中文"

        # 第一段:用旧语言确认,用户看得懂才能做决定
        box = dialogs.message_box(self)
        box.setWindowTitle(product_name())
        box.setText(t("settings.lang_confirm", lang=lang_name))
        confirm_btn = box.addButton(t("common.confirm"), QMessageBox.AcceptRole)
        box.addButton(t("common.cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not confirm_btn:
            # 取消:下拉框回退,不保存任何改动
            self._lang_combo.blockSignals(True)
            self._lang_combo.setCurrentIndex(old_index)
            self._lang_combo.blockSignals(False)
            return

        self._settings.language = lang
        set_language(lang)
        self.changed.emit()

        # 第二段:用新语言提示,顺带预览新语言效果
        box2 = dialogs.message_box(self)
        box2.setWindowTitle(product_name())
        box2.setText(t("settings.lang_restart"))
        restart_btn = box2.addButton(t("common.restart_now"), QMessageBox.AcceptRole)
        box2.addButton(t("common.later"), QMessageBox.RejectRole)
        box2.exec()
        if box2.clickedButton() is restart_btn:
            restart_app()

    # ---- 工具 ----
    def _separator(self):
        """分区之间的细横线(不用文字标题,版面更干净)。"""
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255, 255, 255, 18);")
        return sep

    def _row_label(self, text):
        lbl = QLabel(text)
        # 字号跟随设置(与主界面一致),只固定灰色的次级文字色
        lbl.setStyleSheet("color: #8a8a94;")
        lbl.setFixedHeight(18)
        return lbl

    def _make_color_btn(self, color: QColor) -> QPushButton:
        return make_color_btn(color)

    def _paint_color_btn(self, btn: QPushButton, color: QColor):
        paint_color_btn(btn, color)

    def _emit_changed(self):
        """将当前 UI 状态写回 settings 并通知主窗口刷新。"""
        self._settings.bg_color = self._bg_color.name()
        self._settings.text_color = self._txt_color.name()
        if self._font_combo.currentText() in self._font_families:
            self._settings.font_family = self._font_combo.currentText()
        self._settings.font_size = self._size_spin.value()
        self._settings.bg_opacity = self._op_slider.value()
        self.changed.emit()

    # ---- 槽 ----
    def _pick_bg_color(self):
        color = self._show_color_dialog(
            QColor(self._settings.bg_color), t("settings.pick_bg"),
        )
        if color.isValid():
            self._bg_color = color
            self._paint_color_btn(self._bg_btn, color)
            self._mark_custom_preset()
            self._emit_changed()
        else:
            self.changed.emit()

    def _pick_text_color(self):
        color = self._show_color_dialog(
            QColor(self._settings.text_color), t("settings.pick_text"),
        )
        if color.isValid():
            self._txt_color = color
            self._paint_color_btn(self._txt_btn, color)
            self._mark_custom_preset()
            self._emit_changed()
        else:
            self.changed.emit()

    def _on_font_activated(self, family):
        if family in self._font_families:
            self._settings.font_family = family
            self.changed.emit()

    def _commit_font_text(self):
        family = self._font_combo.currentText().strip()
        match = next(
            (name for name in self._font_families if name.casefold() == family.casefold()),
            None,
        )
        self._font_combo.setCurrentText(match or self._settings.font_family)
        if match:
            self._settings.font_family = match
            self.changed.emit()

    def _on_size_changed(self, val):
        self._emit_changed()

    def _on_opacity_changed(self, val):
        self._op_label.setText(f"{int(val / 255 * 100)}%")
        self._emit_changed()

    def _apply_preset(self, preset):
        """一键应用预设主题。"""
        self._bg_color = QColor(preset["bg"])
        self._txt_color = QColor(preset["text"])
        self._paint_color_btn(self._bg_btn, self._bg_color)
        self._paint_color_btn(self._txt_btn, self._txt_color)
        self._font_combo.blockSignals(True)
        self._size_spin.blockSignals(True)
        self._op_slider.blockSignals(True)
        self._font_combo.setCurrentText(preset["font"])
        self._size_spin.setValue(preset["size"])
        self._op_slider.setValue(preset["opacity"])
        self._font_combo.blockSignals(False)
        self._size_spin.blockSignals(False)
        self._op_slider.blockSignals(False)
        self._op_label.setText(f"{int(preset['opacity'] / 255 * 100)}%")
        # 毛玻璃是一整套外观的一部分:选预设时把模糊开关也一起设好,
        # 否则换了配色还得自己再去勾一下(实底预设开着 blur 也看不出来)。
        self._set_blur_check(bool(preset.get("blur", False)))
        self._settings.appearance_preset = preset["name"]
        self._refresh_preset_selection()
        self.refresh_custom_colors()
        self._emit_changed()

    def _set_blur_check(self, checked):
        """同步毛玻璃勾选框与设置,信号要挡住,免得又走一次"标记自定义配色"。"""
        self._blur_check.blockSignals(True)
        self._blur_check.setChecked(checked)
        self._blur_check.blockSignals(False)
        self._settings.blur_behind = checked

    def _refresh_preset_selection(self):
        """把当前预设对应的圆点亮(自定义配色时亮最右边那个虚线圆)。"""
        current = self._settings.appearance_preset
        for name, btn in self._preset_btns.items():
            self._set_selected(btn, name == current)
        self._set_selected(self._custom_btn, current == CUSTOM_PRESET)

    @staticmethod
    def _set_selected(btn, selected):
        """动态属性驱动 QSS 高亮;值没变时不动,避免多余的样式重算。"""
        key = "true" if selected else "false"
        if btn.property("selected") == key:
            return
        btn.setProperty("selected", key)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _mark_custom_preset(self):
        """手改了背景/字体颜色 → 外观不再等于任何预设。"""
        if self._settings.appearance_preset != CUSTOM_PRESET:
            self._settings.appearance_preset = CUSTOM_PRESET
            self._refresh_preset_selection()

    # ---- 自定义配色窗口 ----
    def open_custom_colors(self):
        """打开自定义配色窗口(非模态,实时生效)。"""
        win = getattr(self, "_custom_win", None)
        if win is None:
            win = CustomColorWindow(self._settings, parent=self)
            win.changed.connect(self._on_custom_colors_changed)
            # 「恢复默认配色」要顺带把预设高亮还原,所以改走设置窗口这条路径
            win.reset_btn.clicked.disconnect()
            win.reset_btn.clicked.connect(self._restore_custom_preset)
            self._custom_win = win
        else:
            win.refresh()
        win.move(
            self.x() + max(0, (self.width() - win.width()) // 2),
            self.y() + max(0, (self.height() - win.height()) // 2),
        )
        win.show()
        win.raise_()
        win.activateWindow()

    def refresh_custom_colors(self):
        """外观被别处改动(换预设/恢复默认)后,把自定义配色窗口的色块同步过来。"""
        win = getattr(self, "_custom_win", None)
        if win is not None and win.isVisible():
            win.refresh()

    def _on_custom_colors_changed(self, bg: QColor, text: QColor):
        """自定义配色窗口改色:同步色块与预设高亮(设置已在那边写好)。

        「恢复默认配色」时不要标记成自定义——那一下恰好是回到默认预设,
        标记会让高亮与刚恢复的颜色对不上(用 _restoring_custom 短路)。
        """
        self._paint_color_btn(self._bg_btn, bg)
        self._paint_color_btn(self._txt_btn, text)
        if self._restoring_custom:
            self._refresh_preset_selection()
        else:
            self._mark_custom_preset()
        self.changed.emit()

    def _restore_custom_preset(self):
        """自定义配色窗口里的「恢复默认配色」:把颜色与预设高亮一起还原。

        必须从这里走:窗口只管把颜色发回来,「回到默认预设」这层语义
        只有设置窗口知道(见 _on_custom_colors_changed 里的短路说明)。
        """
        win = getattr(self, "_custom_win", None)
        if win is None:
            return
        self._restoring_custom = True
        try:
            win.restore_defaults()
        finally:
            self._restoring_custom = False
        self._refresh_preset_selection()
        self.changed.emit()

    def _restore_custom_colors(self):
        for index, color in enumerate(self._settings.custom_colors):
            if index < QColorDialog.customCount():
                QColorDialog.setCustomColor(index, QColor(color))

    def _show_color_dialog(self, initial, title):
        color = pick_color(initial, title, self)
        if color.isValid():
            self._remember_custom_colors()
        return color

    def _remember_custom_colors(self):
        self._settings.custom_colors = [
            QColorDialog.customColor(index).name()
            for index in range(QColorDialog.customCount())
            if QColorDialog.customColor(index).isValid()
        ]

    # ---- 初始化内部状态(从 settings 读取) ----
    @property
    def _bg_color(self):
        return QColor(self._settings.bg_color)

    @_bg_color.setter
    def _bg_color(self, c: QColor):
        self._settings.bg_color = c.name()

    @property
    def _txt_color(self):
        return QColor(self._settings.text_color)

    @_txt_color.setter
    def _txt_color(self, c: QColor):
        self._settings.text_color = c.name()
