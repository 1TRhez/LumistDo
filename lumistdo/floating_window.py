"""无边框浮动窗口的共享零件:面板基类、羽化边缘、自绘关闭按钮、颜色按钮。

设置窗口、快捷键窗口、历史任务窗口、自定义配色窗口是同一套外观(无系统边框、
圆角、边缘向外虚化、右上角自绘 ×、跟随主题),这里放共用的画法,保证它们不会
各自漂移。窗口背景本身走 app_settings.container_qss()。
"""

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt, Signal, QPoint, QRectF
from PySide6.QtGui import (
    QColor, QCursor, QFont, QFontMetrics, QPainter, QPen, QPixmap,
)

from .app_settings import Theme, container_qss
from .i18n import t

# 浮动窗口统一的外边距(留出羽化区域)与容器圆角
OUTER_MARGIN = 8
CONTAINER_RADIUS = 8.0
FADE_WIDTH = 7.0    # 虚化区域宽度,略小于外边距
FADE_LAYERS = 14


def paint_edge_fade(p, cr: QRectF, theme: Theme, radius=CONTAINER_RADIUS,
                    fade=FADE_WIDTH, layers=FADE_LAYERS):
    """把容器边缘向外画成逐渐虚化的环带(多层同心圆角矩形)。

    环带之外不再有任何绘制:容器内部保持原样,透明度与设置值一致。
    羽化强度随背景透明度等比缩放,低透明度时不会残留一圈可见薄雾。
    """
    strength = theme.bg_opacity / 255.0
    base = theme.edge_fade_color
    p.setPen(Qt.NoPen)
    for i in range(layers, 0, -1):
        grow = fade * i / layers
        alpha = int(255 * (1.0 - i / layers) ** 2 * strength)
        if alpha <= 0:
            continue
        p.setBrush(QColor(base.red(), base.green(), base.blue(), alpha))
        p.drawRoundedRect(
            cr.adjusted(-grow, -grow, grow, grow), radius + grow, radius + grow,
        )


def paint_color_btn(btn: QPushButton, color: QColor):
    """把一个按钮画成纯色块(设置窗口与自定义配色窗口共用)。"""
    # 动态属性留个查询口:测试与调试可以按色块当前颜色断言,不用解析样式表
    btn.setProperty("color", color.name())
    btn.setStyleSheet(
        f"QPushButton#colorBtn {{"
        f"  background: {color.name()};"
        f"  border: 1px solid rgba(255,255,255,30);"
        f"  border-radius: 6px;"
        f"  min-width: 60px; min-height: 26px;"
        f"}}"
    )


def make_color_btn(color: QColor) -> QPushButton:
    """新建一个色块按钮(已按 color 上色)。"""
    btn = QPushButton()
    btn.setObjectName("colorBtn")
    btn.setCursor(QCursor(Qt.PointingHandCursor))
    paint_color_btn(btn, color)
    return btn


def custom_preset_glyph(size):
    """画「自定义配色」的图标:背景色块上压一个前景色小方块。

    画成两色叠块而不是调色盘,一眼能看出"自己挑背景+字体颜色"。
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 16.0, size / 16.0)
    p.setPen(Qt.NoPen)
    # 背景块(大)
    p.setBrush(QColor("#6b7280"))
    p.drawRoundedRect(QRectF(1.6, 1.6, 10.4, 10.4), 2.0, 2.0)
    # 字体颜色块(小,右下角,描一圈深边保证在浅色块上也看得见)
    p.setBrush(QColor("#e9e9ef"))
    p.drawRoundedRect(QRectF(6.6, 6.6, 7.8, 7.8), 1.8, 1.8)
    p.setPen(QPen(QColor("#3a3f4b"), 1.0))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(6.6, 6.6, 7.8, 7.8), 1.8, 1.8)
    p.end()
    return pm


def clamp_to_screen(widget):
    """把窗口挪回屏幕可用区域,避免底部（按钮条）落在屏幕外点不到。

    设置窗口这类浮动窗口是按"贴着主窗口居中"摆的:主窗口靠屏幕下方时,
    窗口会有一截跑到屏幕外。内容比屏幕还高时也别切掉顶部——顶栏有拖动热区,
    放回上边缘至少还能拖。
    """
    screen = widget.screen()
    if screen is None:
        return
    area = screen.availableGeometry()
    size = widget.size()
    x = min(max(widget.x(), area.left()), max(area.left(), area.right() - size.width() + 1))
    y = min(max(widget.y(), area.top()), max(area.top(), area.bottom() - size.height() + 1))
    if (x, y) != (widget.x(), widget.y()):
        widget.move(x, y)


def _qss_rgb(color: QColor) -> str:
    """QColor → QSS 可用的 `rgb(r, g, b)`。"""
    return f"rgb({color.red()}, {color.green()}, {color.blue()})"


def panel_widgets_qss(theme: Theme) -> str:
    """浮动窗口里通用控件(标签/输入框/下拉/滑块/勾选)的配色。

    全部按主题明暗生成。以前这里是写死的白 alpha 叠加:深色背景上没问题,
    浅色背景(素白 `#f2f2f4`)上等于什么都看不见 —— 文字、滑轨、输入框边框全糊掉。
    """
    text = _qss_rgb(theme.text_color)
    accent = _qss_rgb(theme.accent_color)
    title = _qss_rgb(theme.fixed_title_color)
    if theme.is_dark:
        inset = "rgba(255, 255, 255, 8)"
        inset_hover = "rgba(255, 255, 255, 16)"
        border = "rgba(255, 255, 255, 24)"
        ring = "rgba(255, 255, 255, 45)"
        groove = "rgba(255, 255, 255, 38)"
        menu_bg = "#282930"
        menu_sel = "rgba(94, 160, 255, 90)"
    else:
        inset = "rgba(0, 0, 0, 7)"
        inset_hover = "rgba(0, 0, 0, 14)"
        border = "rgba(0, 0, 0, 32)"
        ring = "rgba(0, 0, 0, 60)"
        groove = "rgba(0, 0, 0, 48)"
        menu_bg = "#ffffff"
        menu_sel = accent
    return (
        f"QLabel {{ color: {text}; }}"
        f"QLabel#sectionTitle {{ color: {title}; font-weight: 700;"
        "  letter-spacing: 1.5px; }"
        # 色块按钮(背景色/字体颜色):底色由代码自己填,这里只留边框
        f"QPushButton#colorBtn {{ border: 1px solid {border};"
        "  border-radius: 6px; min-width: 60px; min-height: 26px; }"
        f"QPushButton#actionBtn {{ background: {inset};"
        f"  border: 1px solid {border}; border-radius: 7px; color: {text};"
        "  padding: 6px 16px; }"
        f"QPushButton#actionBtn:hover {{ background: {inset_hover};"
        f"  border-color: {accent}; }}"
        f"QPushButton#actionBtn:disabled {{ background: {inset};"
        f"  color: {title}; border-color: {border}; }}"
        f"QPushButton#iconBtn {{ background: {inset};"
        f"  border: 1px solid {border}; border-radius: 7px; color: {text};"
        "  padding: 0; }"
        f"QPushButton#iconBtn:hover {{ background: {inset_hover}; }}"
        f"QLineEdit {{ background: {inset}; border: 1px solid {border};"
        f"  border-radius: 6px; color: {text};"
        f"  selection-background-color: {accent}; }}"
        f"QLineEdit:focus {{ border-color: {accent}; }}"
        f"QSpinBox {{ background: {inset}; border: 1px solid {border};"
        f"  border-radius: 6px; color: {text}; padding: 3px 6px; }}"
        "QSpinBox::up-button, QSpinBox::down-button { width: 16px; }"
        f"QComboBox {{ background: {inset}; border: 1px solid {border};"
        f"  border-radius: 6px; color: {text}; min-height: 28px;"
        "  padding: 2px 8px; }"
        f"QComboBox QAbstractItemView {{ background: {menu_bg};"
        f"  border: 1px solid {border}; color: {text};"
        f"  selection-background-color: {menu_sel}; }}"
        f"QSlider::groove:horizontal {{ height: 4px; background: {groove};"
        "  border-radius: 2px; }"
        f"QSlider::sub-page:horizontal {{ background: {accent};"
        "  border-radius: 2px; }"
        f"QSlider::handle:horizontal {{ width: 14px; height: 14px;"
        f"  margin: -5px 0; background: {accent}; border-radius: 7px; }}"
        f"QCheckBox {{ color: {text}; spacing: 8px; }}"
        f"QCheckBox::indicator {{ width: 15px; height: 15px;"
        f"  border: 1px solid {ring}; border-radius: 4px;"
        f"  background: {inset}; }}"
        f"QCheckBox::indicator:hover {{ border-color: {accent}; }}"
        f"QCheckBox::indicator:checked {{ background: {accent};"
        f"  border-color: {accent}; }}"
        f"QRadioButton {{ color: {text}; spacing: 8px; }}"
        # 单选圆点的形状由 app_settings.radio_qss(theme) 给,这里只管文字色
        f"QFrame#panelSep {{ background: {border}; border: none;"
        "  max-height: 1px; }"
        "QFrame#settingsContainer { border: none; }"
    )


def panel_chrome_qss(theme: Theme) -> str:
    """浮动窗口标题条与提示文字的配色。

    这两个灰要跟着背景明暗走:写死 `#9a9aa5` 在浅色主题(素白)上等于看不见。
    用与主窗口标题/页脚同一套派生色(fixed_title_color / fixed_footer_color)。
    """
    title = theme.fixed_title_color
    hint = theme.fixed_footer_color
    return (
        "QLabel#windowTitle {"
        f"  color: rgb({title.red()}, {title.green()}, {title.blue()});"
        "  font-size: 12px;"
        "  font-weight: 700;"
        "  letter-spacing: 2.0px;"
        "}"
        "QLabel#hintLabel {"
        f"  color: rgb({hint.red()}, {hint.green()}, {hint.blue()});"
        "}"
    )


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


class FloatingHeader(QWidget):
    """浮动窗口顶部条:标题 + 自绘关闭按钮,空白处可按住拖动整个窗口。

    标题统一转大写并按可用宽度省略(窄窗口时不会把关闭按钮顶出去)。
    """

    def __init__(self, window, title="", parent=None, spacing=8):
        super().__init__(parent)
        self._window = window
        self._raw_title = ""
        self._drag_pos = None
        self.setCursor(QCursor(Qt.ArrowCursor))

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing)

        self.title_label = QLabel()
        self.title_label.setObjectName("windowTitle")
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.title_label.setMinimumWidth(0)
        row.addWidget(self.title_label, 1)

        self.close_btn = CloseButton(self)
        self.close_btn.clicked.connect(self._window.close)
        row.addWidget(self.close_btn, 0)

        self.set_title(title)

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
            metrics.elidedText(
                self._raw_title, Qt.ElideRight, self.title_label.width(),
            ),
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide_title()

    # ---- 空白处按住可拖动窗口 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint()
                - self._window.frameGeometry().topLeft()
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


class FloatingPanel(QWidget):
    """无边框半透明浮动面板:圆角容器 + 羽化边缘 + 跟随主题,各浮动窗口的基类。

    子类在 `_build_ui()` 里往 `self.body` 加内容;需要自己的样式表就覆写
    `_panel_qss(theme)`,需要按主题刷图标就覆写 `on_theme_applied()`。
    """

    def __init__(self, settings, parent=None, title="", width=None):
        super().__init__(parent)
        self._settings = settings
        self._fade_pixmap = None
        self._fade_key = None

        self.setWindowFlags(
            Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        if width is not None:
            self.setFixedWidth(width + OUTER_MARGIN * 2)

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

        self.header = FloatingHeader(self, title, self)
        self.header.setFixedHeight(26)
        root.addWidget(self.header)

        # 子类往这里加内容(在顶部条之后)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(10)
        root.addLayout(self.body)

    # ---- 外观:所有浮动窗口同一套(背景/透明度/字体/羽化) ----
    def _panel_qss(self, theme: Theme) -> str:
        """子类自己的样式表;默认没有。"""
        return ""

    def on_theme_applied(self, theme: Theme):
        """子类按主题刷自绘图标/色块用;默认什么都不做。"""

    def apply_theme(self):
        theme = self._settings.to_theme()
        self.container.setStyleSheet(
            container_qss(theme, "QFrame#settingsContainer", CONTAINER_RADIUS),
        )
        self.setStyleSheet(self._panel_qss(theme))
        self.setFont(QFont(theme.font_family, 10))
        self.on_theme_applied(theme)
        self._fade_pixmap = None
        self._fade_key = None
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        # 这些窗口是按"贴着主窗口居中"摆的,主窗口靠屏幕下方时会落到屏幕外
        clamp_to_screen(self)

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
        """与主界面同一套羽化画法(见 paint_edge_fade)。"""
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
