import base64
import logging
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
    NO_READING_SOURCE_INDEX,
    is_window_reading_source,
    reading_source_mode,
)
from klaus.reading_source import ReadingSource, REMARKABLE_PAPER_PURE_SOURCE_INDEX
from klaus.remarkable_reading_source import RemarkableClient, RemarkableReadingSource

logger = logging.getLogger(__name__)

class Camera:
    """Continuously captures frames from a macOS reading window."""

    def __init__(
        self,
        device_index: int | None = None,
    ):
        settings = config.get_runtime_settings()
        self._device_index = (
            settings.camera_device_index if device_index is None else int(device_index)
        )
        self._reading_source: ReadingSource | None = None
        self._frame: np.ndarray | None = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._running:
            return
        if self._device_index == NO_READING_SOURCE_INDEX:
            return
        if self._device_index == REMARKABLE_PAPER_PURE_SOURCE_INDEX:
            self._start_remarkable_source()
            return
        if not is_window_reading_source(self._device_index):
            raise RuntimeError("Choose Desk View or Active window as the reading source")
        self._start_window_source()

    def _start_window_source(self) -> None:
        mode = reading_source_mode(self._device_index)
        source = MacOSReadingSource(mode)
        source.start()
        self._reading_source = source
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("macOS reading source started (%s)", mode)

    def _start_remarkable_source(self) -> None:
        settings = config.get_runtime_settings()
        try:
            password = config.get_remarkable_password()
        except config.secrets_store.SecretsStoreError as exc:
            raise RuntimeError(str(exc)) from exc
        if not settings.remarkable_certificate_sha256 or not password:
            raise RuntimeError("Pair the reMarkable Paper Pure in Settings")
        client = RemarkableClient(
            settings.remarkable_address,
            settings.remarkable_username,
            password,
            settings.remarkable_certificate_sha256,
        )
        source = RemarkableReadingSource(client)
        frame = source.capture_frame()
        if frame is None:
            raise RuntimeError(source.waiting_message)
        self._reading_source = source
        with self._lock:
            self._frame = frame
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("reMarkable Paper Pure reading source started")

    def _capture_loop(self) -> None:
        interval = 1.0 if self._device_index == REMARKABLE_PAPER_PURE_SOURCE_INDEX else 0.2
        while self._running and self._reading_source is not None:
            frame = self._reading_source.capture_frame()
            with self._lock:
                if frame is not None:
                    self._frame = frame
            time.sleep(interval)

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
        """Return selected text for the active-window source when available."""
        if self._reading_source is None:
            return None
        frame = self._reading_source.capture_frame()
        if frame is not None:
            with self._lock:
                self._frame = frame
        return self._reading_source.capture_selected_text()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._reading_source = None
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
    def should_persist_images(self) -> bool:
        """Return whether session history may retain captured images."""
        return self._device_index != REMARKABLE_PAPER_PURE_SOURCE_INDEX

    @property
    def waiting_message(self) -> str:
        if self._device_index == DESK_VIEW_SOURCE_INDEX:
            return "Desk View is not running\nChoose Desk View again to reopen setup"
        if self._device_index == ACTIVE_READING_WINDOW_SOURCE_INDEX:
            return "Keep the window you want to read frontmost"
        if self._device_index == REMARKABLE_PAPER_PURE_SOURCE_INDEX:
            if self._reading_source is not None:
                return self._reading_source.waiting_message
            return "Pair the reMarkable Paper Pure in Settings"
        if self._device_index < 0:
            return "No reading source selected"
        return "Choose Desk View or Active window"
