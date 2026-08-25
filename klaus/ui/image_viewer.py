"""Clickable image previews and a larger screenshot viewer."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QPixmap, QResizeEvent
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget


class ClickableImageLabel(QLabel):
    """A label that emits its current full-size image when clicked."""

    image_clicked = pyqtSignal(QPixmap)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._zoom_pixmap = QPixmap()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click to enlarge")

    def set_zoom_pixmap(self, pixmap: QPixmap) -> None:
        """Keep the full-size image that the viewer should display."""
        self._zoom_pixmap = QPixmap(pixmap)

    def clear_zoom_pixmap(self) -> None:
        """Disable zoom until the label receives another image."""
        self._zoom_pixmap = QPixmap()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and not self._zoom_pixmap.isNull()
        ):
            self.image_clicked.emit(QPixmap(self._zoom_pixmap))
            event.accept()
            return
        super().mousePressEvent(event)


class ImageViewerDialog(QDialog):
    """Show one screenshot at the largest size that fits the display."""

    def __init__(
        self,
        pixmap: QPixmap,
        title: str = "Screenshot",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._pixmap = QPixmap(pixmap)
        self.setWindowTitle(title)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumSize(320, 220)
        layout.addWidget(self._image_label, 1)

        close_button = QPushButton("Close")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)

        screen = self.screen()
        available = screen.availableGeometry() if screen is not None else None
        if available is not None:
            width = min(1200, max(520, int(available.width() * 0.85)))
            height = min(900, max(420, int(available.height() * 0.85)))
            self.resize(width, height)
        else:
            self.resize(900, 650)
        self._update_scaled_pixmap()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        if self._pixmap.isNull():
            return
        target = self._image_label.contentsRect().size()
        if target.width() <= 0 or target.height() <= 0:
            return
        # Scale to physical pixels and tag the ratio, otherwise Retina
        # displays render the image at logical resolution and it looks soft.
        ratio = self.devicePixelRatioF()
        scaled = self._pixmap.scaled(
            int(target.width() * ratio),
            int(target.height() * ratio),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(ratio)
        self._image_label.setPixmap(scaled)


def show_image_viewer(
    pixmap: QPixmap,
    parent: QWidget | None = None,
    title: str = "Screenshot",
) -> None:
    """Open a modal viewer for a screenshot."""
    if pixmap.isNull():
        return
    ImageViewerDialog(pixmap, title=title, parent=parent).exec()
