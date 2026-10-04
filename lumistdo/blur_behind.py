"""真·毛玻璃:让 Windows 合成器把窗口背后的桌面内容模糊掉。

普通半透明窗口只能"透过去看见"背后内容,是清清楚楚地看见;要让背后变糊,
必须动用 DWM 的 blur-behind。实测(见工作区的 probe_blur_checker.py):

- `SetWindowCompositionAttribute` + `ACCENT_ENABLE_BLURBEHIND`(3) → **有效**,黑白
  棋盘的局部对比度从 17.3 掉到 3.4,均值仍是 127(只糊不染色,正是要的效果)
- `ACCENT_ENABLE_ACRYLICBLURBEHIND`(4) 与 `ACCENT_ENABLE_HOSTBACKDROP`(5) → 在这台
  Win11 上返回成功但**什么都不做**(对比度 16.2,与不加效果完全一样),所以不用
- 已废弃的 `DwmEnableBlurBehindWindow` 返回 S_OK 但同样不生效

这个 API 未公开(`SetWindowCompositionAttribute` 不在任何 SDK 头文件里),所以整块
都用 `getattr` 取函数、失败就静默降级——毛玻璃只是锦上添花,绝不能挡住启动。
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_IS_WINDOWS = sys.platform == "win32"

WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_BLURBEHIND = 3

_user32 = ctypes.WinDLL("user32", use_last_error=True) if _IS_WINDOWS else None


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def _accent_function():
    if _user32 is None:
        return None
    fn = getattr(_user32, "SetWindowCompositionAttribute", None)
    if fn is None:
        return None
    fn.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA)]
    fn.restype = wintypes.BOOL
    return fn


def _abgr(alpha: int, red: int, green: int, blue: int) -> int:
    """GradientColor 要的是 ABGR(低字节是 alpha),不是常见的 ARGB。"""
    return (
        ((alpha & 0xFF) << 24)
        | ((blue & 0xFF) << 16)
        | ((green & 0xFF) << 8)
        | (red & 0xFF)
    )


def set_blur_behind(hwnd: int, enabled: bool, tint=(0, 0, 0, 0)) -> bool:
    """给窗口开关毛玻璃。tint 是 (r, g, b, a),a=0 表示不染色。

    返回是否真的调用了 API(平台不支持或没有该导出函数时为 False)。
    """
    fn = _accent_function()
    if fn is None or not hwnd:
        return False
    if enabled:
        red, green, blue, alpha = tint
        state = ACCENT_ENABLE_BLURBEHIND
        gradient = _abgr(alpha, red, green, blue)
    else:
        state = ACCENT_DISABLED
        gradient = 0
    policy = ACCENT_POLICY(state, 0, gradient, 0)
    data = WINDOWCOMPOSITIONATTRIBDATA(
        WCA_ACCENT_POLICY,
        ctypes.cast(ctypes.byref(policy), ctypes.c_void_p),
        ctypes.sizeof(policy),
    )
    return bool(fn(wintypes.HWND(hwnd), ctypes.byref(data)))


def apply_to_widget(widget, enabled: bool, tint=(0, 0, 0, 0)) -> bool:
    """便利入口:直接对 QWidget 用,自己取 HWND。"""
    if not _IS_WINDOWS:
        return False
    try:
        hwnd = int(widget.winId())
    except (RuntimeError, TypeError):
        return False
    return set_blur_behind(hwnd, enabled, tint)
