"""Capture macOS reading windows and selected text."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass

import numpy as np

from klaus.reading_source import (
    ACTIVE_READING_WINDOW_SOURCE_INDEX,
    DESK_VIEW_SOURCE_INDEX,
    NO_READING_SOURCE_INDEX,
)

logger = logging.getLogger(__name__)

DESK_VIEW_MODE = "desk_view"
ACTIVE_READING_WINDOW_MODE = "active_reading_window"

_WINDOW_ID = "kCGWindowNumber"
_OWNER_PID = "kCGWindowOwnerPID"
_OWNER_NAME = "kCGWindowOwnerName"
_WINDOW_NAME = "kCGWindowName"
_WINDOW_LAYER = "kCGWindowLayer"
_WINDOW_ALPHA = "kCGWindowAlpha"
_WINDOW_BOUNDS = "kCGWindowBounds"
_WINDOW_ONSCREEN = "kCGWindowIsOnscreen"

_IGNORED_OWNERS = {
    "control center",
    "dock",
    "notification center",
    "screencaptureui",
    "spotlight",
    "window server",
}
_IGNORED_TITLES = {
    "computer use controls",
}
_MAX_SELECTED_TEXT_CHARS = 20_000


@dataclass(frozen=True)
class WindowTarget:
    window_id: int
    owner_pid: int
    owner_name: str
    window_name: str


def is_window_reading_source(device_index: int) -> bool:
    return device_index in {
        DESK_VIEW_SOURCE_INDEX,
        ACTIVE_READING_WINDOW_SOURCE_INDEX,
    }


def reading_source_mode(device_index: int) -> str:
    if device_index == DESK_VIEW_SOURCE_INDEX:
        return DESK_VIEW_MODE
    if device_index == ACTIVE_READING_WINDOW_SOURCE_INDEX:
        return ACTIVE_READING_WINDOW_MODE
    raise ValueError(f"Unsupported reading source index: {device_index}")


def _window_area(info: dict) -> float:
    bounds = info.get(_WINDOW_BOUNDS) or {}
    try:
        return float(bounds.get("Width", 0)) * float(bounds.get("Height", 0))
    except (TypeError, ValueError):
        return 0.0


def _is_normal_window(info: dict, own_pid: int) -> bool:
    try:
        owner_pid = int(info.get(_OWNER_PID, -1))
        layer = int(info.get(_WINDOW_LAYER, 0))
        alpha = float(info.get(_WINDOW_ALPHA, 1.0))
    except (TypeError, ValueError):
        return False

    owner = str(info.get(_OWNER_NAME, "")).strip().lower()
    title = str(info.get(_WINDOW_NAME, "")).strip().lower()
    return (
        owner_pid != own_pid
        and owner_pid >= 0
        and layer == 0
        and alpha > 0
        and bool(info.get(_WINDOW_ONSCREEN, True))
        and owner not in _IGNORED_OWNERS
        and title not in _IGNORED_TITLES
        and _window_area(info) >= 60_000
    )


def _target_from_info(info: dict) -> WindowTarget | None:
    try:
        return WindowTarget(
            window_id=int(info[_WINDOW_ID]),
            owner_pid=int(info[_OWNER_PID]),
            owner_name=str(info.get(_OWNER_NAME, "")).strip(),
            window_name=str(info.get(_WINDOW_NAME, "")).strip(),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _candidate_targets(
    window_infos: list[dict],
    mode: str,
    *,
    own_pid: int,
) -> list[WindowTarget]:
    """Return eligible windows in front-to-back order for a reading mode."""
    targets: list[WindowTarget] = []
    for info in window_infos:
        if not _is_normal_window(info, own_pid):
            continue
        owner = str(info.get(_OWNER_NAME, ""))
        title = str(info.get(_WINDOW_NAME, ""))
        combined = f"{owner} {title}".lower()
        is_desk_view = "desk view" in combined
        if mode == DESK_VIEW_MODE and not is_desk_view:
            continue
        if mode == ACTIVE_READING_WINDOW_MODE and is_desk_view:
            continue
        target = _target_from_info(info)
        if target is not None:
            targets.append(target)
    return targets


def _select_window(
    window_infos: list[dict],
    mode: str,
    *,
    own_pid: int,
) -> WindowTarget | None:
    """Select the frontmost eligible window for a reading mode."""
    targets = _candidate_targets(window_infos, mode, own_pid=own_pid)
    return targets[0] if targets else None


def _copy_window_infos() -> list[dict]:
    try:
        import Quartz

        options = (
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements
        )
        return list(Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID))
    except Exception as exc:
        logger.debug("Could not list macOS windows: %s", exc)
        return []


def _capture_window_image(window_id: int) -> np.ndarray | None:
    """Return one window image as a BGR array."""
    try:
        import Quartz

        image = Quartz.CGWindowListCreateImage(
            Quartz.CGRectNull,
            Quartz.kCGWindowListOptionIncludingWindow,
            window_id,
            Quartz.kCGWindowImageBoundsIgnoreFraming
            | Quartz.kCGWindowImageBestResolution,
        )
        if image is None:
            return None

        width = int(Quartz.CGImageGetWidth(image))
        height = int(Quartz.CGImageGetHeight(image))
        bytes_per_row = int(Quartz.CGImageGetBytesPerRow(image))
        bits_per_pixel = int(Quartz.CGImageGetBitsPerPixel(image))
        if width <= 0 or height <= 0 or bits_per_pixel != 32:
            return None

        provider = Quartz.CGImageGetDataProvider(image)
        data = Quartz.CGDataProviderCopyData(provider)
        raw = np.frombuffer(bytes(data), dtype=np.uint8)
        required = height * bytes_per_row
        if raw.size < required:
            return None

        rows = raw[:required].reshape(height, bytes_per_row)
        bgra = rows[:, : width * 4].reshape(height, width, 4)
        return bgra[:, :, :3].copy()
    except Exception as exc:
        logger.debug("Could not capture macOS window %d: %s", window_id, exc)
        return None


def _selected_text_for_pid(owner_pid: int) -> str | None:
    """Read selected text through the macOS Accessibility API."""
    try:
        from ApplicationServices import (
            AXIsProcessTrusted,
            AXUIElementCopyAttributeValue,
            AXUIElementCreateApplication,
            kAXErrorSuccess,
            kAXFocusedUIElementAttribute,
            kAXSelectedTextAttribute,
        )

        if not AXIsProcessTrusted():
            return None
        application = AXUIElementCreateApplication(owner_pid)
        error, focused = AXUIElementCopyAttributeValue(
            application,
            kAXFocusedUIElementAttribute,
            None,
        )
        if error != kAXErrorSuccess or focused is None:
            return None
        error, selected = AXUIElementCopyAttributeValue(
            focused,
            kAXSelectedTextAttribute,
            None,
        )
        if error != kAXErrorSuccess or selected is None:
            return None
        text = str(selected).strip()
        if not text:
            return None
        return text[:_MAX_SELECTED_TEXT_CHARS]
    except Exception as exc:
        logger.debug("Could not read selected text from pid %d: %s", owner_pid, exc)
        return None


class MacOSReadingSource:
    """Capture Desk View or the frontmost reading window on macOS."""

    def __init__(self, mode: str):
        if mode not in {DESK_VIEW_MODE, ACTIVE_READING_WINDOW_MODE}:
            raise ValueError(f"Unsupported macOS reading mode: {mode}")
        self._mode = mode
        self._target: WindowTarget | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        try:
            import Quartz

            if Quartz.CGPreflightScreenCaptureAccess():
                return
            if Quartz.CGRequestScreenCaptureAccess():
                return
        except Exception as exc:
            raise RuntimeError(f"Could not check Screen Recording access: {exc}") from exc
        raise RuntimeError(
            "Allow Klaus under System Settings > Privacy & Security > "
            "Screen & System Audio Recording, then restart Klaus."
        )

    def capture_frame(self) -> np.ndarray | None:
        targets = _candidate_targets(
            _copy_window_infos(),
            self._mode,
            own_pid=os.getpid(),
        )
        for target in targets:
            frame = _capture_window_image(target.window_id)
            if frame is None or not np.any(frame):
                continue
            with self._lock:
                self._target = target
            return frame
        with self._lock:
            self._target = None
        return None

    def capture_selected_text(self) -> str | None:
        if self._mode != ACTIVE_READING_WINDOW_MODE:
            return None
        with self._lock:
            target = self._target
        if target is None:
            self.capture_frame()
            with self._lock:
                target = self._target
        if target is None:
            return None
        return _selected_text_for_pid(target.owner_pid)

    @property
    def target(self) -> WindowTarget | None:
        with self._lock:
            return self._target

    @property
    def waiting_message(self) -> str:
        if self._mode == DESK_VIEW_MODE:
            return "Desk View is not running"
        return "Keep the window you want to read frontmost"
