"""Centralized theme tokens for the Klaus UI.

All colors, fonts, dimensions, and the single application-wide QSS live here so
that every widget imports from one place and palette tweaks are a single-file
change.
"""

from __future__ import annotations

import ctypes
import logging
from pathlib import Path
import sys

logger = logging.getLogger(__name__)

_FONTS_DIR = Path(__file__).parent / "fonts"

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

# Base layers (darkest to lightest)
BG = "#131316"
SURFACE = "#1a1a1f"
SURFACE_RAISED = "#222228"
SURFACE_OVERLAY = "#2a2a32"

# Borders
BORDER_MUTED = "#2a2a30"
BORDER_DEFAULT = "#333340"
BORDER_EMPHASIS = "#55556a"

# Text
TEXT_PRIMARY = "#e0e0e6"
TEXT_SECONDARY = "#a0a0ad"
TEXT_MUTED = "#606068"

# Accents
USER_ACCENT = "#8888cc"
USER_BG = "#1e1e2a"
KLAUS_ACCENT = "#66bb6a"
KLAUS_BG = "#1a261a"

LISTENING_COLOR = "#ef4444"
THINKING_COLOR = "#f59e0b"
SPEAKING_COLOR = "#4ade80"
IDLE_COLOR = "#707078"
ERROR_COLOR = "#ef4444"

# Stop button (semantic aliases for ERROR_COLOR shades)
STOP_BG = "#b91c1c"
STOP_BORDER = "#dc2626"
STOP_HOVER_BG = "#dc2626"

# Klaus card accent buttons
KLAUS_BTN_BORDER = "#2a4a2a"
KLAUS_BTN_HOVER_BG = "#1e331e"

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

FONT_FAMILY = '"Inter", "Segoe UI", "SF Pro Text", sans-serif'
FONT_SIZE_BODY = 15
FONT_SIZE_SMALL = 13
FONT_SIZE_CAPTION = 12
FONT_SIZE_HEADING = 20

# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

HEADER_HEIGHT = 52
STATUS_BAR_HEIGHT = 36
CARD_PADDING_H = 14
CARD_PADDING_V = 10
CARD_RADIUS = 10
RADIUS_SM = 6
RADIUS_MD = 10
CAMERA_PREVIEW_WIDTH = 320

# ---------------------------------------------------------------------------
# Application-wide QSS
# ---------------------------------------------------------------------------


def application_stylesheet() -> str:
    """Return the single QSS string that styles every widget in the app."""
    return f"""
/* ===== Base ===== */
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT_PRIMARY};
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_BODY}px;
}}

/* ===== Scrollbar ===== */
QScrollBar:vertical {{
    background: {SURFACE};
    width: 10px;
    border-radius: 5px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_DEFAULT};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {BORDER_EMPHASIS};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

/* ===== ComboBox ===== */
QComboBox {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_SM}px;
    padding: 5px 10px;
    font-size: {FONT_SIZE_SMALL}px;
    min-width: 180px;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    selection-background-color: {SURFACE_OVERLAY};
}}

/* ===== Default button ===== */
QPushButton {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_SM}px;
    padding: 5px 12px;
    font-size: {FONT_SIZE_SMALL}px;
}}
QPushButton:hover {{
    background-color: {SURFACE_OVERLAY};
    border-color: {BORDER_EMPHASIS};
}}

/* ===== Header ===== */
#klaus-header {{
    background-color: {SURFACE};
    border-bottom: 1px solid {BORDER_MUTED};
}}
#klaus-title {{
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_HEADING}px;
    font-weight: bold;
    letter-spacing: 1px;
    background: transparent;
    border: none;
}}
#klaus-session-title {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_SMALL}px;
    background: transparent;
    border: none;
}}
#klaus-settings-btn {{
    color: {TEXT_MUTED};
    background: transparent;
    border: none;
    font-size: 18px;
    padding: 0;
}}
#klaus-settings-btn:hover {{
    color: {TEXT_PRIMARY};
}}

/* ===== Splitter ===== */
QSplitter::handle {{
    background: {BORDER_MUTED};
    width: 1px;
}}

/* ===== Camera preview ===== */
#camera-preview {{
    background-color: {SURFACE};
    border: 1px solid {BORDER_MUTED};
    border-radius: 8px;
}}

/* ===== Session panel ===== */
#session-panel-title {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: bold;
    letter-spacing: 1px;
    background: transparent;
    border: none;
}}
#session-new-btn {{
    color: {TEXT_SECONDARY};
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 4px;
    padding: 2px 8px;
    font-size: {FONT_SIZE_CAPTION}px;
}}
#session-new-btn:hover {{
    background-color: {SURFACE_OVERLAY};
    border-color: {BORDER_EMPHASIS};
}}
#session-list {{
    background: transparent;
    border: none;
    outline: none;
}}
#session-list::item {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0;
    padding: 8px 8px 8px 6px;
    margin: 0;
}}
#session-list::item:selected {{
    background: {SURFACE_RAISED};
    border-left: 3px solid {USER_ACCENT};
}}
#session-list::item:hover:!selected {{
    background: {SURFACE};
}}

/* ===== Session item label (inside QListWidget items) ===== */
QLabel#session-item-label {{
    background: transparent;
    border: none;
    padding: 0;
}}

/* ===== Context menu ===== */
QMenu {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_SM}px;
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 20px;
}}
QMenu::item:selected {{
    background-color: {SURFACE_OVERLAY};
}}

/* ===== Chat scroll area ===== */
#chat-scroll {{
    border: none;
    background: transparent;
}}

/* ===== Chat empty state ===== */
#chat-empty {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_BODY}px;
    padding: 60px 20px;
    border: none;
}}

/* ===== Chat status message ===== */
QLabel#chat-status-msg {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_CAPTION}px;
    font-style: italic;
    padding: 4px;
    border: none;
}}

/* ===== MessageCard (role-based via dynamic property) ===== */
MessageCard[role="user"] {{
    background-color: {USER_BG};
    border: none;
    border-radius: {CARD_RADIUS}px;
}}
MessageCard[role="assistant"] {{
    background-color: {KLAUS_BG};
    border: none;
    border-radius: {CARD_RADIUS}px;
}}

/* Labels inside cards inherit transparent bg */
MessageCard QLabel {{
    border: none;
    background: transparent;
}}

/* Card role name */
QLabel#card-name-user {{
    color: {USER_ACCENT};
    font-weight: 600;
    font-size: {FONT_SIZE_SMALL + 1}px;
}}
QLabel#card-name-assistant {{
    color: {KLAUS_ACCENT};
    font-weight: 600;
    font-size: {FONT_SIZE_SMALL + 1}px;
}}

/* Card timestamp */
QLabel#card-timestamp {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_CAPTION}px;
}}

/* Card body text */
QLabel#card-body {{
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_BODY}px;
}}

/* Card thumbnail */
QLabel#card-thumbnail {{
    border: none;
    margin-bottom: 4px;
}}

/* Accent buttons (copy / replay) on Klaus cards */
QPushButton#card-accent-btn {{
    color: {KLAUS_ACCENT};
    background: transparent;
    border: 1px solid {KLAUS_BTN_BORDER};
    border-radius: 4px;
    font-size: {FONT_SIZE_CAPTION}px;
    padding: 2px 8px;
}}
QPushButton#card-accent-btn:hover {{
    background: {KLAUS_BTN_HOVER_BG};
}}

/* ===== Status bar ===== */
#klaus-status-bar {{
    background-color: {BG};
    border-top: 1px solid {BORDER_MUTED};
}}
#klaus-state-label {{
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: bold;
}}
#klaus-mode-btn {{
    color: {TEXT_SECONDARY};
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_MD}px;
    padding: 3px 12px;
    font-size: {FONT_SIZE_CAPTION}px;
    font-weight: bold;
}}
#klaus-mode-btn:hover {{
    color: {TEXT_PRIMARY};
    background-color: {SURFACE_OVERLAY};
    border: 1px solid {BORDER_EMPHASIS};
}}
#klaus-stop-btn {{
    color: #fff;
    background-color: {STOP_BG};
    border: 1px solid {STOP_BORDER};
    border-radius: {RADIUS_MD}px;
    padding: 3px 12px;
    font-size: {FONT_SIZE_CAPTION}px;
    font-weight: bold;
}}
#klaus-stop-btn:hover {{
    background-color: {STOP_HOVER_BG};
}}
#klaus-hotkey-hint {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_CAPTION}px;
    background: transparent;
    border: none;
}}
#klaus-stats {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_CAPTION}px;
    background: transparent;
    border: none;
}}

/* ===== Tab widget ===== */
QTabWidget::pane {{
    background-color: {SURFACE};
    border: 1px solid {BORDER_DEFAULT};
    border-top: none;
    border-radius: 0 0 {RADIUS_SM}px {RADIUS_SM}px;
}}
QTabBar::tab {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_DEFAULT};
    border-bottom: none;
    padding: 8px 18px;
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 600;
    margin-right: 2px;
    border-radius: {RADIUS_SM}px {RADIUS_SM}px 0 0;
}}
QTabBar::tab:selected {{
    background-color: {SURFACE};
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {USER_ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background-color: {SURFACE_OVERLAY};
    color: {TEXT_PRIMARY};
}}

/* ===== Dialogs ===== */
QDialog {{
    background-color: {SURFACE};
    color: {TEXT_PRIMARY};
}}
QLineEdit {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_SM}px;
    padding: 6px 10px;
    font-size: {FONT_SIZE_BODY}px;
    selection-background-color: {SURFACE_OVERLAY};
}}
QLineEdit:focus {{
    border-color: {BORDER_EMPHASIS};
}}
QMessageBox {{
    background-color: {SURFACE};
    color: {TEXT_PRIMARY};
}}
QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}
QInputDialog {{
    background-color: {SURFACE};
}}
QInputDialog QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}

/* ===== Setup wizard ===== */
#wizard-primary-btn {{
    background-color: {USER_ACCENT};
    color: #fff;
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 10px 24px;
    font-size: {FONT_SIZE_BODY}px;
    font-weight: 600;
}}
#wizard-primary-btn:hover {{
    background-color: #9999dd;
}}
#wizard-link-btn {{
    color: {USER_ACCENT};
    background: transparent;
    border: none;
    font-size: {FONT_SIZE_CAPTION}px;
    text-decoration: underline;
    padding: 2px;
}}
#wizard-link-btn:hover {{
    color: #9999dd;
}}
#wizard-back-btn {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_SM}px;
    padding: 8px 20px;
    font-size: {FONT_SIZE_SMALL}px;
}}
#wizard-back-btn:hover {{
    background-color: {SURFACE_OVERLAY};
    border-color: {BORDER_EMPHASIS};
}}
#wizard-next-btn {{
    background-color: {USER_ACCENT};
    color: #fff;
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 8px 24px;
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 600;
}}
#wizard-next-btn:hover {{
    background-color: #9999dd;
}}
#wizard-next-btn:disabled {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_MUTED};
}}
#wizard-mic-meter, #wizard-model-progress {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 4px;
}}
#wizard-mic-meter::chunk, #wizard-model-progress::chunk {{
    background-color: {KLAUS_ACCENT};
    border-radius: 3px;
}}
"""


# ---------------------------------------------------------------------------
# Kept for backward-compat during transition; prefer application_stylesheet()
# ---------------------------------------------------------------------------

GLOBAL_STYLESHEET = application_stylesheet()


# ---------------------------------------------------------------------------
# Helper functions still used by widget code for dynamic / role-based styling
# ---------------------------------------------------------------------------

def role_color(role: str) -> str:
    """Return the accent color for a given role."""
    return USER_ACCENT if role == "user" else KLAUS_ACCENT


def role_label(role: str) -> str:
    """Return the display name for a given role."""
    return "You" if role == "user" else "Klaus"


# ---------------------------------------------------------------------------
# Windows dark title bar (DWM API)
# ---------------------------------------------------------------------------

def apply_dark_titlebar(window) -> None:
    """Force the native Windows title bar to use dark mode.

    Uses DwmSetWindowAttribute with DWMWA_USE_IMMERSIVE_DARK_MODE (attr 20).
    No-op on non-Windows platforms.
    """
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        logger.debug("Failed to apply dark title bar", exc_info=True)


def load_fonts() -> None:
    """Register bundled Inter font files with Qt's font database.

    Call once before creating any widgets (typically in main.py after
    QApplication is constructed). If the fonts directory or files are missing,
    Qt will fall back to the next family in FONT_FAMILY.
    """
    if not _FONTS_DIR.is_dir():
        logger.debug("Fonts directory not found: %s", _FONTS_DIR)
        return

    from PyQt6.QtGui import QFontDatabase

    for ttf in sorted(_FONTS_DIR.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(ttf))
        if font_id < 0:
            logger.warning("Failed to load font: %s", ttf.name)
        else:
            families = QFontDatabase.applicationFontFamilies(font_id)
            logger.debug("Loaded font %s -> %s", ttf.name, families)
