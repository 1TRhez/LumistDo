"""历史任务窗口:批量恢复或永久删除已完成/已删除任务。

外观与设置窗口、快捷键窗口同一套(无系统边框、圆角、羽化边缘、右上角自绘关闭
按钮、跟随主题),由 floating_window.FloatingPanel 提供;列表用主题色自绘,
不再写死深色。
"""

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QMessageBox,
)

from . import dialogs
from .floating_window import FloatingPanel, panel_chrome_qss
from .i18n import product_name, t

CONTENT_WIDTH = 560
TREE_HEIGHT = 300


def _rgb(color):
    """QColor → QSS 的 rgb(...)。"""
    return f"rgb({color.red()}, {color.green()}, {color.blue()})"


def _rgba(color):
    """QColor → QSS 的 rgba(...),保留 alpha。"""
    return (
        f"rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()})"
    )


class HistoryWindow(FloatingPanel):
    """展示历史任务，并执行批量恢复或永久删除。"""

    changed = Signal()

    def __init__(self, store, settings, parent=None):
        super().__init__(
            settings, parent=parent, title=t("history.title"),
            width=CONTENT_WIDTH,
        )
        self.store = store
        self.setWindowTitle(f"{product_name()} - {t('history.title')}")
        self._build_ui()
        self.apply_theme()
        self.refresh()

    # ---- 界面 ----
    def _build_ui(self):
        # 计数放在顶部条里(标题右边、关闭按钮左边),与旧版信息层级一致
        self.count_label = QLabel()
        self.count_label.setObjectName("countLabel")
        self.header.layout().insertWidget(1, self.count_label)

        self.tree = QTreeWidget()
        self.tree.setObjectName("historyTree")
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([
            t("history.col_task"), t("history.col_status"), t("history.col_time"),
        ])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.setFixedHeight(TREE_HEIGHT)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().resizeSection(0, 300)
        self.tree.header().resizeSection(1, 80)
        self.tree.header().resizeSection(2, 130)
        self.tree.itemChanged.connect(self._update_actions)
        self.body.addWidget(self.tree)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.select_all_btn = QPushButton(t("history.select_all"))
        self.select_all_btn.setObjectName("actionBtn")
        self.select_all_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.select_all_btn.clicked.connect(self._toggle_all)
        actions.addWidget(self.select_all_btn)
        actions.addStretch()
        self.restore_btn = QPushButton(t("history.restore_btn"))
        self.restore_btn.setObjectName("actionBtn")
        self.restore_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.restore_btn.clicked.connect(self.restore_selected)
        actions.addWidget(self.restore_btn)
        self.delete_btn = QPushButton(t("history.delete_btn"))
        self.delete_btn.setObjectName("dangerBtn")
        self.delete_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.delete_btn.clicked.connect(self.delete_selected)
        actions.addWidget(self.delete_btn)
        self.body.addLayout(actions)

    # ---- 主题 ----
    def _panel_qss(self, theme):
        """列表与按钮都按当前主题配色(浅色主题下原来写死的深色会瞎)。"""
        text = theme.text_color
        title = theme.fixed_title_color
        footer = theme.fixed_footer_color
        a = theme.accent_color
        accent = _rgb(a)
        sep = theme.sep_color
        sep_css = _rgba(sep)
        if theme.is_dark:
            inset = "rgba(255, 255, 255, 8)"
            inset_alt = "rgba(255, 255, 255, 3)"
            head = "rgba(255, 255, 255, 4)"
            ring = "rgba(255, 255, 255, 40)"
            btn_bg, btn_bg_hover = "rgba(255, 255, 255, 10)", "rgba(255, 255, 255, 18)"
            btn_border = "rgba(255, 255, 255, 26)"
            danger = "#ff9c9c"
        else:
            inset = "rgba(0, 0, 0, 10)"
            inset_alt = "rgba(0, 0, 0, 4)"
            head = "rgba(0, 0, 0, 5)"
            ring = "rgba(0, 0, 0, 50)"
            btn_bg, btn_bg_hover = "rgba(0, 0, 0, 12)", "rgba(0, 0, 0, 22)"
            btn_border = "rgba(0, 0, 0, 30)"
            danger = "#c0392b"
        return panel_chrome_qss(theme) + f"""
QLabel#countLabel {{
    color: {_rgb(footer)};
    font-size: 12px;
}}
QTreeWidget#historyTree {{
    background: {inset};
    alternate-background-color: {inset_alt};
    border: 1px solid {sep_css};
    border-radius: 6px;
    color: {_rgb(text)};
    outline: none;
}}
QTreeWidget#historyTree::item {{
    min-height: 28px;
    padding: 2px 4px;
}}
QTreeWidget#historyTree::item:selected {{
    background: {accent};
    color: #ffffff;
}}
QTreeWidget#historyTree::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {ring};
    border-radius: 4px;
    background: {inset};
}}
QTreeWidget#historyTree::indicator:checked {{
    background: {accent};
    border-color: {accent};
}}
QHeaderView::section {{
    background: {head};
    color: {_rgb(title)};
    border: none;
    border-bottom: 1px solid {sep_css};
    padding: 6px 6px;
}}
QPushButton#actionBtn, QPushButton#dangerBtn {{
    background: {btn_bg};
    border: 1px solid {btn_border};
    border-radius: 6px;
    color: {_rgb(text)};
    padding: 5px 12px;
}}
QPushButton#actionBtn:hover, QPushButton#dangerBtn:hover {{
    background: {btn_bg_hover};
    border-color: {accent};
}}
QPushButton#dangerBtn {{
    color: {danger};
}}
QPushButton#actionBtn:disabled, QPushButton#dangerBtn:disabled {{
    color: {_rgb(footer)};
}}
"""

    # ---- 数据 ----
    def refresh(self):
        self.tree.blockSignals(True)
        self.tree.clear()
        tasks = self.store.history_tasks()
        for task in tasks:
            status = t(
                "history.status_deleted" if task.deleted
                else "history.status_completed",
            )
            stamp = task.deleted_at or task.completed_at or task.created_at
            item = QTreeWidgetItem([
                task.text or t("history.empty_task"),
                status,
                self._format_time(stamp),
            ])
            item.setData(0, Qt.UserRole, task.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Unchecked)
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(False)
        self.count_label.setText(t("history.count", n=len(tasks)))
        self._update_actions()

    def _checked_ids(self):
        return [
            self.tree.topLevelItem(index).data(0, Qt.UserRole)
            for index in range(self.tree.topLevelItemCount())
            if self.tree.topLevelItem(index).checkState(0) == Qt.Checked
        ]

    def _toggle_all(self):
        items = [
            self.tree.topLevelItem(index)
            for index in range(self.tree.topLevelItemCount())
        ]
        check = Qt.Unchecked if items and all(
            item.checkState(0) == Qt.Checked for item in items
        ) else Qt.Checked
        self.tree.blockSignals(True)
        for item in items:
            item.setCheckState(0, check)
        self.tree.blockSignals(False)
        self._update_actions()

    def _update_actions(self):
        count = len(self._checked_ids())
        self.restore_btn.setEnabled(count > 0)
        self.delete_btn.setEnabled(count > 0)
        self.restore_btn.setText(
            t("history.restore_btn_n", n=count) if count
            else t("history.restore_btn")
        )
        self.delete_btn.setText(
            t("history.delete_btn_n", n=count) if count
            else t("history.delete_btn")
        )

    # ---- 动作 ----
    def restore_selected(self):
        ids = self._checked_ids()
        if not ids:
            return
        self.store.restore_many(ids)
        self.refresh()
        self.changed.emit()

    def delete_selected(self, confirm=True):
        ids = self._checked_ids()
        if not ids:
            return
        if confirm:
            answer = dialogs.question(
                self,
                t("history.delete_btn"),
                t("history.delete_confirm", n=len(ids)),
            )
            if answer != QMessageBox.Yes:
                return
        self.store.permanent_delete(ids)
        self.refresh()
        self.changed.emit()

    @staticmethod
    def _format_time(value):
        try:
            return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            return ""
