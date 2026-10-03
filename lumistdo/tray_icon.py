"""系统托盘图标:任务栏不显示图标时,用它把窗口找回来。

只在「不显示在任务栏」打开时出现:
左键单击显示/隐藏主窗口,右键菜单可显示窗口或退出程序。
Qt 自带 QSystemTrayIcon,不依赖第三方库。
"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .app_paths import icon_file
from .i18n import product_name, t


class TrayIcon(QObject):
    """托盘图标 + 右键菜单,负责主窗口的显示/隐藏与退出。"""

    toggle_requested = Signal()

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self._tray = QSystemTrayIcon(self)
        path = icon_file()
        if path.exists():
            self._tray.setIcon(QIcon(str(path)))
        else:
            self._tray.setIcon(window.windowIcon())
        self._tray.setToolTip(product_name())
        self._tray.activated.connect(self._on_activated)
        self._tray.setContextMenu(self._build_menu())

    def _build_menu(self):
        menu = QMenu()
        self._toggle_action = menu.addAction(t("tray.toggle"))
        self._toggle_action.triggered.connect(self.toggle_requested.emit)
        menu.addSeparator()
        quit_action = menu.addAction(t("tray.quit"))
        quit_action.triggered.connect(QApplication.instance().quit)
        return menu

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # 左键单击:显示/隐藏
            self.toggle_requested.emit()

    def set_visible(self, visible):
        """显示或隐藏托盘图标;系统无托盘时静默跳过。"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False
        if visible:
            self._tray.show()
        else:
            self._tray.hide()
        return True

    def is_visible(self):
        return self._tray.isVisible()

    def refresh_texts(self):
        """语言切换后重建菜单文案(重启生效,这里兜底)。"""
        self._tray.setContextMenu(self._build_menu())
