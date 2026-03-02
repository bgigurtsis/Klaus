"""Hotkey behavior tests for macOS § / Shift+§ semantics."""

from klaus.main import (
    _hotkey_action_for_press,
    _mark_key_pressed,
    _mark_key_released,
)
from klaus.ui.main_window import hotkey_action_for_keypress


def test_listener_plain_section_is_ptt_on_macos_shared_key() -> None:
    action = _hotkey_action_for_press(
        platform_name="darwin",
        key="§",
        ptt_key="§",
        toggle_key="§",
        shift_active=False,
    )
    assert action == "ptt_down"


def test_listener_shift_section_is_toggle_on_macos_shared_key() -> None:
    action = _hotkey_action_for_press(
        platform_name="darwin",
        key="§",
        ptt_key="§",
        toggle_key="§",
        shift_active=True,
    )
    assert action == "toggle"


def test_listener_repeated_press_is_debounced() -> None:
    pressed: set[object] = set()
    assert _mark_key_pressed(pressed, "§") is True
    assert _mark_key_pressed(pressed, "§") is False
    _mark_key_released(pressed, "§")
    assert _mark_key_pressed(pressed, "§") is True


def test_qt_plain_section_is_ptt_on_macos_shared_key() -> None:
    action = hotkey_action_for_keypress(
        key=167,
        shift_pressed=False,
        ptt_key=167,
        toggle_key=167,
        platform_name="darwin",
    )
    assert action == "ptt_down"


def test_qt_shift_section_is_toggle_on_macos_shared_key() -> None:
    action = hotkey_action_for_keypress(
        key=167,
        shift_pressed=True,
        ptt_key=167,
        toggle_key=167,
        platform_name="darwin",
    )
    assert action == "toggle"


def test_qt_distinct_toggle_key_keeps_normal_toggle_behavior() -> None:
    action = hotkey_action_for_keypress(
        key=114,  # r
        shift_pressed=False,
        ptt_key=113,  # q
        toggle_key=114,  # r
        platform_name="linux",
    )
    assert action == "toggle"
