"""主窗口那圈"羽化光环"的窗口(羽化画在窗口外面)。

DWM 的 blur-behind 糊的永远是**整个窗口矩形**,而且裁不小:实测 `SetWindowRgn`
裁不住、`DwmEnableBlurBehindWindow` 的模糊区域返回 S_OK 却没反应、它连窗口自己
的 alpha 都不看。所以卡片只能铺满窗口去对齐糊区(糊区即卡片,开关毛玻璃尺寸
不变),而羽化那一圈必须画在窗口外面 —— 窗口里没有落脚处。

这个窗口就是那一圈:比主窗口四周各宽 8px,只在卡片外侧那圈环带里上色,中间
完全透明。它是主窗口的附属窗口(`Qt.Tool` + 有 parent,Windows 上是 owned
window),所以:

- 永远贴在主窗口上方,主窗口升降层时跟着走,不用自己管 z-order;
- 不进任务栏、不进 Alt+Tab;
- `WindowTransparentForInput` + `WA_TransparentForMouseEvents`,鼠标事件全穿过去;
- `WindowDoesNotAcceptFocus` + `WA_ShowWithoutActivating`,显示时不抢焦点。

`follow()` 由主窗口在移动/缩放/显示时调用 —— 必须**同步**调用,晚一个事件循环
就是拖动时光环落在卡片后面。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from .edge_fade import paint_edge_fade


class EdgeHalo(QWidget):
    def __init__(self, parent, theme, margin: int = 8):
        super().__init__(
            parent,
            Qt.Window
            | Qt.FramelessWindowHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
            | Qt.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setObjectName("edgeHalo")
        self._theme = theme
        self._margin = margin
        self._pixmap = None
        self._key = None

    # ---- 由主窗口调用 ----
    def set_theme(self, theme):
        if theme is self._theme:
            return
        self._theme = theme
        self._pixmap = None
        self._key = None
        self.update()

    def follow(self, card_geo, margin: int = None):
        """把光环摆到卡片四周各外扩 margin 的位置(card_geo 是全局坐标)。"""
        if margin is not None:
            self._margin = margin
        m = self._margin
        self.setGeometry(card_geo.adjusted(-m, -m, m, m))

    # ---- 绘制 ----
    def _halo_pixmap(self):
        key = (self.width(), self.height(), id(self._theme), self._margin)
        if self._pixmap is not None and self._key == key:
            return self._pixmap
        dpr = self.devicePixelRatioF() or 1.0
        pm = QPixmap(int(self.width() * dpr), int(self.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        m = self._margin
        paint_edge_fade(
            p,
            self.rect().adjusted(m, m, -m, -m),
            self._theme,
        )
        p.end()
        self._pixmap = pm
        self._key = key
        return pm

    def paintEvent(self, event):
        if self.width() <= 0 or self.height() <= 0:
            return
        p = QPainter(self)
        p.drawPixmap(0, 0, self._halo_pixmap())
        p.end()
