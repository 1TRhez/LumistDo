"""外观设置持久化与字体选择测试。"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import QApplication, QColorDialog

from lumistdo.app_settings import AppSettings, DEFAULT_TITLE_TEXT, MIN_BG_OPACITY
from lumistdo.settings_dialog import SettingsWindow


@pytest.fixture
def app():
    return QApplication.instance() or QApplication(sys.argv)


def test_font_settings_persist_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    settings = AppSettings(
        font_family="Arial",
        font_size=16,
    )
    settings.save(path)

    loaded = AppSettings.load(path)
    assert loaded.font_family == "Arial"
    assert loaded.font_size == 16
    assert list(tmp_path.glob(".settings.json.*.tmp")) == []


def test_window_geometry_persists_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    settings = AppSettings(
        window_x=120,
        window_y=80,
        window_width=360,
        window_height=520,
    )
    settings.save(path)

    loaded = AppSettings.load(path)
    assert (loaded.window_x, loaded.window_y) == (120, 80)
    assert (loaded.window_width, loaded.window_height) == (360, 520)


def test_background_opacity_starts_at_one_percent(app, tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"bg_opacity": 0}', encoding="utf-8")

    loaded = AppSettings.load(path)
    window = SettingsWindow(loaded)

    assert loaded.bg_opacity == MIN_BG_OPACITY
    assert window._op_slider.minimum() == MIN_BG_OPACITY
    window._op_slider.setValue(window._op_slider.minimum())
    assert window._op_label.text() == "1%"


def test_font_combo_updates_family_without_system_dialog(app):
    settings = AppSettings()
    window = SettingsWindow(settings)
    current = window._font_combo.currentText()
    family = next(
        (name for name in QFontDatabase.families() if name != current),
        current,
    )

    window._font_combo.setCurrentText(family)
    window._on_font_activated(family)

    assert settings.font_family == family


def test_font_search_uses_plain_editable_combo_and_contains_matching(app):
    window = SettingsWindow(AppSettings())
    assert window._font_combo.isEditable()
    assert window._font_combo.completer().filterMode() == Qt.MatchContains
    assert window._font_combo.count() == len(QFontDatabase.families())


def test_custom_colors_persist_roundtrip(app, tmp_path):
    """取色器用过的自定义颜色要跨重启记住(自定义预设按钮已删除)。"""
    path = tmp_path / "settings.json"
    settings = AppSettings()
    window = SettingsWindow(settings)
    QColorDialog.setCustomColor(0, QColor("#123456"))
    window._remember_custom_colors()
    settings.bg_color = "#334455"
    settings.text_color = "#f1f2f3"
    settings.font_size = 17
    settings.save(path)

    loaded = AppSettings.load(path)
    assert loaded.custom_colors[0] == "#123456"
    assert loaded.bg_color == "#334455"
    assert loaded.text_color == "#f1f2f3"
    assert loaded.font_size == 17


def test_language_persists_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    settings = AppSettings(language="en")
    settings.save(path)
    assert AppSettings.load(path).language == "en"


def test_language_default_is_zh():
    assert AppSettings().language == "zh"


def test_always_on_top_persists_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    AppSettings(always_on_top=True).save(path)
    assert AppSettings.load(path).always_on_top is True


def test_always_on_top_default_false_and_invalid_rejected(tmp_path):
    assert AppSettings().always_on_top is False
    path = tmp_path / "settings.json"
    path.write_text('{"always_on_top": "yes"}', encoding="utf-8")
    assert AppSettings.load(path).always_on_top is False


def test_language_invalid_value_rejected(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"language": "fr"}', encoding="utf-8")
    assert AppSettings.load(path).language == "zh"


def test_settings_window_language_combo_reflects_setting(app):
    settings = AppSettings(language="en")
    window = SettingsWindow(settings)
    assert window._lang_combo.currentData() == "en"
    assert window.windowTitle() == "Settings"

    zh_settings = AppSettings(language="zh")
    zh_window = SettingsWindow(zh_settings)
    assert zh_window._lang_combo.currentData() == "zh"
    assert zh_window.windowTitle() == "设置"


# ---- 语言切换两段式交互(模拟弹窗,无头) ----
def _patch_message_boxes(monkeypatch, answers):
    """模拟 QMessageBox:answers 按弹窗出现顺序作答,True=第一个按钮(AcceptRole)。"""
    from PySide6.QtWidgets import QMessageBox as MB

    state = {"calls": 0}

    def fake_exec(self):
        ans = answers[min(state["calls"], len(answers) - 1)]
        state["calls"] += 1
        role = MB.AcceptRole if ans else MB.RejectRole
        picked = None
        for btn in self.buttons():
            if self.buttonRole(btn) == role:
                picked = btn
                break
        self._fake_picked = picked
        return 0

    monkeypatch.setattr(MB, "exec", fake_exec)
    monkeypatch.setattr(
        MB, "clickedButton", lambda self: getattr(self, "_fake_picked", None),
    )
    return state


def test_language_cancel_reverts_combo(app, monkeypatch):
    from lumistdo.i18n import set_language

    _patch_message_boxes(monkeypatch, [False])  # 点"取消"
    settings = AppSettings(language="zh")
    window = SettingsWindow(settings)
    window._lang_combo.setCurrentIndex(1)
    assert settings.language == "zh"          # 未保存
    assert window._lang_combo.currentIndex() == 0  # 下拉框回退
    set_language("zh")


def test_language_confirm_later_saves_without_restart(app, monkeypatch):
    from lumistdo import settings_dialog
    from lumistdo.i18n import set_language

    _patch_message_boxes(monkeypatch, [True, False])  # 确认 + 稍后
    restarted = []
    monkeypatch.setattr(settings_dialog, "restart_app", lambda: restarted.append(True))
    settings = AppSettings(language="zh")
    window = SettingsWindow(settings)
    window._lang_combo.setCurrentIndex(1)
    assert settings.language == "en"
    assert restarted == []                    # 未触发重启
    set_language("zh")


def test_language_confirm_restart_now_calls_restart(app, monkeypatch):
    from lumistdo import settings_dialog
    from lumistdo.i18n import set_language

    _patch_message_boxes(monkeypatch, [True, True])  # 确认 + 立即重启
    restarted = []
    monkeypatch.setattr(settings_dialog, "restart_app", lambda: restarted.append(True))
    settings = AppSettings(language="zh")
    window = SettingsWindow(settings)
    window._lang_combo.setCurrentIndex(1)
    assert settings.language == "en"
    assert restarted == [True]                # 触发了重启
    set_language("zh")


def test_position_fixed_persists_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    AppSettings(position_fixed=True).save(path)
    assert AppSettings.load(path).position_fixed is True

    AppSettings(position_fixed=False).save(path)
    assert AppSettings.load(path).position_fixed is False


def test_non_bool_position_flags_fall_back_to_default(tmp_path):
    """非布尔值不写入,沿用默认 False(与其他字段的白名单校验一致)。"""
    path = tmp_path / "settings.json"
    path.write_text(
        '{"position_fixed": "yes", "always_on_bottom": 1, "always_on_top": null}',
        encoding="utf-8",
    )
    loaded = AppSettings.load(path)
    assert loaded.position_fixed is False
    assert loaded.always_on_bottom is False
    assert loaded.always_on_top is False


def test_title_text_persists_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    AppSettings(title_text="今天要做的事").save(path)
    assert AppSettings.load(path).title_text == "今天要做的事"
    assert AppSettings(title_text="").save(path) is None
    assert AppSettings.load(path).title_text == ""


def test_title_text_is_cleaned_and_truncated(tmp_path):
    """换行/制表符折叠成空格,超长按上限截断(与输入框 maxLength 一致)。"""
    from lumistdo.app_settings import MAX_TITLE_LENGTH

    path = tmp_path / "settings.json"
    path.write_text(
        '{"title_text": "  a\\nb\\tc  "}', encoding="utf-8",
    )
    assert AppSettings.load(path).title_text == "a b c"

    path.write_text(
        '{"title_text": "%s"}' % ("字" * (MAX_TITLE_LENGTH + 20)), encoding="utf-8",
    )
    assert len(AppSettings.load(path).title_text) == MAX_TITLE_LENGTH


def test_non_string_title_falls_back_to_default(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"title_text": 42}', encoding="utf-8")
    assert AppSettings.load(path).title_text == DEFAULT_TITLE_TEXT
    # 老版本设置文件里没有这个键 → 显示默认标语
    path.write_text('{"bg_color": "#25262c"}', encoding="utf-8")
    assert AppSettings.load(path).title_text == DEFAULT_TITLE_TEXT


def test_autostart_persists_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    AppSettings(autostart=True).save(path)
    assert AppSettings.load(path).autostart is True
    path.write_text('{"autostart": "yes"}', encoding="utf-8")
    assert AppSettings.load(path).autostart is False


@pytest.mark.skipif(sys.platform != "win32", reason="注册表只在 Windows 上有")
def test_autostart_module_writes_and_removes_run_entry(monkeypatch):
    """真读写注册表,但换到测试专用的子键,绝不碰用户真正的 Run 项。"""
    import winreg

    from lumistdo import autostart

    test_key = rf"Software\LumistDoTest\Run-{os.getpid()}"
    monkeypatch.setattr(autostart, "RUN_KEY", test_key)
    try:
        assert autostart.is_enabled() is False
        assert autostart.set_enabled(True) is True
        assert autostart.is_enabled() is True
        assert autostart.current_command() == autostart.startup_command()
        assert autostart.startup_command().startswith('"')

        assert autostart.set_enabled(False) is True
        assert autostart.is_enabled() is False
        # 关掉之后注册表里不该留空值
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, test_key) as key:
            with pytest.raises(FileNotFoundError):
                winreg.QueryValueEx(key, autostart.VALUE_NAME)
        # 重复关一次也算成功(幂等)
        assert autostart.set_enabled(False) is True
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, test_key)
        except FileNotFoundError:
            pass


def test_always_on_bottom_wins_over_top_in_saved_file(tmp_path):
    """置顶与置底互斥:文件里两个都为真时以置底为准。"""
    path = tmp_path / "settings.json"
    path.write_text(
        '{"always_on_top": true, "always_on_bottom": true}',
        encoding="utf-8",
    )
    loaded = AppSettings.load(path)
    assert loaded.always_on_bottom is True
    assert loaded.always_on_top is False


def test_settings_window_checks_follow_settings(app):
    settings = AppSettings(always_on_bottom=True, position_fixed=True)
    window = SettingsWindow(settings)
    assert window._layer_radios["top"].isChecked() is False
    assert window._layer_radios["bottom"].isChecked() is True
    assert window._fixed_check.isChecked() is True


def test_settings_window_top_and_bottom_are_mutually_exclusive(app):
    """选置底自动取消置顶,并把具体层级名回传主窗口。"""
    settings = AppSettings(always_on_top=True)
    window = SettingsWindow(settings)
    emitted = []
    window.z_order_changed.connect(emitted.append)

    window._layer_radios["bottom"].setChecked(True)

    assert settings.always_on_bottom is True
    assert settings.always_on_top is False
    assert window._layer_radios["top"].isChecked() is False
    assert emitted == ["bottom"]

    # 反向:选回置顶会自动取消置底
    window._layer_radios["top"].setChecked(True)
    assert settings.always_on_top is True
    assert settings.always_on_bottom is False
    assert window._layer_radios["bottom"].isChecked() is False
    assert emitted == ["bottom", "top"]


def test_settings_window_emits_position_fixed_signal(app):
    settings = AppSettings()
    window = SettingsWindow(settings)
    emitted = []
    window.position_fixed_changed.connect(emitted.append)

    window._fixed_check.setChecked(True)

    assert settings.position_fixed is True
    assert emitted == [True]


def test_light_theme_darkens_text_and_chrome(app):
    """切到浅色主题时字色要变深,标题与页脚的固定灰也要跟着压暗。

    否则浅底上还是浅灰字,等于看不见——这是用「素白」预设最容易踩的坑。
    """
    dark = AppSettings(bg_color="#25262c", text_color="#e9e9ef").to_theme()
    light = AppSettings(bg_color="#f2f2f4", text_color="#2c2c32").to_theme()

    assert dark.is_dark is True
    assert light.is_dark is False

    def luminance(color):
        return (
            0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
        )

    for name in ("fixed_title_color", "fixed_footer_color"):
        dark_gray = luminance(getattr(dark, name))
        light_gray = luminance(getattr(light, name))
        assert light_gray < dark_gray, f"{name} 在浅色主题下应该更深"
        assert light_gray < 140, f"{name} 在浅色主题下仍然太浅,糊在浅底上"

    # 用户自定义的正文颜色要原样保留,不能被"自动加深"改掉
    assert light.text_color.name() == "#2c2c32"
    assert luminance(light.text_color) < luminance(dark.text_color)

