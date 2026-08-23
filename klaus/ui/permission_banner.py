"""Persistent permission warning with a direct macOS Settings action."""

from __future__ import annotations

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from klaus.ui import theme


class PermissionBanner(QFrame):
    """Show an actionable permission problem inside the main window."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("permission-banner")
        self.setStyleSheet(
            f"""
            QFrame#permission-banner {{
                background: #352d1f;
                border-bottom: 1px solid #725a2a;
            }}
            QLabel#permission-banner-title {{
                color: {theme.TEXT_PRIMARY};
                background: transparent;
                font-weight: 700;
            }}
            QLabel#permission-banner-message {{
                color: {theme.TEXT_SECONDARY};
                background: transparent;
            }}
            QPushButton#permission-banner-button {{
                color: #17130b;
                background: #e4b85a;
                border: 1px solid #f0c96f;
                border-radius: 8px;
                padding: 7px 12px;
                font-weight: 700;
            }}
            QPushButton#permission-banner-button:hover {{
                background: #f0c96f;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 12, 22, 12)
        layout.setSpacing(16)

        copy_layout = QVBoxLayout()
        copy_layout.setSpacing(2)
        self._title = QLabel()
        self._title.setObjectName("permission-banner-title")
        self._message = QLabel()
        self._message.setObjectName("permission-banner-message")
        self._message.setWordWrap(True)
        copy_layout.addWidget(self._title)
        copy_layout.addWidget(self._message)
        layout.addLayout(copy_layout, stretch=1)

        self._settings_button = QPushButton("Open Privacy Settings")
        self._settings_button.setObjectName("permission-banner-button")
        self._settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_button.clicked.connect(self._open_settings)
        layout.addWidget(self._settings_button)

        self._settings_url = ""
        self.hide()

    def show_issue(self, title: str, message: str, settings_url: str) -> None:
        self._title.setText(title)
        self._message.setText(message)
        self._settings_url = settings_url
        self.show()

    def clear_issue(self) -> None:
        self._settings_url = ""
        self.hide()

    def _open_settings(self) -> None:
        if self._settings_url:
            QDesktopServices.openUrl(QUrl(self._settings_url))
