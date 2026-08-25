"""Small widgets shared by the setup wizard's steps."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from klaus.camera import Camera
from klaus.ui import theme

STEP_TITLES = [
    "Welcome",
    "API Key",
    "Reading Source",
    "Microphone",
    "Offline Speech",
    "About You",
    "Done",
]
NUM_STEPS = len(STEP_TITLES)


class StepIndicator(QWidget):
    """Row of dots showing which setup step is active."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dots: list[QLabel] = []
        for _ in range(NUM_STEPS):
            dot = QLabel("●")
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setFixedSize(18, 18)
            self._dots.append(dot)
            layout.addWidget(dot)
        self.set_step(0)

    def set_step(self, index: int) -> None:
        for i, dot in enumerate(self._dots):
            if i < index:
                dot.setStyleSheet(f"color: {theme.KLAUS_ACCENT}; font-size: 12px;")
            elif i == index:
                dot.setStyleSheet(f"color: {theme.USER_ACCENT}; font-size: 16px;")
            else:
                dot.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")


class DownloadCancelled(Exception):
    """Raised inside the progress callback to abort the download."""


class ModelDownloadThread(QThread):
    """Downloads the Moonshine STT model in a background thread.

    Emits ``progress`` with a 0..1 fraction as bytes arrive. ``cancel()``
    aborts the download at the next chunk; the thread then finishes with
    ``success=False`` and the error string ``"cancelled"``. Moonshine caches
    completed files, so a retry after cancel resumes at file granularity.
    """

    finished = pyqtSignal(bool, str)  # success, error_message
    progress = pyqtSignal(float, str)  # fraction 0..1, current file name

    def __init__(self, language: str):
        super().__init__()
        self._language = language
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        def on_progress(fraction: float, name: str) -> None:
            if self._cancelled:
                raise DownloadCancelled()
            self.progress.emit(float(fraction), str(name))

        try:
            from moonshine_voice import get_model_for_language
            get_model_for_language(self._language, on_progress=on_progress)
            # Moonshine swallows exceptions from its optional spelling-model
            # prefetch, so a cancel raised there still returns normally.
            if self._cancelled:
                self.finished.emit(False, "cancelled")
            else:
                self.finished.emit(True, "")
        except DownloadCancelled:
            self.finished.emit(False, "cancelled")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class CameraPreview(QWidget):
    """Small live preview of any reading source used during setup."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setFixedSize(320, 240)
        self._label.setStyleSheet(
            f"background: {theme.SURFACE}; border: 1px solid {theme.BORDER_MUTED}; "
            f"border-radius: 8px; color: {theme.TEXT_MUTED};"
        )
        self._label.setText("No preview")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignCenter)

        self._camera: Camera | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_frame)

    def start(self, device_index: int) -> None:
        self.stop()
        self._camera = Camera(device_index=device_index)
        try:
            self._camera.start()
            self._timer.start(66)
            self._label.setText("Waiting for reading source...")
        except RuntimeError as exc:
            self._label.setText(str(exc))
            self._camera = None

    def stop(self) -> None:
        self._timer.stop()
        if self._camera is not None:
            self._camera.stop()
            self._camera = None
        self._label.clear()
        self._label.setText("No preview")

    def _update_frame(self) -> None:
        if self._camera is None:
            return
        rgb = self._camera.get_frame_rgb()
        if rgb is None:
            return
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, w * ch, QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(img).scaled(
            320,
            240,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(pixmap)
