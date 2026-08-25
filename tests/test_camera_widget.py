"""Tests for the live reading-source preview widget."""

from types import SimpleNamespace

import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication

from klaus.ui.camera_widget import CameraWidget


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_active_window_preview_fits_inside_visible_content(qt_app) -> None:
    frame = np.ones((900, 1600, 3), dtype=np.uint8)
    camera = SimpleNamespace(
        get_frame_rgb=lambda: frame,
        waiting_message="Waiting for active window",
    )
    widget = CameraWidget()
    widget.resize(widget.PREVIEW_WIDTH, 260)
    widget._camera = camera
    widget._video_label.show()
    widget.show()
    qt_app.processEvents()

    widget._update_frame()

    pixmap = widget._video_label.pixmap()
    content = widget._video_label.contentsRect()
    assert pixmap.width() <= content.width()
    assert pixmap.height() <= content.height()
    assert pixmap.width() / pixmap.height() == pytest.approx(1600 / 900, rel=0.02)


def test_tall_active_window_preview_fits_inside_visible_content(qt_app) -> None:
    frame = np.ones((1600, 900, 3), dtype=np.uint8)
    camera = SimpleNamespace(
        get_frame_rgb=lambda: frame,
        waiting_message="Waiting for active window",
    )
    widget = CameraWidget()
    widget.resize(widget.PREVIEW_WIDTH, 260)
    widget._camera = camera
    widget._video_label.show()
    widget.show()
    qt_app.processEvents()

    widget._update_frame()

    pixmap = widget._video_label.pixmap()
    content = widget._video_label.contentsRect()
    assert pixmap.width() <= content.width()
    assert pixmap.height() <= content.height()
