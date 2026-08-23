"""Helpers for macOS reading sources and microphone labels."""

from __future__ import annotations

import collections
import logging
from dataclasses import dataclass

import sounddevice as sd

logger = logging.getLogger(__name__)

_GENERIC_MIC_NAMES = {
    "microphone",
    "input",
    "line in",
    "default",
    "default input",
    "unknown",
}


@dataclass(frozen=True)
class CameraDevice:
    index: int
    display_name: str
    width: int
    height: int
    backend: str
    source: str


@dataclass(frozen=True)
class MicDevice:
    index: int
    display_name: str
    hostapi_name: str
    max_input_channels: int
    is_default: bool


def list_camera_devices() -> list[CameraDevice]:
    """Return the macOS reading sources supported by Klaus."""
    from klaus.macos_reading_source import (
        ACTIVE_READING_WINDOW_SOURCE_INDEX,
        DESK_VIEW_SOURCE_INDEX,
    )

    return [
        CameraDevice(
            index=DESK_VIEW_SOURCE_INDEX,
            display_name="Desk View (physical papers)",
            width=0,
            height=0,
            backend="CoreGraphics",
            source="desk_view",
        ),
        CameraDevice(
            index=ACTIVE_READING_WINDOW_SOURCE_INDEX,
            display_name="Active macOS window (any app)",
            width=0,
            height=0,
            backend="CoreGraphics + Accessibility",
            source="active_reading_window",
        ),
    ]


def format_camera_label(device: CameraDevice) -> str:
    """Return the reading source label shown in the app."""
    return device.display_name


def _default_input_index() -> int | None:
    default_device = sd.default.device
    default_input = default_device[0] if isinstance(default_device, tuple) else default_device
    if default_input is None:
        return None
    try:
        default_input = int(default_input)
    except (TypeError, ValueError):
        return None
    return default_input if default_input >= 0 else None


def _hostapi_name(hostapis: list[dict], index: int) -> str:
    if index < 0 or index >= len(hostapis):
        return "Unknown host API"
    return str(hostapis[index].get("name", "")).strip() or "Unknown host API"


def list_input_devices() -> list[MicDevice]:
    """Return input-capable microphones with disambiguated display names."""
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception as exc:
        logger.warning("Failed to enumerate audio devices: %s", exc)
        return []

    default_input = _default_input_index()
    candidates: list[tuple[int, dict]] = []
    name_counts: collections.Counter[str] = collections.Counter()
    for index, device in enumerate(devices):
        if int(device.get("max_input_channels", 0)) <= 0:
            continue
        candidates.append((index, device))
        name = str(device.get("name", "")).strip() or f"Input {index}"
        name_counts[name.lower()] += 1

    results: list[MicDevice] = []
    for index, device in candidates:
        name = str(device.get("name", "")).strip() or f"Input {index}"
        host_name = _hostapi_name(hostapis, int(device.get("hostapi", -1)))
        lowered = name.lower()
        if name_counts[lowered] > 1:
            display_name = f"{name} ({host_name}, id {index})"
        elif lowered in _GENERIC_MIC_NAMES or lowered.startswith("microphone"):
            display_name = f"{name} ({host_name})"
        else:
            display_name = name
        results.append(
            MicDevice(
                index=index,
                display_name=display_name,
                hostapi_name=host_name,
                max_input_channels=int(device.get("max_input_channels", 0)),
                is_default=default_input == index,
            )
        )
    return results


def format_mic_label(device: MicDevice) -> str:
    return f"{device.display_name} [default]" if device.is_default else device.display_name
