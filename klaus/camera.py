import base64
import logging
import os
import threading
import time
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

import klaus.config as config
from klaus.macos_reading_source import (
    ACTIVE_READING_WINDOW_SOURCE_INDEX,
    DESK_VIEW_SOURCE_INDEX,
    MacOSReadingSource,
    is_window_reading_source,
    reading_source_mode,
)

logger = logging.getLogger(__name__)

os.environ["OPENCV_LOG_LEVEL"] = "SILENT"

_BACKEND = cv2.CAP_ANY


def enumerate_cameras(max_index: int = 10) -> list[dict]:
    """Return available cameras as dicts for backward compatibility."""
    from klaus.device_catalog import list_camera_devices

    return [
        {
            "index": cam.index,
            "name": cam.display_name,
            "width": cam.width,
            "height": cam.height,
        }
        for cam in list_camera_devices(max_index=max_index)
    ]


_ROTATION_MAP: dict[str, int | None] = {
    "none": None,
    "90": cv2.ROTATE_90_CLOCKWISE,
    "180": cv2.ROTATE_180,
    "270": cv2.ROTATE_90_COUNTERCLOCKWISE,
}


def _resolve_rotation(setting: str, frame_w: int, frame_h: int) -> int | None:
    """Determine the cv2 rotation constant (or None) from config and frame size."""
    setting = setting.strip().lower()
    if setting != "auto":
        return _ROTATION_MAP.get(setting)
    if frame_h > frame_w:
        logger.info(
            "Auto-rotate: portrait frame detected (%dx%d), rotating 90 CW",
            frame_w, frame_h,
        )
        return cv2.ROTATE_90_CLOCKWISE
    return None


class Camera:
    """Continuously captures frames from a camera or macOS reading window."""

    def __init__(
        self,
        device_index: int | None = None,
        frame_width: int | None = None,
        frame_height: int | None = None,
        rotation: str | None = None,
    ):
        settings = config.get_runtime_settings()
        self._device_index = (
            settings.camera_device_index if device_index is None else int(device_index)
        )
        self._frame_width = (
            settings.camera_frame_width if frame_width is None else int(frame_width)
        )
        self._frame_height = (
            settings.camera_frame_height if frame_height is None else int(frame_height)
        )
        self._rotation_setting = (
            settings.camera_rotation if rotation is None else str(rotation)
        )
        self._cap: cv2.VideoCapture | None = None
        self._window_source: MacOSReadingSource | None = None
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._rotation: int | None = None

    def start(self) -> None:
        if self._running:
            return
        if is_window_reading_source(self._device_index):
            self._start_window_source()
            return
        if self._device_index < 0:
            raise RuntimeError("No reading source selected")
        logger.info("Opening camera (device %d)...", self._device_index)

        self._cap = cv2.VideoCapture(self._device_index, _BACKEND)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._frame_width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._frame_height)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"Cannot open camera at index {self._device_index}. "
                "Check that the document camera is connected."
            )
        actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        logger.info(
            "Camera opened (device %d) at %dx%d (requested %dx%d)",
            self._device_index, actual_w, actual_h,
            self._frame_width, self._frame_height,
        )

        self._rotation = _resolve_rotation(self._rotation_setting, actual_w, actual_h)
        if self._rotation is not None:
            logger.info("Camera rotation: %s", self._rotation_setting)

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _start_window_source(self) -> None:
        mode = reading_source_mode(self._device_index)
        source = MacOSReadingSource(mode)
        source.start()
        self._window_source = source
        self._running = True
        self._thread = threading.Thread(target=self._window_capture_loop, daemon=True)
        self._thread.start()
        logger.info("macOS reading source started (%s)", mode)

    def _window_capture_loop(self) -> None:
        while self._running and self._window_source is not None:
            frame = self._window_source.capture_frame()
            with self._lock:
                self._frame = frame
            time.sleep(0.2)

    def _capture_loop(self) -> None:
        while self._running:
            if self._cap is None:
                break
            ret, frame = self._cap.read()
            if ret:
                if self._rotation is not None:
                    frame = cv2.rotate(frame, self._rotation)
                with self._lock:
                    self._frame = frame
            else:
                time.sleep(0.01)

    def get_frame(self) -> np.ndarray | None:
        """Return the most recent frame as a BGR numpy array, or None."""
        with self._lock:
            if self._frame is None:
                return None
            return self._frame.copy()

    def get_frame_rgb(self) -> np.ndarray | None:
        """Return the most recent frame converted to RGB."""
        frame = self.get_frame()
        if frame is None:
            return None
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def capture_base64_jpeg(self, quality: int = 90) -> str | None:
        """Grab the current frame and return it as a base64-encoded JPEG string."""
        frame = self.get_frame()
        if frame is None:
            return None
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return base64.b64encode(buf.tobytes()).decode("utf-8")

    def capture_thumbnail_bytes(self, max_width: int = 320) -> bytes | None:
        """Return a small JPEG thumbnail as raw bytes (for the chat feed)."""
        frame = self.get_frame_rgb()
        if frame is None:
            return None
        img = Image.fromarray(frame)
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue()

    def capture_text_context(self) -> str | None:
        """Return selected text for the active-window PDF source when available."""
        if self._window_source is None:
            return None
        frame = self._window_source.capture_frame()
        if frame is not None:
            with self._lock:
                self._frame = frame
        return self._window_source.capture_selected_text()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._window_source = None
        with self._lock:
            self._frame = None
        logger.info("Reading source stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def device_index(self) -> int:
        return self._device_index

    @property
    def waiting_message(self) -> str:
        if self._device_index == DESK_VIEW_SOURCE_INDEX:
            return "Desk View is not running\nChoose Desk View again to reopen setup"
        if self._device_index == ACTIVE_READING_WINDOW_SOURCE_INDEX:
            return "Keep your PDF window frontmost"
        if self._device_index < 0:
            return "No reading source selected"
        return "Waiting for camera..."
