"""Tests for klaus.device_catalog device enumeration and labeling."""

from unittest.mock import MagicMock, patch

import klaus.device_catalog as device_catalog
from klaus.device_catalog import (
    format_camera_label,
    format_mic_label,
    list_camera_devices,
    list_input_devices,
)


def _mock_capture(opened: bool, width: int = 0, height: int = 0, backend: str = ""):
    cap = MagicMock()
    cap.isOpened.return_value = opened
    cap.get.side_effect = lambda prop: {
        device_catalog.cv2.CAP_PROP_FRAME_WIDTH: width,
        device_catalog.cv2.CAP_PROP_FRAME_HEIGHT: height,
    }.get(prop, 0)
    cap.getBackendName.return_value = backend
    return cap


class TestCameraCatalog:
    @patch("klaus.device_catalog._macos_reading_sources")
    @patch("klaus.device_catalog.cv2.VideoCapture")
    def test_can_list_reading_sources_without_probing_cameras(
        self, mock_vc, mock_sources
    ):
        source = device_catalog.CameraDevice(
            index=-2,
            display_name="Desk View (physical papers)",
            width=0,
            height=0,
            backend="CoreGraphics",
            source="desk_view",
        )
        mock_sources.return_value = [source]

        cameras = list_camera_devices(include_physical=False)

        assert cameras == [source]
        mock_vc.assert_not_called()

    @patch("klaus.device_catalog._macos_reading_sources", return_value=[])
    @patch("klaus.device_catalog._macos_avfoundation_camera_count", return_value=0)
    @patch("klaus.device_catalog._avfoundation_device_name_at", return_value=None)
    @patch("klaus.device_catalog.cv2.VideoCapture")
    def test_uses_fallback_names_without_avfoundation(
        self, mock_vc, _mock_name, _mock_count, _mock_sources
    ):
        mock_vc.side_effect = [
            _mock_capture(True, width=1280, height=720, backend="MSMF"),
            _mock_capture(False),
        ]

        cameras = list_camera_devices(max_index=2)

        assert len(cameras) == 1
        assert cameras[0].index == 0
        assert cameras[0].display_name == "Camera 0 (MSMF)"
        assert cameras[0].width == 1280
        assert cameras[0].height == 720
        assert cameras[0].source == "opencv"
        assert format_camera_label(cameras[0]) == "Camera 0 (MSMF) (1280x720)"

    @patch("klaus.device_catalog._macos_reading_sources", return_value=[])
    @patch("klaus.device_catalog._macos_avfoundation_camera_count", return_value=2)
    @patch(
        "klaus.device_catalog._avfoundation_device_name_at",
        side_effect=["FaceTime HD Camera", "iPhone Camera"],
    )
    @patch("klaus.device_catalog.cv2.VideoCapture")
    def test_prefers_avfoundation_names_when_available(
        self, mock_vc, _mock_name, _mock_count, _mock_sources
    ):
        mock_vc.side_effect = [
            _mock_capture(True, width=1920, height=1080, backend="AVFOUNDATION"),
            _mock_capture(True, width=1280, height=720, backend="AVFOUNDATION"),
        ]

        cameras = list_camera_devices(max_index=2)

        assert len(cameras) == 2
        assert cameras[0].display_name == "FaceTime HD Camera"
        assert cameras[1].display_name == "iPhone Camera"
        assert cameras[0].source == "avfoundation"
        assert cameras[1].source == "avfoundation"
        assert (
            format_camera_label(cameras[0])
            == "Camera 0 · FaceTime HD Camera (1920x1080)"
        )
        assert (
            format_camera_label(cameras[1])
            == "Camera 1 · iPhone Camera (1280x720)"
        )

    def test_formats_window_reading_source_without_camera_prefix(self):
        source = device_catalog.CameraDevice(
            index=-2,
            display_name="Desk View (physical papers)",
            width=0,
            height=0,
            backend="CoreGraphics",
            source="desk_view",
        )

        assert format_camera_label(source) == "Desk View (physical papers)"

        active_window = device_catalog.CameraDevice(
            index=-3,
            display_name="Active macOS window (any app)",
            width=0,
            height=0,
            backend="CoreGraphics + Accessibility",
            source="active_reading_window",
        )

        assert format_camera_label(active_window) == "Active macOS window (any app)"


class TestMicCatalog:
    @patch("klaus.device_catalog._default_input_index", return_value=3)
    @patch("klaus.device_catalog.sd.query_hostapis")
    @patch("klaus.device_catalog.sd.query_devices")
    def test_disambiguates_duplicate_and_generic_names(
        self,
        mock_query_devices,
        mock_hostapis,
        _mock_default_input,
    ):
        mock_hostapis.return_value = [
            {"name": "CoreAudio"},
            {"name": "BlackHole"},
        ]
        mock_query_devices.return_value = [
            {"name": "Audio Outputs", "max_input_channels": 0, "hostapi": 0},
            {"name": "Microphone", "max_input_channels": 1, "hostapi": 0},
            {"name": "Microphone", "max_input_channels": 1, "hostapi": 1},
            {"name": "Studio Mic", "max_input_channels": 2, "hostapi": 0},
        ]

        mics = list_input_devices()
        labels = [m.display_name for m in mics]

        assert len(mics) == 3
        assert "Microphone (CoreAudio, id 1)" in labels
        assert "Microphone (BlackHole, id 2)" in labels
        assert "Studio Mic" in labels

        default_mic = [m for m in mics if m.index == 3][0]
        assert default_mic.is_default is True
        assert format_mic_label(default_mic) == "Studio Mic [default]"

    @patch("klaus.device_catalog._default_input_index", return_value=None)
    @patch("klaus.device_catalog.sd.query_hostapis", return_value=[{"name": "CoreAudio"}])
    @patch("klaus.device_catalog.sd.query_devices")
    def test_returns_empty_when_no_input_devices(
        self,
        mock_query_devices,
        _mock_hostapis,
        _mock_default_input,
    ):
        mock_query_devices.return_value = [
            {"name": "Audio Outputs", "max_input_channels": 0, "hostapi": 0},
        ]
        assert list_input_devices() == []
