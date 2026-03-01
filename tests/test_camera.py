"""Tests for klaus.camera -- document camera capture."""

import base64
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from klaus.camera import Camera


class TestCameraNoHardware:
    def test_get_frame_returns_none_before_start(self):
        cam = Camera(device_index=99)
        assert cam.get_frame() is None
        assert cam.get_frame_rgb() is None

    def test_is_running_false_by_default(self):
        cam = Camera()
        assert cam.is_running is False

    def test_capture_base64_returns_none_without_frame(self):
        cam = Camera()
        assert cam.capture_base64_jpeg() is None

    def test_capture_thumbnail_returns_none_without_frame(self):
        cam = Camera()
        assert cam.capture_thumbnail_bytes() is None


class TestCameraWithMockFrame:
    def _make_camera_with_frame(self):
        cam = Camera()
        cam._frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cam._frame[100, 100] = [255, 0, 0]  # one blue pixel in BGR
        return cam

    def test_get_frame_returns_copy(self):
        cam = self._make_camera_with_frame()
        frame = cam.get_frame()
        assert frame is not None
        assert frame.shape == (480, 640, 3)
        frame[0, 0] = [1, 2, 3]
        assert not np.array_equal(cam._frame[0, 0], [1, 2, 3])

    @patch("klaus.camera.cv2.cvtColor")
    def test_get_frame_rgb(self, mock_cvt):
        cam = self._make_camera_with_frame()
        mock_cvt.return_value = np.zeros((480, 640, 3), dtype=np.uint8)
        result = cam.get_frame_rgb()
        assert result is not None
        mock_cvt.assert_called_once()

    @patch("klaus.camera.cv2.imencode")
    def test_capture_base64_jpeg(self, mock_imencode):
        cam = self._make_camera_with_frame()
        fake_buf = np.frombuffer(b"fake-jpeg-data", dtype=np.uint8)
        mock_imencode.return_value = (True, fake_buf)

        result = cam.capture_base64_jpeg()
        assert result is not None
        decoded = base64.b64decode(result)
        assert decoded == b"fake-jpeg-data"

    @patch("klaus.camera.cv2.cvtColor")
    def test_capture_thumbnail_bytes(self, mock_cvt):
        cam = self._make_camera_with_frame()
        mock_cvt.return_value = np.zeros((480, 640, 3), dtype=np.uint8)

        thumb = cam.capture_thumbnail_bytes(max_width=160)
        assert thumb is not None
        assert len(thumb) > 0
        assert thumb[:2] == b'\xff\xd8'  # JPEG magic bytes


class TestCameraStartStop:
    @patch("klaus.camera.cv2.VideoCapture")
    def test_start_raises_when_camera_not_available(self, mock_vc_cls):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        mock_vc_cls.return_value = mock_cap

        cam = Camera(device_index=99)
        with pytest.raises(RuntimeError, match="Cannot open camera"):
            cam.start()

    @patch("klaus.camera.cv2.VideoCapture")
    def test_start_succeeds_with_camera(self, mock_vc_cls):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_vc_cls.return_value = mock_cap

        cam = Camera(device_index=0)
        cam.start()
        assert cam.is_running is True
        cam.stop()
        assert cam.is_running is False

    def test_stop_without_start(self):
        cam = Camera()
        cam.stop()
        assert cam.is_running is False

    @patch("klaus.camera.cv2.VideoCapture")
    def test_start_twice_is_idempotent(self, mock_vc_cls):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_vc_cls.return_value = mock_cap

        cam = Camera()
        cam.start()
        cam.start()
        assert mock_vc_cls.call_count == 1
        cam.stop()
