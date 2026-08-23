"""Reveal note links in Finder."""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import QProcess

logger = logging.getLogger(__name__)


def reveal_file_in_browser(path: str) -> bool:
    """Reveal an existing file in Finder."""
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        logger.warning("Cannot reveal missing note file: %s", target)
        return False

    started = QProcess.startDetached("open", ["-R", str(target)])
    if not started:
        logger.warning("Native file browser did not open for note: %s", target)
    return bool(started)
