"""Scrollable chat feed with message cards and empty state."""

from __future__ import annotations

import html
import logging
from pathlib import Path

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
    QBoxLayout,
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap

from klaus.ui import theme
from klaus.ui.file_links import reveal_file_in_browser
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
        note_file_path: str | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._exchange_id = exchange_id
        self._role = role
        self._text = text

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

        self._status_label = QLabel("")
        self._status_label.setObjectName("card-timestamp")
        self._status_label.setVisible(False)
        header.addWidget(self._status_label)

        header.addStretch()

        if not is_user:
            copy_btn = QPushButton("Copy")
            copy_btn.setObjectName("card-accent-btn")
            copy_btn.setFixedHeight(28)
            copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.setToolTip("Copy answer")
            copy_btn.clicked.connect(lambda: self._copy_text(self._text, copy_btn))
            header.addWidget(copy_btn)

            replay_btn = QPushButton("\u25b6  Replay")
            replay_btn.setObjectName("card-accent-btn")
            replay_btn.setFixedHeight(28)
            replay_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            replay_btn.setToolTip("Hear this answer again")
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
        self._body = body

        self._note_link = QLabel()
        self._note_link.setObjectName("card-note-link")
        self._note_link.setTextFormat(Qt.TextFormat.RichText)
        self._note_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self._note_link.setOpenExternalLinks(False)
        self._note_link.linkActivated.connect(self._open_note_link)
        layout.addWidget(self._note_link)
        self.set_note_file(note_file_path)

        self.setMaximumWidth(620 if is_user else 740)
        self.setMinimumWidth(280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def set_text(self, text: str) -> None:
        self._text = text
        self._body.setText(text)

    def append_text(self, text: str) -> None:
        combined = f"{self._text} {text}".strip() if self._text else text
        self.set_text(combined)

    def set_exchange_id(self, exchange_id: str) -> None:
        self._exchange_id = exchange_id

    def set_note_file(self, path: str | None) -> None:
        """Show a link that reveals a changed Obsidian note."""
        if not path:
            self._note_link.clear()
            self._note_link.setVisible(False)
            return
        file_name = Path(path).name
        url = QUrl.fromLocalFile(path).toString()
        self._note_link.setText(
            f'<a style="color:{theme.USER_ACCENT}; text-decoration:none;" '
            f'href="{html.escape(url, quote=True)}">'
            f'Open {html.escape(file_name)} in Finder</a>'
        )
        self._note_link.setVisible(True)

    @staticmethod
    def _open_note_link(url: str) -> None:
        path = QUrl(url).toLocalFile()
        if path:
            reveal_file_in_browser(path)

    def mark_interrupted(self) -> None:
        self._status_label.setText("Interrupted")
        self._status_label.setVisible(True)

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
        self._streaming_card: MessageCard | None = None
        self._message_widgets: list[QWidget] = []
        self._init_ui()

    def _init_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("chat-scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(32, 26, 32, 24)
        self._layout.setSpacing(20)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._empty_state = self._build_empty_state()
        self._layout.addWidget(
            self._empty_state,
            alignment=Qt.AlignmentFlag.AlignCenter,
        )

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
        note_file_path: str | None = None,
    ) -> None:
        was_near_bottom = self._is_near_bottom()
        self._hide_empty()

        card = MessageCard(
            role=role,
            text=text,
            timestamp=timestamp,
            thumbnail_bytes=thumbnail_bytes,
            exchange_id=exchange_id,
            note_file_path=note_file_path,
            parent=self._container,
        )
        card.replay_requested.connect(self.replay_requested.emit)

        self._auto_scroll = was_near_bottom
        row = self._card_row(card, role)
        self._layout.addWidget(row)
        self._message_widgets.append(row)
        self._last_card = card
        logger.debug("Added %s message", role)

    def append_assistant_stream(self, text: str) -> None:
        """Append a streamed sentence to the live assistant card.

        Creates the card on the first sentence of a response.
        """
        if self._streaming_card is None:
            was_near_bottom = self._is_near_bottom()
            self._hide_empty()
            card = MessageCard(role="assistant", text=text, parent=self._container)
            card.replay_requested.connect(self.replay_requested.emit)
            self._auto_scroll = was_near_bottom
            row = self._card_row(card, "assistant")
            self._layout.addWidget(row)
            self._message_widgets.append(row)
            self._last_card = card
            self._streaming_card = card
        else:
            self._streaming_card.append_text(text)

    def finalize_assistant_stream(
        self,
        text: str,
        exchange_id: str,
        note_file_path: str | None = None,
    ) -> bool:
        """Replace the streaming card's text with the final response.

        Returns True if a streaming card was finalized, False if there was
        none (caller should add a regular message instead).
        """
        card = self._streaming_card
        self._streaming_card = None
        if card is None:
            return False
        card.set_text(text)
        card.set_exchange_id(exchange_id)
        card.set_note_file(note_file_path)
        return True

    def abort_assistant_stream(self) -> None:
        """Detach the streaming card after a cancelled turn."""
        if self._streaming_card is not None:
            self._streaming_card.mark_interrupted()
        self._streaming_card = None

    def add_status_message(self, text: str) -> None:
        was_near_bottom = self._is_near_bottom()
        self._hide_empty()
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.addStretch()
        label = QLabel(text)
        label.setObjectName("chat-status-msg")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        row_layout.addWidget(label)
        row_layout.addStretch()
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._auto_scroll = was_near_bottom
        self._layout.addWidget(row)
        self._message_widgets.append(row)

    def clear(self) -> None:
        for widget in self._message_widgets:
            self._layout.removeWidget(widget)
            widget.deleteLater()
        self._message_widgets.clear()
        self._last_card = None
        self._streaming_card = None
        self._auto_scroll = True
        self._show_empty()

    def scroll_to_bottom(self) -> None:
        """Schedule a deferred scroll after layout settles."""
        self._auto_scroll = True
        QTimer.singleShot(0, self._do_scroll_to_bottom)
        QTimer.singleShot(100, self._do_scroll_to_bottom)

    # -- Private --

    def _build_empty_state(self) -> QWidget:
        state = QWidget()
        state.setMinimumWidth(0)
        state.setMaximumWidth(680)
        layout = QVBoxLayout(state)
        layout.setContentsMargins(32, 96, 32, 40)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        orb = QLabel("K")
        orb.setObjectName("chat-empty-orb")
        orb.setFixedSize(64, 64)
        orb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(orb, alignment=Qt.AlignmentFlag.AlignCenter)

        heading = QLabel("What are you reading?")
        heading.setObjectName("chat-empty-heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setWordWrap(True)
        layout.addWidget(heading)

        self._empty_label = QLabel(
            "Select a source, then ask Klaus anything about the page in front of you."
        )
        self._empty_label.setObjectName("chat-empty-subtitle")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setMaximumWidth(500)
        self._empty_label.setMinimumHeight(46)
        layout.addWidget(self._empty_label)

        layout.addSpacing(8)
        self._prompts = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._prompts.setSpacing(10)
        for example in (
            "Explain this\nparagraph",
            "Define the\nkey term",
            "Save this to\nmy notes",
        ):
            label = QLabel(example)
            label.setObjectName("chat-example")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumWidth(0)
            self._prompts.addWidget(label)
        layout.addLayout(self._prompts)
        return state

    def resizeEvent(self, event) -> None:
        """Reduce margins and stack examples when the thread narrows."""
        compact = event.size().width() < 620
        margin = 16 if compact else 32
        self._layout.setContentsMargins(margin, 20, margin, 20)
        direction = (
            QBoxLayout.Direction.TopToBottom
            if event.size().width() < 500
            else QBoxLayout.Direction.LeftToRight
        )
        self._prompts.setDirection(direction)
        super().resizeEvent(event)

    @staticmethod
    def _card_row(card: MessageCard, role: str) -> QWidget:
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        if role == "user":
            layout.addStretch()
            layout.addWidget(card)
        else:
            layout.addWidget(card)
            layout.addStretch()
        return row

    def _hide_empty(self) -> None:
        self._empty_state.setVisible(False)

    def _show_empty(self) -> None:
        self._empty_state.setVisible(True)

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
