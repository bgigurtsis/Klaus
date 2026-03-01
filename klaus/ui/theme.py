"""Centralized theme tokens for the Klaus UI.

All colors, fonts, dimensions, and reusable QSS fragments live here so that
every widget imports from one place and palette tweaks are a single-file change.
"""

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

LIVE_GREEN = "#4ade80"

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------

FONT_FAMILY = '"Segoe UI", "Inter", "SF Pro Text", sans-serif'
FONT_SIZE_BODY = 14
FONT_SIZE_SMALL = 12
FONT_SIZE_CAPTION = 11
FONT_SIZE_HEADING = 18

# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

HEADER_HEIGHT = 52
STATUS_BAR_HEIGHT = 36
CARD_PADDING_H = 14
CARD_PADDING_V = 10
CARD_RADIUS = 10
CAMERA_PREVIEW_WIDTH = 320

# ---------------------------------------------------------------------------
# Reusable QSS
# ---------------------------------------------------------------------------

GLOBAL_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG};
    color: {TEXT_PRIMARY};
    font-family: {FONT_FAMILY};
    font-size: {FONT_SIZE_BODY}px;
}}
QComboBox {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 6px;
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
QPushButton {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 6px;
    padding: 5px 12px;
    font-size: {FONT_SIZE_SMALL}px;
}}
QPushButton:hover {{
    background-color: {SURFACE_OVERLAY};
    border-color: {BORDER_EMPHASIS};
}}
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
"""

HEADER_STYLE = (
    f"background-color: {SURFACE}; border-bottom: 1px solid {BORDER_MUTED};"
)

TITLE_STYLE = (
    f"color: {TEXT_PRIMARY}; font-size: {FONT_SIZE_HEADING}px;"
    f"font-weight: bold; letter-spacing: 1px;"
)

SUBTITLE_STYLE = (
    f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}px;"
)

STATUS_BAR_STYLE = (
    f"background-color: {BG}; border-top: 1px solid {BORDER_MUTED};"
)

MODE_BUTTON_STYLE = (
    f"color: {TEXT_SECONDARY}; background-color: {SURFACE_RAISED};"
    f"border: 1px solid {BORDER_DEFAULT}; border-radius: 10px;"
    f"padding: 3px 12px; font-size: {FONT_SIZE_CAPTION}px; font-weight: bold;"
)

MODE_BUTTON_HOVER = (
    f"color: {TEXT_PRIMARY}; background-color: {SURFACE_OVERLAY};"
    f"border: 1px solid {BORDER_EMPHASIS}; border-radius: 10px;"
    f"padding: 3px 12px; font-size: {FONT_SIZE_CAPTION}px; font-weight: bold;"
)

STOP_BUTTON_STYLE = (
    "color: #fff; background-color: #b91c1c; border: 1px solid #dc2626;"
    f"border-radius: 10px; padding: 3px 12px; font-size: {FONT_SIZE_CAPTION}px;"
    "font-weight: bold;"
)


def card_style(role: str) -> str:
    """Return QSS for a MessageCard based on role."""
    bg = USER_BG if role == "user" else KLAUS_BG
    return (
        f"background-color: {bg}; border: none;"
        f"border-radius: {CARD_RADIUS}px; padding: 0;"
    )


def role_color(role: str) -> str:
    return USER_ACCENT if role == "user" else KLAUS_ACCENT


def role_label(role: str) -> str:
    return "You" if role == "user" else "Klaus"


def accent_button_style(color: str, border_color: str) -> str:
    """Small accent-colored button (replay, copy)."""
    return (
        f"color: {color}; background: transparent;"
        f"border: 1px solid {border_color}; border-radius: 4px;"
        f"font-size: {FONT_SIZE_CAPTION}px; padding: 2px 8px;"
    )


def accent_button_hover(hover_bg: str) -> str:
    return f"background: {hover_bg};"
