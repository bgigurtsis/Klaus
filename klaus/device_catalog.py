"""Helpers for enumerating and labeling camera/microphone devices."""

from __future__ import annotations

import collections
import logging
import os
import sys
from dataclasses import dataclass

import cv2
import sounddevice as sd

logger = logging.getLogger(__name__)

_BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY

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


def _macos_avfoundation_camera_names() -> list[str]:
    """Return best-effort camera names from AVFoundation on macOS."""
    if sys.platform != "darwin":
        return []
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeVideo
    except Exception:
        return []

    names: list[str] = []
    try:
        devices = AVCaptureDevice.devicesWithMediaType_(AVMediaTypeVideo)
    except Exception:
        return []

    # region agent log
    _raw_names = []
    # endregion
    for device in devices or []:
        try:
            localized = device.localizedName()
        except Exception:
            continue
        name = str(localized).strip()
        # region agent log
        _uid = ""
        try: _uid = str(device.uniqueID())
        except Exception: pass
        _raw_names.append({"name": name, "uid": _uid})
        # endregion
        if not name or name in names:
            continue
        names.append(name)
    # region agent log
    import json as _json, time as _time
    with open("/Users/billygigurtsis/Programming/Klaus/.cursor/debug-b06de1.log", "a") as _f:
        _f.write(_json.dumps({"sessionId":"b06de1","hypothesisId":"A,B,C","location":"device_catalog.py:_macos_avfoundation_camera_names","message":"AVFoundation raw devices","data":{"raw_names":_raw_names,"filtered_names":names,"count_raw":len(_raw_names),"count_filtered":len(names)},"timestamp":int(_time.time()*1000)}) + "\n")
    # endregion
    return names


def list_camera_devices(max_index: int = 10) -> list[CameraDevice]:
    """Probe camera indices and return display-friendly camera metadata."""
    cameras: list[dict] = []
    av_names = _macos_avfoundation_camera_names()
    probe_limit = max_index
    if av_names:
        probe_limit = min(max_index, max(len(av_names) + 2, 4))
    devnull = None
    old_stderr = None
    found_any = False
    failure_streak = 0
    try:
        if sys.platform in {"win32", "darwin"}:
            devnull = open(os.devnull, "w")
            old_stderr = os.dup(2)
            os.dup2(devnull.fileno(), 2)

        for i in range(probe_limit):
            cap = cv2.VideoCapture(i, _BACKEND)
            if not cap.isOpened():
                cap.release()
                failure_streak += 1
                if not av_names and found_any and failure_streak >= 3:
                    break
                continue

            found_any = True
            failure_streak = 0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            backend_name = cap.getBackendName() if hasattr(cap, "getBackendName") else ""
            fallback = f"Camera {i}"
            if backend_name:
                fallback = f"{fallback} ({backend_name})"
            cap.release()

            display_name = fallback
            source = "opencv"
            if i < len(av_names):
                display_name = av_names[i]
                source = "avfoundation"

            cameras.append(
                {
                    "index": i,
                    "display_name": display_name,
                    "width": width,
                    "height": height,
                    "backend": backend_name,
                    "source": source,
                }
            )
    finally:
        if old_stderr is not None:
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
        if devnull is not None:
            devnull.close()

    return [
        CameraDevice(
            index=cam["index"],
            display_name=cam["display_name"],
            width=cam["width"],
            height=cam["height"],
            backend=cam["backend"],
            source=cam["source"],
        )
        for cam in cameras
    ]


def format_camera_label(device: CameraDevice) -> str:
    primary = f"Camera {device.index}"
    display_name = (device.display_name or "").strip()
    label = primary

    if display_name:
        if display_name.lower().startswith(primary.lower()):
            suffix = display_name[len(primary):].strip()
            if suffix:
                label = f"{primary} {suffix}"
        elif display_name != primary:
            label = f"{primary} · {display_name}"

    if device.width > 0 and device.height > 0:
        return f"{label} ({device.width}x{device.height})"
    return label


def _default_input_index() -> int | None:
    default_device = sd.default.device
    if isinstance(default_device, tuple):
        default_input = default_device[0]
    else:
        default_input = default_device

    if default_input is None:
        return None
    try:
        default_input = int(default_input)
    except (TypeError, ValueError):
        return None
    if default_input < 0:
        return None
    return default_input


def _hostapi_name(hostapis: list[dict], index: int) -> str:
    if index < 0 or index >= len(hostapis):
        return "Unknown host API"
    name = str(hostapis[index].get("name", "")).strip()
    return name or "Unknown host API"


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

    for i, dev in enumerate(devices):
        max_inputs = int(dev.get("max_input_channels", 0))
        if max_inputs <= 0:
            continue
        candidates.append((i, dev))
        base_name = str(dev.get("name", "")).strip() or f"Input {i}"
        name_counts[base_name.lower()] += 1

    results: list[MicDevice] = []
    for i, dev in candidates:
        max_inputs = int(dev.get("max_input_channels", 0))
        base_name = str(dev.get("name", "")).strip() or f"Input {i}"
        hostapi_idx = int(dev.get("hostapi", -1))
        host_name = _hostapi_name(hostapis, hostapi_idx)

        lowered = base_name.lower()
        is_duplicate = name_counts[lowered] > 1
        is_generic = lowered in _GENERIC_MIC_NAMES or lowered.startswith("microphone")

        display_name = base_name
        if is_duplicate:
            display_name = f"{base_name} ({host_name}, id {i})"
        elif is_generic:
            display_name = f"{base_name} ({host_name})"

        results.append(
            MicDevice(
                index=i,
                display_name=display_name,
                hostapi_name=host_name,
                max_input_channels=max_inputs,
                is_default=(default_input == i),
            )
        )
    return results


def format_mic_label(device: MicDevice) -> str:
    if device.is_default:
        return f"{device.display_name} [default]"
    return device.display_name
