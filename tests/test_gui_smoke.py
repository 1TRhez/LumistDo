"""GUI 冒烟测试:在 offscreen 平台验证核心交互流程,不弹真实窗口。"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import tempfile
import time
from pathlib import Path

import pytest
from PySide6.QtCore import (
    Qt, QEvent, QPointF, QPoint, QTimer, QAbstractAnimation,
)
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit

from lumistdo.main_window import MainWindow, build_qss
from lumistdo import global_hotkeys
from lumistdo.app_settings import (
    CUSTOM_PRESET,
    DEFAULT_PRESET,
    DEFAULT_SHORTCUTS,
    DEFAULT_TITLE_TEXT,
    AppSettings,
)
from lumistdo.completed_panel import build_panel_qss
from lumistdo.i18n import t
from lumistdo.settings_dialog import CONTENT_WIDTH, SettingsWindow
from lumistdo.task_store import TaskStore


@pytest.fixture(autouse=True)
def _window_level_shortcuts(monkeypatch):
    """测试里一律关掉全局热键,退回窗口级 QShortcut。

    offscreen 平台下 `QWidget.winId()` 返回占位值 1(不是真 HWND),
    `RegisterHotKey` 必然失败并报 1400 ERROR_INVALID_WINDOW_HANDLE ——
    所以真机上不存在的"注册失败"路径在这里反而是常态,用它测不出
    "全局热键真的挂上了没有"。真机行为由 tests/test_global_hotkeys.py
    里的真注册用例覆盖,这里只保证其余交互测试稳定可跑。
    """
    monkeypatch.setattr(global_hotkeys, "supported", lambda: False)


@pytest.fixture(autouse=True)
def _tray_available(monkeypatch):
    """默认假装系统托盘可用 —— 真机上它就是可用的。

    MainWindow 有一条安全兜底:托盘拿不到时**不许**关掉任务栏图标,
    否则两个入口一起没,窗口就再也找不回来了。offscreen 下
    `QSystemTrayIcon.isSystemTrayAvailable()` 恒为假,会让"关掉任务栏图标"
    这类动作被兜底改写、相关断言全部失效,所以这里默认放行;
    兜底路径单独由 test_tray_unavailable_keeps_taskbar_icon 覆盖。
    """
    monkeypatch.setattr(
        "lumistdo.tray_icon.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: True),
    )


@pytest.fixture
def app():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture(autouse=True)
def _isolate_windows(app):
    """保证每条用例从"没有别的窗口"开始。

    MainWindow 是常驻可见窗口,用例里若某条断言提前失败,窗口不会走到
    w.close() 就留在进程里:它持有的编辑框仍是"当前焦点控件",下一条用例
    start_edit() 时 Qt 会把这次焦点切换的 FocusOut 投递到遗留编辑框上,
    触发那个窗口的提交逻辑。实测这会让 test_edit_height_follows_task_text
    单独跑通过、整套跑必挂(assert 66 == 19)。用例收尾时统一关窗最省事。
    """
    def _close_all():
        for widget in list(QApplication.topLevelWidgets()):
            if widget.isVisible():
                widget.close()
        app.processEvents()

    _close_all()
    yield
    _close_all()


def _mouse(kind, pos, window, app):
    """造一个窗口内坐标的鼠标事件(局部坐标 + 换算后的全局坐标)。"""
    return QMouseEvent(
        kind,
        QPointF(pos),
        QPointF(window.mapToGlobal(pos)),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )


def _window(root, store=None):
    """建一个完全隔离的 MainWindow(设置写进临时目录)。

    不能省 settings_path:那样会去读本机 %APPDATA%\\LumistDo\\settings.json,
    真实设置里的窗口尺寸/缩略模式会让测试结果随开发机状态漂移。
    """
    if store is None:
        store = TaskStore(root / "tasks.json")
    return MainWindow(store, settings_path=root / "settings.json")


def test_task_scrollbars_share_wider_hover_handle():
    theme = AppSettings().to_theme()
    main_qss = build_qss(theme)
    completed_qss = build_panel_qss(theme)

    for qss in (main_qss, completed_qss):
        assert "width: 9px" in qss
        assert "margin: 0 3px" in qss
        assert "QScrollBar::handle:vertical:hover" in qss
        assert "margin: 0 1px" in qss


def test_core_flow(app):
    """创建 → 完成 → 恢复 → 编辑 → 空任务删除 → 持久化。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        store.add("买牛奶")
        store.add("写报告")
        store.add("回邮件")
        w = _window(Path(d), store)
        w.show()
        app.processEvents()

        # 3 个活跃任务显示在列表
        assert len(w._active_items) == 3

        # 完成第一个
        first = list(w._active_items.keys())[0]
        w.on_complete(first)
        app.processEvents()
        assert len(w._active_items) == 2
        assert len(store.completed_tasks()) == 1
        assert w.footer_btn.text().startswith("已完成  1")

        # 展开已完成面板并恢复
        w.toggle_completed()
        assert w.completed_panel.isVisible()
        w.on_restore(first)
        app.processEvents()
        assert len(w._active_items) == 3
        assert len(store.completed_tasks()) == 0
        assert w.footer_btn.text().startswith("已完成  0")

        # 新建任务并填文本(默认展示 label,需先进入编辑态)
        w.add_task()
        app.processEvents()
        new_item = list(w._active_items.values())[-1]
        new_item.start_edit()
        new_item.edit.setPlainText("新任务")
        new_item._on_editing_finished()
        app.processEvents()
        assert len(w._active_items) == 4
        new_id = list(w._active_items.keys())[-1]
        assert store.get(new_id).text == "新任务"

        # 空任务失焦应被删除
        w.add_task()
        app.processEvents()
        empty_item = list(w._active_items.values())[-1]
        empty_item.start_edit()
        empty_item.edit.setPlainText("")
        empty_item._on_editing_finished()
        app.processEvents()
        assert len(w._active_items) == 4  # 空的被删,回到 4

        # 持久化:重开后活跃任务数一致
        store2 = TaskStore(Path(d) / "tasks.json")
        assert len(store2.active_tasks()) == len(store.active_tasks())


def test_empty_task_completed_is_deleted(app):
    """空任务被点完成时直接删除,不进已完成栏。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        w.add_task()
        app.processEvents()
        empty_id = list(w._active_items.keys())[-1]
        w.on_complete(empty_id)
        app.processEvents()
        assert len(w._active_items) == 0
        assert len(store.completed_tasks()) == 0
        assert store.get(empty_id) is None


def test_empty_new_task_leaves_no_history_record(app):
    """点 + 后未输入任何内容就失焦,不应在历史记录留下空任务。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        w.add_task()
        app.processEvents()
        empty_item = list(w._active_items.values())[-1]
        empty_item.start_edit()
        empty_item._on_editing_finished()  # 模拟未输入直接点空白处失焦
        app.processEvents()

        assert len(w._active_items) == 0
        assert store.history_tasks() == []
        assert store.tasks == []


def test_persistence_reload_restores_ui(app):
    """重开后 UI 正确恢复活跃/已完成任务。"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "tasks.json"
        s1 = TaskStore(p)
        s1.add("活跃任务")
        done = s1.add("已完成任务")
        s1.complete(done.id)

        s2 = TaskStore(p)
        w = MainWindow(s2)
        w.show()
        app.processEvents()
        assert len(w._active_items) == 1
        assert w.footer_btn.text().startswith("已完成  1")


def test_lock_hides_controls_and_unlock_restores(app):
    """锁定后隐藏控件和滚动条，分隔线随文本左移，解锁恢复。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        for index in range(20):
            store.add(f"任务 {index}")
        w = _window(Path(d), store)
        w.show()
        app.processEvents()
        item = list(w._active_items.values())[0]
        bar = w.scroll.verticalScrollBar()
        unlocked_separator_left = item._separator_left()
        assert item.dot.isVisible()
        assert bar.isVisible()
        assert w.scroll.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded

        w.set_compact_mode(True)
        app.processEvents()
        assert not item.dot.isVisible()
        assert item._separator_left() == item.stack.geometry().left()
        assert item._separator_left() < unlocked_separator_left
        stack_left = item.stack.mapTo(w, QPoint()).x()
        stack_right = stack_left + item.stack.width()
        assert stack_left == w.width() - stack_right
        assert not w._inline_add_btn.isVisible()
        # 缩略模式不再逐个隐藏顶栏图标,而是整块顶栏淡出(图标与顶栏同进同出)
        assert w.header.compact_btn.isVisible()
        assert w.header.compact_btn._compact is True
        assert not w.footer_btn.isVisible()
        assert not bar.isVisible()
        assert w.scroll.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff

        w.set_compact_mode(False)
        app.processEvents()
        assert item.dot.isVisible()
        assert w.header.compact_btn.isVisible()
        assert w.header.compact_btn._compact is False
        assert bar.isVisible()
        assert w.scroll.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded


def test_click_compact_icon_toggles_compact_mode(app):
    """回归:点击右上缩略模式图标可进入/退出,再点一次立即恢复全部控件。

    用 QTest.mouseClick 真实走一遍事件管线(含窗口 eventFilter),
    防止点击被边缘缩放逻辑吞掉、或退出后控件可见性不刷新。
    """
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        store.add("任务一")
        w = _window(Path(d), store)
        w.show()
        app.processEvents()
        item = list(w._active_items.values())[0]

        QTest.mouseClick(w.header.compact_btn, Qt.LeftButton, pos=QPoint(14, 14))
        app.processEvents()
        assert w._locked
        assert not item.dot.isVisible()
        assert not w._inline_add_btn.isVisible()
        assert not w.footer_btn.isVisible()

        QTest.mouseClick(w.header.compact_btn, Qt.LeftButton, pos=QPoint(14, 14))
        app.processEvents()
        assert not w._locked
        assert item.dot.isVisible()
        assert w._inline_add_btn.isVisible()
        assert w.footer_btn.isVisible()


def test_compact_mode_still_allows_resize(app):
    """缩略模式下窗口仍可缩放;只有「固定窗口位置」才禁止拖动与缩放。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        w.set_compact_mode(True)
        app.processEvents()
        assert w._locked is True
        assert w._edge(QPointF(2.0, 2.0)) is not None   # 缩略模式仍能拖边缘缩放

        w.set_position_fixed(True)
        assert w._edge(QPointF(2.0, 2.0)) is None       # 固定后禁止缩放
        w.set_position_fixed(False)
        assert w._edge(QPointF(2.0, 2.0)) is not None


def test_compact_mode_fades_header_instead_of_hiding_buttons(app):
    """缩略模式:顶栏整块渐隐(留圆角外框),鼠标靠近顶部时渐显。

    必须替掉 _cursor_near_top:offscreen 平台没有真实鼠标,QCursor.pos()
    恒为屏幕原点 (10,10),正好落在窗口左上角的顶栏范围内,不替的话
    "鼠标离开顶栏"这个前提在测试里永远不成立。
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        w._cursor_near_top = lambda: False       # 鼠标不在顶栏那一带
        w.set_compact_mode(True, animate=False)
        app.processEvents()
        assert w._header_opacity == 0.0          # 顶栏已渐隐
        assert w.header.isVisible() is False     # 淡出结束后才真正隐藏
        assert w._scroll_opacity == 1.0          # 清单照常显示

        w._cursor_near_top = lambda: True        # 模拟鼠标贴到窗口顶部
        w._refresh_chrome(animate=False)
        app.processEvents()
        assert w._header_opacity == 1.0
        assert w.header.isVisible() is True
        # 图标与顶栏同进同出:不再有"顶栏在、图标自己消失"的状态
        for btn in w._header_icon_btns():
            assert btn.isVisible() is True
            assert btn.parent() is w.header


def test_compact_mode_hides_header_only(app):
    """缩略模式只隐去顶栏;鼠标贴到顶部那一带时顶栏渐显回来,清单一直在。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        w._cursor_near_top = lambda: False       # offscreen 下鼠标恒在原点,必须替掉
        w.set_compact_mode(True, animate=False)
        app.processEvents()
        assert w._header_opacity == 0.0
        assert w._scroll_opacity == 1.0          # 清单不受缩略模式影响

        w._cursor_near_top = lambda: True        # 鼠标贴到顶部:顶栏回来
        w._refresh_chrome(animate=False)
        app.processEvents()
        assert w._header_opacity == 1.0
        assert w._scroll_opacity == 1.0


def test_macos_style_header_structure(app):
    """标题栏保留标语与锁头图标、底部保留行内加号。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        # 用临时设置文件:否则会读到本机 %APPDATA% 里的真实设置(标题可能被改过)
        w = MainWindow(store, settings_path=root / "settings.json")

        # 默认标题 = 产品名(标签层转大写、真实内容保持原样),
        # 取自 DEFAULT_TITLE_TEXT 以免改默认值就挂
        assert w.header._raw_title == DEFAULT_TITLE_TEXT
        assert w.header.title_label.text() == DEFAULT_TITLE_TEXT.upper()
        assert w.header.height() == 40
        assert w.header.compact_btn.width() == 28
        assert w._inline_add_btn.height() == 36
        assert "font-size: 20px" in w.container.styleSheet()


def test_clearing_header_title_hides_the_label(app):
    """顶部栏文字留空 = 不显示文字(不是回落到默认标语)。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        assert w.header.title_label.isVisible(), "默认应该显示默认标语"

        w.set_title_text("")
        app.processEvents()
        assert w.header._raw_title == ""
        assert w.settings.title_text == ""
        assert not w.header.title_label.isVisible(), "留空后标题标签应该隐藏"

        # 设置窗口里清空输入框同样立即隐藏
        w.open_settings()
        app.processEvents()
        w._settings_win._title_edit.setText("FOCUS")
        app.processEvents()
        assert w.header.title_label.isVisible()
        w._settings_win._title_edit.setText("")
        app.processEvents()
        assert not w.header.title_label.isVisible(), "输入框清空后标题标签应该隐藏"

        w.set_title_text("FOCUS")
        app.processEvents()
        assert w.header.title_label.isVisible(), "重新填了文字应该恢复显示"
        assert w.header.title_label.text() == "FOCUS"
        w.close()


def test_settings_window_is_frameless_dark_and_closable(app):
    """设置窗口自绘外观:无系统边框、半透明底、右上角自绘 × 能关掉它。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()
        win = w._settings_win

        assert win.windowFlags() & Qt.FramelessWindowHint, "还有系统边框"
        assert win.testAttribute(Qt.WA_TranslucentBackground), "圆角外没有透明底"
        assert win.windowFlags() & Qt.WindowStaysOnTopHint, "应始终在置底的主窗口之上"
        # 与主界面同一套底色/圆角/透明度
        qss = win.container.styleSheet()
        theme = w.settings.to_theme()
        assert f"rgba({theme.bg_color.red()}, {theme.bg_color.green()}," in qss
        assert f"{theme.bg_opacity}" in qss
        assert "border-radius: 8px" in qss
        assert win.font().family() == theme.font_family, "字体没跟随设置"
        # 宽度 = 内容宽 + 左右各 8px 羽化留白
        assert win.width() == CONTENT_WIDTH + 16
        assert win.container.width() == CONTENT_WIDTH

        win.header.close_btn.clicked.emit()
        app.processEvents()
        assert not win.isVisible(), "自绘关闭按钮没关掉设置窗口"
        w.close()


def test_settings_footer_buttons_fit_without_eliding(app):
    """底部按钮条三个控件等宽等距,文字都不被挤成省略号。"""
    from PySide6.QtWidgets import QPushButton

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()
        win = w._settings_win

        buttons = [
            btn for btn in win.container.findChildren(QPushButton) if btn.text()
        ]
        texts = {btn.text() for btn in buttons}
        assert t("settings.keybind_btn") in texts
        assert t("settings.history_btn") in texts
        assert t("settings.save_preset_btn") not in texts   # 用户要求删掉这一项
        for btn in buttons:
            needed = btn.minimumSizeHint().width()
            assert btn.width() >= needed, (
                f"按钮「{btn.text()}」被压到 {btn.width()}px,至少需要 {needed}px"
            )
        # 三格等宽:编辑快捷键 / 恢复默认(图标) / 查看历史
        # (offscreen 下字体度量退化、宽高比真机大,所以只断言"间距一致",宽度由布局自适应)
        row = win._keybind_btn.parentWidget().layout()
        assert row.spacing() == 10
        row_width = sum(btn.sizeHint().width() for btn in buttons)
        row_width += win._reset_btn.width() + 8 * 2
        assert row_width <= CONTENT_WIDTH - 40, (
            f"底部按钮条需要 {row_width}px,可用 {CONTENT_WIDTH - 40}px"
        )
        w.close()


def test_settings_header_drag_moves_window(app):
    """无系统边框后,按住顶部条空白处仍然能拖动设置窗口。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()
        win = w._settings_win
        win.move(200, 200)
        app.processEvents()
        start = win.pos()

        header = win.header
        pos = QPoint(header.width() // 2, header.height() // 2)
        header.mousePressEvent(_mouse(QEvent.MouseButtonPress, pos, header, app))
        header.mouseMoveEvent(_mouse(QEvent.MouseMove, pos + QPoint(40, 25), header, app))
        header.mouseReleaseEvent(_mouse(QEvent.MouseButtonRelease, pos, header, app))
        app.processEvents()

        assert win.pos() == start + QPoint(40, 25), "顶部条拖动没生效"
        w.close()


def test_settings_reset_appearance_restores_defaults(app, monkeypatch):
    """恢复默认设置:外观、快捷键与功能开关一起回默认。"""
    from lumistdo import settings_dialog

    monkeypatch.setattr(settings_dialog, "dialogs", _AutoConfirmDialogs())

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()
        win = w._settings_win

        # 先把外观改花,并把各种功能开关全打开
        win._title_edit.setText("乱改的标题")
        win._size_spin.setValue(20)
        win._op_slider.setValue(30)
        win._bg_color = QColor("#ff00ff")
        win._emit_changed()
        win._mark_custom_preset()
        win._layer_radios["top"].setChecked(True)
        win._fixed_check.setChecked(True)
        win._taskbar_check.setChecked(True)   # 「在任务栏显示图标」= 反着出厂值来
        w.settings.shortcuts = {"z_order": "Ctrl+9", "fixed": "", "compact": ""}
        w.set_compact_mode(True, animate=False)
        app.processEvents()
        assert w.settings.title_text == "乱改的标题"
        assert w.settings.always_on_top is True
        assert w.settings.appearance_preset == CUSTOM_PRESET

        # 恢复默认设置:外观、快捷键与功能开关一起回默认
        defaults = AppSettings()
        win._reset_appearance()
        app.processEvents()

        assert w.settings.title_text == DEFAULT_TITLE_TEXT
        assert (w.settings.bg_color, w.settings.text_color) == (
            defaults.bg_color, defaults.text_color,
        )
        assert w.settings.font_size == defaults.font_size
        assert w.settings.bg_opacity == defaults.bg_opacity
        # 快捷键一起回默认(出厂值见 app_settings.DEFAULT_SHORTCUTS)
        assert w.settings.shortcuts == DEFAULT_SHORTCUTS
        # 界面控件也同步回默认值
        assert win._title_edit.text() == DEFAULT_TITLE_TEXT
        assert win._size_spin.value() == defaults.font_size
        assert win._op_slider.value() == defaults.bg_opacity
        # 功能开关全部回到关闭状态(用户要求:除了任务列表以外的所有功能都重置到关闭)
        assert w.settings.always_on_top is False
        assert w.settings.always_on_bottom is False
        assert w.settings.position_fixed is False
        assert w.settings.compact_mode is False
        # 「在任务栏显示图标」也回到出厂值(默认关:只在托盘)
        assert w.settings.show_in_taskbar == defaults.show_in_taskbar
        assert win._taskbar_check.isChecked() == defaults.show_in_taskbar
        # 预设高亮也要回到默认那个(否则色块回到深空、圆点还停在自定义上)
        assert w.settings.appearance_preset == DEFAULT_PRESET
        assert win._preset_btns[DEFAULT_PRESET].property("selected") == "true"
        assert win._custom_btn.property("selected") == "false"
        # 界面状态也一起收掉了:顶栏回来、清单可点
        assert w._compact is False
        assert w._header_opacity == 1.0
        assert w.header.isVisible() is True
        w.close()


def test_preset_row_highlights_current_and_marks_custom(app):
    """预设行:点哪套主题就亮哪个圆点;手改颜色后亮最右边的自定义入口。"""
    from lumistdo import settings_dialog

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()
        win = w._settings_win

        # 默认亮「深空」
        assert w.settings.appearance_preset == DEFAULT_PRESET
        assert win._preset_btns[DEFAULT_PRESET].property("selected") == "true"

        # 森林已删掉,换成毛玻璃
        assert "森林" not in win._preset_btns
        assert "毛玻璃" in win._preset_btns
        preset = next(p for p in settings_dialog.PRESETS if p["name"] == "毛玻璃")
        win._preset_btns["毛玻璃"].click()
        app.processEvents()
        assert w.settings.appearance_preset == "毛玻璃"
        assert w.settings.bg_color == preset["bg"]
        assert w.settings.bg_opacity == preset["opacity"], "毛玻璃要真的更透明"
        assert preset["blur"] is True, "毛玻璃预设要顺带打开背后的模糊"
        assert w.settings.blur_behind is True
        assert win._blur_check.isChecked() is True
        assert win._preset_btns["毛玻璃"].property("selected") == "true"
        assert win._preset_btns[DEFAULT_PRESET].property("selected") == "false"

        # 手动改背景色 → 不再等于任何预设,高亮转到自定义入口
        win._bg_color = QColor("#123456")
        win._emit_changed()
        win._mark_custom_preset()
        app.processEvents()
        assert w.settings.appearance_preset == CUSTOM_PRESET
        assert win._custom_btn.property("selected") == "true"
        assert win._preset_btns["毛玻璃"].property("selected") == "false"
        w.close()


def test_blur_behind_toggle_drives_the_window_effect(app, monkeypatch):
    """毛玻璃开关:勾上要把真·模糊下发给窗口,换实底预设要关掉,重启后还记得。"""
    from lumistdo import blur_behind

    calls = []
    monkeypatch.setattr(
        blur_behind, "set_blur_behind",
        lambda hwnd, enabled, tint=(0, 0, 0, 0): calls.append(enabled) or True,
    )
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        settings_path = root / "settings.json"
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=settings_path)
        w.show()
        app.processEvents()
        assert w.settings.blur_behind is False, "默认不该开毛玻璃"

        w.open_settings()
        app.processEvents()
        win = w._settings_win
        calls.clear()
        win._blur_check.setChecked(True)
        app.processEvents()
        assert w.settings.blur_behind is True
        assert True in calls, "勾上毛玻璃没有把模糊下发给窗口"
        # 只是开关一件效果,配色没动,高亮不该跳到"自定义配色"
        assert w.settings.appearance_preset == DEFAULT_PRESET

        # 换一套实底预设:连带把模糊关掉(实底开着也看不出来,留着只会误导)
        calls.clear()
        win._preset_btns["素白"].click()
        app.processEvents()
        assert w.settings.blur_behind is False
        assert win._blur_check.isChecked() is False
        assert False in calls, "关掉毛玻璃没有通知窗口撤销模糊"

        # 再开一次并落盘,重启后要记得
        win._blur_check.setChecked(True)
        app.processEvents()
        w._flush_settings_save()
        w.close()
        w2 = MainWindow(TaskStore(root / "tasks.json"), settings_path=settings_path)
        w2.show()
        app.processEvents()
        assert w2.settings.blur_behind is True, "毛玻璃开关没存进设置文件"
        w2.close()


def test_frost_flushes_panel_to_window_edges(app, monkeypatch):
    """开毛玻璃时容器必须铺满窗口。

    模糊的是整个窗口矩形(Win10 上裁不住、也圆不了,详见 AGENTS.md),
    容器内缩多少,糊出来的那块就比可见背景大多少 —— 所以开模糊就把边距压成 0,
    关掉再收回来(边缘羽化要那圈环带)。
    """
    from lumistdo import blur_behind

    monkeypatch.setattr(
        blur_behind, "set_blur_behind",
        lambda hwnd, enabled, tint=(0, 0, 0, 0): True,
    )

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        w = MainWindow(TaskStore(root / "tasks.json"), settings_path=root / "settings.json")

        def edge_margins():
            m = w.layout().contentsMargins()
            return (m.left(), m.top(), m.right(), m.bottom())

        w.show()
        app.processEvents()
        w.layout().activate()

        assert edge_margins() == (8, 8, 8, 8), "没开毛玻璃时边距该是 8"
        assert w.container.geometry() == w.rect().adjusted(8, 8, -8, -8)
        assert "border-radius: 8px" in w.container.styleSheet()

        w.settings.blur_behind = True
        w._apply_blur_behind()
        app.processEvents()
        w.layout().activate()
        assert edge_margins() == (0, 0, 0, 0), "开毛玻璃后容器没铺满窗口"
        assert w.container.geometry() == w.rect(), "容器没和窗口对齐,模糊会比背景大一圈"
        # 圆角保留:容器铺满窗口后糊区与面板同大,四角只差十来平方像素的残糊
        assert "border-radius: 8px" in w.container.styleSheet()

        w.settings.blur_behind = False
        w._apply_blur_behind()
        app.processEvents()
        w.layout().activate()
        assert edge_margins() == (8, 8, 8, 8), "关掉毛玻璃后边距没收回"
        assert w.container.geometry() == w.rect().adjusted(8, 8, -8, -8)
        assert "border-radius: 8px" in w.container.styleSheet()
        w.close()


def test_custom_color_window_edits_colors_and_flags_custom(app):
    """自定义配色窗口:改色即时写进设置、主窗口与设置窗口色块同步、高亮转自定义。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()
        win = w._settings_win

        win._custom_btn.click()
        app.processEvents()
        cw = win._custom_win
        assert cw is not None and cw.isVisible()

        # 窗口自带一套自绘外观:无边框 + 透明底 + 与设置窗口同宽
        assert cw.windowFlags() & Qt.FramelessWindowHint
        assert cw.testAttribute(Qt.WA_TranslucentBackground)
        assert cw.width() == win.width()

        # 改背景色(不走取色器,直接改色块走同一条回传路径)
        cw._settings.bg_color = "#204060"
        cw._emit()
        app.processEvents()
        assert w.settings.bg_color == "#204060"
        assert w.settings.appearance_preset == CUSTOM_PRESET
        assert win._custom_btn.property("selected") == "true"
        assert win._bg_btn.property("color") == "#204060", "设置窗口色块没跟上"

        # 窗口里的「恢复默认配色」把颜色与高亮一起还原成默认预设
        # (点按钮 → 设置窗口接管,而不是窗口自己直接改设置)
        cw.reset_btn.click()
        app.processEvents()
        defaults = AppSettings()
        assert w.settings.bg_color == defaults.bg_color
        assert w.settings.text_color == defaults.text_color
        assert w.settings.appearance_preset == DEFAULT_PRESET
        assert win._preset_btns[DEFAULT_PRESET].property("selected") == "true"
        w.close()


def test_reset_confirm_text_describes_feature_switches_too():
    """恢复默认的确认文案必须说清功能开关也会关掉,并且提到自启动不受影响。

    重置范围变宽后文案若还写"只重置外观",用户会以为层级/缩略这些不受影响。
    """
    import lumistdo.i18n as i18n

    for lang in ("zh", "en"):
        text = i18n._TRANSLATIONS[lang]["settings.reset_confirm"]
        assert "开机自启动" in text or "Start with Windows" in text, (
            f"{lang}: 没说明开机自启动不受影响"
        )
        assert "缩略" in text or "compact" in text, (
            f"{lang}: 没说明缩略模式会被关掉"
        )
        assert "固定窗口位置" in text or "fix position" in text, (
            f"{lang}: 没说明固定窗口位置会被关掉"
        )
    assert i18n._TRANSLATIONS["zh"]["settings.reset_done"] == "已恢复默认设置。"


class _FakeMessageBox:
    """替身弹窗:exec() 什么都不做,clickedButton() 返回同一批按钮对象。

    注意按钮必须是"同一个对象":真实代码用 `is` 比较点击的按钮,
    每次新建字符串/对象会让比较恒为 False。
    """

    def __init__(self):
        from lumistdo.i18n import t as _t

        self.confirm_button = object()
        self.cancel_button = object()
        self._texts = (_t("common.confirm"), _t("common.cancel"))
        self._buttons = [self.confirm_button, self.cancel_button]

    def setWindowTitle(self, _text):
        pass

    def setText(self, _text):
        pass

    def addButton(self, _text, _role):
        return self._buttons.pop(0)

    def exec(self):
        return 0

    def clickedButton(self):
        return self.confirm_button


class _AutoConfirmDialogs:
    """把 dialogs 模块包一层:确认框自动点「确定」,信息框不弹。"""

    def message_box(self, _parent=None):
        return _FakeMessageBox()

    def information(self, *_args, **_kwargs):
        return 0


def test_task_rows_stay_compact_when_window_grows(app):
    """窗口变高时，任务行保持紧凑，额外空间留在列表底部。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        store.add("任务一")
        store.add("任务二")
        w = _window(Path(d), store)
        w.show()
        app.processEvents()

        heights_before = [item.height() for item in w._active_items.values()]
        assert max(heights_before) <= 48
        w.resize(w.width(), w.height() + 240)
        app.processEvents()
        heights_after = [item.height() for item in w._active_items.values()]

        assert heights_after == heights_before


def test_edit_height_follows_task_text(app):
    """编辑框只占文本所需高度，多行内容再相应增长。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        task = store.add("短任务")
        w = _window(Path(d), store)
        w.show()
        app.processEvents()

        item = w._active_items[task.id]
        item.start_edit()
        app.processEvents()
        single_line_height = item.edit.height()
        assert not item.edit.textCursor().hasSelection()
        assert item.edit.minimumHeight() == item.edit.maximumHeight()
        assert single_line_height >= item.edit.fontMetrics().lineSpacing() + 14

        item.edit.setPlainText("第一行\n第二行\n第三行")
        app.processEvents()
        assert item.edit.height() > single_line_height
        assert item.edit.height() == item.stack.height()
        assert item.edit.verticalScrollBar().maximum() == 0
        assert item.edit.verticalScrollBar().value() == 0

        item._on_editing_finished()
        app.processEvents()
        assert item.stack.height() == item.label.height()
        assert item.height() >= item.dot.height() + 8

        item.start_edit()
        app.processEvents()
        assert item.edit.toPlainText() == "第一行\n第二行\n第三行"
        assert item.edit.height() > single_line_height
        assert not item.edit.textCursor().hasSelection()
        assert item.edit.verticalScrollBar().maximum() == 0
        assert item.edit.verticalScrollBar().value() == 0


def test_long_text_stays_visible_after_reopening_and_resizing(app):
    """长文本重新编辑和缩窄窗口后，编辑框仍完整容纳文本。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        text = "这是一段用于验证自动换行和重新编辑的较长任务文本。" * 4
        task = store.add(text)
        w = _window(Path(d), store)
        w.show()
        app.processEvents()

        item = w._active_items[task.id]
        item.start_edit()
        app.processEvents()
        first_height = item.edit.height()
        assert item.edit.textCursor().position() == len(text)
        assert not item.edit.textCursor().hasSelection()

        item._on_editing_finished()
        w.resize(220, w.height())
        app.processEvents()
        assert item.label.height() >= item.label.heightForWidth(item.label.width())

        item.start_edit()
        app.processEvents()
        assert item.edit.toPlainText() == text
        assert item.edit.textCursor().position() == len(text)
        assert item.edit.height() >= first_height
        assert item.edit.verticalScrollBar().maximum() == 0
        assert item.edit.verticalScrollBar().value() == 0


def test_unbreakable_long_string_wraps_and_does_not_stretch_window(app):
    """连续无空格长串(如纯数字)应换行显示,且不把任务行撑到内容宽度。

    历史 bug 1:QLabel.wordWrap 只在词边界换行,纯数字/无空格长串没有
    断行点,minimumSizeHint 返回整行宽度,把任务行和窗口撑爆。
    修复:展示文本经 _wrap_for_label 在每个字符后注入零宽空格(U+200B)
    提供断行点;label 水平方向用 QSizePolicy.Ignored,宽度不参与布局。
    store 里的文本始终是原始内容,不含零宽空格。
    """
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        task = store.add("1" * 364)
        store.add("正常任务")
        w = _window(Path(d), store)
        w.resize(320, 460)
        w.show()
        for _ in range(5):
            app.processEvents()

        item = w._active_items[task.id]
        # 数字长串确实换行了:高度超过单行行高
        assert item.label.height() > item.label.fontMetrics().lineSpacing() + 1
        # 任务行宽度受窗口约束,不被长串撑开
        assert item.width() <= w.width()
        assert item.stack.width() <= w.width()
        # 行高足够容纳全部换行后的文本
        assert item.label.height() >= item.label.heightForWidth(item.label.width())

        # 缩窄窗口后约束依然成立,且换行更多(高度增加)
        h_before = item.label.height()
        w.resize(220, w.height())
        for _ in range(5):
            app.processEvents()
        assert item.stack.width() <= w.width()
        assert item.label.height() > h_before

        # store 不被零宽空格污染
        assert "​" not in store.get(task.id).text

        # 重开后同样成立
        store2 = TaskStore(Path(d) / "tasks.json")
        w2 = MainWindow(store2)
        w2.resize(320, 460)
        w2.show()
        for _ in range(5):
            app.processEvents()
        item2 = w2._active_items[task.id]
        assert item2.stack.width() <= w2.width()
        assert item2.label.height() > item2.label.fontMetrics().lineSpacing() + 1


def test_long_press_drag_reorders_tasks_and_persists(app):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        path = root / "tasks.json"
        store = TaskStore(path)
        first = store.add("第一")
        second = store.add("第二")
        third = store.add("第三")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        item = w._active_items[first.id]
        target = w._active_items[third.id]
        press_global = item.label.mapToGlobal(item.label.rect().center())
        target_global = target.mapToGlobal(QPoint(target.width() // 2, target.height() + 8))
        press = QMouseEvent(
            QEvent.MouseButtonPress,
            QPointF(item.label.rect().center()),
            QPointF(press_global),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        assert item.eventFilter(item.label, press) is True
        assert item._dragging is False
        QTest.qWait(item.LONG_PRESS_MS + 30)
        assert item._dragging is True

        move = QMouseEvent(
            QEvent.MouseMove,
            QPointF(item.label.mapFromGlobal(target_global)),
            QPointF(target_global),
            Qt.NoButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        assert item.eventFilter(item.label, move) is True
        app.processEvents()
        assert [row.task.id for row in w._ordered_task_items()] == [second.id, third.id, first.id]

        release = QMouseEvent(
            QEvent.MouseButtonRelease,
            QPointF(item.label.mapFromGlobal(target_global)),
            QPointF(target_global),
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        assert item.eventFilter(item.label, release) is True
        app.processEvents()
        assert item._dragging is False
        assert [task.id for task in TaskStore(path).active_tasks()] == [second.id, third.id, first.id]


def test_edge_hover_sets_resize_cursor(app):
    """鼠标悬停到窗口边缘/角落时,容器光标变为对应的缩放光标。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        store.add("任务一")
        w = _window(Path(d), store)
        w.move(0, 0)
        w.resize(300, 440)
        w.show()
        app.processEvents()

        def hover(gx, gy):
            ev = QMouseEvent(
                QEvent.MouseMove, QPointF(1, 1), QPointF(gx, gy),
                Qt.NoButton, Qt.NoButton, Qt.NoModifier,
            )
            w.eventFilter(w.container, ev)
            oc = QApplication.overrideCursor()
            return oc.shape() if oc is not None else Qt.ArrowCursor

        wd, ht = w.width(), w.height()
        assert hover(wd - 1, ht // 2) == Qt.SizeHorCursor      # 右边 → ↔
        assert hover(wd // 2, ht - 1) == Qt.SizeVerCursor      # 下边 → ↕
        assert hover(wd - 1, ht - 1) == Qt.SizeFDiagCursor     # 右下角 → ↖↘
        assert hover(1, ht - 1) == Qt.SizeBDiagCursor          # 左下角 → ↗↙
        assert hover(wd - 1, 1) == Qt.SizeBDiagCursor          # 右上角 → ↗↙
        assert hover(wd // 2, ht // 2) == Qt.ArrowCursor       # 中间 → 箭头
        w._apply_edge_cursor(None)  # 复位,避免污染后续测试


def test_collapsed_footer_bottom_edge_can_resize(app):
    """已完成栏折叠时,footer 底边仍能拖拽缩放窗口。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        store.add("任务一")
        w = _window(Path(d), store)
        w.move(0, 0)
        w.resize(300, 440)
        w.show()
        app.processEvents()

        old_h = w.height()
        x = w.width() // 2
        y = old_h - 1
        press = QMouseEvent(
            QEvent.MouseButtonPress, QPointF(x, y), QPointF(x, y),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
        )
        assert w.eventFilter(w.footer_btn, press) is True

        move = QMouseEvent(
            QEvent.MouseMove, QPointF(x, y + 30), QPointF(x, y + 30),
            Qt.NoButton, Qt.LeftButton, Qt.NoModifier,
        )
        assert w.eventFilter(w.footer_btn, move) is True

        release = QMouseEvent(
            QEvent.MouseButtonRelease, QPointF(x, y + 30), QPointF(x, y + 30),
            Qt.LeftButton, Qt.NoButton, Qt.NoModifier,
        )
        assert w.eventFilter(w.footer_btn, release) is True
        assert w.height() > old_h
        w._apply_edge_cursor(None)


def test_completed_right_click_delete(app):
    """已完成任务通过右键删除信号删除后,store 与面板同步。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        t = store.add("做完的")
        store.complete(t.id)
        w = _window(Path(d), store)
        w.show()
        app.processEvents()
        assert len(store.completed_tasks()) == 1

        # 模拟已完成行右键 → 删除
        w.completed_panel.deleted.emit(t.id)
        app.processEvents()
        assert len(store.completed_tasks()) == 0
        assert store.get(t.id) is t
        assert t.deleted is True
        assert store.history_tasks() == [t]
        assert w.footer_btn.text().startswith("已完成  0")


def test_completed_text_is_always_plain_text(app):
    """HTML 形态的任务完成后仍按字面显示，不改变内容样式。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        task = store.add("<b>字面标签</b>")
        store.complete(task.id)
        w = MainWindow(store, settings_path=Path(d) / "settings.json")
        row = w.completed_panel._row_for[task.id]
        label = row.findChild(QLabel)

        assert label.textFormat() == Qt.PlainText
        # label 存的是注入零宽空格的展示文本,去掉 ZWSP 后应还原原始文本
        assert label.text().replace("​", "") == "<b>字面标签</b>"
        # store 里始终是原始文本,不含零宽空格
        assert "​" not in store.get(task.id).text


def test_completed_panel_wraps_long_unbreakable_text(app):
    """已完成面板的连续数字/无空格长串也能换行显示。

    与主列表同源 bug:QLabel.wordWrap 只在词边界换行。已完成行同样
    注入零宽空格提供断行点,label 水平方向 Ignored 防撑宽。
    """
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        task = store.add("2" * 200)
        store.complete(task.id)
        store.add("正常任务")
        w = MainWindow(store, settings_path=Path(d) / "settings.json")
        w.resize(320, 460)
        w.show()
        for _ in range(5):
            app.processEvents()

        # 展开已完成面板(否则面板隐藏态宽度是残留值,断言无意义)
        w.toggle_completed()
        for _ in range(5):
            app.processEvents()

        row = w.completed_panel._row_for[task.id]
        label = row.findChild(QLabel)
        line_h = label.fontMetrics().lineSpacing()
        # 数字长串确实换行了
        assert label.height() > line_h + 1
        # 行没有被撑到内容宽度
        assert row.width() <= w.width()
        # content_height 能反映完整换行后的内容高度
        assert w.completed_panel.content_height() > line_h * 2
        # store 不被零宽空格污染
        assert "​" not in store.get(task.id).text


def test_collapsing_completed_panel_keeps_manual_height_change(app):
    """展开状态下手动调整的高度，在折叠后继续保留。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        w = MainWindow(store, settings_path=Path(d) / "settings.json")
        w.show()
        app.processEvents()

        collapsed_h = w.height()
        w.toggle_completed()
        w.resize(w.width(), w.height() + 80)
        w.toggle_completed()

        assert w.height() == collapsed_h + 80


def test_settings_window_closes_with_main_window(app):
    """独立设置窗口不能在主窗口关闭后继续让应用驻留。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        w = MainWindow(store, settings_path=Path(d) / "settings.json")
        w.show()
        w.open_settings()
        app.processEvents()
        settings_win = w._settings_win
        assert settings_win.isVisible()

        w.close()
        app.processEvents()
        assert not settings_win.isVisible()


def test_dot_only_completes_when_released_inside(app):
    """在圆点按下后拖出再释放，不应误完成任务。"""
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        task = store.add("任务")
        w = MainWindow(store, settings_path=Path(d) / "settings.json")
        w.show()
        app.processEvents()
        dot = w._active_items[task.id].dot

        QTest.mousePress(dot, Qt.LeftButton, pos=QPoint(9, 9))
        QTest.mouseRelease(dot, Qt.LeftButton, pos=QPoint(-2, -2))
        app.processEvents()
        assert store.get(task.id).completed is False

        QTest.mouseClick(dot, Qt.LeftButton, pos=QPoint(9, 9))
        app.processEvents()
        assert store.get(task.id).completed is True


def test_font_settings_apply_and_flush_on_immediate_close(app):
    """字体名称/字号立即生效，防抖期内退出也必须保存。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        settings_path = root / "settings.json"
        store = TaskStore(root / "tasks.json")
        task = store.add("带样式任务")
        w = MainWindow(store, settings_path=settings_path)
        w.show()
        w.settings.font_family = "Arial"
        w.settings.font_size = 16
        w._on_settings_changed()

        font = w._active_items[task.id].label.font()
        assert font.family() == "Arial"
        assert font.pixelSize() == 16

        w.close()
        loaded = AppSettings.load(settings_path)
        assert loaded.font_family == "Arial"
        assert loaded.font_size == 16


def test_double_click_task_text_starts_edit_unless_locked(app):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        task = store.add("点我编辑")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        item = w._active_items[task.id]

        QTest.mouseClick(item.label, Qt.LeftButton)
        app.processEvents()
        assert item.stack.currentIndex() == item._LABEL_PAGE

        QTest.mouseDClick(item.label, Qt.LeftButton)
        app.processEvents()
        assert item.stack.currentIndex() == item._EDIT_PAGE

        item._exit_edit()
        w.set_compact_mode(True)
        QTest.mouseDClick(item.label, Qt.LeftButton)
        app.processEvents()
        assert item.stack.currentIndex() == item._LABEL_PAGE


def test_keyboard_shortcuts_create_and_toggle_compact(app):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        # 关掉前面用例遗留的窗口:QShortcut 是窗口级绑定,别的窗口还开着时
        # Ctrl+N 可能被它抢走(单独跑这条用例能过、整套跑就挂,就是这个原因)
        for other in QApplication.topLevelWidgets():
            if other is not w and other.isWindow():
                other.setVisible(False)
        w.show()
        w.activateWindow()
        app.processEvents()

        QTest.keyClick(w, Qt.Key_N, Qt.ControlModifier)
        app.processEvents()
        assert len(store.active_tasks()) == 1
        new_item = list(w._active_items.values())[-1]
        new_item.edit.setPlainText("快捷键任务")
        new_item._on_editing_finished()

        # 「缩略模式」的出厂绑定是 Ctrl+Alt+3(全局热键要避让常用键,见 app_settings)
        QTest.keyClick(
            w, Qt.Key_3, Qt.ControlModifier | Qt.AltModifier,
        )
        app.processEvents()
        assert w._compact is True          # 默认绑定 Ctrl+Alt+3 = 缩略模式
        QTest.keyClick(w, Qt.Key_N, Qt.ControlModifier)
        app.processEvents()
        assert len(store.active_tasks()) == 1

        # 绑定存在 settings 里,且三个动作都有默认值(恢复默认设置时回到这一组)
        saved = AppSettings.load(root / "settings.json")
        assert saved.shortcuts == DEFAULT_SHORTCUTS
        assert set(w._action_shortcuts) == {"z_order", "fixed", "compact"}


def test_keybind_window_edits_and_applies_shortcut(app):
    """快捷键窗口:改键后立刻生效、写进设置;退格清空=不绑定。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_keybinds()
        app.processEvents()
        kw = w._keybind_win

        edit = kw._edits["fixed"]
        assert edit.sequence() == DEFAULT_SHORTCUTS["fixed"]
        QTest.keyClick(edit, Qt.Key_J, Qt.ControlModifier)
        app.processEvents()
        assert edit.sequence() == "Ctrl+J"
        assert w.settings.shortcuts["fixed"] == "Ctrl+J"
        assert w._action_shortcuts["fixed"].key().toString() == "Ctrl+J"

        # 新键位真的能触发「固定窗口位置」
        # (快捷键窗口在最上层、是当前活动窗口,不关掉它主窗口的 QShortcut 不会响应)
        kw.hide()
        w.activateWindow()
        app.processEvents()
        QTest.keyClick(w, Qt.Key_J, Qt.ControlModifier)
        app.processEvents()
        assert w._position_fixed is True

        # 退格清空 = 这一项不绑定(空串会被保留,不是回退到默认值)
        edit = kw._edits["fixed"]
        QTest.keyClick(edit, Qt.Key_Backspace)
        app.processEvents()
        assert edit.sequence() == ""
        assert w.settings.shortcuts["fixed"] == ""
        assert edit.text() == t("keys.cleared")
        assert "fixed" not in w._action_shortcuts     # 清空后不再注册这个快捷键
        w.close()


def test_keybind_window_steals_duplicate_binding(app):
    """同一个组合键绑到第二个动作时,从原来那一项上摘掉并提示。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_keybinds()
        app.processEvents()
        kw = w._keybind_win

        # 把「缩略模式」绑成「固定窗口位置」正在用的组合键
        QTest.keyClick(
            kw._edits["compact"], Qt.Key_2,
            Qt.ControlModifier | Qt.AltModifier,
        )
        app.processEvents()

        assert w.settings.shortcuts["compact"] == "Ctrl+Alt+2"
        assert w.settings.shortcuts["fixed"] == ""
        assert kw._edits["fixed"].sequence() == ""
        assert kw._note.isVisible() is True
        assert t("keys.action_fixed") in kw._note.text()

        # 恢复出厂绑定按钮把三项都还原
        kw._restore_defaults()
        app.processEvents()
        assert w.settings.shortcuts == DEFAULT_SHORTCUTS
        assert kw._edits["fixed"].sequence() == DEFAULT_SHORTCUTS["fixed"]
        w.close()


def test_compact_mode_persists(app):
    """缩略模式要跨重启保持。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w._cursor_near_top = lambda: False
        w.set_compact_mode(True, animate=False)
        w._flush_settings_save()

        saved = AppSettings.load(root / "settings.json")
        assert saved.compact_mode is True

        reopened = MainWindow(store, settings_path=root / "settings.json")
        reopened._cursor_near_top = lambda: False
        reopened.show()
        app.processEvents()
        assert reopened._compact is True
        # 启动时立刻按持久化状态收起顶栏,不等鼠标移动
        assert reopened._header_opacity == 0.0
        assert reopened._scroll_opacity == 1.0
        reopened.close()
        w.close()


def test_deleted_task_can_be_restored_from_history_window(app):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        task = store.add("不要删我")
        second = store.add("第二个任务")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        w.on_delete(task.id)
        app.processEvents()
        assert task.deleted is True
        assert task.id not in w._active_items

        w.open_history()
        history = w._history_win
        item = history.tree.topLevelItem(0)
        assert item.data(0, Qt.UserRole) == task.id
        item.setCheckState(0, Qt.Checked)
        history.restore_selected()
        app.processEvents()
        assert store.get(task.id) is task
        assert task.deleted is False
        assert task.id in w._active_items
        visible_ids = [
            w.list_layout.itemAt(index).widget().task.id
            for index in range(2)
        ]
        assert visible_ids == [task.id, second.id]


def test_history_window_batch_permanently_deletes_selected(app):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        completed = store.add("完成项")
        deleted = store.add("删除项")
        store.complete(completed.id)
        store.delete(deleted.id)
        w = MainWindow(store, settings_path=root / "settings.json")
        w.open_history()
        history = w._history_win

        history._toggle_all()
        history.delete_selected(confirm=False)
        app.processEvents()

        assert store.history_tasks() == []
        assert history.tree.topLevelItemCount() == 0


def test_loaded_rows_do_not_animate_but_new_rows_do(app):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        existing = store.add("已有任务")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        assert w._active_items[existing.id].graphicsEffect() is None
        w.add_task()
        new_item = list(w._active_items.values())[-1]
        assert new_item.graphicsEffect() is not None


def test_completed_panel_uses_content_height_and_stays_on_screen(app):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        task = store.add("已完成")
        store.complete(task.id)
        w = MainWindow(store, settings_path=root / "settings.json")
        screen = QApplication.primaryScreen().availableGeometry()
        w.resize(320, 300)
        w.move(screen.left() + 20, screen.bottom() - w.height() + 1)
        w.show()
        app.processEvents()

        w.toggle_completed()
        app.processEvents()
        assert 42 <= w._expanded_panel_h < 160
        assert w.frameGeometry().bottom() <= screen.bottom()


def test_completed_panel_keeps_height_after_complete_restore_and_delete(app):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        active = store.add("待完成")
        completed = []
        for index in range(5):
            task = store.add(f"完成任务 {index}")
            store.complete(task.id)
            completed.append(task)
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        w.toggle_completed()
        app.processEvents()
        initial_height = w.completed_panel.height()
        assert initial_height > 80

        w.on_complete(active.id)
        app.processEvents()
        assert w.completed_panel.height() > 80

        w.on_restore(completed[0].id)
        app.processEvents()
        assert w.completed_panel.height() > 80

        w.on_delete(completed[1].id)
        app.processEvents()
        assert w.completed_panel.height() > 80


def test_window_geometry_is_restored_and_clamped_to_screen(app):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        settings_path = root / "settings.json"
        settings = AppSettings(
            window_x=100000,
            window_y=100000,
            window_width=360,
            window_height=500,
        )
        settings.save(settings_path)
        w = MainWindow(TaskStore(root / "tasks.json"), settings_path=settings_path)
        screen = QApplication.primaryScreen().availableGeometry()

        assert screen.contains(w.frameGeometry().topLeft())
        assert w.width() == 360
        assert w.height() == 500


def test_empty_hint_visibility_follows_task_count(app):
    """无活跃任务时显示引导提示,有任务时隐藏。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        assert w._empty_hint.isVisible()

        w.add_task()
        app.processEvents()
        new_item = list(w._active_items.values())[-1]
        new_item.edit.setPlainText("第一个任务")
        new_item._on_editing_finished()
        app.processEvents()
        assert not w._empty_hint.isVisible()

        # 完成唯一任务(非空,进已完成栏)后列表又空了
        only_id = list(w._active_items.keys())[0]
        w.on_complete(only_id)
        app.processEvents()
        assert w._empty_hint.isVisible()


def test_expand_collapse_restores_exact_geometry(app):
    """展开/折叠已完成面板后,窗口几何精确回到原位。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        task = store.add("做完的")
        store.complete(task.id)
        w = MainWindow(store, settings_path=root / "settings.json")
        w.move(120, 80)
        w.resize(300, 400)
        w.show()
        app.processEvents()
        geo = (w.x(), w.y(), w.width(), w.height())

        w.toggle_completed()
        app.processEvents()
        assert w.height() == geo[3] + w._expanded_panel_h

        w.toggle_completed()
        app.processEvents()
        assert (w.x(), w.y(), w.width(), w.height()) == geo
        assert w._panel_lift == 0


def test_expand_near_screen_bottom_lifts_and_collapse_restores(app):
    """贴屏幕底边展开时窗口上移避让,折叠后精确回到原位。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        task = store.add("做完的")
        store.complete(task.id)
        w = MainWindow(store, settings_path=root / "settings.json")
        screen = QApplication.primaryScreen().availableGeometry()
        w.resize(320, 320)
        w.move(screen.left() + 40, screen.bottom() - 320 + 1)
        w.show()
        app.processEvents()
        y0, h0 = w.y(), w.height()

        w.toggle_completed()
        app.processEvents()
        assert w.frameGeometry().bottom() <= screen.bottom()
        assert w.y() < y0
        assert w._panel_lift > 0

        w.toggle_completed()
        app.processEvents()
        assert w.height() == h0
        assert w.y() == y0
        assert w._panel_lift == 0


def test_expanded_panel_shrink_then_collapse_restores(app):
    """展开期间面板内容变少(高度收缩),折叠后仍精确回到原位。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        task = store.add("做完的")
        store.complete(task.id)
        w = MainWindow(store, settings_path=root / "settings.json")
        screen = QApplication.primaryScreen().availableGeometry()
        w.resize(320, 320)
        w.move(screen.left() + 40, screen.bottom() - 320 + 1)
        w.show()
        app.processEvents()
        y0, h0 = w.y(), w.height()

        w.toggle_completed()
        app.processEvents()
        expanded_h = w.height()

        # 删掉唯一的已完成任务 → 面板高度收缩
        w.on_delete(task.id)
        app.processEvents()
        assert w.height() < expanded_h

        w.toggle_completed()
        app.processEvents()
        assert w.height() == h0
        assert w.y() == y0
        assert w._panel_lift == 0


def test_edge_fade_pixmap_is_cached_until_resize_or_theme_change(app):
    """羽化位图只在尺寸/主题变化时重建。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.resize(300, 400)
        w.show()
        app.processEvents()

        pm1 = w._edge_fade_pixmap()
        pm2 = w._edge_fade_pixmap()
        assert pm1 is pm2

        w.resize(310, 400)
        app.processEvents()
        pm3 = w._edge_fade_pixmap()
        assert pm3 is not pm1


def test_single_instance_lock_blocks_second_acquire(tmp_path):
    """同一数据目录的第二个实例拿不到锁。"""
    from lumistdo.single_instance import SingleInstance

    first = SingleInstance(tmp_path)
    assert first.try_acquire() is True
    second = SingleInstance(tmp_path)
    assert second.try_acquire() is False


# ---- 图钉置顶 / 眼睛隐藏文本 / 最小化菜单 ----
def test_pin_toggles_stays_on_top_and_persists(app):
    """图钉切换置顶,状态写入 settings 跨重启保持。

    运行时置顶走原生 SetWindowPos(不重建窗口、不闪烁),
    故这里只验证按钮状态与持久化;启动恢复另测 windowFlags。
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        w.set_always_on_top(True)
        app.processEvents()
        assert w.header.pin_btn._mode == "top"
        w._flush_settings_save()
        assert AppSettings.load(root / "settings.json").always_on_top is True

        w.set_always_on_top(False)
        app.processEvents()
        assert w.header.pin_btn._mode == "normal"
        w._flush_settings_save()
        assert AppSettings.load(root / "settings.json").always_on_top is False


def test_pin_state_restored_on_startup(app):
    """重启后按 settings 恢复置顶态(状态模型 + 按钮同步)。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        AppSettings(always_on_top=True).save(root / "settings.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        assert w._always_on_top is True
        assert w.header.pin_btn._mode == "top"


def test_fixed_button_locks_drag_and_resize(app):
    """固定态:拖动与边缘缩放都失效,再按一次解除,状态写入 settings。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        pos = QPoint(w.width() // 2, 120)       # 避开顶部栏与四角/四边
        start = w.pos()

        w.header.fixed_btn.toggled.emit(True)   # 等价于点击固定按钮
        app.processEvents()
        assert w._position_fixed is True
        assert w.header.fixed_btn._fixed is True
        assert w._edge(QPointF(2.0, 2.0)) is None      # 边缘缩放失效

        w.mousePressEvent(_mouse(QEvent.MouseButtonPress, pos, w, app))
        assert w._drag_pos is None                     # 没进入拖动
        w.mouseMoveEvent(_mouse(QEvent.MouseMove, pos + QPoint(60, 40), w, app))
        app.processEvents()
        assert w.pos() == start                        # 窗口没动

        w._flush_settings_save()
        assert AppSettings.load(root / "settings.json").position_fixed is True

        w.header.fixed_btn.toggled.emit(False)         # 再按一次解除
        app.processEvents()
        assert w._position_fixed is False
        assert w._edge(QPointF(2.0, 2.0)) is not None  # 缩放恢复

        w.mousePressEvent(_mouse(QEvent.MouseButtonPress, pos, w, app))
        w.mouseMoveEvent(_mouse(QEvent.MouseMove, pos + QPoint(60, 40), w, app))
        app.processEvents()
        assert w.pos() != start                        # 又能拖动了
        w._flush_settings_save()
        assert AppSettings.load(root / "settings.json").position_fixed is False


def test_position_fixed_state_restored_on_startup(app):
    """重启后按 settings 恢复固定态(状态模型 + 按钮同步)。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        AppSettings(position_fixed=True).save(root / "settings.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        assert w._position_fixed is True
        assert w.header.fixed_btn._fixed is True


def test_top_and_bottom_are_mutually_exclusive(app):
    """置顶与置底互斥:开一个自动关掉另一个,状态都写回 settings。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        w.set_always_on_top(True)
        assert w._always_on_top is True

        w.set_always_on_bottom(True)            # 置底顶掉置顶
        app.processEvents()
        assert w._always_on_bottom is True
        assert w._always_on_top is False
        assert w.header.pin_btn._mode == "bottom"

        w.set_always_on_top(True)               # 置顶顶掉置底
        app.processEvents()
        assert w._always_on_top is True
        assert w._always_on_bottom is False

        w._flush_settings_save()
        saved = AppSettings.load(root / "settings.json")
        assert saved.always_on_top is True
        assert saved.always_on_bottom is False


def test_bottom_state_restored_on_startup(app):
    """重启后按 settings 直接进入置底态,且不会同时置顶。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        AppSettings(always_on_bottom=True).save(root / "settings.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        assert w._always_on_bottom is True
        assert w._always_on_top is False


def test_settings_window_text_and_controls_follow_theme(app):
    """设置窗口自己的字色/滑轨要跟着配色走。

    回归:这些控件的样式以前是写死的白 alpha 叠加,深色背景没问题,
    浅色主题(素白)下文字、滑轨、输入框边框全都看不见;而且改字体颜色时
    设置窗口自己的字色不跟着变。
    """
    settings = AppSettings(bg_color="#f2f2f4", text_color="#2c2c32", bg_opacity=248)
    win = SettingsWindow(settings)
    qss = win.styleSheet()
    assert "rgb(44, 44, 50)" in qss           # 字色 = text_color
    assert "rgba(0, 0, 0" in qss              # 浅色主题用黑色低透明度
    assert "rgba(255, 255, 255" not in qss    # 不能残留深色主题的白色叠加
    assert "QSlider::groove:horizontal" in qss  # 滑轨也在自适应之列

    # 改字体颜色 → 设置窗口自己的字色立刻跟着变
    settings.text_color = "#c81e1e"
    win.apply_theme()
    assert "rgb(200, 30, 30)" in win.styleSheet()

    # 深色主题回到白色低透明度
    dark = SettingsWindow(AppSettings())
    assert "rgba(255, 255, 255" in dark.styleSheet()
    assert "rgba(0, 0, 0" not in dark.styleSheet()


def test_settings_window_checks_sync_with_header_buttons(app):
    """顶部栏固定按钮/图钉三态与设置窗口控件双向同步。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        w.header.fixed_btn.toggled.emit(True)
        w.header.pin_btn.toggled.emit("top")    # 图钉信号带的是目标层级名
        w.open_settings()
        app.processEvents()

        win = w._settings_win
        assert win._fixed_check.isChecked() is True
        assert win._layer_radios["top"].isChecked() is True

        win._layer_radios["bottom"].setChecked(True)   # 设置里改置底 → 主窗口生效
        app.processEvents()
        assert w._always_on_bottom is True
        assert w._always_on_top is False        # 与置顶互斥
        assert w.header.pin_btn._mode == "bottom"
        w._flush_settings_save()                # 触发主题重刷:设置窗口会重建勾选框
        app.processEvents()

        win = w._settings_win
        assert win._layer_radios["bottom"].isChecked() is True
        assert win._layer_radios["top"].isChecked() is False
        assert win._fixed_check.isChecked() is True

        w.set_position_fixed(False)             # 主窗口改固定态 → 设置同步
        assert win._fixed_check.isChecked() is False


def test_settings_layer_top_click_sticks(app):
    """设置里点「置于最上层」必须真的选上(回归:点了会被弹回「普通层级」)。

    以前 `z_order_changed` 只回传"要不要置底"的布尔值,选置顶时回传 False 被
    主窗口当成"回到普通层级",于是单选又被弹回「普通层级」——用户看到的就是
    "置顶点击不了"。
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()

        win = w._settings_win
        assert win._layer_radios["normal"].isChecked() is True   # 起点:普通层级

        win._layer_radios["top"].setChecked(True)
        app.processEvents()

        assert win._layer_radios["top"].isChecked() is True
        assert win._layer_radios["normal"].isChecked() is False
        assert w._always_on_top is True
        assert w.settings.always_on_top is True
        assert w.header.pin_btn._mode == "top"

        # 再选回普通层级也要留住
        win._layer_radios["normal"].setChecked(True)
        app.processEvents()
        assert win._layer_radios["normal"].isChecked() is True
        assert w._always_on_top is False
        assert w.settings.always_on_top is False


def test_header_menu_contains_quit_and_minimize(app, monkeypatch):
    """顶部栏右键菜单含退出与最小化(替换模块内 QMenu 避免真弹菜单)。"""
    from lumistdo import main_window as mw

    captured = {}

    class FakeMenu:
        def __init__(self, parent=None):
            self._texts = []

        def addAction(self, text, slot=None):
            self._texts.append(text)

        def exec(self, *args):
            captured["actions"] = list(self._texts)
            return None

    monkeypatch.setattr(mw, "QMenu", FakeMenu)
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        w = MainWindow(store, settings_path=Path(d) / "settings.json")
        w.show_header_menu(QPoint(0, 0))
    assert captured["actions"][-2:] == ["退出", "最小化"]


def test_locked_header_right_click_is_ignored(app, monkeypatch):
    """锁定态下右键顶部栏不弹菜单。"""
    from lumistdo import main_window as mw
    from PySide6.QtGui import QContextMenuEvent

    captured = {}

    class FakeMenu:
        def __init__(self, parent=None):
            pass

        def addAction(self, text, slot=None):
            pass

        def exec(self, *args):
            captured["shown"] = True
            return None

    monkeypatch.setattr(mw, "QMenu", FakeMenu)
    with tempfile.TemporaryDirectory() as d:
        store = TaskStore(Path(d) / "tasks.json")
        w = MainWindow(store, settings_path=Path(d) / "settings.json")
        w.set_compact_mode(True)
        ev = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, QPoint(5, 5), QPoint(5, 5),
        )
        w.header.contextMenuEvent(ev)
    assert "shown" not in captured


# ---- 置底:必须是延迟应用的,否则会被 Qt 的显示流程顶回来 ----
def test_z_order_applied_after_qt_show_sequence(app):
    """showEvent 里只安排延迟应用 z-order,不能在事件处理中同步调用。

    showEvent 里立刻调 SetWindowPos(HWND_BOTTOM),Qt 随后自己的显示流程会把它
    顶回来(真实窗口实测:置底名次纹丝不动;置顶靠 WS_EX_TOPMOST 样式不受影响)。
    所以这里断言调用顺序:show() 返回时还没应用,事件循环再走一轮才应用。
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        events = []
        w._apply_z_order = lambda: events.append("apply") or True

        w.show()
        events.append("showEvent returned")
        app.processEvents()
        events.append("processEvents done")

    assert events[0] == "showEvent returned", f"showEvent 里同步应用了 z-order: {events}"
    assert "apply" in events, f"延迟应用没有发生: {events}"


def test_z_order_reapplied_on_activation_when_pinned_bottom(app):
    """置底态下窗口被激活(打开设置等)后要重新压回底层。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.set_always_on_bottom(True)
        app.processEvents()

        events = []
        w._apply_z_order = lambda: events.append("apply") or True
        app.sendEvent(w, QEvent(QEvent.WindowActivate))
        events.append("sendEvent returned")
        app.processEvents()
        pinned_events = list(events)

        # 没有置底时同样的事件不应再压底
        w.set_always_on_bottom(False)
        app.processEvents()
        events.clear()
        app.sendEvent(w, QEvent(QEvent.WindowActivate))
        app.processEvents()
        unpinned_events = list(events)

    assert pinned_events[0] == "sendEvent returned", f"激活事件里同步应用了 z-order: {pinned_events}"
    assert "apply" in pinned_events, "置底态激活后没有重新应用 z-order"
    assert "apply" not in unpinned_events, "未置底时不该改层级"


def test_settings_and_history_windows_stay_above_pinned_bottom(app):
    """设置/历史窗口是独立置顶工具窗:主窗口沉底时它们仍能被看到和操作。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.set_always_on_bottom(True)
        w.open_settings()
        w.open_history()
        app.processEvents()

        for win in (w._settings_win, w._history_win):
            assert win.isVisible()
            assert win.windowFlags() & Qt.WindowStaysOnTopHint

        w.close()


# ---- 任务栏图标与系统托盘 ----

class _FakeUser32:
    """最小的 user32 替身:只记 SetWindowPos 调用,让样式代码能跑通。"""

    def __init__(self):
        self.set_window_pos = []

    def SetWindowPos(self, hwnd, after, x, y, cx, cy, flags):
        self.set_window_pos.append((hwnd, after, flags))
        return 1


def test_taskbar_icon_toggle_sets_toolwindow_without_appwindow(app, monkeypatch):
    """关掉「在任务栏显示图标」后写 WS_EX_TOOLWINDOW 并清掉 WS_EX_APPWINDOW,开回来能还原。

    offscreen 平台没有真实 HWND(winId() 恒为 1,IsWindow 为 False),
    所以这里记录原生调用而不是读真实样式位;真机效果由打包版实测覆盖。
    """
    from lumistdo import main_window as mw

    written = []
    state = {"ex": mw.WS_EX_APPWINDOW}  # 从一个带 APPWINDOW 的窗口开始
    fake = _FakeUser32()
    monkeypatch.setattr(mw, "_user32", fake)
    monkeypatch.setattr(
        mw, "_get_window_long", lambda hwnd, index: state["ex"],
    )

    def fake_set(hwnd, index, value):
        written.append((index, value))
        state["ex"] = value

    monkeypatch.setattr(mw, "_set_window_long", fake_set)
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        # 关掉「在任务栏显示图标」→ 应该带上 TOOLWINDOW;再开回来 → 应该还原
        w.set_show_in_taskbar(False)
        app.processEvents()
        off_value = written[-1][1]
        visible_after_off = w.isVisible()

        w.set_show_in_taskbar(True)
        app.processEvents()
        on_value = written[-1][1]
        visible_after_on = w.isVisible()
        w.close()

    assert written and written[-1][0] == mw.GWL_EXSTYLE, "没有写扩展样式位"
    assert off_value & mw.WS_EX_TOOLWINDOW, f"关掉后没带上 TOOLWINDOW: {off_value:#x}"
    assert not off_value & mw.WS_EX_APPWINDOW, "APPWINDOW 会把任务栏按钮带回来"
    assert not on_value & mw.WS_EX_TOOLWINDOW, f"开回来没还原: {on_value:#x}"
    # 只挑改样式的那些调用(同一进程里 _apply_z_order 也在调这个函数)
    style_calls = [
        flags for _, _, flags in fake.set_window_pos
        if flags & mw.SWP_FRAMECHANGED
    ]
    assert len(style_calls) >= 2, f"改样式后没调 SetWindowPos: {style_calls}"
    assert visible_after_on and visible_after_off, "重新登记任务栏按钮后窗口没显示回来"


def test_tray_unavailable_keeps_taskbar_icon(app, monkeypatch):
    """系统没有托盘时**不许**关掉任务栏图标,否则窗口两个入口都没了。

    兜底逻辑在 MainWindow.__init__ 与 set_show_in_taskbar 里:托盘不可用时
    `TrayIcon.set_visible` 返回 False,这时候如果把任务栏图标也关了,
    用户就再也找不到窗口 —— 只能去任务管理器杀进程。
    """
    monkeypatch.setattr(
        "lumistdo.tray_icon.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: False),
    )
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        assert w.settings.show_in_taskbar is True, "没有托盘就该老实待在任务栏"
        assert w._show_in_taskbar is True
        assert not w._tray.is_visible(), "托盘起不来就不该假装它起来了"

        # 运行中想关掉也必须被挡回来
        w.set_show_in_taskbar(False)
        app.processEvents()
        assert w.settings.show_in_taskbar is True
        assert w._show_in_taskbar is True
        win = w.open_settings()
        app.processEvents()
        assert w._settings_win._taskbar_check.isChecked() is True, "勾选框得跟上兜底结果"
        w.close()


def test_taskbar_icon_toggle_keeps_window_visible_after_reshow(app):
    """重新登记任务栏按钮用 hide→show,结束后窗口必须还是可见的。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        w.set_show_in_taskbar(True)
        app.processEvents()
        visible_after_toggle = w.isVisible()

        w.set_show_in_taskbar(False)
        app.processEvents()
        visible_after_restore = w.isVisible()
        w.close()

    assert visible_after_toggle, "开启后窗口被藏起来没显示回来"
    assert visible_after_restore, "取消后窗口没显示回来"


def test_taskbar_icon_choice_persists_and_drives_tray(app, monkeypatch):
    """「在任务栏显示图标」跨重启保持;关着(出厂值)时常驻托盘图标。"""
    monkeypatch.setattr(
        "lumistdo.tray_icon.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: True),
    )
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        settings_path = root / "settings.json"
        store = TaskStore(root / "tasks.json")
        first = MainWindow(store, settings_path=settings_path)
        first.show()
        app.processEvents()
        # 出厂值是"只在托盘":先开到任务栏,验证这个选择能落盘并还原
        first.set_show_in_taskbar(True)
        first._flush_settings_save()
        first.close()

        assert AppSettings.load(settings_path).show_in_taskbar is True

        second = MainWindow(store, settings_path=settings_path)
        second.show()
        app.processEvents()
        tray_visible_when_in_taskbar = second._tray.is_visible()
        second.set_show_in_taskbar(False)   # 关掉任务栏图标 → 托盘必须顶上
        app.processEvents()
        tray_visible_after_off = second._tray.is_visible()
        second.close()

    assert second._show_in_taskbar is False, "关掉后主窗口状态没跟上"
    assert tray_visible_after_off, "关掉任务栏图标后常驻托盘图标没出现"
    assert tray_visible_when_in_taskbar is False, "在任务栏显示时不该多占一个托盘图标"


def test_tray_toggle_hides_and_shows_window(app, monkeypatch):
    """托盘左键:窗口可见就藏,藏起来了就显示。"""
    monkeypatch.setattr(
        "lumistdo.tray_icon.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: True),
    )
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        w.toggle_visible()
        app.processEvents()
        hidden = w.isVisible()

        w.toggle_visible()
        app.processEvents()
        shown = w.isVisible()
        w.close()

    assert hidden is False, "托盘左键没把窗口藏起来"
    assert shown is True, "再按一次没把窗口显示回来"


def test_settings_window_taskbar_check_follows_header(app):
    """设置窗勾选与主窗口状态双向同步,且不互相递归。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()

        # 出厂值:不在任务栏显示图标(只在托盘)
        assert w._settings_win._taskbar_check.isChecked() is False
        w._settings_win._taskbar_check.setChecked(True)  # 模拟用户点击
        app.processEvents()
        assert w._show_in_taskbar is True, "勾选后主窗口没跟上"
        assert w.settings.show_in_taskbar is True
        assert w._settings_win._taskbar_check.isChecked() is True

        w.set_show_in_taskbar(False)  # 主窗口侧改动要回同步到勾选
        app.processEvents()
        assert w._settings_win._taskbar_check.isChecked() is False, "勾选没被回同步"
        w.close()


def test_default_is_tray_only_and_startup_keeps_new_task(app, monkeypatch):
    """出厂默认「不在任务栏显示图标」(只在托盘),且启动时不抢焦点。

    回归:首次应用任务栏扩展样式时也走 hide→show 重新登记,会把刚聚焦的新任务
    输入框打掉 —— 空任务被 editingFinished 判成空任务清掉,表现就是"点 + 后
    输入框瞬间消失"。
    """
    monkeypatch.setattr(
        "lumistdo.tray_icon.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: True),
    )
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        assert w.settings.show_in_taskbar is False, "出厂值应该是只在托盘"
        assert w._show_in_taskbar is False
        assert w._tray.is_visible(), "只在托盘时托盘图标必须常驻"

        w.add_task()
        app.processEvents()
        assert len(w._active_items) == 1, "新任务被启动时的焦点变动清掉了"
        w.close()


def test_restore_focus_skips_hidden_and_destroyed_widgets(app):
    """重新登记任务栏后的"把焦点还回去"要能安静跳过隐藏/已销毁的控件。

    hide→show 会顺带把空任务清掉,那时焦点控件已经是野指针了,不能抛出去。
    """
    from lumistdo.main_window import MainWindow

    edit = QLineEdit()
    edit.show()
    edit.setFocus()
    app.processEvents()
    assert edit.hasFocus(), "前置条件:独立小窗口里的输入框该能拿到焦点"

    MainWindow._restore_focus(edit)          # 正常:还焦点
    assert edit.hasFocus()

    edit.hide()
    MainWindow._restore_focus(edit)          # 隐藏:跳过,不抛

    edit.deleteLater()
    app.processEvents()
    MainWindow._restore_focus(edit)          # C++ 对象已销毁:吞掉 RuntimeError


def test_header_title_editable_and_upper_cased(app):
    """设置里改顶部栏文字:立即生效、拉丁字母转大写、留空则不显示文字。

    断言用 _raw_title(真实内容)而不是标签文字:标签在窄宽度或字体缺字时
    会按 Om 省略号截断,那是显示层的事,由 test_header_title_is_elided_when_too_long 覆盖。
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()

        assert w.header._raw_title == DEFAULT_TITLE_TEXT

        w.open_settings()
        app.processEvents()
        w._settings_win._title_edit.setText("my tasks")
        app.processEvents()
        assert w.header._raw_title == "my tasks", "自定义标题没生效"
        assert w.header.title_label.text() == "MY TASKS", "拉丁字母没转大写"

        w._settings_win._title_edit.setText("今天要做的事")
        app.processEvents()
        assert w.header.title_label.text() == "今天要做的事", "中文不该被大写化"

        w._settings_win._title_edit.setText("")   # 清空 = 不显示文字
        app.processEvents()
        assert w.header._raw_title == ""
        assert not w.header.title_label.isVisible(), "留空后标题标签应该隐藏"

        w.set_title_text("   ")                   # 只有空白也当作没填
        assert w.settings.title_text == ""
        assert w.header._raw_title == ""
        w.close()


def test_title_text_persists_and_restores(app):
    """顶部栏文字跨重启保持,且文件里被塞了换行/超长也照样读得回来。"""
    from lumistdo.app_settings import MAX_TITLE_LENGTH

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        settings_path = root / "settings.json"
        store = TaskStore(root / "tasks.json")
        first = MainWindow(store, settings_path=settings_path)
        first.show()
        app.processEvents()
        first.set_title_text("FOCUS")
        first._flush_settings_save()
        first.close()

        assert AppSettings.load(settings_path).title_text == "FOCUS"
        # 换行/制表符折叠成空格(单独校验,别覆盖掉上面那份设置)
        AppSettings(title_text="a\nb\tc").save(settings_path)
        assert AppSettings.load(settings_path).title_text == "a b c"
        assert len("字" * 60) > MAX_TITLE_LENGTH  # 上限确实小于这条输入

        # 重新写回合法设置,检查重启后的行为
        AppSettings(title_text="focus").save(settings_path)
        second = MainWindow(store, settings_path=settings_path)
        second.show()
        app.processEvents()
        raw_title = second.header._raw_title
        shown_title = second.header.title_label.text()
        second.close()

    assert raw_title == "focus", "重启后没恢复自定义标题"
    assert shown_title in ("FOCUS", "FOCU…"), f"显示内容不对: {shown_title!r}"


def test_header_title_is_elided_when_too_long(app):
    """标题过长时截断加省略号,不把右侧图标挤出顶栏,也不把窗口撑宽。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        original_width = w.width()
        # 先给一个正常长度的标题,再量标签宽度(默认标题在无字体环境下也许已被省略,
        # 但布局给标签的宽度与内容无关,量哪个标题都一样)
        w.set_title_text("FOCUS")
        app.processEvents()
        label_width = w.header.title_label.width()

        w.set_title_text("A" * 60)
        app.processEvents()
        shown = w.header.title_label.text()

        assert w.width() == original_width, "标题把窗口撑宽了"
        assert w.header.title_label.width() == label_width, "标题把顶栏挤变形了"
        assert shown.endswith("…"), f"超长标题没有被省略: {shown!r}"
        assert len(shown) < len(w.header._raw_title)
        assert w.header.pin_btn.isVisible(), "图标按钮被挤出顶栏"
        w.close()


def test_typing_in_title_field_keeps_focus(app):
    """逐字输入时不能被主题重刷抢走焦点(否则打一个字就断)。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()

        edit = w._settings_win._title_edit
        edit.setFocus()
        app.processEvents()
        for ch in "ABC":
            edit.setText(edit.text() + ch)
            app.processEvents()
            assert edit.hasFocus(), f"输入 {ch!r} 后焦点跑掉了"
        w.close()


class _FakeAutostart:
    """替身:记录调用,不碰真实注册表。"""

    def __init__(self, ok=True):
        self.ok = ok
        self.enabled = False
        self.calls = []

    def set_enabled(self, enabled):
        self.calls.append(enabled)
        if not self.ok:
            return False
        self.enabled = enabled
        return True

    def is_enabled(self):
        return self.enabled

    def current_command(self):
        return '"C:\\LumistDo\\LumistDo.exe"' if self.enabled else ""

    def startup_command(self):
        return '"C:\\LumistDo\\LumistDo.exe"'


def test_autostart_toggle_writes_registry_and_persists(app, monkeypatch):
    """勾上开机自启动:写注册表 + 存设置;重启后勾选状态跟着回来。"""
    fake = _FakeAutostart()
    monkeypatch.setattr("lumistdo.main_window.autostart", fake)
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        settings_path = root / "settings.json"
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=settings_path)
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()

        assert w._settings_win._autostart_check.isChecked() is False
        w._settings_win._autostart_check.setChecked(True)   # 模拟用户点击
        app.processEvents()

        assert fake.calls == [True], f"没写注册表: {fake.calls}"
        assert fake.enabled is True
        assert w.settings.autostart is True

        w._flush_settings_save()
        assert AppSettings.load(settings_path).autostart is True
        w.close()

        second = MainWindow(store, settings_path=settings_path)
        second.show()
        app.processEvents()
        second.open_settings()
        app.processEvents()
        checked = second._settings_win._autostart_check.isChecked()
        second.close()

    assert checked is True, "重启后开机自启动勾选没恢复"


def test_autostart_failure_reverts_checkbox(app, monkeypatch):
    """写注册表失败时勾选退回真实状态,不假装成功。"""
    fake = _FakeAutostart(ok=False)
    monkeypatch.setattr("lumistdo.main_window.autostart", fake)
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=root / "settings.json")
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()

        w._settings_win._autostart_check.setChecked(True)
        app.processEvents()

        assert w.settings.autostart is False, "失败时不该记成已开启"
        assert w._settings_win._autostart_check.isChecked() is False
        assert w._settings_win._autostart_check.toolTip(), "失败时应当给出提示"
        w.close()


def test_settings_saved_when_window_hidden_to_tray(app, monkeypatch):
    """藏进托盘(不关程序)也要立刻落盘,不能等 180ms 的合并保存。"""
    monkeypatch.setattr(
        "lumistdo.tray_icon.QSystemTrayIcon.isSystemTrayAvailable",
        staticmethod(lambda: True),
    )
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        settings_path = root / "settings.json"
        store = TaskStore(root / "tasks.json")
        w = MainWindow(store, settings_path=settings_path)
        w.show()
        app.processEvents()

        w.set_title_text("HIDDEN")
        w.set_position_fixed(True)
        w.resize(333, 444)
        w.toggle_visible()                 # 藏进托盘
        app.processEvents()

        loaded = AppSettings.load(settings_path)
        w.close()

    assert loaded.title_text == "HIDDEN", "隐藏时没把设置落盘"
    assert loaded.position_fixed is True
    assert loaded.window_width == 333, "隐藏时没保存窗口尺寸"


def test_clicking_compact_window_reveals_header_temporarily(app):
    """缩略模式下点窗口能临时唤回顶栏,几秒后自己收回去。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        store.add("唤回测试")
        w = _window(root, store)
        w.show()
        app.processEvents()

        w._cursor_near_top = lambda: False
        w.set_compact_mode(True, animate=False)
        app.processEvents()
        assert w._header_opacity == 0.0, "缩略模式后顶栏没有渐隐"
        assert w._chrome_wanted() is False

        w.mousePressEvent(_mouse(QEvent.MouseButtonPress, QPoint(150, 300), w, app))
        app.processEvents()
        assert w._reveal_until > 0.0, "点击没有唤回顶栏"
        assert w._chrome_wanted() is True
        assert w._header_opacity == 1.0, "唤回后顶栏没有显示"

        w._reveal_until = 0.0
        w._refresh_chrome(animate=False)
        assert w._chrome_wanted() is False
        assert w._header_opacity == 0.0, "临时唤回到期后顶栏没有收起"
        w.close()


def test_compact_window_keeps_sane_layout(app):
    """缩略模式下窗口宽度不能被滚动区撑开(曾出现 scroll 宽度 640 > 窗口 320)。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = _window(root, store)
        w.show()
        app.processEvents()

        w._cursor_near_top = lambda: False
        w.set_compact_mode(True, animate=False)
        app.processEvents()

        assert w.scroll.isVisible(), "不能把滚动区整体 setVisible(False),否则宽度会卡住"
        assert w.scroll.width() <= w.width(), "滚动区比窗口还宽"
        w.close()


def test_reregister_for_taskbar_is_deferred_out_of_toggle_call(app, monkeypatch):
    """任务栏重新登记必须推迟到事件循环下一轮,否则会打断 Qt 的显示流程。

    这是托盘点了没反应的根因:同步 hide→show 发生在设置变更的调用栈里,
    原生窗口真的被藏起来而 Qt 仍以为可见,之后点托盘再也回不来。
    这里用"重新登记"与"之后排的哨兵定时器"的先后顺序来判定是否被推迟。
    """
    import lumistdo.main_window as mw

    # 非 Windows 上 _user32/_set_window_long 都是 None,那会走 setWindowFlag
    # 分支而不是重新登记;这里补上替身,并用 style 恒为 0(永远和 target 不同)
    # 保证 style_changed 为真、必然走到重新登记那一步。
    fake = _FakeUser32()
    monkeypatch.setattr(mw, "_user32", fake)
    monkeypatch.setattr(mw, "_get_window_long", lambda hwnd, index: 0)
    monkeypatch.setattr(mw, "_set_window_long", lambda hwnd, index, value: None)

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = _window(root, store)
        w.show()
        app.processEvents()

        order = []
        w._reregister_for_taskbar = lambda: order.append("reregister")
        # 出厂值是"只在托盘",所以这里切到"在任务栏显示图标"也是一次真实变更
        w.set_show_in_taskbar(True)
        assert order == [], "重新登记同步执行了,会打断 Qt 的显示流程"
        order.append("sentinel")
        for _ in range(20):
            app.processEvents()
            if "reregister" in order:
                break

        assert w.isVisible(), "推迟登记后窗口丢了可见状态"
        assert order == ["sentinel", "reregister"], (
            f"重新登记没有推迟到事件循环下一轮: {order}"
        )
        w.close()


def test_settings_and_history_windows_stay_above_pinned_bottom(app):
    """主窗口置底后设置/历史窗口仍要在最上层,否则被压在别的程序下面没法点。"""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = _window(root, store)
        w.show()
        app.processEvents()

        w.set_always_on_bottom(True)
        w.open_settings()
        w.open_history()
        app.processEvents()

        settings_win = w._settings_win
        history_win = w._history_win

        assert settings_win.isVisible() and history_win.isVisible()
        for win in (settings_win, history_win):
            assert win.windowFlags() & Qt.WindowStaysOnTopHint, (
                f"{type(win).__name__} 没有置顶标志,置底时会被压住"
            )
        w.close()


def test_reveal_and_expire_header_can_repeat_without_crashing(app):
    """缩略模式下反复"点窗口唤回 → 到点隐去"不能再崩。

    踩过的坑:Qt 的 setGraphicsEffect(None) 会把那个 QGraphicsOpacityEffect
    **删掉**,而代码还把它缓存在 self._header_effect 里;第二次动画直接摸
    死对象 → RuntimeError: Internal C++ object already deleted。
    """
    def settle():
        """把淡入/淡出动画跑完(动画要 190ms,单次 processEvents 追不上)。"""
        for _ in range(60):
            app.processEvents()
            anim = w._header_anim
            if anim is None or anim.state() != QAbstractAnimation.Running:
                break
            time.sleep(0.01)
        app.processEvents()

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = _window(root, store)
        w.show()
        app.processEvents()
        w._cursor_near_top = lambda: False
        w.set_compact_mode(True, animate=False)
        app.processEvents()
        assert w._header_opacity == 0.0

        for round_no in (1, 2, 3):
            w._reveal_chrome()
            settle()
            assert w._header_opacity == 1.0, f"第 {round_no} 次唤回没显示顶栏"
            assert w.header.isVisible()
            assert w._header_effect is None, (
                f"第 {round_no} 次唤回后还留着已删除的特效引用"
            )
            # 模拟 3 秒到期
            w._reveal_until = 0.0
            w._refresh_chrome()
            settle()
            assert w._header_opacity == 0.0, f"第 {round_no} 次到点没收起顶栏"
            assert w._header_effect is None, (
                f"第 {round_no} 次隐去后还留着已删除的特效引用"
            )
        assert w.settings.compact_mode is True, "唤回不应改动设置本身"
        assert w._compact is True, "唤回只该临时露顶栏,缩略模式仍开着"
        w.close()


def test_reset_button_has_accessible_name_for_ui_automation(app):
    """「恢复默认设置」是纯自绘图标按钮,没有文字。

    真机验收脚本要靠 UI Automation 点它:不设 accessibleName 时 UIA 读到的
    Name 是空串,脚本只能靠坐标瞎猜(实测一次都点不中,最后改用 Invoke 才通)。
    """
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        store = TaskStore(root / "tasks.json")
        w = _window(root, store)
        w.show()
        app.processEvents()
        w.open_settings()
        app.processEvents()

        win = w._settings_win
        assert win._reset_btn.accessibleName() == t("settings.reset_btn")
        assert win._reset_btn.accessibleName(), "恢复默认按钮缺少可访问名称"
        w.close()

