"""Live reading-source selector and preview widget."""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QListView, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
import cv2
import numpy as np

from klaus.macos_reading_source import (
    ACTIVE_READING_WINDOW_SOURCE_INDEX,
    DESK_VIEW_SOURCE_INDEX,
)
from klaus.reading_source import REMARKABLE_PAPER_PURE_SOURCE_INDEX
from klaus.ui import theme
from klaus.ui.desk_view_setup import launch_desk_view_setup


class CameraWidget(QWidget):
    """Compact reading-source selector and live preview."""

    source_changed = pyqtSignal(int)
    PREVIEW_WIDTH = theme.CAMERA_PREVIEW_WIDTH

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("reading-source-panel")
        self._camera = None
        self._init_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_frame)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        heading = QLabel("Reading context")
        heading.setObjectName("reading-context-title")
        header.addWidget(heading)
        header.addStretch()
        self._status_badge = QLabel()
        self._status_badge.setObjectName("reading-context-badge")
        header.addWidget(self._status_badge)
        layout.addLayout(header)
        self._set_status("off")

        self._source_combo = QComboBox()
        self._source_combo.setObjectName("reading-source-combo")
        self._source_combo.setFixedHeight(34)
        source_view = QListView()
        source_view.setObjectName("reading-source-menu")
        source_view.setMouseTracking(True)
        source_view.setUniformItemSizes(True)
        self._source_combo.setView(source_view)
        self._source_combo.addItem("Desk View  ·  paper", DESK_VIEW_SOURCE_INDEX)
        self._source_combo.addItem(
            "Active window  ·  any app",
            ACTIVE_READING_WINDOW_SOURCE_INDEX,
        )
        self._source_combo.addItem(
            "reMarkable Paper Pure  ·  tablet",
            REMARKABLE_PAPER_PURE_SOURCE_INDEX,
        )
        self._source_combo.activated.connect(self._on_source_activated)
        layout.addWidget(self._source_combo)

        self._video_label = QLabel()
        self._video_label.setObjectName("camera-preview")
        self._video_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video_label.setWordWrap(True)
        self._video_label.setContentsMargins(18, 12, 18, 12)
        self._video_label.setMinimumSize(270, 160)
        self._video_label.setMaximumHeight(204)
        self._video_label.setText("No reading context\nSelect a source to begin")
        self._video_label.setVisible(False)
        layout.addWidget(self._video_label)
        self.setMaximumWidth(self.PREVIEW_WIDTH)

    _STATUS_STYLES = {
        "off": ("Off", theme.IDLE_COLOR),
        "waiting": ("Waiting", theme.THINKING_COLOR),
        "live": ("Live", theme.SPEAKING_COLOR),
    }

    def _set_status(self, status: str) -> None:
        """Show the reading-context state as a small colored word."""
        label, color = self._STATUS_STYLES[status]
        self._status_badge.setText(label)
        self._status_badge.setStyleSheet(f"color: {color};")

    def set_camera(self, camera) -> None:
        """Bind a Camera instance and start preview if running."""
        self._camera = camera
        self.set_source_selection(camera.device_index if camera is not None else -1)
        if camera and camera.is_running:
            self._video_label.setText(camera.waiting_message)
            self._video_label.setVisible(True)
            self._set_status("waiting")
            self._timer.start(33)
            if camera.device_index == DESK_VIEW_SOURCE_INDEX:
                QTimer.singleShot(0, self._launch_desk_view_if_current)
        else:
            self._timer.stop()
            self._set_status("off")
            self._video_label.setVisible(False)

    def _launch_desk_view_if_current(self) -> None:
        if (
            self._camera is not None
            and self._camera.device_index == DESK_VIEW_SOURCE_INDEX
        ):
            launch_desk_view_setup(self)

    def _on_source_activated(self, _combo_index: int) -> None:
        if self._source_combo is None:
            return
        source_index = self._source_combo.currentData()
        if source_index is not None:
            if (
                int(source_index) == DESK_VIEW_SOURCE_INDEX
                and self._camera is not None
                and self._camera.device_index == DESK_VIEW_SOURCE_INDEX
            ):
                launch_desk_view_setup(self)
            self.source_changed.emit(int(source_index))

    def set_source_selection(self, device_index: int) -> None:
        if self._source_combo is None:
            return
        special_sources = {
            DESK_VIEW_SOURCE_INDEX,
            ACTIVE_READING_WINDOW_SOURCE_INDEX,
            REMARKABLE_PAPER_PURE_SOURCE_INDEX,
        }
        for item_index in range(self._source_combo.count() - 1, -1, -1):
            if self._source_combo.itemData(item_index) not in special_sources:
                self._source_combo.removeItem(item_index)
        combo_index = self._source_combo.findData(int(device_index))
        if combo_index < 0:
            label = (
                "No reading source"
                if device_index < 0
                else "Unsupported reading source"
            )
            self._source_combo.addItem(label, int(device_index))
            combo_index = self._source_combo.count() - 1
        self._source_combo.setCurrentIndex(combo_index)

    def _update_frame(self) -> None:
        if self._camera is None:
            return
        frame = self._camera.get_frame_rgb()
        if frame is None:
            self._set_status("waiting")
            self._video_label.setText(self._camera.waiting_message)
            return

        self._set_status("live")

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
