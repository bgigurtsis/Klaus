"""Launch Desk View and guide the user through its setup."""

from __future__ import annotations

import logging
import subprocess
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox, QWidget

logger = logging.getLogger(__name__)

_desk_view_application = None
_desk_view_completion = None


def _manual_desk_view_setup(parent: QWidget | None) -> None:
    """Open Photo Booth and explain how to start Desk View from macOS."""
    photo_booth_opened = _open_photo_booth()
    opening_text = (
        "Photo Booth is opening to turn on your camera."
        if photo_booth_opened
        else "Open Photo Booth to turn on your camera."
    )
    QMessageBox.information(
        parent,
        "Turn on Desk View",
        f"{opening_text}\n\n"
        "1. Click the Video icon in the macOS menu bar.\n"
        "2. Choose Desk View.\n"
        "3. Frame your paper and click Start Desk View.\n"
        "4. Return to Klaus. The preview will appear automatically.",
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
        QMessageBox.information(
            parent,
            "Set up Desk View",
            "Desk View is opening.\n\n"
            "1. Frame the paper on your desk.\n"
            "2. Click Start Desk View.\n"
            "3. Return to Klaus. The preview will appear automatically.",
        )
        return

    _manual_desk_view_setup(parent)
