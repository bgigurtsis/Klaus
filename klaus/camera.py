import base64
import logging
import os
import sys
import threading
import time
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

from klaus.config import (
    CAMERA_DEVICE_INDEX,
    CAMERA_FRAME_WIDTH,
    CAMERA_FRAME_HEIGHT,
    CAMERA_ROTATION,
)

logger = logging.getLogger(__name__)

os.environ["OPENCV_LOG_LEVEL"] = "SILENT"

_BACKEND = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY


def enumerate_cameras(max_index: int = 10) -> list[dict]:
    """Probe camera indices and return info for each available camera.

    Returns a list of dicts with keys ``index``, ``name``, ``width``, ``height``.
    Temporarily suppresses stderr to silence DSHOW backend warnings on Windows
    for indices that have no camera attached.
    """
    cameras: list[dict] = []
    devnull = None
    old_stderr = None
    try:
        if sys.platform == "win32":
            devnull = open(os.devnull, "w")
            old_stderr = os.dup(2)
            os.dup2(devnull.fileno(), 2)

        for i in range(max_index):
            cap = cv2.VideoCapture(i, _BACKEND)
            if not cap.isOpened():
                cap.release()
                continue
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            name = f"Camera {i}"
            backend_name = cap.getBackendName() if hasattr(cap, "getBackendName") else ""
            if backend_name:
                name = f"Camera {i} ({backend_name})"
            cap.release()
            cameras.append({"index": i, "name": name, "width": w, "height": h})
    finally:
        if old_stderr is not None:
            os.dup2(old_stderr, 2)
            os.close(old_stderr)
        if devnull is not None:
            devnull.close()
    return cameras


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
    """Continuously captures frames from a document camera in a background thread."""

    def __init__(self, device_index: int = CAMERA_DEVICE_INDEX):
        self._device_index = device_index
        self._cap: cv2.VideoCapture | None = None
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._rotation: int | None = None

    def start(self) -> None:
        if self._running:
            return
        logger.info("Opening camera (device %d)...", self._device_index)

        self._cap = cv2.VideoCapture(self._device_index, _BACKEND)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_FRAME_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_FRAME_HEIGHT)
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
            CAMERA_FRAME_WIDTH, CAMERA_FRAME_HEIGHT,
        )

        self._rotation = _resolve_rotation(CAMERA_ROTATION, actual_w, actual_h)
        if self._rotation is not None:
            logger.info("Camera rotation: %s", CAMERA_ROTATION)

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

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

    def capture_base64_jpeg(self, quality: int = 85) -> str | None:
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

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info("Camera stopped")

    @property
    def is_running(self) -> bool:
        return self._running
