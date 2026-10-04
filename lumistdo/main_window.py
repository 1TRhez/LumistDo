"""主窗口:半透明、无边框、普通层级的桌面便签。"""

import math
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    _user32 = ctypes.WinDLL("user32")
    # 必须声明 argtypes:HWND_TOPMOST(-1)/HWND_NOTOPMOST(-2) 是 64 位
    # 指针宽度的哨兵值,不声明时 ctypes 按 32 位 int 传递,高字节
    # 为垃圾值,调用会静默失败(置顶不生效/取消不掉)。
    _user32.SetWindowPos.restype = ctypes.c_int
    _user32.SetWindowPos.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        ctypes.c_uint,
    ]
    # 读写扩展样式用 SetWindowLongPtrW(64 位下 GetWindowLongW 对 exstyle 够用,
    # 但 SetWindowLongPtrW 在 32/64 位都正确,统一用它避免截断)。
    _set_window_long = getattr(_user32, "SetWindowLongPtrW", None) or _user32.SetWindowLongW
    _set_window_long.restype = ctypes.c_void_p
    _set_window_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    _get_window_long = getattr(_user32, "GetWindowLongPtrW", None) or _user32.GetWindowLongW
    _get_window_long.restype = ctypes.c_void_p
    _get_window_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
else:
    _user32 = None
    wintypes = None
    _set_window_long = None
    _get_window_long = None

# SetWindowPos 的层级哨兵值:置顶/取消置顶用 ±1,置底用 HWND_BOTTOM。
# 三个都是指针宽度的值,必须配上面的 argtypes 才能正确传递。
HWND_TOPMOST, HWND_NOTOPMOST, HWND_BOTTOM = -1, -2, 1
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x1, 0x2, 0x10
SWP_NOZORDER, SWP_FRAMECHANGED = 0x4, 0x20
# WS_EX_TOOLWINDOW 让窗口不占任务栏按钮与 Alt+Tab 列表;
# WS_EX_APPWINDOW 必须一起清掉,否则它的优先级更高,按钮还在。
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x00000080, 0x00040000

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea, QFrame,
    QApplication, QMenu, QGraphicsOpacityEffect, QAbstractButton, QSizePolicy,
)
from PySide6.QtCore import (
    Qt, QEvent, QSize, QPoint, QPointF, QRect, Signal, QRectF, QPropertyAnimation,
    QEasingCurve, QTimer,
)
from PySide6.QtGui import (
    QCursor, QPixmap, QPainter, QPainterPath, QColor, QIcon, QFont, QPen,
    QShortcut, QKeySequence,
)

from .i18n import product_name, t
from .task_store import TaskStore
from .task_item import TaskItem
from .completed_panel import CompletedPanel
from .app_paths import SETTINGS_FILE
from .app_settings import AppSettings, Theme
from .settings_dialog import SettingsWindow
from .keybind_window import KeybindWindow
from .history_window import HistoryWindow
from .tray_icon import TrayIcon
from .blur_behind import apply_to_widget
from .edge_halo import EdgeHalo
from . import autostart
from . import global_hotkeys

PANEL_MARGIN = 8    # 羽化环带的宽度:光环窗口比窗口四周各宽这么多
PANEL_RADIUS = 8    # 容器圆角(糊区永远是窗口矩形,四角那点残糊见 _apply_blur_behind)


def build_qss(t: Theme, radius: int = PANEL_RADIUS) -> str:
    """根据主题动态生成 QSS。

    radius 是容器圆角,默认 PANEL_RADIUS。开毛玻璃时**不**把它压成 0:
    模糊区永远是整个窗口矩形、裁不住也圆不了,但容器铺满窗口后,糊区与
    可见背景本来就同大,圆角只会在四个角留下约 14 平方像素的残糊 ——
    比"直角面板"划算得多(详见 MainWindow._apply_blur_behind)。
    """
    bg = t.bg_color
    # 背景用垂直渐变(三档停靠点,见 app_settings.container_qss 的说明):
    # 两档渐变要跨满整个窗口高度,8bit 量化下会出现一条条水平色带。
    op = t.bg_opacity
    sep = t.sep_color
    sb = t.scrollbar_color
    sbh = t.scrollbar_hover_color
    txt = t.text_color
    ico = t.icon_color
    ico_h = t.icon_hover_color
    hl = t.highlight_color
    acc = t.accent_color

    return f"""
QFrame#container {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba({t.bg_top_color.red()}, {t.bg_top_color.green()}, {t.bg_top_color.blue()}, {t.bg_top_color.alpha()}),
        stop:0.45 rgba({bg.red()}, {bg.green()}, {bg.blue()}, {op}),
        stop:1 rgba({t.bg_bottom_color.red()}, {t.bg_bottom_color.green()}, {t.bg_bottom_color.blue()}, {t.bg_bottom_color.alpha()}));
    border: none;
    border-radius: {radius}px;
}}
QFrame#sectionSep {{
    background: rgba({sep.red()}, {sep.green()}, {sep.blue()}, {sep.alpha()});
    border: none;
    max-height: 1px;
}}
QLabel {{ color: {txt.name()}; font-size: {t.font_size}px; font-family: "{t.font_family}"; }}
QStackedWidget#taskStack {{ background: transparent; }}
QLabel#taskText {{
    background: transparent;
    border: none;
    color: {txt.name()};
    font-size: {t.font_size}px;
    font-family: "{t.font_family}";
    padding: 0px;
}}
QPlainTextEdit#taskEdit {{
    background: rgba({hl.red()},{hl.green()},{hl.blue()},12);
    border: 1px solid rgba({acc.red()}, {acc.green()}, {acc.blue()}, 140);
    border-radius: 8px;
    color: {txt.name()};
    font-size: {t.font_size}px;
    font-family: "{t.font_family}";
    padding: 5px 7px;
}}
QLabel#titleLabel {{
    color: {t.fixed_title_color.name()};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2.5px;
    font-family: "Segoe UI Variable";
}}
QPushButton {{ color: {txt.name()}; background: transparent; border: none; }}
QPushButton#inlineAddBtn {{
    color: rgba({ico.red()}, {ico.green()}, {ico.blue()}, 215);
    background: transparent;
    border: none;
    border-radius: 9px;
    font-size: 20px;
    font-weight: 600;
    text-align: left;
    padding: 5px 0 5px 16px;
}}
QPushButton#inlineAddBtn:hover {{
    color: {acc.name()};
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {hl.alpha()});
}}
QPushButton#footerBtn {{
    color: {t.fixed_footer_color.name()};
    font-family: "Microsoft YaHei UI";
    text-align: left;
    border: none;
    padding: 9px 0 10px 14px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QPushButton#footerBtn:hover {{ color: #d0d0d8; }}
QPushButton#settingsBtn {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 4px;
}}
QPushButton#settingsBtn:hover {{
    background: rgba({hl.red()}, {hl.green()}, {hl.blue()}, {hl.alpha() + 4});
}}
QFrame#footerBar {{
    border-top: 1px solid rgba({sep.red()}, {sep.green()}, {sep.blue()}, {sep.alpha()});
    background: transparent;
}}
QScrollArea#listScroll {{ border: none; background: transparent; }}
QScrollArea#listScroll viewport {{ background: transparent; }}
QWidget#listWidget {{ background: transparent; }}
QLabel#emptyHint {{
    color: rgba({ico.red()}, {ico.green()}, {ico.blue()}, 110);
    font-size: 11px;
    padding: 6px 16px 0 16px;
}}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 6px 0; }}
QScrollBar::handle:vertical {{
    background: rgba({sb.red()},{sb.green()},{sb.blue()},{sb.alpha()});
    border-radius: 2px;
    min-height: 24px;
    margin: 0 3px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba({sbh.red()},{sbh.green()},{sbh.blue()},{sbh.alpha()});
    border-radius: 3px;
    margin: 0 1px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""

EDGE = 10           # 边 resize 检测宽度(匹配 8px 外边距)
CORNER = 14         # 角 resize 检测范围(缩小避免与右下角设置按钮重叠)
MIN_W, MIN_H = 220, 200
PANEL_H = 160       # 已完成面板展开时向下扩展的高度
# 清单区域"展开"时的高度上限。清单从不真的 setVisible(False)(见 _set_widget_shown),
# 而是把高度在 0 与这个上限之间切换 —— 上限取得比任何真实窗口都大,等于不限制。
SCROLL_MAX_H = 16777215


def _on_segment(a: QPointF, b: QPointF, dist: float) -> QPointF:
    """从 a 沿 a→b 方向取距离 dist 的点(螺母图标削角/凹曲线用)。"""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy)
    if length == 0:
        return QPointF(a)
    return QPointF(a.x() + dx / length * dist, a.y() + dy / length * dist)




class CompactButton(QWidget):
    """缩略模式按钮:开启后窗口只留任务列表(顶栏渐隐)。

    图标是一把"缩小"的锁:紧凑态高亮,且锁体比展开态明显小一圈。
    换过几种画法都不如它一眼能认,所以保留锁形,只把尺寸缩小来表达"变小"。
    """

    toggled = Signal(bool)

    def __init__(self, compact=False, parent=None):
        super().__init__(parent)
        self._compact = compact
        self._shortcut = ""
        self._color = QColor("#8e9099")
        self._accent = QColor("#5ea0ff")
        self._sync_tooltip()

    def set_theme(self, theme: Theme):
        self._color = theme.icon_color
        self._accent = theme.accent_color
        self.update()

    def set_compact(self, compact):
        self._compact = compact
        self._sync_tooltip()
        self.update()

    def set_shortcut(self, text):
        """由快捷键设置窗口回填,显示在 tooltip 里。"""
        self._shortcut = f" ({text})" if text else ""
        self._sync_tooltip()

    def _sync_tooltip(self):
        action = t("main.compact_action_on") if self._compact else t(
            "main.compact_action_off",
        )
        self.setToolTip(f"{action}{self._shortcut}")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        compact = self._compact
        color = self._accent if compact else self._color
        pen = QPen(color, 1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        # 整把锁按比例缩小,而不是只缩锁体:缩略模式下图标明确小一圈,
        # 与"窗口变小"的语义对齐,同时仍保留锁形的辨识度。
        scale = 0.74 if compact else 1.0
        p.save()
        p.translate(14.0, 14.0)
        p.scale(scale, scale)
        p.translate(-14.0, -14.0)

        body = QRectF(6.5, 14.0, 15.0, 10.5)
        center_x = 14.0
        body_top = 14.0
        p.drawRoundedRect(body, 2.2, 2.2)

        # 锁孔:圆点 + 短竖槽(跟随锁体缩放)
        hole_y = body.center().y()
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(QPointF(center_x, hole_y - 0.4), 1.2, 1.2)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        p.drawLine(QPointF(center_x, hole_y + 0.9), QPointF(center_x, hole_y + 1.9))

        # 锁梁:锁上=居中扣在锁体上;开锁=整体向右平移错开锁体。
        # (真实挂锁是锁梁绕腿轴前后甩开的三维动作,二维图标画不出深度旋转,
        #  用左右平移来表现这个"甩出"——锁梁错开锁体即表示已开。)
        lift = 3.8
        span = 8.0
        left = center_x - span / 2
        shift = 0.0 if compact else 5.0
        shackle = QPainterPath()
        shackle.moveTo(left + shift, body_top)
        shackle.lineTo(left + shift, body_top - lift)
        shackle.arcTo(
            QRectF(left + shift, body_top - lift - span / 2, span, span),
            180.0, -180.0,
        )
        shackle.lineTo(left + shift + span, body_top)
        p.drawPath(shackle)
        p.restore()
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggled.emit(not self._compact)

class PinButton(QWidget):
    """图钉按钮:点击在 置底 -> 普通 -> 置顶 三态间循环。

    置顶竖立并高亮,普通倾斜置灰,置底再翻 180 度(针尖朝下)。
    """

    toggled = Signal(str)

    def __init__(self, mode="normal", parent=None):
        super().__init__(parent)
        self._mode = mode if mode in ("top", "normal", "bottom") else "normal"
        self._shortcut = ""
        self._color = QColor("#8e9099")
        self._accent = QColor("#5ea0ff")
        self._sync_tooltip()

    def set_theme(self, theme: Theme):
        self._color = theme.icon_color
        self._accent = theme.accent_color
        self.update()

    def set_mode(self, mode):
        self._mode = mode if mode in ("top", "normal", "bottom") else "normal"
        self._sync_tooltip()
        self.update()

    def set_shortcut(self, text):
        """由快捷键设置窗口回填,显示在 tooltip 里。"""
        self._shortcut = f" ({text})" if text else ""
        self._sync_tooltip()

    def _sync_tooltip(self):
        key = {
            "top": "main.pin_tooltip_on",
            "normal": "main.pin_tooltip_mid",
            "bottom": "main.pin_tooltip_off",
        }[self._mode]
        self.setToolTip(t(key, sc=self._shortcut))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = self._accent if self._mode == "top" else self._color
        pen = QPen(color, 1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.save()
        p.translate(14.0, 14.0)
        if self._mode == "normal":
            p.rotate(45.0)    # 普通层级:图钉倾斜,表示"没钉住"
        elif self._mode == "bottom":
            p.rotate(180.0)   # 置底:针尖朝下
        # 图钉头:上方小倒三角 + 下方大正三角,两角在交接处大幅重叠。
        # 沿融合后的外轮廓一笔画出,重叠区不显示内部轮廓:
        # (±1.47,-2.1) 是两个三角形侧边的交点,小三角尖角深伸至大三角近底部。
        head = QPainterPath()
        head.moveTo(-3.2, -7.5)
        head.lineTo(3.2, -7.5)
        head.lineTo(1.47, -2.1)    # 小三角右缘下行至重叠交点
        head.lineTo(5.2, 4.0)      # 接大三角右缘下行至底角
        head.lineTo(-5.2, 4.0)
        head.lineTo(-1.47, -2.1)   # 大三角左缘上行至重叠交点
        head.closeSubpath()        # 闭合回起点(小三角左缘)
        p.drawPath(head)
        p.drawLine(QPointF(0.0, 4.0), QPointF(0.0, 8.5))
        p.restore()
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            order = ("top", "bottom", "normal")
            nxt = order[(order.index(self._mode) + 1) % len(order)]
            self.toggled.emit(nxt)


class FixedButton(QWidget):
    """固定按钮:钉住窗口位置(禁止拖动与缩放),再按解除。固定态高亮。"""
    toggled = Signal(bool)

    def __init__(self, fixed=False, parent=None):
        super().__init__(parent)
        self._fixed = fixed
        self._shortcut = ""
        self._color = QColor("#8e9099")
        self._accent = QColor("#5ea0ff")
        self._sync_tooltip()

    def set_theme(self, theme: Theme):
        self._color = theme.icon_color
        self._accent = theme.accent_color
        self.update()

    def set_fixed(self, fixed):
        self._fixed = fixed
        self._sync_tooltip()
        self.update()

    def set_shortcut(self, text):
        """由快捷键设置窗口回填,显示在 tooltip 里。"""
        self._shortcut = f" ({text})" if text else ""
        self._sync_tooltip()

    def _sync_tooltip(self):
        key = (
            "main.fixed_tooltip_on" if self._fixed else "main.fixed_tooltip_off"
        )
        self.setToolTip(t(key, sc=self._shortcut))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = self._accent if self._fixed else self._color
        pen = QPen(color, 1.7)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        # 十字锚点表示"可以挪位置";固定后叠一道斜杠(=失效,与眼睛的斜杠同一语言)
        for a, b in (
            ((14.0, 6.2), (14.0, 10.6)), ((14.0, 17.4), (14.0, 21.8)),
            ((6.2, 14.0), (10.6, 14.0)), ((17.4, 14.0), (21.8, 14.0)),
        ):
            p.drawLine(QPointF(*a), QPointF(*b))
        p.setBrush(color)
        p.drawEllipse(QPointF(14.0, 14.0), 1.6, 1.6)
        if self._fixed:
            p.setBrush(Qt.NoBrush)
            # 斜杠中点避开中心圆点,两段分开画
            p.drawLine(QPointF(5.6, 22.4), QPointF(11.2, 16.8))
            p.drawLine(QPointF(16.8, 11.2), QPointF(22.4, 5.6))
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.toggled.emit(not self._fixed)


class HeaderBar(QFrame):
    """上方栏:标题、图标按钮、空白拖动区域及右键菜单。"""

    clicked = Signal()  # 顶栏被点击:缩略模式下用来把界面临时唤回来

    def __init__(self, window):
        super().__init__()
        self._window = window

        hl = QHBoxLayout(self)
        hl.setContentsMargins(16, 6, 12, 6)
        hl.setSpacing(7)
        # 固定高度:顶栏渐隐时布局不塌缩
        self.setFixedHeight(6 + 28 + 6)

        self.title_label = QLabel()
        self.title_label.setObjectName("titleLabel")
        self.title_label.setTextFormat(Qt.PlainText)  # 用户自定义文字,不当富文本解析
        # 弹性宽度:窗口窄时先压缩标题,页面撑到最小也不会顶掉右侧图标
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.title_label.setMinimumWidth(0)
        hl.addWidget(self.title_label, 1)
        self._raw_title = t("main.title_default")
        self.set_title(self._raw_title)

        # 顺序:图钉(层级三态) → 固定(钉住位置) → 缩略模式
        self.pin_btn = PinButton(parent=self)
        self.pin_btn.setFixedSize(28, 28)
        self.pin_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.pin_btn.toggled.connect(lambda mode: window.cycle_z_order(mode))
        hl.addWidget(self.pin_btn)

        self.fixed_btn = FixedButton(parent=self)
        self.fixed_btn.setFixedSize(28, 28)
        self.fixed_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.fixed_btn.toggled.connect(lambda f: window.set_position_fixed(f))
        hl.addWidget(self.fixed_btn)

        self.compact_btn = CompactButton(parent=self)
        self.compact_btn.setFixedSize(28, 28)
        self.compact_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.compact_btn.toggled.connect(lambda c: window.set_compact_mode(c))
        hl.addWidget(self.compact_btn)

    def set_title(self, text):
        """设置顶部栏文字(过长时按实际可用宽度省略,不挤掉右侧按钮)。

        传空字符串表示不显示标题,右侧图标按钮照常工作。
        """
        self._raw_title = (text or "").strip()
        # 拉丁字母统一大写,保持原有 JUST DO IT. 的设计语气;中日韩文字不受影响
        self.title_label.setText(self._raw_title.upper())
        self.title_label.setVisible(bool(self._raw_title))
        self._elide_title()

    def _elide_title(self):
        """按标题当前拿到的宽度截断并加省略号。

        宽度取控件自身算出来的宽度,而不是"窗口宽 - 图标宽"的估算:
        布局已经先给图标和间距分好位置,剩下的才是标题的,估算容易差出一截。
        控件还没被布局过(width 为 0)时不处理,等 resizeEvent 再来。
        """
        if not self._raw_title or self.title_label.width() <= 0:
            return
        metrics = self.title_label.fontMetrics()
        self.title_label.setText(
            metrics.elidedText(
                self._raw_title.upper(), Qt.ElideRight, self.title_label.width(),
            ),
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide_title()

    def contextMenuEvent(self, event):
        # 锁定态下右键菜单不响应(解锁走锁头点击)
        if self._window._locked:
            return
        self._window.show_header_menu(event.globalPos())

    def mousePressEvent(self, event):
        # 只上报,不消费:拖动逻辑还在 MainWindow.mousePressEvent 里
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class MainWindow(QWidget):
    # 隐藏清单时点窗口,装饰临时回来多久(秒)
    REVEAL_SECONDS = 3.0

    def __init__(self, store: TaskStore, settings_path: Path = None):
        super().__init__()
        self.store = store
        self._settings_path = settings_path or SETTINGS_FILE
        self.settings = AppSettings.load(self._settings_path)
        self.theme = self.settings.to_theme()
        self._drag_pos = None
        self._active_items = {}  # task_id -> TaskItem
        self._locked = False  # 缩略模式的镜像:任务行据此禁止编辑与拖拽排序
        self._compact = self.settings.compact_mode     # 缩略模式:只留任务列表
        self._chrome_shown = True     # 鼠标当前是否在窗口内(顶栏据此显隐)
        self._chrome_target = None    # 顶栏目标显隐状态(None=还没定过,首次调用必须应用)
        # 缩略模式下点窗口临时唤回顶栏的截止时刻(monotonic 秒),0 表示没在临时显示
        self._reveal_until = 0.0
        self._header_opacity = 1.0
        self._scroll_opacity = 1.0
        self._header_effect = None
        self._scroll_effect = None
        self._header_anim = None
        self._scroll_anim = None
        self._always_on_top = self.settings.always_on_top  # 置顶态,showEvent 里原生应用
        self._always_on_bottom = self.settings.always_on_bottom  # 置底态,同上
        self._position_fixed = self.settings.position_fixed  # 固定态:禁止拖动与缩放
        self._show_in_taskbar = self.settings.show_in_taskbar  # 是否在任务栏放图标
        self._taskbar_style_applied = None  # None = 还没应用过,见 _apply_taskbar_style
        self._tray = None  # 托盘图标:默认常驻(任务栏图标是选配)
        self._completed_expanded = False
        self._collapsed_h = None  # 已完成面板折叠时窗口高度
        self._expanded_panel_h = 0
        self._panel_lift = 0
        self._resize_dir = None
        self._resize_start_geo = None
        self._resize_origin = None
        self._edge_watch_ready = False
        self._cursor_overriding = False  # 是否已压入应用级 resize 光标
        self._settings_dirty = False
        self._settings_save_timer = QTimer(self)
        self._settings_save_timer.setSingleShot(True)
        self._settings_save_timer.setInterval(180)
        self._settings_save_timer.timeout.connect(self._flush_settings_save)
        # 缩略模式下临时唤回顶栏的收尾定时器(到点自动重新隐去)
        self._reveal_timer = QTimer(self)
        self._reveal_timer.setSingleShot(True)
        self._reveal_timer.timeout.connect(self._on_reveal_timeout)
        QApplication.instance().aboutToQuit.connect(self._save_settings_on_quit)
        self._dragged_task_id = None
        self._task_drag_global_pos = None
        self._task_drag_order_changed = False
        self._task_drag_scroll_timer = QTimer(self)
        self._task_drag_scroll_timer.setInterval(40)
        self._task_drag_scroll_timer.timeout.connect(self._auto_scroll_task_drag)

        self.setWindowTitle(product_name())
        self.setFont(QFont(self.theme.font_family, 10))
        # 仅无边框;置顶不用 Qt 标志而用原生 API(showEvent),
        # 避免 Qt 标志残留与原生层级不一致导致置顶无法取消
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(MIN_W, MIN_H)
        self.setMouseTracking(True)
        self.resize(320, 460)

        outer = QVBoxLayout(self)
        # 容器**永远**铺满整扇窗口:糊区只能是窗口矩形,卡片比窗口小多少,糊出来
        # 的那块就比卡片大多少(用户看到的"毛玻璃比背景大一圈")。所以卡片就是
        # 窗口矩形,开关毛玻璃不改变任何尺寸。羽化因此没有落脚处 —— 见下面的光环。
        outer.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame()
        self.container.setObjectName("container")
        self.container.setStyleSheet(build_qss(self.theme))
        # 容器内固定箭头光标,避免被窗口边缘的 resize 光标继承
        self.container.setCursor(QCursor(Qt.ArrowCursor))
        outer.addWidget(self.container)

        # 羽化那一圈画在窗口外面(窗口里脚下就是卡片),交给这个附属窗口
        self._halo = EdgeHalo(self, self.theme, PANEL_MARGIN)

        v = QVBoxLayout(self.container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # ---- 标题栏(标题 + 右侧三个图标;空白处可拖动窗口,右键退出/最小化)----
        self.header = HeaderBar(self)
        # 图钉三态/固定/缩略模式初始状态跟随持久化设置
        self._sync_pin_btn()
        self.header.fixed_btn.set_fixed(self.settings.position_fixed)
        self.header.compact_btn.set_compact(self.settings.compact_mode)
        # 顶部栏文字:设置里没写就用界面语言的默认文案
        self.header.set_title(self.settings.title_text)
        # 缩略模式下点顶栏 = 把图标临时唤回来
        self.header.clicked.connect(self._reveal_chrome)
        v.addWidget(self.header)

        # 托盘图标:默认就常驻 —— 任务栏那枚图标是选配,关了它托盘是唯一入口
        self._tray = TrayIcon(self)
        self._tray.toggle_requested.connect(self.toggle_visible)
        if not self.settings.show_in_taskbar and not self._tray.set_visible(True):
            # 没有托盘还不在任务栏显示 = 窗口再也找不回来,所以退回任务栏
            self._show_in_taskbar = True
            self.settings.show_in_taskbar = True
            self._settings_dirty = True
            self._settings_save_timer.start()

        # 开机自启动:注册表是真实状态,启动时按设置补齐/纠正(程序被挪过位置也能修正)
        if self.settings.autostart and autostart.current_command() != autostart.startup_command():
            autostart.set_enabled(True)

        # ---- 顶部分隔线 ----
        self.top_sep = QFrame()
        self.top_sep.setObjectName("sectionSep")
        self.top_sep.setFrameShape(QFrame.NoFrame)
        self.top_sep.setFixedHeight(1)
        v.addWidget(self.top_sep)

        # ---- 任务列表(可滚动)----
        self.scroll = QScrollArea()
        self.scroll.setObjectName("listScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget = QWidget()
        self.list_widget.setObjectName("listWidget")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.setAlignment(Qt.AlignTop)

        # ---- 行内加号:放进列表里,始终紧跟最后一个任务 ----
        self._inline_add_btn = QPushButton("+")
        self._inline_add_btn.setObjectName("inlineAddBtn")
        self._inline_add_btn.setFixedHeight(36)
        self._inline_add_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._inline_add_btn.setFocusPolicy(Qt.NoFocus)
        self._inline_add_btn.setToolTip(t("main.new_tooltip"))
        self._inline_add_btn.clicked.connect(self.add_task)
        self.list_layout.addWidget(self._inline_add_btn)

        # ---- 空列表引导提示(紧跟加号之后;不占用任务的索引空间)----
        self._empty_hint = QLabel(t("main.empty_hint"))
        self._empty_hint.setObjectName("emptyHint")
        self._empty_hint.setVisible(False)
        self.list_layout.addWidget(self._empty_hint)

        self.list_layout.addStretch()  # 末尾占位,任务顶对齐
        self.scroll.setWidget(self.list_widget)
        v.addWidget(self.scroll, 1)

        # ---- 底部:已完成按钮 + 设置齿轮(最右) ----
        self.footer_bar = QFrame()
        self.footer_bar.setObjectName("footerBar")
        footer_layout = QHBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(0, 0, 6, 0)
        footer_layout.setSpacing(0)

        self.footer_btn = QPushButton(t("main.completed_count", n=0))
        self.footer_btn.setObjectName("footerBtn")
        self.footer_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.footer_btn.setFocusPolicy(Qt.NoFocus)
        self.footer_btn.setIconSize(QSize(14, 14))
        self.footer_btn.setIcon(QIcon(self._chevron_pixmap("right")))
        self.footer_btn.clicked.connect(self.toggle_completed)
        footer_layout.addWidget(self.footer_btn, 1)

        self.settings_btn = QPushButton()
        self.settings_btn.setObjectName("settingsBtn")
        self.settings_btn.setFixedSize(28, 28)
        self.settings_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.settings_btn.setFocusPolicy(Qt.NoFocus)
        self.settings_btn.setToolTip(t("main.settings_tooltip"))
        self.settings_btn.setIcon(QIcon(self._gear_pixmap()))
        self.settings_btn.setIconSize(QSize(16, 16))
        self.settings_btn.clicked.connect(self.open_settings)
        footer_layout.addWidget(self.settings_btn)

        v.addWidget(self.footer_bar)

        # ---- 已完成面板(在 footer 下方,默认隐藏)----
        self.completed_panel = CompletedPanel()
        self.completed_panel.set_theme(self.theme)
        self.completed_panel.restored.connect(self.on_restore)
        self.completed_panel.deleted.connect(self.on_delete)
        self.completed_panel.setVisible(False)
        v.addWidget(self.completed_panel)

        self.load_tasks()
        self._restore_window_geometry()

        self._new_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        self._new_shortcut.activated.connect(self.add_task)
        # 顶栏三个按钮的快捷键来自设置(可在「编辑快捷键」窗口里改);
        # 默认注册成系统级热键,窗口不在前台也能用(见 global_hotkeys)。
        self._action_shortcuts = {}
        self._hotkeys = None
        self._hotkeys_window = 0
        self._apply_shortcuts()
        self._ensure_hotkeys()

        # 老设置文件里的出厂快捷键(不带 Alt 的 Ctrl+O/K/L)已被 load() 升级,
        # 立刻落盘一次,免得每次启动都重算
        if self.settings.shortcuts_upgraded:
            self._settings_dirty = True
            self._settings_save_timer.start()

        # 让边缘缩放对"可见深色块边缘"生效:给容器及所有子控件开鼠标追踪 + 事件过滤
        self._install_edge_watch(self.container)
        self._edge_watch_ready = True

        # 启动时把持久化的缩略模式立刻生效(不带动画,避免开场闪一下)。
        # 必须走 _apply_compact_visibility():只 _refresh_chrome() 的话顶栏是淡出了,
        # 但行内加号、底部「已完成 N」那条和任务行的锁定状态都还留在普通模式,
        # 于是"上次关在缩略模式、这次启动"看到的是一半缩略一半普通。
        if self._compact:
            self._apply_compact_visibility()
            self._refresh_chrome(animate=False)

    # ---- 边缘缩放:让 container 及子控件把鼠标事件转给窗口做边缘检测 ----
    def _watch_widget(self, w):
        w.setMouseTracking(True)
        w.installEventFilter(self)
        for c in w.findChildren(QWidget):
            c.setMouseTracking(True)
            c.installEventFilter(self)

    def _install_edge_watch(self, root):
        self._watch_widget(root)

    def eventFilter(self, obj, event):
        et = event.type()
        # 鼠标在窗口内移动:顶栏渐隐时要能按"靠近顶部"渐显回来
        if et == QEvent.MouseMove and self._compact:
            self._refresh_chrome()
        # 容器收到 Enter/Leave = 鼠标进出窗口内容区(所有子控件都被过滤,不会误判)
        if obj is self.container and et in (QEvent.Enter, QEvent.Leave):
            shown = et == QEvent.Enter
            if shown != self._chrome_shown:
                self._chrome_shown = shown
                self._refresh_chrome()
            return False
        # footer 图标颜色随主题:hover 提亮
        if obj is self.footer_btn and not self._locked:
            if et == QEvent.Enter:
                self.footer_btn.setIcon(
                    QIcon(self._chevron_pixmap(self._chevron_dir(), color=self.theme.icon_hover_color)))
                return False
            elif et == QEvent.Leave:
                self.footer_btn.setIcon(
                    QIcon(self._chevron_pixmap(self._chevron_dir(), color=self.theme.icon_color)))
                return False
        if et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            pos = self.mapFromGlobal(event.globalPosition().toPoint())
            direction = self._edge(pos)
            if direction is not None:
                # 角落区域与 footer 按钮重叠时,优先让按钮处理点击;
                # 边(非角)仍照常启动缩放。
                corners = ("topleft", "topright", "bottomleft", "bottomright")
                if isinstance(obj, QAbstractButton) and direction in corners:
                    return False
                self._resize_dir = direction
                self._resize_start_geo = self.frameGeometry()
                self._resize_origin = event.globalPosition().toPoint()
                return True  # 消费,防止子控件把它当普通点击
        elif et == QEvent.MouseMove:
            if self._resize_dir is not None and (event.buttons() & Qt.LeftButton):
                self._do_resize(event.globalPosition().toPoint())
                return True
            if not event.buttons():
                pos = self.mapFromGlobal(event.globalPosition().toPoint())
                direction = self._edge(pos)
                self._apply_edge_cursor(direction)
        elif et == QEvent.MouseButtonRelease:
            if self._resize_dir is not None:
                self._resize_dir = None
                self._resize_start_geo = None
                self._resize_origin = None
                self._apply_edge_cursor(None)
                return True
        return super().eventFilter(obj, event)

    def _screen_dpr(self):
        """窗口所在屏幕的设备像素比(副屏高DPI下图标不糊)。"""
        try:
            screen = (
                QApplication.screenAt(self.frameGeometry().center())
                or QApplication.primaryScreen()
            )
            return (screen.devicePixelRatio() if screen else None) or 1.0
        except Exception:
            return 1.0

    # ---- 加载 ----
    def _update_empty_hint(self):
        """无活跃任务时显示引导提示。"""
        self._empty_hint.setVisible(not self._active_items)

    def load_tasks(self):
        # 清理上次退出时残留的空任务(新建后未输入即退出所致)
        empty_ids = [t.id for t in self.store.active_tasks() if not t.text.strip()]
        if empty_ids:
            self.store.permanent_delete(empty_ids)
        for t in self.store.active_tasks():
            self._add_item_widget(t, focus=False, animate=False)
        self.completed_panel.set_tasks(self.store.completed_tasks())
        self._update_footer()
        self._update_empty_hint()

    def _add_item_widget(self, task, focus=True, animate=True, position=None):
        item = TaskItem(task)
        item.set_theme(self.theme)
        item.completed.connect(self.on_complete)
        item.text_changed.connect(self.on_text_changed)
        item.delete_requested.connect(self.on_delete)
        item.drag_started.connect(self._on_task_drag_started)
        item.drag_moved.connect(self._on_task_drag_moved)
        item.drag_finished.connect(self._on_task_drag_finished)
        # 插到加号按钮之前(加号始终紧跟最后一个任务)
        if position is None:
            position = self.list_layout.indexOf(self._inline_add_btn)
        self.list_layout.insertWidget(position, item)
        self._active_items[task.id] = item
        if self._edge_watch_ready:
            self._watch_widget(item)  # 新任务行也纳入边缘检测
        if animate:
            self._fade_in(item)
        if focus:
            item.start_edit()
        self._update_empty_hint()
        return item

    def _fade_in(self, item):
        """新任务行淡入,完成后移除特效减少渲染开销。"""
        effect = QGraphicsOpacityEffect(item)
        effect.setOpacity(0)
        item.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: item.setGraphicsEffect(None))
        item._fade_anim = anim  # 持有引用,防止动画被提前回收
        anim.start()

    # ---- 操作 ----
    def add_task(self):
        if self._locked:
            return
        task = self.store.add("")
        self._add_item_widget(task, focus=True)

    def on_complete(self, task_id):
        task = self.store.get(task_id)
        if task is None:
            return
        if task.text.strip() == "":
            # 空任务:直接删除,不进已完成栏
            self.on_delete(task_id, permanent=True)
            return
        self.store.complete(task_id)
        item = self._active_items.pop(task_id, None)
        if item is not None:
            self.list_layout.removeWidget(item)
            item.deleteLater()
        self.completed_panel.set_tasks(self.store.completed_tasks())
        self._sync_expanded_panel_height()
        self._update_footer()
        self._update_empty_hint()

    def on_restore(self, task_id):
        self.store.restore(task_id)
        self.completed_panel.set_tasks(self.store.completed_tasks())
        self._sync_expanded_panel_height()
        task = self.store.get(task_id)
        if task is not None:
            self._add_item_widget(task, focus=False)
        self._update_footer()

    def on_text_changed(self, task_id, text):
        self.store.update_text(task_id, text)

    def _ordered_task_items(self):
        return [
            self.list_layout.itemAt(index).widget()
            for index in range(self.list_layout.count())
            if isinstance(self.list_layout.itemAt(index).widget(), TaskItem)
        ]

    def _on_task_drag_started(self, task_id, global_pos):
        if self._locked or task_id not in self._active_items:
            return
        self._dragged_task_id = task_id
        self._task_drag_global_pos = global_pos
        self._task_drag_order_changed = False
        self._task_drag_scroll_timer.start()

    def _on_task_drag_moved(self, task_id, global_pos):
        if task_id != self._dragged_task_id:
            return
        self._task_drag_global_pos = global_pos
        self._reorder_dragged_task(global_pos)

    def _reorder_dragged_task(self, global_pos):
        dragged = self._active_items.get(self._dragged_task_id)
        if dragged is None:
            return
        items = self._ordered_task_items()
        if dragged not in items:
            return

        pointer_y = self.list_widget.mapFromGlobal(global_pos).y()
        others = [item for item in items if item is not dragged]
        target_index = len(others)
        for index, item in enumerate(others):
            if pointer_y < item.geometry().center().y():
                target_index = index
                break
        if target_index == items.index(dragged):
            return

        self.list_layout.removeWidget(dragged)
        self.list_layout.insertWidget(target_index, dragged)
        self.list_layout.activate()
        self._task_drag_order_changed = True

    def _auto_scroll_task_drag(self):
        if self._dragged_task_id is None or self._task_drag_global_pos is None:
            self._task_drag_scroll_timer.stop()
            return
        viewport = self.scroll.viewport()
        pos = viewport.mapFromGlobal(self._task_drag_global_pos)
        margin = 28
        delta = 0
        if pos.y() < margin:
            delta = -12
        elif pos.y() > viewport.height() - margin:
            delta = 12
        if delta == 0:
            return
        bar = self.scroll.verticalScrollBar()
        old_value = bar.value()
        bar.setValue(old_value + delta)
        if bar.value() != old_value:
            self._reorder_dragged_task(self._task_drag_global_pos)

    def _on_task_drag_finished(self, task_id):
        if task_id != self._dragged_task_id:
            return
        self._task_drag_scroll_timer.stop()
        if self._task_drag_order_changed:
            ordered_items = self._ordered_task_items()
            ordered_ids = [item.task.id for item in ordered_items]
            self.store.reorder_active(ordered_ids)
            self._active_items = {item.task.id: item for item in ordered_items}
        self._dragged_task_id = None
        self._task_drag_global_pos = None
        self._task_drag_order_changed = False

    def on_delete(self, task_id, permanent=False):
        task = self.store.get(task_id)
        # 从未有过内容的任务(如点 + 后未输入直接取消)不留历史记录
        if task is not None and task.text.strip() == "":
            permanent = True
        if permanent:
            deleted = self.store.permanent_delete([task_id])
        else:
            deleted = [self.store.delete(task_id)]
        if not deleted or deleted[0] is None:
            return
        item = self._active_items.pop(task_id, None)
        if item is not None:
            self.list_layout.removeWidget(item)
            item.deleteLater()
        # 已完成任务删除后也要刷新面板
        self.completed_panel.set_tasks(self.store.completed_tasks())
        self._sync_expanded_panel_height()
        self._update_footer()
        self._update_empty_hint()

    # ---- 已完成面板展开/折叠(向下扩展窗口高度,不挤压任务列表)----
    def toggle_completed(self):
        if not self._completed_expanded:
            self._collapsed_h = self.height()
            self._completed_expanded = True
            self.completed_panel.setVisible(True)
            self._expanded_panel_h = min(PANEL_H, self.completed_panel.content_height())
            self.completed_panel.setFixedHeight(self._expanded_panel_h)
            self.resize(self.width(), self._collapsed_h + self._expanded_panel_h)
            self._keep_expanded_panel_on_screen()
        else:
            self._completed_expanded = False
            self.completed_panel.setVisible(False)
            # 用户可能在展开状态下调整过高度，应保留这次调整。
            self._collapsed_h = max(MIN_H, self.height() - self._expanded_panel_h)
            self.resize(self.width(), self._collapsed_h)
            if self._panel_lift:
                self.move(self.x(), self.y() + self._panel_lift)
            self._panel_lift = 0
            self.completed_panel.setMinimumHeight(0)
            self.completed_panel.setMaximumHeight(PANEL_H)
        self._update_footer()

    def _sync_expanded_panel_height(self):
        if not self._completed_expanded:
            return
        old_height = self._expanded_panel_h
        self._expanded_panel_h = min(PANEL_H, self.completed_panel.content_height())
        self.completed_panel.setFixedHeight(self._expanded_panel_h)
        self.resize(
            self.width(),
            max(MIN_H, self.height() + self._expanded_panel_h - old_height),
        )
        if self._expanded_panel_h < old_height and self._panel_lift:
            drop = min(self._panel_lift, old_height - self._expanded_panel_h)
            self.move(self.x(), self.y() + drop)
            self._panel_lift -= drop
        self._keep_expanded_panel_on_screen()

    def _keep_expanded_panel_on_screen(self):
        screen = (
            QApplication.screenAt(self.frameGeometry().center())
            or QApplication.primaryScreen()
        )
        if screen is None:
            return
        available = screen.availableGeometry()
        overflow = max(0, self.frameGeometry().bottom() - available.bottom())
        if overflow:
            lift = min(overflow, max(0, self.y() - available.top()))
            self.move(self.x(), self.y() - lift)
            self._panel_lift += lift

    def _restore_window_geometry(self):
        width = self.settings.window_width or 320
        height = self.settings.window_height or 460
        x = self.settings.window_x
        y = self.settings.window_y
        if x is None or y is None:
            self.resize(width, height)
            return
        primary = QApplication.primaryScreen()
        target = next(
            (screen for screen in QApplication.screens()
             if screen.availableGeometry().contains(x, y)),
            primary,
        )
        if target is None:
            self.setGeometry(x, y, width, height)
            return
        available = target.availableGeometry()
        width = min(max(MIN_W, width), available.width())
        height = min(max(MIN_H, height), available.height())
        x = min(max(x, available.left()), available.right() - width + 1)
        y = min(max(y, available.top()), available.bottom() - height + 1)
        self.setGeometry(x, y, width, height)

    def _footer_text(self):
        n = len(self.store.completed_tasks())
        return t("main.completed_count", n=n)

    def _update_footer(self):
        self.footer_btn.setText(self._footer_text())
        # chevron 图标:折叠朝右 >,展开朝下 v;颜色与 footer 字体一致
        self.footer_btn.setIcon(QIcon(self._chevron_pixmap(self._chevron_dir())))

    def _chevron_dir(self):
        return "down" if self._completed_expanded else "right"

    def _chevron_pixmap(self, direction, size=14, color=None):
        """用 QPainter 画矢量 chevron:浮点坐标严格对称 + 按所在屏幕 DPR 高清渲染,不糊。"""
        if color is None:
            color = self.theme.icon_color
        dpr = self._screen_dpr()
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen = p.pen()
        pen.setColor(color)
        pen.setWidthF(max(1.5, size * 0.16))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)

        cx = cy = size / 2.0
        off = size * 0.20    # 顶点相对中心的横向偏移
        off2 = size * 0.32   # 两臂展开的纵向偏移
        if direction == "down":
            p.drawLine(QPointF(cx - off2, cy - off), QPointF(cx, cy + off))
            p.drawLine(QPointF(cx, cy + off), QPointF(cx + off2, cy - off))
        else:  # right
            p.drawLine(QPointF(cx - off, cy - off2), QPointF(cx + off, cy))
            p.drawLine(QPointF(cx + off, cy), QPointF(cx - off, cy + off2))
        p.end()
        return pm

    def _gear_pixmap(self, size=16, color=None):
        """画设置图标:凹边削角螺母造型 + 中心小圆孔(定稿 nut3_B)。

        尖头六边形(上下为角),每条边用二次贝塞尔曲线向中心内凹,
        六个角各削去一小段平面,细线条 + 小圆孔。
        """
        if color is None:
            color = self.theme.icon_color
        dpr = self._screen_dpr()
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        cx = cy = size / 2.0
        center = QPointF(cx, cy)
        hex_r = size * 0.44          # 顶点半径
        stroke_w = max(1.0, size * 0.085)  # 细线条
        chamfer = size * 0.10        # 削角长度
        depth = size * 0.12          # 边中点向中心内凹的深度
        # 尖头六边形顶点(上下为角)
        verts = [
            QPointF(
                cx + math.cos(math.radians(90 + i * 60)) * hex_r,
                cy + math.sin(math.radians(90 + i * 60)) * hex_r,
            )
            for i in range(6)
        ]
        path = QPainterPath()
        path.moveTo(_on_segment(verts[0], verts[1], chamfer))
        for i in range(6):
            a = verts[i]
            b = verts[(i + 1) % 6]
            nxt = verts[(i + 2) % 6]
            # 边 a→b 的内凹曲线:控制点 = 边中点向中心拉 depth
            mid = QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2)
            path.quadTo(_on_segment(mid, center, depth), _on_segment(b, a, chamfer))
            # 顶点 b 的削角小平面(微圆角由 RoundJoin 提供)
            path.lineTo(_on_segment(b, nxt, chamfer))
        path.closeSubpath()
        pen = QPen(color, stroke_w)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        # 中心小圆孔
        p.drawEllipse(center, size * 0.11, size * 0.11)
        p.end()
        return pm

    # ---- 设置 ----
    def open_settings(self):
        win = getattr(self, "_settings_win", None)
        if win is not None:
            # 窗口已存在(可能只是被关闭隐藏),直接显示
            win.show()
            win.raise_()
            win.activateWindow()
            return
        win = SettingsWindow(self.settings, parent=self)
        win.changed.connect(self._on_settings_changed)
        win.z_order_changed.connect(self.set_layer)
        win.position_fixed_changed.connect(self.set_position_fixed)
        win.taskbar_changed.connect(self.set_show_in_taskbar)
        win.autostart_changed.connect(self.set_autostart)
        win.title_changed.connect(self.set_title_text)
        win.history_requested.connect(self.open_history)
        win.keybind_requested.connect(self.open_keybinds)
        win.reset_requested.connect(self.reset_behaviour)
        self._settings_win = win
        win.show()

    def open_keybinds(self):
        """打开「编辑快捷键」窗口(外观与设置窗口同一套自绘样式)。"""
        win = getattr(self, "_keybind_win", None)
        if win is not None:
            win.show()
            win.raise_()
            win.activateWindow()
            return
        win = KeybindWindow(self.settings, parent=self)
        win.changed.connect(self.set_shortcuts)
        self._keybind_win = win
        win.show()

    def open_history(self):
        win = getattr(self, "_history_win", None)
        if win is None:
            win = HistoryWindow(self.store, self.settings, parent=self)
            win.changed.connect(self._reload_task_views)
            self._history_win = win
        win.refresh()
        win.show()
        win.raise_()
        win.activateWindow()

    def _reload_task_views(self):
        for item in self._active_items.values():
            self.list_layout.removeWidget(item)
            item.deleteLater()
        self._active_items.clear()
        for task in self.store.active_tasks():
            self._add_item_widget(task, focus=False, animate=False)
        self.completed_panel.set_tasks(self.store.completed_tasks())
        self._sync_expanded_panel_height()
        self._update_footer()
        self._update_empty_hint()

    def _on_settings_changed(self):
        """设置变动立即预览，短时间内的连续磁盘写入合并保存。"""
        self.apply_theme()
        self._apply_blur_behind()
        # 设置窗口自绘外观(背景色/透明度/字体),跟着一起刷新;
        # 自定义配色窗口若开着,色块也要同步(从里面改的颜色不用重画,幂等)
        win = getattr(self, "_settings_win", None)
        if win is not None:
            win.apply_theme()
            win.refresh_custom_colors()
        # 历史任务窗口也是同一套浮动外观,主题变了要跟着刷
        hist = getattr(self, "_history_win", None)
        if hist is not None:
            hist.apply_theme()
        # 快捷键窗口同理(它的控件配色也按主题生成)
        keys = getattr(self, "_keybind_win", None)
        if keys is not None:
            keys.apply_theme()
        self._settings_dirty = True
        self._settings_save_timer.start()

    def _snapshot_geometry(self):
        """把当前窗口位置/大小写入 settings(展开态折算回折叠态)。"""
        saved_height = self.height()
        saved_y = self.y()
        if self._completed_expanded:
            saved_height = max(MIN_H, saved_height - self._expanded_panel_h)
            saved_y += self._panel_lift
        self.settings.window_x = self.x()
        self.settings.window_y = saved_y
        self.settings.window_width = self.width()
        self.settings.window_height = saved_height

    def _flush_settings_save(self):
        if not self._settings_dirty:
            return
        self._settings_save_timer.stop()
        self.settings.save(self._settings_path)
        self._settings_dirty = False

    def _save_settings_on_quit(self):
        """退出前强制保存一次。

        菜单"退出"走 QApplication.quit(),不触发 closeEvent,
        若只依赖 closeEvent,窗口位置/大小会丢失。
        """
        self._snapshot_geometry()
        self._settings_dirty = True
        self._flush_settings_save()

    def apply_theme(self):
        """重新从 settings 生成主题并刷新所有 UI。"""
        self.theme = self.settings.to_theme()
        t = self.theme
        # 容器 QSS
        self.container.setStyleSheet(build_qss(t))
        # 全局字体
        self.setFont(QFont(t.font_family, 10))
        # 锁头
        self.header.compact_btn.set_theme(t)
        # 图钉与固定
        self.header.pin_btn.set_theme(t)
        self.header.fixed_btn.set_theme(t)
        # 齿轮图标
        self.settings_btn.setIcon(QIcon(self._gear_pixmap()))
        # 顶部栏文字(换语言/改文案后要重排省略);空字符串=不显示文字
        self.header.set_title(self.settings.title_text)
        # chevron
        self._update_footer()
        # 任务项
        for item in self._active_items.values():
            item.set_theme(t)
        # 已完成面板
        self.completed_panel.set_theme(t)
        # 主题变了,光环窗口吃同一份主题
        self._halo.set_theme(t)
        self._sync_halo()

    # ---- 缩略模式(靠鼠标靠近顶栏决定顶栏显隐) ----
    def set_compact_mode(self, compact, animate=True):
        """缩略模式:只留任务列表(顶栏整体渐隐、隐藏已完成面板、底部栏与加号)。

        禁止编辑与拖拽排序;**允许缩放窗口** —— 只有「固定窗口位置」才禁止拖动与缩放。
        顶栏不是把按钮逐个藏起来,而是整块淡出(见 _animate_chrome),所以
        顶部栏文字与另外三个图标永远同进同出。
        """
        compact = bool(compact)
        if compact == self._compact:
            return
        self._compact = compact
        self.settings.compact_mode = compact
        self._apply_compact_visibility()
        # 缩略模式只收起底部栏与加号,窗口大小仍可自由缩放 ——
        # 只有「固定窗口位置」才禁止拖动与缩放,所以这里不再自动改高度。
        self._refresh_chrome(animate=animate)
        self._settings_dirty = True
        self._settings_save_timer.start()
        self.update()

    def _apply_compact_visibility(self):
        """把"缩略模式"该有的外观一次性铺上(启动路径与切换路径共用)。

        只改"看得见什么",不碰动画、不落盘——所以 __init__ 也能直接调。
        """
        compact = self._compact
        self._locked = compact      # 任务行按"锁定"处理:禁编辑、禁拖拽排序
        self.header.compact_btn.set_compact(compact)
        self._inline_add_btn.setVisible(not compact)
        self.footer_bar.setVisible(not compact)
        # 顶栏与图标不单独显隐,整块顶栏的渐隐由 _refresh_chrome 负责
        self.header.setVisible(True)
        for btn in self._header_icon_btns():
            btn.setVisible(True)
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff if compact else Qt.ScrollBarAsNeeded,
        )
        if compact and self._completed_expanded:
            self.toggle_completed()      # 缩略模式收起已完成面板
        for item in list(self._active_items.values()):
            item.set_locked(compact)

    def _compact_height(self):
        """缩略模式下的目标高度:顶栏高度 + 上下留白 + 一行左右的任务区。"""
        return max(MIN_H, self.header.height() + 8 + 90)

    def toggle_compact_mode(self):
        self.set_compact_mode(not self._compact)

    # ---- 快捷键:顶栏三个按钮的绑定可在「编辑快捷键」窗口里改 ----
    def _shortcut_actions(self):
        """动作名 -> 触发函数(顺序即设置窗口里的显示顺序)。"""
        return {
            "z_order": self._cycle_z_order_shortcut,
            "fixed": self.toggle_position_fixed,
            "compact": self.toggle_compact_mode,
        }

    def _cycle_z_order_shortcut(self):
        """快捷键用的层级循环:置顶 -> 置底 -> 普通 -> 置顶。"""
        if not self._always_on_top and not self._always_on_bottom:
            self.set_always_on_top(True)
        elif self._always_on_top:
            self.set_always_on_bottom(True)
        else:
            self.set_always_on_bottom(False)

    def _apply_shortcuts(self):
        """按 settings.shortcuts 重建三个动作的绑定(空串=不绑定)。

        默认走**全局热键**(Win32 RegisterHotKey):窗口不在前台时也能触发,
        因为这些动作本来就是"在别的窗口里顺手拨一下"的。注册不到(被别的
        程序占了、绑定没带修饰键、非 Windows、开关关掉了)就退回 Qt 的
        QShortcut —— 只在主窗口被选中时响应,也就是旧行为。
        """
        self._release_hotkeys()
        for shortcut in self._action_shortcuts.values():
            shortcut.setParent(None)
            shortcut.deleteLater()
        self._action_shortcuts = {}

        actions = self._shortcut_actions()
        bindings = {
            name: self.settings.shortcuts.get(name, "") for name in actions
        }
        registered = {}
        if self.settings.global_shortcuts and global_hotkeys.supported():
            if self._hotkeys is None:
                self._hotkeys = global_hotkeys.GlobalHotkeys()
                QApplication.instance().installNativeEventFilter(self._hotkeys)
            registered = self._hotkeys.apply(
                int(self.winId()), bindings, actions,
            )

        for name, handler in actions.items():
            if registered.get(name):
                continue      # 已经在系统层注册,不再叠一个窗口级绑定
            text = bindings[name]
            if not text:
                continue
            shortcut = QShortcut(QKeySequence(text), self)
            shortcut.activated.connect(handler)
            self._action_shortcuts[name] = shortcut
        self._sync_shortcut_tooltips()

    def _release_hotkeys(self):
        """注销全部全局热键(改键前、退出前都要调,否则会一直占着这些键)。"""
        if self._hotkeys is not None:
            self._hotkeys.release()

    def _sync_shortcut_tooltips(self):
        """把绑定显示在三个按钮的 tooltip 里。"""
        for name, btn in (
            ("z_order", self.header.pin_btn),
            ("compact", self.header.compact_btn),
            ("fixed", self.header.fixed_btn),
        ):
            btn.set_shortcut(self.settings.shortcuts.get(name, ""))

    def set_shortcuts(self, shortcuts):
        """「编辑快捷键」窗口改完绑定后回调。"""
        self.settings.shortcuts = dict(shortcuts)
        self._apply_shortcuts()
        self._settings_dirty = True
        self._settings_save_timer.start()

    def _chrome_wanted(self):
        """鼠标是否希望看到顶部栏(缩略模式下由鼠标位置决定)。

        普通模式顶栏一直在;缩略模式只隐去顶栏,鼠标贴到窗口顶部那一带时渐显回来。
        例外:缩略模式下点一下窗口,顶栏临时回来 3 秒(_reveal_chrome),
        这样鼠标没贴边时也有入口点图标。
        """
        if time.monotonic() < self._reveal_until:
            return True
        if not self._compact:
            return True
        return self._cursor_near_top()

    def _reveal_chrome(self):
        """缩略模式下点击窗口时把顶栏临时唤回几秒。

        不改 settings.compact_mode:这只是给用户一个能点到图标的窗口,
        到时间后自动按原设置隐去。
        """
        if not self._compact:
            return
        self._reveal_until = time.monotonic() + self.REVEAL_SECONDS
        self._refresh_chrome()
        self._reveal_timer.start(int(self.REVEAL_SECONDS * 1000) + 60)

    def _on_reveal_timeout(self):
        """临时显示到期:重新隐去(还在临时窗口内留着,不重复触发)。"""
        if time.monotonic() >= self._reveal_until:
            self._reveal_until = 0.0
            self._refresh_chrome()
        else:
            self._reveal_timer.start(int(self.REVEAL_SECONDS * 1000) + 60)

    def _hide_chrome_now(self):
        """按当前设置立刻同步顶栏显隐(重置用:不带动画,免得和"全部关掉"抢时间)。"""
        self._reveal_until = 0.0
        self._reveal_timer.stop()
        self._chrome_target = None
        self._refresh_chrome(animate=False)

    def _cursor_near_top(self):
        """鼠标是否贴在窗口顶部那一带(顶栏区域)。

        用几何位置判断而不是可见性:顶栏完全淡出后 widget 仍占着那块地方。
        """
        rect = QRect(
            self.header.mapToGlobal(QPoint(0, 0)), self.header.size(),
        )
        return rect.contains(QCursor.pos())

    def _refresh_chrome(self, animate=True):
        """按鼠标位置刷新顶部栏的显隐。

        目标状态没变就直接返回,免得鼠标一动就重启动画(闪烁)。
        """
        show = self._chrome_wanted()
        if show == self._chrome_target:
            return
        self._chrome_target = show
        self._animate_chrome(show, animate=animate)

    def _animate_chrome(self, show, animate=True):
        """淡入淡出顶部栏(自身淡出,就能露出圆角外框)。

        清单区不参与渐隐:顶栏淡出后它就是窗口最上面那块。
        """
        self._animate_widget(
            "header", self.header, show,
            duration=190 if animate else 0,
        )

    def _animate_widget(self, name, widget, show, duration):
        """把某个子控件淡入(0→1)或淡出(1→0),结束后按结果决定是否隐藏。

        Qt 的 setGraphicsEffect(None) 会 **delete** 掉原来那个特效对象
        (实测 PySide 里紧接着再碰它就会抛 "Internal C++ object already deleted"),
        所以每次摘掉特效后必须立刻丢掉 Python 侧的引用,否则下次
        `_{name}_effect` 拿到的是个死对象,一碰就崩。
        """
        effect = getattr(self, f"_{name}_effect", None)
        if effect is None:
            effect = QGraphicsOpacityEffect(widget)
            setattr(self, f"_{name}_effect", effect)
        start = getattr(self, f"_{name}_opacity", 1.0)
        end = 1.0 if show else 0.0
        if show:
            widget.setVisible(True)
        anim = getattr(self, f"_{name}_anim", None)
        if anim is not None:
            anim.stop()
        if duration <= 0 or start == end:
            widget.setGraphicsEffect(None)
            self._forget_effect(name)
            self._set_widget_shown(name, widget, show)
            setattr(self, f"_{name}_opacity", end)
            return
        if widget.graphicsEffect() is not effect:
            widget.setGraphicsEffect(effect)
        effect.setOpacity(start)
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(duration)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(lambda: self._on_fade_finished(name, widget, end))
        setattr(self, f"_{name}_anim", anim)
        setattr(self, f"_{name}_opacity", end)
        anim.start()

    def _forget_effect(self, name):
        """丢掉已被 Qt 删掉的透明度特效引用(见 _animate_widget 的说明)。"""
        setattr(self, f"_{name}_effect", None)

    def _set_widget_shown(self, name, widget, show):
        """淡出/淡入的收尾动作。

        清单区域特殊对待:它从来不 setVisible(False),而是把高度收成 0。
        QScrollArea 一旦被隐藏,内部 widget 就再也不跟随 viewport 重新布局 ——
        实测隐藏后再显示,窗口宽 320 时 scroll/list 的宽度会停在 640,
        任务行被撑出窗口外(用户看到的就是内容布局乱掉)。
        高度收成 0 时它仍然"可见",viewport 照常重算,所以不会留下坏几何。
        """
        widget.setVisible(True if name == "scroll" else show)
        if name == "scroll":
            widget.setMaximumHeight(SCROLL_MAX_H if show else 0)
            if show:
                # 显示回来时补一次几何校正,避免布局和 viewport 不同步
                QTimer.singleShot(0, self._fix_scroll_geometry)

    def _fix_scroll_geometry(self):
        """把清单内部 widget 的宽度重新对齐到 viewport(只在需要时动)。"""
        vp = self.scroll.viewport()
        if vp is None or not self.list_widget.parent():
            return
        if self.list_widget.width() != vp.width():
            self.list_widget.resize(vp.width(), self.list_widget.height())

    def _on_fade_finished(self, name, widget, end):
        """淡出结束后把特效摘掉,避免长期挂着 opacity effect 影响渲染。"""
        widget.setGraphicsEffect(None)
        self._forget_effect(name)
        if end <= 0.0:
            self._set_widget_shown(name, widget, False)

    def _header_icon_btns(self):
        """顶部栏右侧图标按钮组(与顶栏同进同出,不再单独显隐)。"""
        return (
            self.header.pin_btn,
            self.header.compact_btn, self.header.fixed_btn,
        )

    # ---- 层级:图钉置顶 / 置底 ----
    def event(self, event):
        """置底态下窗口被激活时重新压回底层。

        打开设置/历史窗口(它们是独立的置顶工具窗)会让系统把主窗口一起提到前面,
        用户看到的就是"置底失灵";激活事件里再压一次即可恢复。
        """
        if event.type() == QEvent.WindowActivate and self._always_on_bottom:
            QTimer.singleShot(0, self._apply_z_order)
        return super().event(event)

    def _apply_z_order(self):
        """按当前置顶/置底状态校正窗口层级(置底优先)。

        Windows 上直接走原生 SetWindowPos 改 z-order,不重建窗口也不闪烁;
        原生不可用(非 Windows 或窗口未显示)时返回 False,由调用方退回 Qt 标志。
        """
        if _user32 is None or not self.isVisible():
            return False
        if self._always_on_bottom:
            layer = HWND_BOTTOM       # 压到所有普通窗口与输入法窗口之下、桌面之上
        elif self._always_on_top:
            layer = HWND_TOPMOST
        else:
            layer = HWND_NOTOPMOST
        return bool(_user32.SetWindowPos(
            int(self.winId()),
            layer,
            0, 0, 0, 0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE,
        ))

    def _ensure_hotkeys(self):
        """窗口句柄变了就重挂全局热键。

        ``RegisterHotKey`` 绑的是当时的 HWND:Qt 重建窗口标志
        (``setWindowFlags`` / ``show``/``hide`` 流程)会换掉 HWND,
        旧注册就再也收不到 WM_HOTKEY 了,所以要按当前 winId 重新挂。
        """
        if self._hotkeys is None:
            return
        hwnd = int(self.winId())
        if hwnd == self._hotkeys_window:
            return
        self._hotkeys_window = hwnd
        self._hotkeys.apply(
            hwnd,
            {name: self.settings.shortcuts.get(name, "")
             for name in self._shortcut_actions()},
            self._shortcut_actions(),
        )

    def showEvent(self, event):
        """每次窗口(重)显示后按当前层级设置校正 z-order。

        覆盖最小化还原、隐藏重显等场景,避免状态丢失或残留。
        必须等 Qt 自己的显示流程走完:showEvent 里立刻调 SetWindowPos(HWND_BOTTOM),
        随后的默认层级会把它顶回来(置顶靠 WS_EX_TOPMOST 样式不受影响,只有置底会失效),
        所以推迟到事件循环的下一轮再应用。
        """
        super().showEvent(event)
        # 光环在这里同步摆好:推到事件循环下一轮才 show 的话,它会晚一步
        # "成为活动窗口"——那时用户可能已经点进某个任务在打字,焦点就被它带走了
        # (离屏平台必然如此;真机上靠 WS_EX_NOACTIVATE 不会,见 probe_halo_ring)。
        self._sync_halo()
        QTimer.singleShot(0, self._apply_z_order)
        QTimer.singleShot(0, self._apply_taskbar_style)
        QTimer.singleShot(0, self._apply_blur_behind)
        QTimer.singleShot(0, self._ensure_hotkeys)

    def changeEvent(self, event):
        """窗口标志被重建后补回任务栏样式(Qt 的 show/hide 流程会重置扩展样式)。"""
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            QTimer.singleShot(0, self._apply_taskbar_style)
            QTimer.singleShot(0, self._apply_blur_behind)
            QTimer.singleShot(0, self._sync_halo)

    def hideEvent(self, event):
        """窗口被隐藏(托盘收起/最小化)时立刻落盘。

        合并保存的定时器有 180ms 延迟,窗口一藏起来用户就可能直接关掉
        程序或让电脑休眠,来不及写的改动会整批丢掉,所以这里先刷一次盘。
        """
        super().hideEvent(event)
        self._halo.hide()  # 主窗藏了,附属的光环必须跟着消失
        self._save_settings_on_quit()

    def _sync_pin_btn(self):
        """把图钉按钮切到当前层级对应的三态。"""
        mode = "top" if self._always_on_top else (
            "bottom" if self._always_on_bottom else "normal"
        )
        self.header.pin_btn.set_mode(mode)

    def _sync_layer_checks(self):
        """把设置窗口里的层级单选项同步到当前层级。

        一律按当前状态算,不再由调用方猜是哪一层 —— 之前置顶分支写死
        同步 "top"、置底分支写死同步 "normal",选「置于最上层」时
        后一次调用就把单选项弹回了「普通层级」。
        """
        win = getattr(self, "_settings_win", None)
        if win is None:
            return
        mode = "top" if self._always_on_top else (
            "bottom" if self._always_on_bottom else "normal"
        )
        win.set_z_order_checks(mode)

    def cycle_z_order(self, mode):
        """图钉点击:在 置顶 -> 置底 -> 普通 三态间循环。"""
        if mode == "top":
            self.set_always_on_top(True)
        elif mode == "bottom":
            self.set_always_on_bottom(True)
        else:
            self.set_always_on_bottom(False)
            self.set_always_on_top(False)

    def set_layer(self, name):
        """设置窗口里选了窗口层级("top"/"bottom"/"normal")。

        必须按名字分派:以前只回传"要不要置底"的布尔值,选「置于最上层」时
        回传 False 被当成"回到普通层级",`set_always_on_bottom(False)` 又把
        单选项弹回「普通层级」——用户看到的就是"点了没反应"。
        """
        if name == "top":
            self.set_always_on_top(True)
        elif name == "bottom":
            self.set_always_on_bottom(True)
        else:
            self.set_always_on_bottom(False)
            self.set_always_on_top(False)

    def set_always_on_top(self, pinned):
        """切换窗口置顶;状态写入 settings 跨重启保持。

        Windows 上直接走原生 SetWindowPos 改 z-order,避免
        setWindowFlags 重建窗口导致的整界面闪烁;非 Windows 退回重建方式。
        置顶与置底互斥:置顶时自动取消置底。
        """
        pinned = bool(pinned)
        changed = pinned != self._always_on_top
        self.settings.always_on_top = pinned
        self._always_on_top = pinned
        if pinned:
            self._always_on_bottom = False
            self.settings.always_on_bottom = False
        self._sync_pin_btn()
        self._sync_layer_checks()
        if changed and not self._apply_z_order():
            # 非 Windows(或窗口尚未显示):重建窗口标志兼容
            flags = Qt.FramelessWindowHint
            if pinned:
                flags |= Qt.WindowStaysOnTopHint
            was_visible = self.isVisible()
            geo = self.geometry()
            self.setWindowFlags(flags)
            self.setGeometry(geo)
            if was_visible:
                self.show()
        self._settings_dirty = True
        self._settings_save_timer.start()

    def set_always_on_bottom(self, on_bottom):
        """切换窗口置底:始终排在所有普通窗口之下、桌面之上。

        与置顶互斥,置底时自动取消置顶;非 Windows 无原生支持,退回普通层级。
        """
        on_bottom = bool(on_bottom)
        self.settings.always_on_bottom = on_bottom
        self._always_on_bottom = on_bottom
        if on_bottom:
            self._always_on_top = False
            self.settings.always_on_top = False
        self._sync_pin_btn()
        self._sync_layer_checks()
        self._apply_z_order()  # 开关置底后立刻按新层级校正
        self._settings_dirty = True
        self._settings_save_timer.start()

    # ---- 真·毛玻璃 ----
    def _sync_halo(self):
        """把羽化那一圈交给光环窗口,并让它跟住主窗口。

        容器永远铺满窗口(卡片 == 窗口矩形),窗口里脚下就是卡片、没有画羽化的
        地方,所以羽化整圈都画在窗口外面 —— 由这个比窗口四周各宽 PANEL_MARGIN
        的透明附属窗口负责,开关毛玻璃都一样。窗口不可见时收起,免得窗口藏起来
        了光环还留在屏幕上。
        """
        if not self.isVisible():
            self._halo.hide()
            return
        self._halo.set_theme(self.theme)
        self._halo.follow(self.frameGeometry(), PANEL_MARGIN)
        if not self._halo.isVisible():
            self._halo.show()

    def moveEvent(self, event):
        """拖动/被系统挪动时,光环必须同一轮就跟过去(晚一拍就成了拖影)。"""
        super().moveEvent(event)
        self._sync_halo()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_halo()

    def _apply_blur_behind(self):
        """按设置开关窗口背后的模糊(真·毛玻璃)。

        只是把设置转给 blur_behind 模块,失败静默——这个 API 未公开,
        不支持时只是没有毛玻璃,不该影响其它功能。窗口标志重建(最小化还原、
        改任务栏样式)会丢掉这个效果,所以 showEvent/changeEvent 里都要补一次。

        糊的是**整个窗口矩形**、而且只能是方的:实测 SetWindowRgn 裁不住它,
        DwmEnableBlurBehindWindow 传模糊区域返回 S_OK 却没反应,这台 Win10
        没有 DWMWA_WINDOW_CORNER_PREFERENCE;连窗口自己的 alpha 都不看
        (bg_opacity 压到 0 里面照样糊)。既然糊区钉死在窗口矩形上,可见的卡片
        就**永远**铺满窗口(`__init__` 里边距恒为 0),糊区与卡片逐像素重合,
        圆角照常保留 —— 四个角各剩约 14 平方像素的残糊,透明度拉满时能看见,
        但比"卡片内缩 8px"那种整圈大一圈划算得多。

        所以这里**不碰任何尺寸**:以前是"开毛玻璃才把边距压成 0",结果一开关
        卡片就整个胀出去 8px、羽化也跟着从窗口里跳到窗口外,用户看到的就是
        "开了毛玻璃主界面突然大一圈"。现在开关只决定背后糊不糊。
        """
        if not self.isVisible():
            return False
        return apply_to_widget(self, bool(self.settings.blur_behind))

    # ---- 任务栏图标与系统托盘 ----
    def _apply_taskbar_style(self):
        """按设置增删 WS_EX_TOOLWINDOW,决定窗口是否占一个任务栏按钮。

        只改扩展样式不够:任务栏按钮是窗口管理器在登记窗口时决定的,必须
        hide→show 让窗口重新登记,按钮才会消失/回来。

        这里的 hide/show 用 singleShot 推到事件循环下一轮再执行:本方法也会
        被 showEvent 里的 singleShot(0) 调到,而 showEvent 是从 Qt 的显示流程
        里进来的。在显示流程中同步 hide() 会把 Qt 的"已可见"状态清掉、紧接着
        的 show() 又被当成重复请求而早退,结果原生窗口真的被藏起来、Qt 却以为
        它可见 —— 之后 isVisible() 一直为真,点托盘图标走到 hide 分支,
        窗口就再也回不来了。非 Windows 退回 Qt 的 WindowType 标志。
        """
        if not self.isVisible():
            return False  # 窗口没显示时不动它,免得凭空 show 出来
        hidden = not self._show_in_taskbar
        if _user32 is None or _set_window_long is None:
            self.setWindowFlag(Qt.Tool, hidden)
            return False
        hwnd = int(self.winId())
        ex_style = _get_window_long(hwnd, GWL_EXSTYLE) or 0
        if hidden:
            # WS_EX_APPWINDOW 优先级高于 TOOLWINDOW,必须一起清掉
            target = (ex_style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
        else:
            target = ex_style & ~WS_EX_TOOLWINDOW & ~WS_EX_APPWINDOW
        style_changed = target != ex_style
        _set_window_long(hwnd, GWL_EXSTYLE, target)
        if style_changed:
            _user32.SetWindowPos(
                hwnd, None, 0, 0, 0, 0,
                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
        previous = self._taskbar_style_applied
        self._taskbar_style_applied = hidden
        if previous is not None and (style_changed or previous != hidden):
            # 让任务栏重新登记这个窗口:必须离开当前调用栈再显隐,
            # 否则会和 Qt 的显示流程打架(见上面的说明)。
            #
            # 首次应用(窗口刚显示)不重登记:此时窗口还没进过任务栏,样式已经是
            # 最终态,而 hide→show 会抢走焦点 —— 正在输入的新任务会被
            # editingFinished 判成空任务清掉,设置窗口里的输入框也会掉焦点。
            QTimer.singleShot(0, self._reregister_for_taskbar)
        return True

    def _reregister_for_taskbar(self):
        """离开事件循环当前这一轮再隐藏/重显,让任务栏重新登记窗口。

        hide→show 会让窗口失去激活、焦点也一起掉光。用户是点着设置窗口里那个
        勾选框切过来的,焦点不该就这么没了,所以先记下焦点控件、显示回来之后再还回去
        (重显后子窗口的可见性要等下一轮才恢复,所以还焦点也要再推一轮)。
        """
        if not self.isVisible():
            return
        focused = QApplication.focusWidget()
        self.hide()
        self.show()
        if focused is not None:
            QTimer.singleShot(0, lambda: self._restore_focus(focused))

    @staticmethod
    def _restore_focus(widget):
        """把焦点还给 hide→show 之前那个控件;控件已销毁就算了。"""
        try:
            if not widget.isHidden():
                widget.setFocus()
        except RuntimeError:
            pass  # C++ 对象已经销毁(比如空任务被清掉)

    def set_show_in_taskbar(self, shown):
        """切换是否在任务栏显示图标;关掉(默认)时常驻托盘图标作为入口。

        托盘起不来(系统没托盘/托盘服务没响应)时**不许**关掉任务栏图标:
        两个入口一起没了,窗口就再也找不回来了。
        """
        shown = bool(shown)
        if not shown and self._tray is not None and not self._tray.set_visible(True):
            shown = True  # 托盘不可用 → 老实留在任务栏
        self.settings.show_in_taskbar = shown
        self._show_in_taskbar = shown
        self._apply_taskbar_style()
        if self._tray is not None:
            self._tray.set_visible(not shown)
        win = getattr(self, "_settings_win", None)
        if win is not None:
            win.set_taskbar_check(shown)
        self._settings_dirty = True
        self._settings_save_timer.start()

    # ---- 顶部栏文字 ----
    def set_title_text(self, text):
        """改顶部栏文字(设置里填的原文,空字符串表示不显示文字)。"""
        self.settings.title_text = (text or "").strip()
        self.header.set_title(self.settings.title_text)
        self._settings_dirty = True
        self._settings_save_timer.start()

    # ---- 开机自启动 ----
    def set_autostart(self, enabled):
        """开关开机自启动(写 HKCU 的 Run 项);写不进去就回滚勾选状态。"""
        ok = autostart.set_enabled(enabled)
        self.settings.autostart = enabled if ok else autostart.is_enabled()
        win = getattr(self, "_settings_win", None)
        if win is not None:
            win.set_autostart_check(self.settings.autostart, ok)
        self._settings_dirty = True
        self._settings_save_timer.start()

    def toggle_visible(self):
        """托盘图标左键:窗口可见就藏起来,藏起来了就显示并激活。"""
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self._show_and_raise()

    def _show_and_raise(self):
        """显示窗口并提到当前层级设置允许的最前面(置底态下仍是置底)。"""
        # 先兜住"被最小化/被原生隐藏"两种状态:showNormal 对隐藏窗口也安全,
        # 能保证窗口状态与 Qt 的可见性标记一致,不会出现点了没反应。
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        # show() 是必需的:只调 showNormal() 在窗口处于隐藏态时不会真的显示
        # (用户碰到的就是托盘点了以后窗口再也回不来)。
        self.show()
        self.showNormal()
        # 任务栏扩展样式(Qt 的显示流程可能重置过),重新按设置对齐一次
        QTimer.singleShot(0, self._apply_taskbar_style)
        QTimer.singleShot(0, self._apply_z_order)
        self.raise_()
        self.activateWindow()

    # ---- 固定窗口位置(禁止拖动与缩放) ----
    def set_position_fixed(self, fixed):
        """钉住/松开窗口位置。固定后拖动与边缘缩放都失效,状态跨重启保持。"""
        self.settings.position_fixed = fixed
        self._position_fixed = fixed
        self.header.fixed_btn.set_fixed(fixed)
        if fixed:
            self._drag_pos = None
            self._resize_dir = None
            self._apply_edge_cursor(None)
        win = getattr(self, "_settings_win", None)
        if win is not None:
            win.set_fixed_check(fixed)
        self._settings_dirty = True
        self._settings_save_timer.start()

    def toggle_position_fixed(self):
        self.set_position_fixed(not self._position_fixed)

    # ---- 恢复默认设置:把功能开关全部收回关闭状态 ----
    def reset_behaviour(self):
        """设置窗口点了「恢复默认设置」后,把主窗口的功能状态也收回默认。

        外观与快捷键由设置窗口自己写回;这里负责只有主窗口知道的界面状态:
        缩略模式、固定窗口位置、窗口层级(置顶/置底)、
        在任务栏显示图标(恢复成默认的"只在托盘")。
        「开机自启动」不在这里动 —— 那是注册表里的系统侧设置。
        """
        self._reveal_until = 0.0
        self._reveal_timer.stop()
        if self._compact:
            self.set_compact_mode(False, animate=False)
        if self._position_fixed:
            self.set_position_fixed(False)
        if self._always_on_bottom:
            self.set_always_on_bottom(False)
        if self._always_on_top:
            self.set_always_on_top(False)
        if self._show_in_taskbar:
            # 出厂值是"只在托盘",开着的话把任务栏图标收回
            self.set_show_in_taskbar(False)
        self._sync_pin_btn()
        self._apply_shortcuts()
        self._hide_chrome_now()
        self._settings_dirty = True
        self._settings_save_timer.start()

    def show_header_menu(self, global_pos):
        """上方栏右键菜单:退出/最小化(锁定态不弹,见 HeaderBar)。"""
        menu = QMenu(self)
        menu.addAction(t("main.menu_quit"), QApplication.quit)
        menu.addAction(t("main.menu_minimize"), self.showMinimized)
        menu.exec(global_pos)

    # ---- 边缘 8 方向 resize ----
    def _edge(self, pos):
        if self._position_fixed:  # 固定窗口位置后不允许调整窗口大小
            return None
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        # 角:用更大的 CORNER 范围优先判定,便于命中对角缩放
        left_c = x < CORNER
        right_c = x > w - CORNER
        top_c = y < CORNER
        bottom_c = y > h - CORNER
        if top_c and left_c:
            return "topleft"
        if top_c and right_c:
            return "topright"
        if bottom_c and left_c:
            return "bottomleft"
        if bottom_c and right_c:
            return "bottomright"
        # 边:用较窄的 EDGE 范围
        if x < EDGE:
            return "left"
        if x > w - EDGE:
            return "right"
        if y < EDGE:
            return "top"
        if y > h - EDGE:
            return "bottom"
        return None

    def _apply_edge_cursor(self, direction):
        """用应用级 override 光标,确保能盖过 footer 等子控件自带的光标。"""
        if direction is not None:
            cur = QCursor(self._cursor_for(direction))
            if self._cursor_overriding:
                QApplication.changeOverrideCursor(cur)
            else:
                QApplication.setOverrideCursor(cur)
                self._cursor_overriding = True
        elif self._cursor_overriding:
            QApplication.restoreOverrideCursor()
            self._cursor_overriding = False

    def _cursor_for(self, direction):
        if direction in ("left", "right"):
            return Qt.SizeHorCursor
        if direction in ("top", "bottom"):
            return Qt.SizeVerCursor
        if direction in ("topleft", "bottomright"):
            return Qt.SizeFDiagCursor
        if direction in ("topright", "bottomleft"):
            return Qt.SizeBDiagCursor
        return Qt.ArrowCursor

    def _do_resize(self, global_pos):
        g = self._resize_start_geo
        dx = global_pos.x() - self._resize_origin.x()
        dy = global_pos.y() - self._resize_origin.y()
        d = self._resize_dir
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        if "left" in d:
            new_w = max(MIN_W, w - dx)
            x = g.x() + (w - new_w)
            w = new_w
        if "right" in d:
            w = max(MIN_W, w + dx)
        if "top" in d:
            new_h = max(MIN_H, h - dy)
            y = g.y() + (h - new_h)
            h = new_h
        if "bottom" in d:
            h = max(MIN_H, h + dy)
        self.setGeometry(x, y, w, h)
        self._sync_halo()  # 缩放时光环跟着变,别等 moveEvent/resizeEvent

    def closeEvent(self, event):
        """主窗口关闭时同步关闭独立设置窗口并清理全局光标。"""
        win = getattr(self, "_settings_win", None)
        if win is not None:
            win.close()
        history_win = getattr(self, "_history_win", None)
        if history_win is not None:
            history_win.close()
        keybind_win = getattr(self, "_keybind_win", None)
        if keybind_win is not None:
            keybind_win.close()
        self._snapshot_geometry()
        self._settings_dirty = True
        self._flush_settings_save()
        self._apply_edge_cursor(None)
        # 全局热键是系统级独占的,退出前一定注销,否则这些键要等进程消失才还回去
        self._release_hotkeys()
        super().closeEvent(event)

    # ---- 拖动窗口(点空白区域拖动) + 边缘 resize----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 清单隐藏时点窗口就把装饰临时唤回来(缩略模式下点任意处即露出顶栏)
            self._reveal_chrome()
            direction = self._edge(event.position())
            if direction is not None:
                self._resize_dir = direction
                self._resize_start_geo = self.frameGeometry()
                self._resize_origin = event.globalPosition().toPoint()
                event.accept()
                return
            if self._position_fixed:  # 固定态:不启动拖动
                event.accept()
                return
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._resize_dir is not None and (event.buttons() & Qt.LeftButton):
            self._do_resize(event.globalPosition().toPoint())
            event.accept()
            return
        if self._drag_pos is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            self._sync_halo()  # 同一轮就搬,晚一个事件循环光环会落在卡片后面
            event.accept()
            return
        # 无按键:按是否在边缘更新光标
        if not event.buttons():
            direction = self._edge(event.position())
            self._apply_edge_cursor(direction)
            # 鼠标靠近顶部时把渐隐的顶栏渐显回来
            self._refresh_chrome()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_dir = None
        self._resize_start_geo = None
        self._resize_origin = None
        self._apply_edge_cursor(None)

    # ---- 鼠标进出:按需显隐顶栏/清单(图标与顶栏同进同出) ----
    def enterEvent(self, event):
        super().enterEvent(event)
        self._refresh_chrome()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._refresh_chrome()
        # 鼠标真正离开窗口且不在缩放中时,复位 resize 光标
        if self._resize_dir is None:
            self._apply_edge_cursor(None)

