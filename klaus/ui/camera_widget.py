"""Live camera preview widget."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap
import cv2
import numpy as np

from klaus.ui import theme


class CameraWidget(QWidget):
    """Compact live camera preview."""

    PREVIEW_WIDTH = theme.CAMERA_PREVIEW_WIDTH

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._camera = None
        self._init_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_frame)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._video_label = QLabel()
        self._video_label.setObjectName("camera-preview")
        self._video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_label.setMinimumSize(280, 210)
        self._video_label.setMaximumHeight(300)
        layout.addWidget(self._video_label)
        self.setMaximumWidth(self.PREVIEW_WIDTH)

    def set_camera(self, camera) -> None:
        """Bind a Camera instance and start preview if running."""
        self._camera = camera
        if camera and camera.is_running:
            self._timer.start(33)
        else:
            self._timer.stop()

    def _update_frame(self) -> None:
        if self._camera is None:
            return
        frame = self._camera.get_frame_rgb()
        if frame is None:
            return

        h, w, ch = frame.shape
        if w > self.PREVIEW_WIDTH:
            scale = self.PREVIEW_WIDTH / w
            frame = cv2.resize(
                frame, (self.PREVIEW_WIDTH, int(h * scale)),
                interpolation=cv2.INTER_AREA,
            )
            h, w, ch = frame.shape

        frame = np.ascontiguousarray(frame)
        bytes_per_line = ch * w
        qt_image = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_image)
        self._video_label.setPixmap(pixmap)

    def stop(self) -> None:
        self._timer.stop()
