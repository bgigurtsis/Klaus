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
    KLAUS_BTN_BORDER,
    KLAUS_BTN_HOVER_BG,
    LISTENING_COLOR,
    RADIUS_MD,
    RADIUS_SM,
    SIDEBAR,
    SPEAKING_COLOR,
    STOP_BG,
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
    from klaus.ui.theme_qss_dialogs import dialog_stylesheet

    return _main_stylesheet() + dialog_stylesheet()


def _main_stylesheet() -> str:
    """Return the QSS for the main window and its widgets."""
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
    border-radius: 16px;
    padding: 5px 14px;
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
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 17px;
    padding: 5px 14px;
    font-size: {FONT_SIZE_SMALL}px;
    font-weight: 500;
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
    border-radius: 16px;
    padding: 7px 16px;
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
#wizard-primary-btn, #wizard-next-btn,
#desk-view-confirm-button {{
    background-color: {ACCENT};
    color: {ACCENT_TEXT};
    border: none;
    font-weight: 700;
}}
#wizard-primary-btn:hover, #wizard-next-btn:hover,
#desk-view-confirm-button:hover {{
    background-color: {ACCENT_HOVER};
}}
#wizard-primary-btn:pressed, #wizard-next-btn:pressed,
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
    font-size: {FONT_SIZE_BODY + 1}px;
    font-weight: 700;
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
    border-radius: 8px;
    font-size: 13px;
    font-weight: 800;
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
    background-color: {SURFACE};
    border: 1px solid {BORDER_MUTED};
    border-radius: 12px;
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_SMALL}px;
}}
#reading-context-title {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_CAPTION - 1}px;
    font-weight: 600;
    letter-spacing: 0.4px;
    background: transparent;
}}
#reading-context-badge {{
    background: transparent;
    border: none;
    padding: 0;
    font-size: {FONT_SIZE_CAPTION - 1}px;
    font-weight: 600;
}}

/* ===== Session panel ===== */
#session-panel-title {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_CAPTION - 1}px;
    font-weight: 600;
    letter-spacing: 0.4px;
    background: transparent;
    border: none;
}}
#session-new-btn {{
    color: {TEXT_SECONDARY};
    background-color: transparent;
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 16px;
    padding: 0 14px;
    font-size: {FONT_SIZE_CAPTION}px;
    font-weight: 600;
}}
#session-new-btn:hover {{
    color: {TEXT_PRIMARY};
    background-color: {SURFACE_OVERLAY};
    border-color: {BORDER_EMPHASIS};
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
/* ===== Chat empty state ===== */
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
    border-radius: 16px;
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

/* ===== Chat error message ===== */
#chat-error-card {{
    background-color: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.35);
    border-radius: 10px;
}}
QLabel#chat-error-msg {{
    color: {ERROR_COLOR};
    font-size: {FONT_SIZE_CAPTION}px;
    padding: 2px;
    border: none;
    background: transparent;
}}
QPushButton#chat-error-retry {{
    color: {ERROR_COLOR};
    background: transparent;
    border: 1px solid rgba(239, 68, 68, 0.45);
    border-radius: 12px;
    padding: 3px 12px;
    font-size: {FONT_SIZE_CAPTION}px;
}}
QPushButton#chat-error-retry:hover {{
    background: rgba(239, 68, 68, 0.14);
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
    border-radius: 26px;
}}
#klaus-voice-composer[dockState="hot"] {{
    border-color: rgba(226, 84, 102, 0.45);
}}
#klaus-state-dot {{
    background: transparent;
    border: none;
}}
#klaus-state-label {{
    font-size: {FONT_SIZE_SMALL + 1}px;
    font-weight: 600;
    background: transparent;
}}
#klaus-state-detail {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_SMALL}px;
    background: transparent;
}}
#klaus-mode-btn {{
    color: {TEXT_SECONDARY};
    background-color: {SURFACE_RAISED};
    border: 1px solid {BORDER_DEFAULT};
    border-radius: 16px;
    padding: 0 16px;
    font-size: {FONT_SIZE_CAPTION}px;
    font-weight: 600;
}}
#klaus-mode-btn:hover {{
    color: {TEXT_PRIMARY};
    background-color: {SURFACE_OVERLAY};
    border: 1px solid {BORDER_EMPHASIS};
}}
#klaus-stop-btn {{
    color: #ffffff;
    background-color: {STOP_BG};
    border: none;
    border-radius: 16px;
    padding: 0 18px;
    font-size: {FONT_SIZE_CAPTION}px;
    font-weight: 700;
}}
#klaus-stop-btn:hover {{
    background-color: {STOP_HOVER_BG};
}}
#klaus-stats {{
    color: {TEXT_MUTED};
    font-size: {FONT_SIZE_CAPTION}px;
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
    border-radius: 15px;
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
"""
