"""Application-wide QSS for the Klaus UI.

Split out of theme.py so the token module stays under the module-size ceiling.
All values come from klaus.ui.theme; this module only assembles the stylesheet.
"""

from __future__ import annotations

from klaus.ui.theme import (  # noqa: F401
    ACCENT,
    ACCENT_HOVER,
    ACCENT_PRESSED,
    ACCENT_TEXT,
    BG,
    BORDER_DEFAULT,
    BORDER_EMPHASIS,
    BORDER_MUTED,
    CARD_RADIUS,
    ERROR_COLOR,
    FONT_FAMILY,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_HEADING,
    FONT_SIZE_SMALL,
    IDLE_COLOR,
    KLAUS_ACCENT,
    KLAUS_BG,
    KLAUS_BTN_BORDER,
    KLAUS_BTN_HOVER_BG,
    LISTENING_COLOR,
    RADIUS_MD,
    RADIUS_SM,
    SIDEBAR,
    SPEAKING_COLOR,
    STOP_BG,
    STOP_BORDER,
    STOP_HOVER_BG,
    SURFACE,
    SURFACE_OVERLAY,
    SURFACE_RAISED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    THINKING_COLOR,
    USER_ACCENT,
    USER_BG,
    USER_BORDER,
    _ICONS_DIR,
)


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
QToolTip {{
    background-color: {SURFACE_OVERLAY};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 6px;
    padding: 6px 8px;
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
    border-radius: 9px;
    padding: 5px 12px;
    font-size: {FONT_SIZE_SMALL}px;
    min-height: 26px;
    min-width: 180px;
}}
QComboBox:hover {{
    border-color: {BORDER_EMPHASIS};
}}
QComboBox:on, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 30px;
}}
QComboBox::down-arrow {{
    image: url({_ICONS_DIR.as_posix()}/chevron-down.svg);
    width: 12px;
    height: 12px;
}}
QComboBox QAbstractItemView {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    selection-background-color: {SURFACE_OVERLAY};
    selection-color: {TEXT_PRIMARY};
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 8px;
}}
QComboBox QAbstractItemView::item:hover {{
    background-color: {BORDER_EMPHASIS};
    color: {TEXT_PRIMARY};
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {USER_BG};
    color: {TEXT_PRIMARY};
}}
QComboBox QAbstractItemView::item:selected:hover {{
    background-color: {USER_ACCENT};
    color: #ffffff;
}}
#reading-source-combo {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER_EMPHASIS};
    border-radius: 9px;
    padding: 7px 12px;
    font-size: {FONT_SIZE_BODY}px;
    font-weight: 600;
}}
#reading-source-combo:hover, #reading-source-combo:on {{
    background-color: {SURFACE_OVERLAY};
    border-color: {USER_ACCENT};
}}
#reading-source-menu {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_EMPHASIS};
    border-radius: 10px;
    padding: 6px;
    outline: none;
}}
#reading-source-menu::item {{
    min-height: 38px;
    padding: 0 10px;
    border-radius: 7px;
    font-size: {FONT_SIZE_BODY}px;
}}
#reading-source-menu::item:selected {{
    color: #ffffff;
    background-color: #5b4f88;
}}
#reading-source-menu::item:hover:!selected {{
    color: {TEXT_PRIMARY};
    background-color: {SURFACE_OVERLAY};
}}

/* ===== Buttons =====
   Hierarchy: default = quiet secondary; primary ids get the filled accent;
   card/icon buttons are ghosts that only surface on hover. */
QPushButton {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 9px;
    padding: 7px 14px;
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {SURFACE_OVERLAY};
    border-color: {BORDER_EMPHASIS};
}}
QPushButton:pressed {{
    background-color: {SURFACE};
    border-color: {BORDER_EMPHASIS};
}}
QPushButton:disabled {{
    background-color: {SURFACE};
    color: {TEXT_MUTED};
    border-color: {BORDER_MUTED};
}}
QPushButton:focus {{
    border-color: {ACCENT};
    outline: none;
}}
#wizard-primary-btn, #wizard-next-btn, #session-new-btn,
#desk-view-confirm-button {{
    background-color: {ACCENT};
    color: {ACCENT_TEXT};
    border: none;
    font-weight: 700;
}}
#wizard-primary-btn:hover, #wizard-next-btn:hover, #session-new-btn:hover,
#desk-view-confirm-button:hover {{
    background-color: {ACCENT_HOVER};
}}
#wizard-primary-btn:pressed, #wizard-next-btn:pressed, #session-new-btn:pressed,
#desk-view-confirm-button:pressed {{
    background-color: {ACCENT_PRESSED};
}}

/* ===== Checkbox ===== */
QCheckBox {{
    spacing: 8px;
    background: transparent;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid {BORDER_EMPHASIS};
    background-color: {SURFACE_RAISED};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    image: url({_ICONS_DIR.as_posix()}/check.svg);
}}

/* ===== Header ===== */
#klaus-header {{
    background-color: {BG};
    border-bottom: 1px solid {BORDER_MUTED};
}}
#klaus-title {{
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_HEADING}px;
    font-weight: bold;
    letter-spacing: -0.2px;
    background: transparent;
    border: none;
}}
#klaus-session-title {{
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_SMALL + 1}px;
    font-weight: 650;
    background: transparent;
    border: none;
}}
#klaus-brand-mark {{
    color: {ACCENT_TEXT};
    background: {ACCENT};
    border: none;
    border-radius: 9px;
    font-size: 15px;
    font-weight: 800;
}}
#klaus-brand-subtitle {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_CAPTION}px;
    background: transparent;
    border: none;
}}
#klaus-breadcrumb {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_CAPTION}px;
    background: transparent;
    border: none;
}}
#klaus-model-pill {{
    color: {TEXT_SECONDARY};
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 12px;
    padding: 3px 10px;
    font-size: {FONT_SIZE_CAPTION}px;
}}
#klaus-settings-btn {{
    color: {TEXT_SECONDARY};
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    font-size: 16px;
    padding: 0;
}}
#klaus-settings-btn:hover {{
    color: {TEXT_PRIMARY};
    background: {SURFACE_OVERLAY};
    border-color: {BORDER_EMPHASIS};
}}
#klaus-sidebar-btn {{
    color: {TEXT_SECONDARY};
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0;
    font-size: 18px;
}}
#klaus-sidebar-btn:hover {{
    color: {TEXT_PRIMARY};
    background: {SURFACE_OVERLAY};
    border-color: {BORDER_EMPHASIS};
}}

/* ===== Splitter ===== */
QSplitter::handle {{
    background: {BORDER_MUTED};
    width: 1px;
}}
#klaus-sidebar {{
    background: {SIDEBAR};
    border-right: 1px solid {BORDER_MUTED};
}}
#reading-source-panel, #session-panel {{
    background: transparent;
}}
#klaus-thread {{
    background: {BG};
}}

/* ===== Camera preview ===== */
#camera-preview {{
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 14px;
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_SMALL + 1}px;
}}
#reading-context-title {{
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_CAPTION}px;
    font-weight: 700;
    letter-spacing: 0.8px;
    background: transparent;
}}
#reading-context-badge {{
    color: {KLAUS_ACCENT};
    background: {KLAUS_BG};
    border: 1px solid {KLAUS_BTN_BORDER};
    border-radius: 9px;
    padding: 3px 8px;
    font-size: 11px;
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
    border-radius: 8px;
    padding: 6px 12px;
    font-size: {FONT_SIZE_CAPTION}px;
}}
#session-list {{
    background: transparent;
    border: none;
    outline: none;
}}
#session-list QWidget {{
    background: transparent;
}}
#session-list::item {{
    background: transparent;
    border: none;
    border: 1px solid transparent;
    border-radius: 10px;
    padding: 8px;
    margin: 3px 0;
}}
#session-list::item:selected {{
    background: {SURFACE_OVERLAY};
    border: 1px solid {BORDER_DEFAULT};
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
#session-more-btn {{
    color: {TEXT_MUTED};
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 0;
    font-size: 18px;
}}
#session-more-btn:hover {{
    color: {TEXT_PRIMARY};
    background: {SURFACE_OVERLAY};
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
#conversation-header {{
    background: {BG};
    border-bottom: 1px solid {BORDER_MUTED};
}}
#conversation-heading {{
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_SMALL + 1}px;
    font-weight: 700;
    background: transparent;
    border: none;
}}
#conversation-subtitle {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_CAPTION}px;
    background: transparent;
    border: none;
}}
#conversation-badge {{
    color: {KLAUS_ACCENT};
    background: {KLAUS_BG};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 10px;
    padding: 3px 9px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.7px;
}}

/* ===== Chat empty state ===== */
#chat-empty {{
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_BODY + 1}px;
    border: none;
}}
#chat-empty-heading {{
    color: {TEXT_PRIMARY};
    font-size: {FONT_SIZE_HEADING + 8}px;
    font-weight: 700;
    background: transparent;
    border: none;
}}
#chat-empty-subtitle {{
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_BODY}px;
    background: transparent;
    border: none;
}}
#chat-empty-orb {{
    color: {USER_ACCENT};
    background: {USER_BG};
    border: 1px solid {USER_BORDER};
    border-radius: 32px;
    font-size: 27px;
    font-weight: 700;
}}
#chat-example {{
    color: {TEXT_SECONDARY};
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 12px;
    padding: 10px 12px;
    font-size: {FONT_SIZE_CAPTION}px;
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
    border: 1px solid {USER_BORDER};
    border-radius: {CARD_RADIUS}px;
}}
MessageCard[role="assistant"] {{
    background-color: {BG};
    border: none;
    border-radius: 0;
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

QLabel#card-note-link {{
    color: {USER_ACCENT};
    font-size: {FONT_SIZE_SMALL}px;
    padding-top: 4px;
}}
QLabel#card-note-link a {{
    color: {USER_ACCENT};
}}

/* Card thumbnail */
QLabel#card-thumbnail {{
    border: none;
    margin-bottom: 4px;
}}

/* Ghost buttons (copy / replay) on Klaus cards */
QPushButton#card-accent-btn {{
    color: {TEXT_MUTED};
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    font-size: {FONT_SIZE_CAPTION}px;
    font-weight: 600;
    padding: 4px 9px;
}}
QPushButton#card-accent-btn:hover {{
    color: {TEXT_PRIMARY};
    background: {SURFACE_RAISED};
    border-color: {BORDER_DEFAULT};
}}
QPushButton#card-accent-btn:pressed {{
    background: {SURFACE};
}}

/* ===== Status bar ===== */
#klaus-status-bar {{
    background-color: {BG};
    border: none;
}}
#klaus-voice-composer {{
    background-color: {SURFACE};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 18px;
}}
#klaus-state-label {{
    font-size: {FONT_SIZE_BODY + 1}px;
    font-weight: 700;
}}
#klaus-state-detail {{
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_SMALL + 1}px;
    background: transparent;
}}
#klaus-state-orb {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 20px;
    font-size: 18px;
}}
#klaus-mode-btn {{
    color: {TEXT_SECONDARY};
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 10px;
    padding: 8px 14px;
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 600;
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
    border-radius: 10px;
    padding: 9px 18px;
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 700;
}}
#klaus-stop-btn:hover {{
    background-color: {STOP_HOVER_BG};
}}
#klaus-hotkey-hint {{
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_SMALL + 1}px;
    font-weight: 600;
    background: transparent;
    border: none;
}}
#klaus-hotkey-keycap {{
    color: {TEXT_PRIMARY};
    background: {SURFACE_OVERLAY};
    border: 1px solid {BORDER_EMPHASIS};
    border-bottom: 2px solid {BORDER_EMPHASIS};
    border-radius: 6px;
    padding: 4px 8px;
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 700;
}}
#klaus-stats {{
    color: {TEXT_SECONDARY};
    font-size: {FONT_SIZE_SMALL + 1}px;
    background: transparent;
    border: none;
}}

/* ===== Tab widget (segmented pills, no boxed pane) ===== */
QTabWidget::pane {{
    background-color: transparent;
    border: none;
    border-top: 1px solid {BORDER_MUTED};
    margin-top: 6px;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_MUTED};
    border: 1px solid transparent;
    padding: 7px 16px;
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 600;
    margin-right: 4px;
    margin-bottom: 8px;
    border-radius: 9px;
}}
QTabBar::tab:selected {{
    background-color: {SURFACE_RAISED};
    color: {TEXT_PRIMARY};
    border-color: {BORDER_DEFAULT};
}}
QTabBar::tab:hover:!selected {{
    background-color: {SURFACE};
    color: {TEXT_SECONDARY};
}}

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
    border-radius: 9px;
    padding: 9px 18px;
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
    border-radius: 9px;
    padding: 10px 24px;
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
    border-radius: {RADIUS_SM}px;
    padding: 8px 20px;
    font-size: {FONT_SIZE_SMALL}px;
}}
#wizard-back-btn:hover {{
    background-color: {SURFACE_OVERLAY};
    border-color: {BORDER_EMPHASIS};
}}
#wizard-next-btn {{
    border-radius: 9px;
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
