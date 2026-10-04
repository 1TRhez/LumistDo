"""全局快捷键:窗口不在前台时也能触发顶栏那三个动作。

Qt 的 ``QShortcut`` 是**窗口级**绑定:主窗口没被选中(用户正在别的程序里)
就完全不响应。而「切换窗口层级 / 固定位置 / 缩略模式」这三件事天生是
"在别的窗口里干活时顺手拨一下"的动作,所以要走 Win32 的 ``RegisterHotKey``
注册成系统级热键 —— 它是全局独占的,注册成功后无论焦点在哪都会被系统路由到
本进程的消息队列。

代价与限制(写清楚,免得以后踩):

* ``RegisterHotKey`` 是**独占**的。一旦注册了 ``Ctrl+L``,别的软件就收不到这个键了。
  所以设置里给了一个「全局快捷键」开关,不想要就关掉(关掉后仍按老办法用
  ``QShortcut``,只在窗口被选中时响应)。
* 必须带修饰键。不带修饰键的全局热键会吃掉整个键盘(单独一个字母再也打不出来),
  ``vk_and_mods`` 对这种绑定直接返回空,调用方跳过注册。
* 非 Windows 平台没有这套机制,``supported()`` 返回 False,调用方一律走 ``QShortcut``。
"""

from __future__ import annotations

import sys
import time

from PySide6.QtCore import QAbstractNativeEventFilter, Qt

from .i18n import t  # noqa: F401  (保留给将来做失败提示)

_IS_WINDOWS = sys.platform == "win32"

# 功能键区(F1~F24)是连续的,单独放一张表不用写 24 行
_FUNCTION_KEYS = {Qt.Key_F1 + i: 0x70 + i for i in range(24)}

_VK_KEYS = {
    # 字母与数字的 VK 码就是 ASCII:VK_A=0x41 … VK_Z=0x5A,VK_0=0x30 … VK_9=0x39
    **{Qt.Key_A + i: 0x41 + i for i in range(26)},
    **{Qt.Key_0 + i: 0x30 + i for i in range(10)},
    **_FUNCTION_KEYS,
    Qt.Key_Space: 0x20,
    Qt.Key_Tab: 0x09,
    Qt.Key_Backtab: 0x09,
    Qt.Key_Return: 0x0D,
    Qt.Key_Enter: 0x0D,
    Qt.Key_Escape: 0x1B,
    Qt.Key_Backspace: 0x08,
    Qt.Key_Delete: 0x2E,
    Qt.Key_Insert: 0x2D,
    Qt.Key_Home: 0x24,
    Qt.Key_End: 0x23,
    Qt.Key_PageUp: 0x21,
    Qt.Key_PageDown: 0x22,
    Qt.Key_Left: 0x25,
    Qt.Key_Up: 0x26,
    Qt.Key_Right: 0x27,
    Qt.Key_Down: 0x28,
    Qt.Key_Print: 0x2C,
    Qt.Key_ScrollLock: 0x91,
    Qt.Key_Pause: 0x13,
    Qt.Key_NumLock: 0x90,
    Qt.Key_CapsLock: 0x14,
    Qt.Key_Menu: 0x5D,
    Qt.Key_Semicolon: 0xBA,
    Qt.Key_Equal: 0xBB,
    Qt.Key_Comma: 0xBC,
    Qt.Key_Minus: 0xBD,
    Qt.Key_Period: 0xBE,
    Qt.Key_Slash: 0xBF,
    Qt.Key_QuoteLeft: 0xC0,
    Qt.Key_BracketLeft: 0xDB,
    Qt.Key_Backslash: 0xDC,
    Qt.Key_BracketRight: 0xDD,
    Qt.Key_Apostrophe: 0xDE,
}

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
# Win7 以后支持:按住不放只触发一次,而不是系统自动重复触发
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312


def supported() -> bool:
    """只有 Windows 有 RegisterHotKey。"""
    return _IS_WINDOWS


def vk_and_mods(sequence: str) -> tuple[int, int] | None:
    """把 ``"Ctrl+Alt+O"`` 这样的绑定翻成 ``(virtual_key, modifiers)``。

    返回 None 表示这个绑定**不能**做成全局热键:解析不出来,或者没带修饰键
    (不带修饰键的全局热键会把整个键盘吃干净)。
    """
    # 不导入 QKeyCombination:6.11 的 PySide6 里没有这个名字(用不到,
    # seq[0] 拿到的对象本身就有 key() / keyboardModifiers())
    from PySide6.QtGui import QKeySequence

    seq = QKeySequence(sequence)
    if seq.isEmpty():
        return None
    combo = seq[0]
    key = combo.key()
    vk = _VK_KEYS.get(key)
    if vk is None:
        return None
    mods = combo.keyboardModifiers()
    win_mods = 0
    if mods & Qt.AltModifier:
        win_mods |= MOD_ALT
    if mods & Qt.ControlModifier:
        win_mods |= MOD_CONTROL
    if mods & Qt.ShiftModifier:
        win_mods |= MOD_SHIFT
    if mods & Qt.MetaModifier:
        win_mods |= MOD_WIN
    if not win_mods:
        return None
    return vk, win_mods


class GlobalHotkeys(QAbstractNativeEventFilter):
    """一组全局热键:注册、注销、收到 WM_HOTKEY 时分派给回调。

    必须自己持有实例的强引用(``app.installNativeEventFilter(manager)``
    不会替你保活) —— 用 ``QApplication.nativeEventFilter`` 的调用方要把它
    存成属性,否则对象被回收后系统仍往这个地址投递,直接崩。
    """

    # 起始 id:0 也是合法 id,但用非零值方便排查"到底是哪一条触发的"
    _FIRST_ID = 0x4C44  # "LD"

    # 同一条热键在这么短时间内只认一次。系统对**一次**组合键按键会投递两条
    # WM_HOTKEY(实测:只注入"按下"就收到 2 条,抬起 0 条;三条 keybd_event
    # 完成的组合键会被算成两次),不去抖的话"按一次切两下"——层级这种循环动作
    # 连切两下正好回到原位,用户看到的就是"按了没反应"。
    _REPEAT_GUARD_SECONDS = 0.3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ids = {}          # id -> action 名
        self._handlers = {}     # action 名 -> 回调
        self._bindings = {}     # action 名 -> 绑定文本(便于排查)
        self._next_id = self._FIRST_ID
        self._hwnd = 0          # 注册时用的窗口句柄:注销必须用**同一个**,见 release()
        self._last_fired = {}   # action 名 -> 上次触发时间(去抖用)

    # ---- 注册 / 注销 ----
    def apply(self, hwnd: int, bindings: dict, handlers: dict) -> dict:
        """按 ``{action: "Ctrl+O"}`` 重建全部注册,返回 ``{action: 是否成功}``。

        ``hwnd`` 是接收 WM_HOTKEY 的窗口;注册失败(被别的程序占了、绑定不带
        修饰键)会在返回结果里标 False,调用方据此决定要不要退回 QShortcut。
        """
        self.release()
        self._hwnd = int(hwnd or 0)
        result = {}
        self._handlers = dict(handlers)
        for action, sequence in bindings.items():
            result[action] = False
            if not sequence:
                continue
            parsed = vk_and_mods(sequence)
            if parsed is None:
                continue
            vk, mods = parsed
            hotkey_id = self._next_id
            if not self._register(self._hwnd, hotkey_id, mods | MOD_NOREPEAT, vk):
                continue
            self._next_id += 1
            self._ids[hotkey_id] = action
            self._bindings[action] = sequence
            result[action] = True
        return result

    def release(self):
        """注销全部热键(退出前、改键前都要调,否则会一直占着键不放)。

        必须把**注册时那个 hwnd** 原样传给 ``UnregisterHotKey``:它是按
        "(窗口, id)" 这一对来登记的,传 NULL 只对"注册时也没传窗口"的
        (挂在线程队列上的)热键有效。传错了会静默失败,留下一个**孤儿热键**
        —— 系统照样把 WM_HOTKEY(id 是我们发的)投过来,但我们的 ``_ids``
        已经清空,于是"按键有反应"变成"什么都没发生"。这个坑真踩过:
        窗口被 Qt 重建后重新 ``apply()``,就是先注销失败、再注册失败(1409),
        最后只剩一个没人认领的热键。
        """
        if not _IS_WINDOWS:
            self._ids.clear()
            self._bindings.clear()
            self._hwnd = 0
            return
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.UnregisterHotKey.restype = ctypes.c_int
        handle = ctypes.c_void_p(self._hwnd) if self._hwnd else None
        for hotkey_id in list(self._ids):
            user32.UnregisterHotKey(handle, hotkey_id)
        self._ids.clear()
        self._bindings.clear()
        self._hwnd = 0

    def _register(self, hwnd: int, hotkey_id: int, mods: int, vk: int) -> bool:
        if not _IS_WINDOWS or not hwnd:
            return False
        import ctypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
        ]
        user32.RegisterHotKey.restype = ctypes.c_int
        ok = user32.RegisterHotKey(
            ctypes.c_void_p(hwnd), hotkey_id, ctypes.c_uint(mods), ctypes.c_uint(vk),
        )
        return bool(ok)

    # ---- 派发 ----
    def bound_actions(self) -> tuple:
        """当前真的注册成功、会响应的动作名(测试与排查用)。"""
        return tuple(self._bindings)

    def handle_hotkey(self, hotkey_id: int) -> bool:
        """按热键 id 调回调;返回是否命中并真的调用了。

        独立成方法是为了能脱离真实消息循环测(offscreen 平台拿不到
        真的 ``WM_HOTKEY``,真机验收另算)。

        带一层去抖:同一条热键在 ``_REPEAT_GUARD_SECONDS`` 内只认第一次
        (系统一次按键会投两条,见 ``_REPEAT_GUARD_SECONDS`` 的注释)。
        """
        action = self._ids.get(int(hotkey_id))
        if action is None:
            return False
        handler = self._handlers.get(action)
        if handler is None:
            return False
        now = time.monotonic()
        if now - self._last_fired.get(action, -1e9) < self._REPEAT_GUARD_SECONDS:
            return False
        self._last_fired[action] = now
        handler()
        return True

    def nativeEventFilter(self, event_type, message):
        """收到 WM_HOTKEY 就调对应回调。返回 ``(False, 0)`` 表示不拦截消息。"""
        if not _IS_WINDOWS or event_type != b"windows_generic_MSG":
            return False, 0
        try:
            import ctypes
            from ctypes import wintypes

            class MSG(ctypes.Structure):
                _fields_ = [
                    ("hwnd", wintypes.HWND),
                    ("message", wintypes.UINT),
                    ("wParam", ctypes.c_size_t),
                    ("lParam", ctypes.c_ssize_t),
                    ("time", wintypes.DWORD),
                    ("pt_x", wintypes.LONG),
                    ("pt_y", wintypes.LONG),
                ]

            try:
                msg = ctypes.cast(
                    int(message), ctypes.POINTER(MSG),
                ).contents
            except (TypeError, ValueError):
                return False, 0
            if msg.message != WM_HOTKEY:
                return False, 0
            self.handle_hotkey(int(msg.wParam))
        except Exception:  # noqa: BLE001 —— 事件过滤里绝不能把异常抛给 Qt
            return False, 0
        return False, 0
