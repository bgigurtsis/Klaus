"""Klaus main application window."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal

from klaus.ui import theme
from klaus.ui.camera_widget import CameraWidget
from klaus.ui.chat_widget import ChatWidget
from klaus.ui.session_panel import SessionPanel
from klaus.ui.status_widget import StatusWidget


class MainWindow(QMainWindow):
    """Klaus main application window."""

    session_changed = pyqtSignal(str)             # session_id
    new_session_requested = pyqtSignal(str)       # title
    rename_requested = pyqtSignal(str, str)       # session_id, new_title
    delete_requested = pyqtSignal(str)            # session_id
    replay_requested = pyqtSignal(str)            # exchange_id
    mode_toggle_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Klaus")
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)
        self.setStyleSheet(theme.GLOBAL_STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -- Header --
        header = QWidget()
        header.setFixedHeight(theme.HEADER_HEIGHT)
        header.setStyleSheet(theme.HEADER_STYLE)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)

        title = QLabel("Klaus")
        title.setStyleSheet(theme.TITLE_STYLE)
        header_layout.addWidget(title)

        header_layout.addStretch()

        self._session_title_label = QLabel("")
        self._session_title_label.setStyleSheet(theme.SUBTITLE_STYLE)
        header_layout.addWidget(self._session_title_label)

        main_layout.addWidget(header)

        # -- Body: left sidebar + chat --
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {theme.BORDER_MUTED}; width: 1px; }}"
        )

        # Left panel: camera + session list
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 0, 8)
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
        self.status_widget = StatusWidget()
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
