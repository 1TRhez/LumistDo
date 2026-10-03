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
from .app_settings import AppSettings, MAX_TITLE_LENGTH, MIN_BG_OPACITY
from .i18n import LANG_EN, LANG_ZH, product_name, set_language, t
from .restart import restart_app

# 设置窗口的外边距:留出羽化区域,与主界面一致
OUTER_MARGIN = 8
CONTAINER_RADIUS = 8.0
# 内容区宽度:底部三个按钮(保存预设/恢复默认/查看历史)要放得下,
# 300px 会把「保存为自定义预设」挤成省略号,这里留足 340px
CONTENT_WIDTH = 340

WINDOW_QSS = """
QLabel { color: #c8c8d2; }
QLabel#sectionTitle {
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
QRadioButton::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid rgba(255,255,255,40);
    border-radius: 8px;
    background: rgba(255,255,255,8);
}
QRadioButton::indicator:hover {
    border-color: #5ea0ff;
}
QRadioButton::indicator:checked {
    background: #5ea0ff;
    border: 4px solid rgba(30,31,36,255);
}
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

# 预设主题:每套包含 bg_color, text_color, font_family, font_size, bg_opacity
PRESETS = [
    {"name": "深空",   "bg": "#25262c", "text": "#e9e9ef", "font": "Segoe UI Variable", "size": 13, "opacity": 240},
    {"name": "暖夜",   "bg": "#2c2420", "text": "#f0e6dc", "font": "Microsoft YaHei UI", "size": 13, "opacity": 235},
    {"name": "森林",   "bg": "#1e2a22", "text": "#e4f0e8", "font": "Microsoft YaHei UI", "size": 13, "opacity": 238},
    {"name": "海洋",   "bg": "#1a2432", "text": "#dce8f4", "font": "Segoe UI Variable", "size": 13, "opacity": 240},
    {"name": "薰衣草", "bg": "#282430", "text": "#ece6f4", "font": "Microsoft YaHei UI", "size": 13, "opacity": 236},
    {"name": "素白",   "bg": "#f2f2f4", "text": "#2c2c32", "font": "Microsoft YaHei UI", "size": 13, "opacity": 248},
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


class ResetButton(QWidget):
    """自绘「恢复默认设置」图标按钮(圆形箭头,风格与其他图标按钮一致)。"""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(30, 30)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip(t("settings.reset_btn"))
        self._hover = False
        self._ink = QColor("#c8c8d2")

    def set_theme(self, theme):
        """跟随主题取图标颜色(与其他图标按钮同一套接口)。"""
        self._ink = QColor(theme.text_color)
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 18) if self._hover else QColor(255, 255, 255, 7))
        p.drawRoundedRect(QRectF(0.0, 0.0, 30.0, 30.0), 7.0, 7.0)
        color = self._ink.lighter(120) if self._hover else self._ink
        p.drawPixmap(0, 0, reset_glyph(30, color))
        p.end()


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


class CloseButton(QWidget):
    """自绘关闭按钮(替代系统标题栏的 ×)。"""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setToolTip(t("settings.close"))
        self._hover = False

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 30))
            p.drawRoundedRect(QRectF(0.0, 0.0, 24.0, 24.0), 6.0, 6.0)
        color = QColor("#e0e0e8") if self._hover else QColor("#9a9aa5")
        p.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPoint(9, 9), QPoint(15, 15))
        p.drawLine(QPoint(15, 9), QPoint(9, 15))
        p.end()


class SettingsWindow(QWidget):
    """外观设置独立窗口(非模态,实时预览)。"""

    changed = Signal()  # 任何设置变动时发出,主窗口据此实时刷新
    z_order_changed = Signal(bool)       # 置底开关:需即时改窗口层级,单独回传
    position_fixed_changed = Signal(bool)  # 固定开关:同样需即时生效
    taskbar_changed = Signal(bool)       # 任务栏图标开关:需即时改扩展样式
    autostart_changed = Signal(bool)     # 开机自启动:需即时写注册表
    title_changed = Signal(str)          # 顶部栏文字:需即时重排标题
    keybind_requested = Signal()         # 打开快捷键设置窗口
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
        for p in PRESETS:
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setToolTip(p["name"])
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  background: {p['bg']};"
                f"  border: 2px solid rgba(255,255,255,40);"
                f"  border-radius: 14px;"
                f"}}"
                f"QPushButton:hover {{"
                f"  border-color: #5ea0ff;"
                f"}}"
            )
            btn.clicked.connect(lambda checked=False, preset=p: self._apply_preset(preset))
            preset_row.addWidget(btn)
        preset_row.addStretch()
        root.addLayout(preset_row)

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
            f"QFrame#settingsContainer {{"
            f"  background: rgba({theme.bg_color.red()}, {theme.bg_color.green()},"
            f" {theme.bg_color.blue()}, {theme.bg_opacity});"
            f"  border: none;"
            f"  border-radius: {CONTAINER_RADIUS:g}px;"
            f"}}"
        )
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
        self._paint_edge_fade(p, QRectF(self.container.geometry()), theme)
        p.end()
        self._fade_pixmap = pm
        self._fade_key = key
        return pm

    def _paint_edge_fade(self, p, cr, theme):
        """容器边缘向外逐渐虚化:多层同心圆角矩形的环带,越外 alpha 越低。"""
        radius = CONTAINER_RADIUS
        fade = 7.0       # 虚化区域宽度(略小于 8px 外边距)
        layers = 14
        base = theme.edge_fade_color
        # 羽化强度随背景透明度等比缩放:低透明度时不再残留一圈可见薄雾
        fade_strength = theme.bg_opacity / 255.0
        p.setPen(Qt.NoPen)
        for i in range(layers, 0, -1):
            grow = fade * i / layers
            alpha = int(26 * fade_strength * (1.0 - (i - 1) / layers))
            if alpha <= 0:
                continue
            p.setBrush(QColor(base.red(), base.green(), base.blue(), alpha))
            p.drawRoundedRect(
                cr.adjusted(-grow, -grow, grow, grow), radius + grow, radius + grow,
            )
        # 环带之外不再有任何绘制:容器内部保持原样(透明度与设置值一致)

    # ---- 窗口层级(三选一,回传主窗口即时改层级)与固定 ----
    def _on_layer_selected(self, name, checked):
        """层级单选项被选中:写设置并把「置底」状态回传主窗口。

        置顶与置底互斥由单选的互斥性天然保证:选中一项即取消其余两项。
        """
        if not checked:
            return
        self._settings.always_on_top = name == "top"
        self._settings.always_on_bottom = name == "bottom"
        self.z_order_changed.emit(name == "bottom")
        self.changed.emit()

    def set_z_order_checks(self, layer=None, fixed=None):
        """主窗口改动层级/固定态后回同步(仅主窗口调用,防止回环)。

        layer 取 "top" / "bottom" / "normal",由主窗口直接给出 ——
        不再从 settings 反推,否则主窗口刚改完还没落盘的状态会同步错。
        """
        if layer is not None:
            radio = self._layer_radios.get(layer)
            if radio is not None and not radio.isChecked():
                radio.blockSignals(True)
                radio.setChecked(True)
                radio.blockSignals(False)
        if fixed is not None and self._fixed_check.isChecked() != fixed:
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
        self.set_z_order_checks("normal", False)
        self.set_taskbar_check(False)
        self.title_changed.emit(s.title_text)
        self.changed.emit()
        # 交给主窗口把缩略模式/隐藏清单/托盘图标这些界面状态一起收掉
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
        btn = QPushButton()
        btn.setObjectName("colorBtn")
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._paint_color_btn(btn, color)
        return btn

    def _paint_color_btn(self, btn: QPushButton, color: QColor):
        btn.setStyleSheet(
            f"QPushButton#colorBtn {{"
            f"  background: {color.name()};"
            f"  border: 1px solid rgba(255,255,255,30);"
            f"  border-radius: 6px;"
            f"  min-width: 60px; min-height: 26px;"
            f"}}"
        )

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
        self._emit_changed()

    def _restore_custom_colors(self):
        for index, color in enumerate(self._settings.custom_colors):
            if index < QColorDialog.customCount():
                QColorDialog.setCustomColor(index, QColor(color))

    def _show_color_dialog(self, initial, title):
        self._restore_custom_colors()
        dialog = QColorDialog(initial, self)
        dialog.setWindowTitle(title)
        dialog.setOption(QColorDialog.DontUseNativeDialog, True)
        accepted = dialog.exec()
        self._remember_custom_colors()
        return dialog.selectedColor() if accepted else QColor()

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
