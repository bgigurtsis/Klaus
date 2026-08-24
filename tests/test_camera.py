"""Tests for macOS reading-window capture."""

import base64
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from klaus.camera import Camera


def test_camera_has_no_frame_before_capture_starts():
    camera = Camera(device_index=-2)
    assert camera.get_frame() is None
    assert camera.get_frame_rgb() is None


def test_disabled_reading_source_starts_without_error():
    camera = Camera(device_index=-1)

    camera.start()

    assert camera.is_running is False


def test_active_window_text_refreshes_frame():
    camera = Camera(device_index=-3)
    source = MagicMock()
    frame = np.ones((100, 200, 3), dtype=np.uint8)
    source.capture_frame.return_value = frame
    source.capture_selected_text.return_value = "selected passage"
    camera._reading_source = source

    assert camera.capture_text_context() == "selected passage"
    assert np.array_equal(camera.get_frame(), frame)


def test_frame_encodes_as_base64_jpeg():
    camera = Camera(device_index=-2)
    camera._frame = np.zeros((100, 200, 3), dtype=np.uint8)
    with patch("klaus.camera.cv2.imencode", return_value=(True, np.frombuffer(b"jpeg", dtype=np.uint8))):
        assert base64.b64decode(camera.capture_base64_jpeg()) == b"jpeg"


def test_unsupported_reading_source_fails_cleanly():
    with pytest.raises(RuntimeError, match="Choose Desk View"):
        Camera(device_index=0).start()


def test_window_source_starts_and_stops():
    with patch("klaus.camera.MacOSReadingSource") as source_class:
        source_class.return_value.capture_frame.return_value = None
        camera = Camera(device_index=-2)
        camera.start()
        source_class.return_value.start.assert_called_once()
        assert camera.is_running is True
        camera.stop()
        assert camera.is_running is False


def test_remarkable_source_starts_and_refreshes_each_question():
    frame = np.ones((80, 60, 3), dtype=np.uint8)
    with (
        patch("klaus.camera.config.get_remarkable_password", return_value="secret"),
        patch(
            "klaus.camera.config.get_runtime_settings",
            return_value=SimpleNamespace(
                remarkable_address="https://tablet:2001",
                remarkable_username="klaus",
                remarkable_certificate_sha256="abc",
            ),
        ),
        patch("klaus.camera.RemarkableClient"),
        patch("klaus.camera.RemarkableReadingSource") as source_class,
    ):
        source_class.return_value.capture_frame.return_value = frame
        camera = Camera(device_index=-4)
        camera.start()
        initial_calls = source_class.return_value.capture_frame.call_count
        camera.capture_text_context()
        assert source_class.return_value.capture_frame.call_count == initial_calls + 1
        camera.stop()
