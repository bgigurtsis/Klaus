"""Centralized theme tokens for the Klaus UI.

All colors, fonts, dimensions, and the single application-wide QSS live here so
that every widget imports from one place and palette tweaks are a single-file
change.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_FONTS_DIR = Path(__file__).parent / "fonts"
_ICONS_DIR = Path(__file__).parent / "icons"

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

# Base layers (darkest to lightest), hue-biased toward the violet accent
BG = "#141418"
SURFACE = "#1a1a20"
SURFACE_RAISED = "#22222b"
SURFACE_OVERLAY = "#2c2c38"
SIDEBAR = "#0f0f13"

# Borders
BORDER_MUTED = "#26262f"
BORDER_DEFAULT = "#35353f"
BORDER_EMPHASIS = "#4c4c5c"

# Text
TEXT_PRIMARY = "#ededf2"
TEXT_SECONDARY = "#b6b6c2"
TEXT_MUTED = "#80808f"

# Accents
USER_ACCENT = "#aa9cf1"
USER_BG = "#282444"
USER_BORDER = "#3d3763"
KLAUS_ACCENT = "#ededf2"
KLAUS_BG = "#22222b"

# Primary action (filled buttons, selected states, focus)
ACCENT = "#a495f0"
ACCENT_HOVER = "#b9adf6"
ACCENT_PRESSED = "#8d7de6"
ACCENT_TEXT = "#17131f"

LISTENING_COLOR = "#e25466"
THINKING_COLOR = "#b7791f"
SPEAKING_COLOR = "#16835f"
IDLE_COLOR = "#74746e"
ERROR_COLOR = "#ef4444"

# Stop button (semantic aliases for ERROR_COLOR shades)
STOP_BG = "#b91c1c"
STOP_BORDER = "#dc2626"
STOP_HOVER_BG = "#dc2626"

# Klaus card accent buttons
KLAUS_BTN_BORDER = "#3b3b48"
KLAUS_BTN_HOVER_BG = "#2c2c38"

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

FONT_FAMILY_NAME = "Helvetica Neue"
FONT_FAMILY = f'"{FONT_FAMILY_NAME}"'
FONT_SIZE_BODY = 15
FONT_SIZE_SMALL = 13
FONT_SIZE_CAPTION = 12
FONT_SIZE_HEADING = 20

# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

HEADER_HEIGHT = 58
STATUS_BAR_HEIGHT = 104
CARD_PADDING_H = 20
CARD_PADDING_V = 16
CARD_RADIUS = 16
RADIUS_SM = 8
RADIUS_MD = 12
CAMERA_PREVIEW_WIDTH = 286

# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Application-wide QSS (assembled in theme_qss.py)
# ---------------------------------------------------------------------------


def application_stylesheet() -> str:
    """Return the single QSS string that styles every widget in the app."""
    from klaus.ui import theme_qss

    return theme_qss.application_stylesheet()


# ---------------------------------------------------------------------------
# Helper functions still used by widget code for dynamic / role-based styling
# ---------------------------------------------------------------------------

def role_color(role: str) -> str:
    """Return the accent color for a given role."""
    return USER_ACCENT if role == "user" else KLAUS_ACCENT


def role_label(role: str) -> str:
    """Return the display name for a given role."""
    return "You" if role == "user" else "Klaus"


def load_fonts() -> None:
    """Register any bundled font files with Qt's font database.

    Call once before creating any widgets (typically in main.py after
    QApplication is constructed). If the fonts directory or files are missing,
    Qt will use the installed Helvetica Neue family.
    """
    if not _FONTS_DIR.is_dir():
        logger.debug("Fonts directory not found: %s", _FONTS_DIR)
        return

    from PyQt6.QtGui import QFontDatabase

    font_files = sorted(
        path
        for path in _FONTS_DIR.iterdir()
        if path.suffix.lower() in {".otf", ".ttc", ".ttf"}
    )
    for font_path in font_files:
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            logger.warning("Failed to load font: %s", font_path.name)
        else:
            families = QFontDatabase.applicationFontFamilies(font_id)
            logger.debug("Loaded font %s -> %s", font_path.name, families)
