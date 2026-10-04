"""可见背景外那一圈羽化(替代硬阴影)的绘制。

从卡片边缘向外画多层同心圆角矩形的"环带"(外扩矩形减去卡片矩形),越往外
alpha 越低,形成背景色→透明的柔和过渡。环带画法保证卡片内部不被叠加任何
颜色,透明度与滑杆值一致。

主窗口那圈羽化由光环窗口 `edge_halo.EdgeHalo` 画(它比窗口四周各宽这么一圈)——
糊区永远是整个窗口矩形,所以卡片永远铺满窗口,窗口里没有落脚处画羽化。设置窗口、
历史窗口这些浮动面板则在窗口内自己留白、自己画这一圈。
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath

RADIUS = 8.0   # 卡片圆角
FADE = 7.0     # 羽化宽度(略小于 8px 外边距,最外一像素留空)
LAYERS = 14


def paint_edge_fade(painter, card_rect: QRectF, theme):
    """把 card_rect 外圈的羽化环带画到 painter 上(内部不着色)。"""
    cr = QRectF(card_rect)
    base = theme.edge_fade_color
    # 羽化强度随背景透明度等比缩放:低透明度时不再残留一圈可见薄雾
    strength = theme.bg_opacity / 255.0
    inner = QPainterPath()
    inner.addRoundedRect(cr, RADIUS, RADIUS)
    painter.setPen(Qt.NoPen)
    for i in range(LAYERS, 0, -1):
        expand = FADE * i / LAYERS
        # 越贴近卡片边缘越不透明,最外层趋近全透明
        alpha = int(56 * strength * (1.0 - (i - 1) / LAYERS))
        rect = cr.adjusted(-expand, -expand, expand, expand)
        r = RADIUS + expand
        ring = QPainterPath()
        ring.addRoundedRect(rect, r, r)
        painter.setBrush(QColor(base.red(), base.green(), base.blue(), alpha))
        painter.drawPath(ring.subtracted(inner))
