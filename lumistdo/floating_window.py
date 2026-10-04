"""无边框浮动窗口的共享零件:羽化边缘、自绘关闭按钮、颜色按钮。

设置窗口、快捷键窗口、自定义配色窗口是同一套外观(无系统边框、圆角、
边缘向外虚化、右上角自绘 ×),这里放共用的画法,保证三个窗口不会各自漂移。
窗口背景本身走 app_settings.container_qss()。
"""

from PySide6.QtWidgets import QWidget, QPushButton
from PySide6.QtCore import Qt, Signal, QPoint, QRectF
from PySide6.QtGui import QColor, QCursor, QPainter, QPen, QPixmap

from .app_settings import Theme
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
