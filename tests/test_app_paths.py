"""软件目录与数据路径测试。"""

import sys

from lumistdo import app_paths
from lumistdo.app_paths import data_dir, icon_file, software_dir


def test_source_run_uses_project_directory():
    assert (software_dir() / "main.py").is_file()


def test_packaged_run_uses_executable_directory(monkeypatch, tmp_path):
    executable = tmp_path / "LumistDo.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert software_dir() == tmp_path


def test_data_dir_under_appdata(monkeypatch, tmp_path):
    """用户数据目录在 %APPDATA%\\LumistDo,与安装目录解耦。"""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    # 程序目录旁无旧数据,不产生迁移
    monkeypatch.setattr(app_paths, "software_dir", lambda: tmp_path / "prog")
    assert data_dir() == tmp_path / "LumistDo"


def test_migrates_legacy_portable_data_once(monkeypatch, tmp_path):
    """新数据目录为空且程序目录旁有旧版数据时,复制迁入且不覆盖已有数据。"""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    prog = tmp_path / "prog"
    legacy = prog / ".lumistdo"
    legacy.mkdir(parents=True)
    (legacy / "tasks.json").write_text("[1]", encoding="utf-8")
    (legacy / "settings.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(app_paths, "software_dir", lambda: prog)

    target = data_dir()
    assert (target / "tasks.json").read_text(encoding="utf-8") == "[1]"
    assert (target / "settings.json").exists()
    assert (legacy / "tasks.json").exists()  # 只复制,不删旧文件

    # 目标已有数据时不再覆盖(只迁一次)
    (target / "tasks.json").write_text("[2]", encoding="utf-8")
    data_dir()
    assert (target / "tasks.json").read_text(encoding="utf-8") == "[2]"


def test_icon_file_source_and_packaged(monkeypatch, tmp_path):
    """图标先找软件目录 assets/,打包态再退回 _MEIPASS。"""
    assert icon_file() == software_dir() / "assets" / "icon.ico"
    assert icon_file().is_file()

    monkeypatch.setattr(app_paths, "software_dir", lambda: tmp_path / "prog")
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "meipass"), raising=False)
    assert icon_file() == tmp_path / "meipass" / "assets" / "icon.ico"
