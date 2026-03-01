import base64
import json
import logging
import threading
import time
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

from klaus.config import CAMERA_DEVICE_INDEX, CAMERA_FRAME_WIDTH, CAMERA_FRAME_HEIGHT

logger = logging.getLogger(__name__)

# #region agent log
_DEBUG_LOG_PATH = "debug-18f7f4.log"
def _dbg(message: str, data: dict | None = None, hypothesis: str = "") -> None:
    import time as _t
    entry = {"sessionId": "18f7f4", "location": "camera.py", "message": message, "data": data or {}, "hypothesisId": hypothesis, "timestamp": int(_t.time() * 1000)}
    try:
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass
# #endregion


class Camera:
    """Continuously captures frames from a document camera in a background thread."""

    def __init__(self, device_index: int = CAMERA_DEVICE_INDEX):
        self._device_index = device_index
        self._cap: cv2.VideoCapture | None = None
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        logger.info("Opening camera (device %d)...", self._device_index)

        # #region agent log
        _dbg("opencv_build_info", {"version": cv2.__version__, "has_dshow": hasattr(cv2, 'CAP_DSHOW'), "has_msmf": hasattr(cv2, 'CAP_MSMF')}, "H5")
        backends_to_try = [
            ("CAP_DSHOW", cv2.CAP_DSHOW),
            ("CAP_MSMF", cv2.CAP_MSMF),
            ("CAP_ANY", cv2.CAP_ANY),
        ]
        for idx in range(3):
            for bname, bval in backends_to_try:
                try:
                    test_cap = cv2.VideoCapture(idx, bval)
                    opened = test_cap.isOpened()
                    backend_name = test_cap.getBackendName() if opened else "N/A"
                    test_cap.release()
                    _dbg("camera_probe", {"index": idx, "backend_requested": bname, "opened": opened, "actual_backend": backend_name}, "H1,H2")
                except Exception as e:
                    _dbg("camera_probe_error", {"index": idx, "backend_requested": bname, "error": str(e)}, "H1,H2")
        # #endregion

        self._cap = cv2.VideoCapture(self._device_index, cv2.CAP_DSHOW)
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_FRAME_WIDTH)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_FRAME_HEIGHT)
        if not self._cap.isOpened():
            # #region agent log
            _dbg("camera_open_failed", {"index": self._device_index, "backend": "CAP_DSHOW"}, "H1")
            # #endregion
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
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self) -> None:
        while self._running:
            if self._cap is None:
                break
            ret, frame = self._cap.read()
            if ret:
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
