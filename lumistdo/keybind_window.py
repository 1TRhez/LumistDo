"""快捷键设置窗口:给顶部栏三个功能按钮绑定快捷键。

外观与设置窗口/历史任务窗口同一套(无系统边框、圆角、羽化边缘、右上角自绘关闭
按钮、跟随主题),由 floating_window.FloatingPanel 提供。输入框直接吃按键事件,
所以支持 Ctrl+O 这类组合键,不用手打字符串。
"""

import math

from PySide6.QtWidgets import (
    QHBoxLayout, QPushButton, QLabel, QLineEdit, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QSize
from PySide6.QtGui import (
    QColor, QCursor, QIcon, QKeySequence, QPainter, QPen, QPixmap, QPolygonF,
)

from .floating_window import FloatingPanel, panel_chrome_qss, panel_widgets_qss

from .app_settings import (
    DEFAULT_SHORTCUTS, SHORTCUT_ACTIONS, normalize_sequence,
)
from .i18n import product_name, t

CONTENT_WIDTH = 340

# 控件配色全部由 floating_window 里按主题生成的 panel_widgets_qss(theme) /
# panel_chrome_qss(theme) 提供 —— 以前这里写死白 alpha 叠加,浅色主题下看不见。


def _polar(center, radius, angle_deg):
    """极坐标取点:角度按数学惯例(0 度在右,逆时针为正)。"""
    rad = math.radians(angle_deg)
    return QPointF(
        center + radius * math.cos(rad), center - radius * math.sin(rad),
    )


def reset_glyph(size, color):
    """画一个「恢复默认」圆形箭头位图(留口圆环 + 加粗箭头)。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 30.0, size / 30.0)
    center = 15.0
    radius = 6.6
    start_deg, span_deg = 60.0, 230.0
    p.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap))
    p.setBrush(Qt.NoBrush)
    p.drawArc(
        QRectF(center - radius, center - radius, radius * 2, radius * 2),
        int(start_deg * 16), int(span_deg * 16),
    )
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


class ShortcutEdit(QLineEdit):
    """吃按键的输入框:按下组合键即记录,退格清空绑定。"""

    def __init__(self, sequence="", parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setAlignment(Qt.AlignCenter)
        self.setFixedWidth(150)
        self.setSequence(sequence)

    def setSequence(self, sequence):
        """写入绑定(空串显示「未绑定」)。"""
        self._sequence = sequence or ""
        self.setText(self._sequence or t("keys.cleared"))

    def sequence(self):
        return self._sequence

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Backspace, Qt.Key_Delete):
            self.setSequence("")
            self.textEdited.emit("")
            event.accept()
            return
        if key in (
            Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
            Qt.Key_unknown,
        ):
            event.accept()   # 只按修饰键不算一次绑定
            return
        text = QKeySequence(event.keyCombination()).toString(
            QKeySequence.PortableText,
        )
        normalized = normalize_sequence(text)
        if normalized:
            self.setSequence(normalized)
            self.textEdited.emit(normalized)
        event.accept()


class KeybindWindow(FloatingPanel):
    """快捷键设置窗口(外观与设置窗口/历史任务窗口一致)。"""

    changed = Signal(dict)   # 任一绑定变动:回传完整 shortcuts 字典

    def __init__(self, settings, parent=None):
        super().__init__(
            settings, parent=parent, title=t("keys.title"),
            width=CONTENT_WIDTH,
        )
        self._edits = {}
        self._labels = {
            "z_order": t("keys.action_z_order"),
            "fixed": t("keys.action_fixed"),
            "compact": t("keys.action_compact"),
        }

        self.setWindowTitle(f"{product_name()} - {t('keys.title')}")
        self._build_ui()
        self.apply_theme()

    # ---- 界面 ----
    def _build_ui(self):
        root = self.body

        hint = QLabel(t("keys.hint"))
        hint.setObjectName("hintLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        for action in SHORTCUT_ACTIONS:
            row = QHBoxLayout()
            label = QLabel(self._labels[action])
            label.setObjectName("actionLabel")
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            row.addWidget(label, 1)
            edit = ShortcutEdit(self._settings.shortcuts.get(action, ""))
            edit.textEdited.connect(
                lambda value, name=action: self._on_edited(name, value),
            )
            self._edits[action] = edit
            row.addWidget(edit)
            root.addLayout(row)

        tip = QLabel(t("keys.hint_cleared"))
        tip.setObjectName("hintLabel")
        root.addWidget(tip)

        note = QLabel("")
        note.setObjectName("hintLabel")
        note.setVisible(False)
        self._note = note
        root.addWidget(note)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        reset_btn = QPushButton()
        reset_btn.setObjectName("actionBtn")
        reset_btn.setCursor(QCursor(Qt.PointingHandCursor))
        reset_btn.setToolTip(t("keys.reset_btn"))
        reset_btn.setIconSize(QSize(16, 16))
        reset_btn.clicked.connect(self._restore_defaults)
        self._reset_btn = reset_btn
        btn_row.addWidget(reset_btn, 1)
        close_btn = QPushButton(t("common.confirm"))
        close_btn.setObjectName("actionBtn")
        close_btn.setCursor(QCursor(Qt.PointingHandCursor))
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn, 1)
        root.addLayout(btn_row)

    def _restore_defaults(self):
        """全部恢复出厂绑定。"""
        self._settings.shortcuts = dict(DEFAULT_SHORTCUTS)
        for action, edit in self._edits.items():
            edit.setSequence(self._settings.shortcuts.get(action, ""))
        self._show_note(t("keys.done"))
        self.changed.emit(dict(self._settings.shortcuts))

    def _on_edited(self, action, value):
        """某一项被改动:重复的绑定从原来那一项上摘掉(互相顶掉,不报错)。"""
        note = ""
        if value:
            for other, current in self._settings.shortcuts.items():
                if other != action and current and current == value:
                    self._settings.shortcuts[other] = ""
                    edit = self._edits.get(other)
                    if edit is not None:
                        edit.setSequence("")
                    note = t("keys.taken", other=self._labels.get(other, other))
                    break
        self._settings.shortcuts[action] = value
        self._show_note(note)
        self.changed.emit(dict(self._settings.shortcuts))

    def _show_note(self, text):
        self._note.setText(text)
        self._note.setVisible(bool(text))

    # ---- 外观:面板基类负责背景/字体/羽化,这里只管自己的样式与图标 ----
    def _panel_qss(self, theme):
        return panel_widgets_qss(theme) + panel_chrome_qss(theme)

    def on_theme_applied(self, theme):
        self._reset_btn.setIcon(QIcon(reset_glyph(16, QColor(theme.text_color))))
