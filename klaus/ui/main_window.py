"""Klaus main application window."""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QKeyEvent

import klaus.config as config
from klaus.ui import theme
from klaus.ui.camera_widget import CameraWidget
from klaus.ui.chat_widget import ChatWidget
from klaus.ui.session_panel import SessionPanel
from klaus.ui.status_widget import StatusWidget

logger = logging.getLogger(__name__)

_QT_KEY_MAP: dict[str, Qt.Key] = {
    "f1": Qt.Key.Key_F1, "f2": Qt.Key.Key_F2, "f3": Qt.Key.Key_F3,
    "f4": Qt.Key.Key_F4, "f5": Qt.Key.Key_F5, "f6": Qt.Key.Key_F6,
    "f7": Qt.Key.Key_F7, "f8": Qt.Key.Key_F8, "f9": Qt.Key.Key_F9,
    "f10": Qt.Key.Key_F10, "f11": Qt.Key.Key_F11, "f12": Qt.Key.Key_F12,
    "space": Qt.Key.Key_Space, "escape": Qt.Key.Key_Escape,
    "tab": Qt.Key.Key_Tab, "backspace": Qt.Key.Key_Backspace,
}


def resolve_qt_key(key_name: str) -> int:
    """Map a config key name (e.g. ``'F2'``) to a ``Qt.Key`` value."""
    lower = key_name.lower()
    if lower in _QT_KEY_MAP:
        return _QT_KEY_MAP[lower]
    if len(key_name) == 1:
        return ord(key_name.upper())
    raise ValueError(f"Unknown hotkey for Qt: {key_name!r}")


class MainWindow(QMainWindow):
    """Klaus main application window."""

    session_changed = pyqtSignal(str)             # session_id
    new_session_requested = pyqtSignal(str)       # title
    rename_requested = pyqtSignal(str, str)       # session_id, new_title
    delete_requested = pyqtSignal(str)            # session_id
    replay_requested = pyqtSignal(str)            # exchange_id
    mode_toggle_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    settings_requested = pyqtSignal()

    ptt_key_pressed = pyqtSignal()
    ptt_key_released = pyqtSignal()
    toggle_key_pressed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._qt_ptt_key: int = Qt.Key.Key_F2
        self._qt_toggle_key: int = Qt.Key.Key_F3
        self.setWindowTitle("Klaus")
        self.setWindowIcon(QIcon(str(theme.ICON_PATH)))
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)

        theme.apply_dark_titlebar(self)
        self.setStyleSheet(theme.application_stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -- Header --
        header = QWidget()
        header.setObjectName("klaus-header")
        header.setFixedHeight(theme.HEADER_HEIGHT)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("Klaus")
        title.setObjectName("klaus-title")
        header_layout.addWidget(title)

        header_layout.addStretch()

        self._session_title_label = QLabel("")
        self._session_title_label.setObjectName("klaus-session-title")
        header_layout.addWidget(self._session_title_label)

        settings_btn = QPushButton("\u2699")
        settings_btn.setObjectName("klaus-settings-btn")
        settings_btn.setFixedSize(32, 32)
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setToolTip("Settings")
        settings_btn.clicked.connect(self.settings_requested.emit)
        header_layout.addWidget(settings_btn)

        main_layout.addWidget(header)

        # -- Body: left sidebar + chat --
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: camera + session list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)

        self.camera_widget = CameraWidget()
        left_layout.addWidget(self.camera_widget)

        self.session_panel = SessionPanel()
        self.session_panel.session_selected.connect(self.session_changed.emit)
        self.session_panel.new_session_requested.connect(
            self.new_session_requested.emit
        )
        self.session_panel.rename_requested.connect(self.rename_requested.emit)
        self.session_panel.delete_requested.connect(self.delete_requested.emit)
        left_layout.addWidget(self.session_panel, stretch=1)

        splitter.addWidget(left_panel)

        # Right panel: chat
        self.chat_widget = ChatWidget()
        self.chat_widget.replay_requested.connect(self.replay_requested.emit)
        splitter.addWidget(self.chat_widget)

        splitter.setSizes([300, 700])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter, stretch=1)

        # -- Status Bar --
        self.status_widget = StatusWidget(
            hotkey=config.PUSH_TO_TALK_KEY,
            toggle_key=config.TOGGLE_KEY,
        )
        self.status_widget.mode_toggle_clicked.connect(
            self.mode_toggle_requested.emit
        )
        self.status_widget.stop_clicked.connect(self.stop_requested.emit)
        main_layout.addWidget(self.status_widget)

    # -- Session management --

    def set_sessions(
        self,
        sessions: list[dict],
        current_id: str | None = None,
    ) -> None:
        """Populate the session panel. Each dict: id, title, (updated_at, exchange_count)."""
        self.session_panel.set_sessions(sessions, current_id)
        if current_id:
            for s in sessions:
                if s["id"] == current_id:
                    self._session_title_label.setText(s["title"])
                    break

    def set_current_session_title(self, title: str) -> None:
        """Update the header subtitle with the active session name."""
        self._session_title_label.setText(title)

    def get_current_session_id(self) -> str | None:
        """Return the currently selected session id from the session panel."""
        return self.session_panel._current_id

    # -- In-app keyboard shortcuts (no Accessibility permission needed) --

    def set_hotkeys(self, ptt_key: str, toggle_key: str) -> None:
        """Configure which keys trigger PTT and mode toggle via Qt events."""
        self._qt_ptt_key = resolve_qt_key(ptt_key)
        self._qt_toggle_key = resolve_qt_key(toggle_key)
        logger.info(
            "Qt in-app hotkeys configured (ptt=%s, toggle=%s)", ptt_key, toggle_key,
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            return
        key = event.key()
        if key == self._qt_ptt_key:
            self.ptt_key_pressed.emit()
        elif key == self._qt_toggle_key:
            self.toggle_key_pressed.emit()
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            return
        key = event.key()
        if key == self._qt_ptt_key:
            self.ptt_key_released.emit()
        else:
            super().keyReleaseEvent(event)
