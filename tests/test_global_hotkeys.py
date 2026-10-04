"""全局快捷键(RegisterHotKey)的测试。

分两层:
- 纯解析:把 ``"Ctrl+Alt+O"`` 翻成 ``(VK, MOD)``,不需要窗口;
- 真注册:在真的 Win32 窗口上 ``RegisterHotKey`` / ``UnregisterHotKey``。
  这一层必须**绕过** ``test_gui_smoke.py`` 里那个把 ``supported()`` 关掉的
  autouse fixture —— 它在 offscreen 平台下会让全局热键永远走"注册失败"分支,
  而 offscreen 的 ``QWidget.winId()`` 恰好就是占位值 1,于是这条路径在
  CI/无头环境下天然测不到。所以这里用真窗口句柄,并且显式断言
  ``GetLastError() == 1400``(ERROR_INVALID_WINDOW_HANDLE)来证明
  ctypes 调用链真的一路走到了 user32。
"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ctypes
import sys
from ctypes import wintypes

import pytest

from lumistdo import global_hotkeys as gh


@pytest.fixture
def qapp():
    """真注册那条用例需要一个 QApplication(拿真窗口句柄)。"""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


# ---------------------------------------------------------------- 纯解析

@pytest.mark.parametrize(
    "sequence,expected",
    [
        ("Ctrl+O", (0x4F, gh.MOD_CONTROL)),
        ("Ctrl+Alt+O", (0x4F, gh.MOD_CONTROL | gh.MOD_ALT)),
        ("Ctrl+Shift+K", (0x4B, gh.MOD_CONTROL | gh.MOD_SHIFT)),
        ("Ctrl+Alt+Shift+F5", (0x74, gh.MOD_CONTROL | gh.MOD_ALT | gh.MOD_SHIFT)),
        ("Alt+L", (0x4C, gh.MOD_ALT)),
        ("Ctrl+Alt+Space", (0x20, gh.MOD_CONTROL | gh.MOD_ALT)),
        ("Ctrl+Alt+Left", (0x25, gh.MOD_CONTROL | gh.MOD_ALT)),
    ],
)
def test_vk_and_mods_maps_letters_and_modifiers(sequence, expected):
    assert gh.vk_and_mods(sequence) == expected


@pytest.mark.parametrize("sequence", ["O", "F5", "Space", "", "Ctrl", "Alt+Shift"])
def test_vk_and_mods_refuses_bindings_without_a_real_keyboard_modifier(sequence):
    """不带 Alt/Ctrl/Shift/Win 的绑定不能做成全局热键。

    否则注册出来的热键会把整个键盘吞掉(按一下 O 就触发),所以宁可返回
    None 让调用方退回窗口级 QShortcut。
    """
    assert gh.vk_and_mods(sequence) is None


def test_vk_and_mods_ignores_unknown_keys():
    assert gh.vk_and_mods("Ctrl+Alt+不存在的键") is None


def test_bound_actions_reports_only_successful_registrations():
    mgr = gh.GlobalHotkeys()
    # 没有窗口句柄 → 三个都注册失败,但对象本身不该炸
    result = mgr.apply(
        0,
        {"z_order": "Ctrl+Alt+O", "fixed": "Ctrl+Alt+K", "compact": ""},
        {},
    )
    assert result == {"z_order": False, "fixed": False, "compact": False}
    assert mgr.bound_actions() == ()


def test_handle_hotkey_dispatches_by_id_and_ignores_unknown_ids():
    mgr = gh.GlobalHotkeys()
    calls = []
    mgr._ids = {0x4C44: "z_order", 0x4C45: "fixed"}
    mgr._handlers = {"z_order": lambda: calls.append("z_order")}

    assert mgr.handle_hotkey(0x4C44) is True
    assert calls == ["z_order"]
    # 注册过但没有处理函数的动作:不该抛,也不该算命中
    assert mgr.handle_hotkey(0x4C45) is False
    # 完全没注册过的 id:同样安全
    assert mgr.handle_hotkey(0x9999) is False
    assert calls == ["z_order"]


def test_native_event_filter_passes_through_non_windows_messages():
    mgr = gh.GlobalHotkeys()
    assert mgr.nativeEventFilter(b"windows_dispatcher_MSG", 0) == (False, 0)
    assert mgr.nativeEventFilter(b"xcb_generic_event_t", 0) == (False, 0)


def test_native_event_filter_tolerates_bogus_message_pointer():
    """消息指针是垃圾值时也不能把异常抛回 Qt(事件过滤里的异常会静默崩)。"""
    mgr = gh.GlobalHotkeys()
    assert mgr.nativeEventFilter(b"windows_generic_MSG", 0) == (False, 0)
    assert mgr.nativeEventFilter(b"windows_generic_MSG", "not-a-pointer") == (False, 0)


# ---------------------------------------------------------------- 真注册

requires_windows = pytest.mark.skipif(
    sys.platform != "win32" or not gh.supported(),
    reason="RegisterHotKey 只在 Windows 上存在",
)


def real_hwnd_or_skip(qapp, window):
    """拿真窗口句柄;offscreen 平台给的是假句柄,拿不到就 skip。

    不能只看 ``winId() <= 1``:offscreen 平台也会给出 >1 的合成句柄,
    但那种句柄在 user32 里是无效的,注册/注销的语义全都不成立
    (会得到"注册成功但注销不掉"这种自相矛盾的结果)。
    """
    if qapp.platformName() == "offscreen":
        pytest.skip("offscreen 平台没有真窗口句柄,跳过真注册")
    window.resize(120, 60)
    window.show()
    qapp.processEvents()
    hwnd = int(window.winId())
    if hwnd <= 1:
        pytest.skip(f"这个平台拿不到真窗口句柄(winId={hwnd}),跳过真注册")
    return hwnd


@requires_windows
def test_invalid_handle_reports_1400_invalid_window_handle():
    """用占位句柄注册必须失败,并且 GetLastError 是 1400。

    这条同时钉住"ctypes 调用真的走到底了"——不显式声明 argtypes 时,
    64 位下句柄会被截断成 32 位,错误码就不是 1400 了。
    """
    ctypes.set_last_error(0)
    mgr = gh.GlobalHotkeys()
    assert mgr._register(1, 0x4C44, gh.MOD_CONTROL | gh.MOD_ALT, 0x4F) is False
    assert ctypes.get_last_error() == 1400


@requires_windows
def test_register_and_release_real_hotkey(qapp):
    """真窗口上注册 → 收到 WM_HOTKEY 的 id → 注销后不再响应。

    只在真机跑:offscreen 平台的 ``QWidget.winId()`` 是占位值 1,
    注册必然失败(见上面那条),所以这里要一个能拿到真句柄的窗口。
    """
    from PySide6.QtWidgets import QWidget

    window = QWidget()
    hwnd = real_hwnd_or_skip(qapp, window)

    calls = []
    mgr = gh.GlobalHotkeys()
    try:
        result = mgr.apply(
            hwnd,
            {"z_order": "Ctrl+Alt+1", "fixed": "Ctrl+Alt+2", "compact": "Ctrl+Alt+3"},
            {
                "z_order": lambda: calls.append("z_order"),
                "fixed": lambda: calls.append("fixed"),
                "compact": lambda: calls.append("compact"),
            },
        )
        assert result == {"z_order": True, "fixed": True, "compact": True}
        assert mgr.bound_actions() == ("z_order", "fixed", "compact")

        # 注册成功的 id 应当能被分派到对应回调
        ids = {action: hotkey_id for hotkey_id, action in mgr._ids.items()}
        assert mgr.handle_hotkey(ids["compact"]) is True
        assert calls == ["compact"]

        # 同一个组合键再注册一次必然失败(已被自己占用),证明真的进了系统
        again = gh.GlobalHotkeys()
        dup = again.apply(hwnd, {"z_order": "Ctrl+Alt+1"}, {"z_order": lambda: None})
        assert dup == {"z_order": False}
        again.release()
    finally:
        mgr.release()
    assert mgr.bound_actions() == ()
    window.close()


def test_handle_hotkey_debounces_system_double_post(monkeypatch):
    """一次按键系统会投两条 WM_HOTKEY,回调只能被调一次。

    实测(``lumistdo-dev/probe_hotkey_downup.py``):只注入"按下"就收到 2 条,
    "抬起"0 条。循环动作(层级三态)连切两下正好回到原位,用户看到的就是
    "按了没反应",所以必须去抖。
    """
    calls = []
    mgr = gh.GlobalHotkeys()
    mgr._ids = {gh.GlobalHotkeys._FIRST_ID: "z_order"}
    mgr._handlers = {"z_order": lambda: calls.append("z_order")}

    assert mgr.handle_hotkey(gh.GlobalHotkeys._FIRST_ID) is True
    assert mgr.handle_hotkey(gh.GlobalHotkeys._FIRST_ID) is False   # 重复投递被吃掉
    assert calls == ["z_order"]

    # 过了保护窗口就恢复正常
    monkeypatch.setattr(
        mgr, "_last_fired",
        {"z_order": __import__("time").monotonic() - mgr._REPEAT_GUARD_SECONDS - 1},
    )
    assert mgr.handle_hotkey(gh.GlobalHotkeys._FIRST_ID) is True
    assert calls == ["z_order", "z_order"]


@requires_windows
def test_release_unregisters_with_the_registration_handle(qapp):
    """注销必须用注册时那个 hwnd,否则会留下"孤儿热键"。

    这条钉住真踩过的坑:窗口被 Qt 重建后重新 ``apply()``,旧代码用
    ``UnregisterHotKey(None, id)`` 注销(静默失败)→ 再注册返回 1409(被自己占)
    → 系统仍投 WM_HOTKEY,但 ``_ids`` 已清空,于是"按键有反应"变成"什么都没发生"。
    所以注销之后,**同一个 hwnd** 再注册必须能成功。
    """
    from PySide6.QtWidgets import QWidget

    window = QWidget()
    hwnd = real_hwnd_or_skip(qapp, window)

    first = gh.GlobalHotkeys()
    second = gh.GlobalHotkeys()
    try:
        assert first.apply(
            hwnd, {"z_order": "Ctrl+Alt+1"}, {"z_order": lambda: None},
        ) == {"z_order": True}
        first.release()
        # 注销干净了:别人(自己另一个实例)现在能注册同一个组合键
        assert second.apply(
            hwnd, {"z_order": "Ctrl+Alt+1"}, {"z_order": lambda: None},
        ) == {"z_order": True}
    finally:
        first.release()
        second.release()
    window.close()
