"""Scrollable chat feed with message cards and empty state."""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QSizePolicy,
    QFrame,
    QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap

from klaus.ui import theme
from klaus.ui.shared.relative_time import format_relative_time_with_tooltip

logger = logging.getLogger(__name__)

_SCROLL_THRESHOLD = 30


class MessageCard(QFrame):
    """A single message card in the chat feed."""

    replay_requested = pyqtSignal(str)

    def __init__(
        self,
        role: str,
        text: str,
        timestamp: float | None = None,
        thumbnail_bytes: bytes | None = None,
        exchange_id: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._exchange_id = exchange_id
        self._role = role

        is_user = role == "user"

        self.setProperty("role", "user" if is_user else "assistant")
        self.setObjectName("message-card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            theme.CARD_PADDING_H, theme.CARD_PADDING_V,
            theme.CARD_PADDING_H, theme.CARD_PADDING_V,
        )
        layout.setSpacing(6)

        # Header row: name, timestamp, action buttons
        header = QHBoxLayout()
        header.setSpacing(8)

        name = QLabel(theme.role_label(role))
        name.setObjectName("card-name-user" if is_user else "card-name-assistant")
        header.addWidget(name)

        if timestamp:
            display, tooltip = format_relative_time_with_tooltip(timestamp)
            ts_label = QLabel(display)
            ts_label.setObjectName("card-timestamp")
            ts_label.setToolTip(tooltip)
            header.addWidget(ts_label)

        header.addStretch()

        if not is_user:
            copy_btn = QPushButton("\u2398 copy")
            copy_btn.setObjectName("card-accent-btn")
            copy_btn.setFixedHeight(22)
            copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.clicked.connect(lambda: self._copy_text(text, copy_btn))
            header.addWidget(copy_btn)

            replay_btn = QPushButton("\u25b6 replay")
            replay_btn.setObjectName("card-accent-btn")
            replay_btn.setFixedHeight(22)
            replay_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            replay_btn.clicked.connect(
                lambda: self.replay_requested.emit(self._exchange_id)
            )
            header.addWidget(replay_btn)

        layout.addLayout(header)

        # Thumbnail (user messages only)
        if thumbnail_bytes and is_user:
            thumb = QLabel()
            thumb.setObjectName("card-thumbnail")
            pixmap = QPixmap()
            pixmap.loadFromData(thumbnail_bytes)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    500, 180,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                thumb.setPixmap(scaled)
            thumb.setMaximumHeight(180)
            layout.addWidget(thumb)

        # Body text
        body = QLabel(text)
        body.setObjectName("card-body")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(body)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    @staticmethod
    def _copy_text(text: str, btn: QPushButton) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
        original = btn.text()
        btn.setText("\u2714 copied")
        QTimer.singleShot(1500, lambda: btn.setText(original))


class ChatWidget(QWidget):
    """Scrollable chat feed showing the conversation history."""

    replay_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._auto_scroll = True
        self._shown = False
        self._last_card: QWidget | None = None
        self._message_widgets: list[QWidget] = []
        self._init_ui()

    def _init_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("chat-scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(10, 10, 10, 10)
        self._layout.setSpacing(12)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignBottom)

        # Empty state placeholder
        self._empty_label = QLabel(
            "Place a page under the camera and ask a question"
        )
        self._empty_label.setObjectName("chat-empty")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._layout.addWidget(self._empty_label)

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

        sb = self._scroll.verticalScrollBar()
        sb.rangeChanged.connect(self._on_range_changed)
        sb.valueChanged.connect(self._on_scroll_value_changed)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._shown:
            self._shown = True
            self._auto_scroll = True
            QTimer.singleShot(0, self._do_scroll_to_bottom)
            QTimer.singleShot(100, self._do_scroll_to_bottom)

    # -- Public API --

    def add_message(
        self,
        role: str,
        text: str,
        timestamp: float | None = None,
        thumbnail_bytes: bytes | None = None,
        exchange_id: str = "",
    ) -> None:
        was_near_bottom = self._is_near_bottom()
        self._hide_empty()

        card = MessageCard(
            role=role,
            text=text,
            timestamp=timestamp,
            thumbnail_bytes=thumbnail_bytes,
            exchange_id=exchange_id,
            parent=self._container,
        )
        card.replay_requested.connect(self.replay_requested.emit)

        self._auto_scroll = was_near_bottom
        self._layout.addWidget(card)
        self._message_widgets.append(card)
        self._last_card = card
        logger.debug("Added %s message", role)

    def add_status_message(self, text: str) -> None:
        was_near_bottom = self._is_near_bottom()
        self._hide_empty()
        label = QLabel(text)
        label.setObjectName("chat-status-msg")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._auto_scroll = was_near_bottom
        self._layout.addWidget(label)
        self._message_widgets.append(label)

    def clear(self) -> None:
        for widget in self._message_widgets:
            self._layout.removeWidget(widget)
            widget.deleteLater()
        self._message_widgets.clear()
        self._last_card = None
        self._auto_scroll = True
        self._show_empty()

    def scroll_to_bottom(self) -> None:
        """Schedule a deferred scroll after layout settles."""
        self._auto_scroll = True
        QTimer.singleShot(0, self._do_scroll_to_bottom)
        QTimer.singleShot(100, self._do_scroll_to_bottom)

    # -- Private --

    def _hide_empty(self) -> None:
        self._empty_label.setVisible(False)

    def _show_empty(self) -> None:
        self._empty_label.setVisible(True)

    def _is_near_bottom(self) -> bool:
        sb = self._scroll.verticalScrollBar()
        return sb.maximum() == 0 or sb.value() >= sb.maximum() - _SCROLL_THRESHOLD

    def _on_scroll_value_changed(self, value: int) -> None:
        self._auto_scroll = self._is_near_bottom()

    def _on_range_changed(self, _min: int, new_max: int) -> None:
        if self._auto_scroll:
            QTimer.singleShot(0, self._do_scroll_to_bottom)

    def _do_scroll_to_bottom(self) -> None:
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())
