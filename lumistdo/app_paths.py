"""软件目录与本地数据文件路径。

用户数据存放在 %APPDATA%\\LumistDo,与安装目录解耦:
安装/更新/卸载覆盖程序文件时不会碰到数据。
旧便携版(程序目录内 .lumistdo)的数据在首次启动时一次性迁入。
更早期版本用的数据目录名不同,首次启动时也会自动迁入(见 LEGACY_APP_DIR_NAME)。
"""

import os
import shutil
import sys
from pathlib import Path

APP_DIR_NAME = "LumistDo"
# 更早期版本用过的数据目录名。首次启动时搬过来,让老用户无感升级。
LEGACY_APP_DIR_NAME = "LumistDo"
LEGACY_DIR_NAME = ".lumistdo"
_DATA_FILES = ("tasks.json", "settings.json")


def software_dir() -> Path:
    """返回源码入口或打包后可执行文件所在目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def icon_file() -> Path:
    """应用图标路径:源码态在软件目录 assets/;打包态 PyInstaller 放进 _internal。"""
    candidate = software_dir() / "assets" / "icon.ico"
    if candidate.exists():
        return candidate
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / "assets" / "icon.ico"
    return candidate


def _migrate_legacy_data(target: Path) -> None:
    """新数据目录为空且程序目录旁有旧版数据时,复制 tasks/settings 过来。

    只迁一次:目标目录已有任何文件即跳过;只复制不删除旧文件,
    失败静默(不影响启动,用户仍得到全新空数据)。
    """
    try:
        if any(target.iterdir()):
            return
    except FileNotFoundError:
        pass
    except OSError:
        return
    legacy = software_dir() / LEGACY_DIR_NAME
    if not legacy.is_dir():
        return
    for name in _DATA_FILES:
        src = legacy / name
        if src.is_file():
            try:
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target / name)
            except OSError:
                pass


def _migrate_appdata_data(base: Path, target: Path) -> None:
    """把早期版本目录(LEGACY_APP_DIR_NAME)里的数据搬到新目录。

    逐个文件判断:目标已有同名文件就不覆盖(尊重新目录里的现状);
    复制成功后才删掉旧文件,下次启动不会重复搬。失败静默——迁移是尽力而为,
    绝不能因为老数据读不动就挡住启动。
    """
    old = base / LEGACY_APP_DIR_NAME
    if not old.is_dir() or old.resolve() == target.resolve():
        return
    for name in _DATA_FILES:
        src = old / name
        if not src.is_file():
            continue
        try:
            if not (target / name).exists():
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target / name)
            src.unlink()
        except OSError:
            pass


def data_dir() -> Path:
    """用户数据目录(%APPDATA%\\LumistDo),取用时顺带做旧数据迁移。"""
    base = Path(
        os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    )
    target = base / APP_DIR_NAME
    _migrate_appdata_data(base, target)
    _migrate_legacy_data(target)
    return target


DATA_DIR = data_dir()
TASKS_FILE = DATA_DIR / "tasks.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
