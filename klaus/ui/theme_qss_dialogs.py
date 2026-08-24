"""Dialog and setup-wizard QSS for the Klaus UI (see theme_qss.py)."""

from __future__ import annotations

from klaus.ui.theme import (  # noqa: F401
    ACCENT,
    BORDER_DEFAULT,
    BORDER_EMPHASIS,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_HEADING,
    FONT_SIZE_SMALL,
    RADIUS_MD,
    SURFACE,
    SURFACE_OVERLAY,
    SURFACE_RAISED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    USER_ACCENT,
    USER_BG,
)


def dialog_stylesheet() -> str:
    """Return the QSS for dialogs and the setup wizard."""
    return f"""
/* ===== Dialogs ===== */
QDialog {{
    background-color: {SURFACE};
    color: {TEXT_PRIMARY};
}}
QLineEdit, QPlainTextEdit {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 9px;
    padding: 7px 11px;
    font-size: {FONT_SIZE_SMALL + 1}px;
    selection-background-color: {USER_BG};
}}
QLineEdit:focus, QPlainTextEdit:focus {{
    border-color: {ACCENT};
}}
QMessageBox {{
    background-color: {SURFACE};
    color: {TEXT_PRIMARY};
}}
QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}
#desk-view-dialog {{
    background-color: {SURFACE};
}}
#desk-view-title {{
    color: {TEXT_PRIMARY};
    font-size: 24px;
    font-weight: 500;
    letter-spacing: -0.3px;
    background: transparent;
}}
#desk-view-intro {{
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_BODY}px;
    font-weight: 400;
    background: transparent;
}}
#desk-view-step-number {{
    color: {TEXT_PRIMARY};
    background-color: {SURFACE_OVERLAY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 12px;
    font-size: {FONT_SIZE_CAPTION}px;
    font-weight: 500;
}}
#desk-view-step-text {{
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_BODY + 1}px;
    font-weight: 400;
    background: transparent;
}}
#desk-view-confirm-button {{
    border-radius: 19px;
    padding: 9px 20px;
    font-size: {FONT_SIZE_SMALL + 1}px;
}}
QInputDialog {{
    background-color: {SURFACE};
}}
QInputDialog QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}

/* ===== Setup wizard ===== */
#wizard-welcome-title {{
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_HEADING + 10}px;
    font-weight: 700;
    background: transparent;
    border: none;
}}
#wizard-welcome-subtitle {{
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_BODY}px;
    background: transparent;
    border: none;
    padding: 0 24px;
}}
#wizard-welcome-card {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: {RADIUS_MD}px;
}}
#wizard-welcome-card-title {{
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_SMALL + 1}px;
    font-weight: 700;
    background: transparent;
    border: none;
}}
#wizard-welcome-card-body {{
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_SMALL}px;
    background: transparent;
    border: none;
}}
#wizard-welcome-footer {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_CAPTION}px;
    background: transparent;
    border: none;
}}
#wizard-primary-btn {{
    border-radius: 20px;
    padding: 10px 26px;
    font-size: {FONT_SIZE_BODY}px;
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
    border-radius: 17px;
    padding: 8px 20px;
    font-size: {FONT_SIZE_SMALL}px;
}}
#wizard-back-btn:hover {{
    background-color: {SURFACE_OVERLAY};
    border-color: {BORDER_EMPHASIS};
}}
#wizard-next-btn {{
    border-radius: 17px;
    padding: 8px 24px;
    font-size: {FONT_SIZE_SMALL}px;
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
    background-color: {ACCENT};
    border-radius: 3px;
}}
"""
