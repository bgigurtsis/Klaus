"""Tests for the macOS Desk View launcher."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from klaus.ui.camera_widget import CameraWidget
from klaus.ui.desk_view_setup import (
    _launch_native_desk_view,
    _open_photo_booth,
    launch_desk_view_setup,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_native_launcher_uses_avfoundation() -> None:
    application = MagicMock()
    desk_view_class = MagicMock()
    desk_view_class.alloc.return_value.init.return_value = application
    avfoundation = SimpleNamespace(AVCaptureDeskViewApplication=desk_view_class)

    with patch.object(sys, "platform", "darwin"), patch.dict(
        sys.modules, {"AVFoundation": avfoundation}
    ):
        assert _launch_native_desk_view() is True

    application.presentWithCompletionHandler_.assert_called_once()


def test_api_key_screen_supports_gemini_and_openai() -> None:
    from klaus.ui.shared.key_validation import KEY_PATTERNS, KEY_URLS

    assert KEY_PATTERNS == [
        ("Gemini", "gemini", "AIza", 20),
        ("OpenAI", "openai", "sk-", 20),
    ]
    assert KEY_URLS["gemini"] == "https://aistudio.google.com/app/apikey"
    assert KEY_URLS["openai"] == "https://platform.openai.com/api-keys"


@patch("klaus.ui.desk_view_setup.subprocess.Popen")
def test_photo_booth_fallback_opens_camera_app(mock_popen) -> None:
    with patch.object(sys, "platform", "darwin"):
        assert _open_photo_booth() is True

    mock_popen.assert_called_once()
    assert mock_popen.call_args.args[0] == ["/usr/bin/open", "-a", "Photo Booth"]


@patch("klaus.ui.desk_view_setup._show_desk_view_instructions")
@patch("klaus.ui.desk_view_setup._open_photo_booth", return_value=True)
@patch("klaus.ui.desk_view_setup._launch_native_desk_view", return_value=False)
def test_fallback_explains_how_to_enable_desk_view(
    _mock_native,
    _mock_photo_booth,
    mock_information,
) -> None:
    launch_desk_view_setup()

    intro = mock_information.call_args.args[2]
    steps = mock_information.call_args.args[3]
    assert "Photo Booth is opening" in intro
    assert any("Video icon" in step for step in steps)
    assert any("Choose Desk View" in step for step in steps)
    assert any("Start Desk View" in step for step in steps)


@patch("klaus.ui.camera_widget.launch_desk_view_setup")
def test_startup_launches_selected_desk_view(mock_launch, qt_app) -> None:
    camera = SimpleNamespace(
        device_index=-2,
        is_running=True,
        waiting_message="Waiting for Desk View",
    )
    widget = CameraWidget()

    with patch.object(QTimer, "singleShot") as mock_single_shot:
        widget.set_camera(camera)

    assert widget._status_badge.text() == "Waiting"
    callback = mock_single_shot.call_args.args[1]
    callback()
    mock_launch.assert_called_once_with(widget)


@patch("klaus.ui.camera_widget.launch_desk_view_setup")
def test_selecting_active_desk_view_reopens_setup(mock_launch, qt_app) -> None:
    camera = SimpleNamespace(device_index=-2)
    widget = CameraWidget()
    widget._camera = camera
    widget.set_source_selection(-2)

    widget._on_source_activated(0)

    mock_launch.assert_called_once_with(widget)


def test_preview_only_marks_desk_view_live_after_a_frame(qt_app) -> None:
    frame = np.ones((20, 30, 3), dtype=np.uint8)
    camera = SimpleNamespace(
        device_index=-2,
        is_running=True,
        waiting_message="Waiting for Desk View",
        get_frame_rgb=MagicMock(return_value=frame),
    )
    widget = CameraWidget()

    with patch.object(QTimer, "singleShot"):
        widget.set_camera(camera)
    widget._update_frame()

    assert widget._status_badge.text() == "Live"
