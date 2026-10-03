"""开机自启动:读写当前用户的 Run 注册表项。

只碰 ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`` 一个值,
不需要管理员权限,也不写任何系统级位置;非 Windows 平台一律当作"不支持"。
"""

from __future__ import annotations

import os
import sys

from . import APP_NAME

# Run 项里的值名:用英文产品名而不是界面上的中文名,
# 这样用户在任务管理器的"启动"页里能一眼认出是哪一行。
VALUE_NAME = APP_NAME

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def supported() -> bool:
    """非 Windows 没有这套机制。"""
    return sys.platform == "win32"


def startup_command() -> str:
    """写进 Run 项的命令行:带引号的可执行文件绝对路径。

    打包态 ``sys.executable`` 就是 LumistDo.exe;源码态是 python.exe,
    则连脚本路径一起写,方便开发时验证。
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if script:
        return f'"{sys.executable}" "{script}"'
    return f'"{sys.executable}"'


def is_enabled() -> bool:
    """Run 项里是否已经有这一条。"""
    if not supported():
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return False
    return bool(str(value).strip())


def current_command() -> str:
    """读出 Run 项里现有的命令行(没有则返回空串)。"""
    if not supported():
        return ""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
    except OSError:
        return ""
    return str(value)


def set_enabled(enabled: bool) -> bool:
    """打开/关闭开机自启动,返回是否成功。

    关掉时连值一起删掉,不在注册表里留空值。
    """
    if not supported():
        return False
    import winreg

    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, VALUE_NAME, 0, winreg.REG_SZ, startup_command(),
                )
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass  # 本来就没有,当作关掉成功
    except OSError:
        return False
    return True
