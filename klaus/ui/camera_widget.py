"""Live camera preview with overlay LIVE badge."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage, QPixmap, QPainter, QBrush, QColor, QFont, QPen
import cv2
import numpy as np

from klaus.ui import theme


class CameraWidget(QWidget):
    """Compact live camera preview with an overlay LIVE indicator."""

    PREVIEW_WIDTH = theme.CAMERA_PREVIEW_WIDTH

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._camera = None
        self._is_live = False
        self._init_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_frame)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._video_label = QLabel()
        self._video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_label.setMinimumSize(280, 210)
        self._video_label.setMaximumHeight(300)
        self._video_label.setStyleSheet(
            f"background-color: {theme.SURFACE};"
            f"border: 1px solid {theme.BORDER_MUTED};"
            "border-radius: 8px;"
        )
        layout.addWidget(self._video_label)
        self.setMaximumWidth(self.PREVIEW_WIDTH)

    def set_camera(self, camera) -> None:
        """Bind a Camera instance and start preview if running."""
        self._camera = camera
        if camera and camera.is_running:
            self._is_live = True
            self._timer.start(33)
        else:
            self._is_live = False
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

        if self._is_live:
            pixmap = self._draw_live_badge(pixmap)

        self._video_label.setPixmap(pixmap)

    @staticmethod
    def _draw_live_badge(pixmap: QPixmap) -> QPixmap:
        """Paint a 'LIVE' pill overlay on the top-left of the frame."""
        pm = pixmap.copy()
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        badge_w, badge_h = 58, 22
        x, y = 8, 8

        painter.setBrush(QBrush(QColor(0, 0, 0, 160)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(x, y, badge_w, badge_h, 6, 6)

        # Green dot
        painter.setBrush(QBrush(QColor(theme.LIVE_GREEN)))
        painter.drawEllipse(x + 8, y + 7, 8, 8)

        # "LIVE" text
        font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QPen(QColor(theme.LIVE_GREEN)))
        painter.drawText(x + 22, y + 16, "LIVE")

        painter.end()
        return pm

    def stop(self) -> None:
        self._timer.stop()
