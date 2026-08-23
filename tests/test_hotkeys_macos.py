"""Hotkey behavior tests for macOS § / Shift+§ semantics."""

import sys

import klaus.main as main_module
import pytest
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QPushButton
from klaus.main import (
    _hotkey_action_for_press,
    _mark_key_pressed,
    _mark_key_released,
    _should_disable_global_hotkeys,
)
from klaus.ui.main_window import MainWindow, hotkey_action_for_keypress


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def send_key_event(
    app: QApplication,
    child: QPushButton,
    event_type: QEvent.Type,
    key: int,
    modifiers: Qt.KeyboardModifier,
) -> None:
    app.sendEvent(child, QKeyEvent(event_type, key, modifiers))


def test_disables_global_hotkeys_on_macos_26_with_python_312(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        main_module.platform,
        "mac_ver",
        lambda: ("26.5.2", ("", "", ""), "arm64"),
    )
    monkeypatch.delenv("KLAUS_FORCE_GLOBAL_HOTKEYS", raising=False)

    assert _should_disable_global_hotkeys() is True


def test_allows_global_hotkeys_before_macos_26(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        main_module.platform,
        "mac_ver",
        lambda: ("15.7", ("", "", ""), "arm64"),
    )
    monkeypatch.delenv("KLAUS_FORCE_GLOBAL_HOTKEYS", raising=False)

    assert _should_disable_global_hotkeys() is False


def test_force_override_allows_global_hotkeys_on_macos_26(monkeypatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(
        main_module.platform,
        "mac_ver",
        lambda: ("26.5.2", ("", "", ""), "arm64"),
    )
    monkeypatch.setenv("KLAUS_FORCE_GLOBAL_HOTKEYS", "1")

    assert _should_disable_global_hotkeys() is False


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


def test_focused_child_cannot_consume_plain_section_hotkey(
    qt_app,
    monkeypatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    window = MainWindow()
    window.set_hotkeys("§", "§")
    child = QPushButton(window)
    presses: list[bool] = []
    releases: list[bool] = []
    window.ptt_key_pressed.connect(lambda: presses.append(True))
    window.ptt_key_released.connect(lambda: releases.append(True))

    send_key_event(
        qt_app,
        child,
        QEvent.Type.KeyPress,
        ord("§"),
        Qt.KeyboardModifier.NoModifier,
    )
    send_key_event(
        qt_app,
        child,
        QEvent.Type.KeyRelease,
        ord("§"),
        Qt.KeyboardModifier.NoModifier,
    )

    assert presses == [True]
    assert releases == [True]
    window.close()


def test_focused_child_cannot_consume_shift_section_hotkey(
    qt_app,
    monkeypatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    window = MainWindow()
    window.set_hotkeys("§", "§")
    child = QPushButton(window)
    toggles: list[bool] = []
    window.toggle_key_pressed.connect(lambda: toggles.append(True))

    send_key_event(
        qt_app,
        child,
        QEvent.Type.KeyPress,
        ord("±"),
        Qt.KeyboardModifier.ShiftModifier,
    )
    send_key_event(
        qt_app,
        child,
        QEvent.Type.KeyRelease,
        ord("±"),
        Qt.KeyboardModifier.ShiftModifier,
    )

    assert toggles == [True]
    window.close()
