"""Tests for current reading sources and microphone labels."""

from unittest.mock import patch

from klaus.device_catalog import format_camera_label, list_camera_devices, list_input_devices


def test_lists_only_current_macos_reading_sources():
    sources = list_camera_devices()
    assert [source.index for source in sources] == [-2, -3]
    assert [format_camera_label(source) for source in sources] == [
        "Desk View (physical papers)",
        "Active macOS window (any app)",
    ]


@patch("klaus.device_catalog._default_input_index", return_value=3)
@patch("klaus.device_catalog.sd.query_hostapis")
@patch("klaus.device_catalog.sd.query_devices")
def test_disambiguates_duplicate_and_generic_microphones(
    query_devices,
    query_hostapis,
    _default_input,
):
    query_hostapis.return_value = [{"name": "CoreAudio"}, {"name": "BlackHole"}]
    query_devices.return_value = [
        {"name": "Audio Outputs", "max_input_channels": 0, "hostapi": 0},
        {"name": "Microphone", "max_input_channels": 1, "hostapi": 0},
        {"name": "Microphone", "max_input_channels": 1, "hostapi": 1},
        {"name": "Studio Mic", "max_input_channels": 2, "hostapi": 0},
    ]

    labels = [device.display_name for device in list_input_devices()]

    assert labels == [
        "Microphone (CoreAudio, id 1)",
        "Microphone (BlackHole, id 2)",
        "Studio Mic",
    ]
