"""Launch Desk View and guide the user through its setup."""

from __future__ import annotations

import logging
import subprocess
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from klaus.ui import theme

logger = logging.getLogger(__name__)

_desk_view_application = None
_desk_view_completion = None


def _show_desk_view_instructions(
    parent: QWidget | None,
    title: str,
    intro: str,
    steps: list[str],
) -> None:
    """Show Desk View instructions in a compact Klaus dialog."""
    dialog = QDialog(parent)
    dialog.setObjectName("desk-view-dialog")
    dialog.setWindowTitle("Desk View")
    dialog.setModal(True)
    dialog.setMinimumWidth(520)
    dialog.setMaximumWidth(600)
    dialog.setStyleSheet(theme.application_stylesheet())

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(32, 30, 32, 26)
    layout.setSpacing(0)

    heading = QLabel(title)
    heading.setObjectName("desk-view-title")
    layout.addWidget(heading)

    intro_label = QLabel(intro)
    intro_label.setObjectName("desk-view-intro")
    intro_label.setWordWrap(True)
    layout.addSpacing(8)
    layout.addWidget(intro_label)
    layout.addSpacing(26)

    for index, step in enumerate(steps, start=1):
        row = QHBoxLayout()
        row.setSpacing(12)

        number = QLabel(str(index))
        number.setObjectName("desk-view-step-number")
        number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        number.setFixedSize(24, 24)
        row.addWidget(number, alignment=Qt.AlignmentFlag.AlignTop)

        instruction = QLabel(step)
        instruction.setObjectName("desk-view-step-text")
        instruction.setWordWrap(True)
        row.addWidget(instruction, stretch=1)

        layout.addLayout(row)
        if index < len(steps):
            layout.addSpacing(16)

    button_row = QHBoxLayout()
    button_row.addStretch()
    confirm = QPushButton("Got it")
    confirm.setObjectName("desk-view-confirm-button")
    confirm.setDefault(True)
    confirm.clicked.connect(dialog.accept)
    button_row.addWidget(confirm)
    layout.addSpacing(30)
    layout.addLayout(button_row)

    dialog.exec()


def _manual_desk_view_setup(parent: QWidget | None) -> None:
    """Open Photo Booth and explain how to start Desk View from macOS."""
    photo_booth_opened = _open_photo_booth()
    opening_text = (
        "Photo Booth is opening to turn on your camera."
        if photo_booth_opened
        else "Open Photo Booth to turn on your camera."
    )
    _show_desk_view_instructions(
        parent,
        "Turn on Desk View",
        opening_text,
        [
            "Click the Video icon in the macOS menu bar.",
            "Choose Desk View.",
            "Frame your paper and click Start Desk View.",
            "Return to Klaus. The preview will appear automatically.",
        ],
    )


def _launch_native_desk_view(parent: QWidget | None = None) -> bool:
    """Launch Apple's Desk View app through AVFoundation when available."""
    if sys.platform != "darwin":
        return False

    try:
        import AVFoundation

        desk_view_class = getattr(
            AVFoundation,
            "AVCaptureDeskViewApplication",
            None,
        )
        if desk_view_class is None:
            return False

        global _desk_view_application, _desk_view_completion
        _desk_view_application = desk_view_class.alloc().init()

        def _log_completion(error) -> None:
            if error is not None:
                logger.warning("Desk View could not open: %s", error)
                QTimer.singleShot(0, lambda: _manual_desk_view_setup(parent))

        _desk_view_completion = _log_completion
        _desk_view_application.presentWithCompletionHandler_(_desk_view_completion)
        return True
    except Exception as exc:
        logger.warning("Could not launch Desk View through AVFoundation: %s", exc)
        return False


def _open_photo_booth() -> bool:
    """Open Photo Booth so macOS activates its Video menu."""
    if sys.platform != "darwin":
        return False
    try:
        subprocess.Popen(
            ["/usr/bin/open", "-a", "Photo Booth"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except OSError as exc:
        logger.warning("Could not open Photo Booth: %s", exc)
        return False


def launch_desk_view_setup(parent: QWidget | None = None) -> None:
    """Open Desk View, or open Photo Booth and explain the manual path."""
    if _launch_native_desk_view(parent):
        _show_desk_view_instructions(
            parent,
            "Desk View is opening",
            "Finish setup in the Desk View window, then return to Klaus.",
            [
                "Frame the paper on your desk.",
                "Click Start Desk View.",
                "Return to Klaus. The preview will appear automatically.",
            ],
        )
        return

    _manual_desk_view_setup(parent)
