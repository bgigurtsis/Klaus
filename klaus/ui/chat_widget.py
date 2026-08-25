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
from klaus.ui.image_viewer import ClickableImageLabel, show_image_viewer
from klaus.ui.shared.relative_time import format_relative_time_with_tooltip

logger = logging.getLogger(__name__)

_SCROLL_THRESHOLD = 30
_COLUMN_MAX_WIDTH = 860
_THINKING_FRAMES = ("·", "· ·", "· · ·")
_THINKING_INTERVAL_MS = 400


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
            thumb = ClickableImageLabel()
            thumb.setObjectName("card-thumbnail")
            pixmap = QPixmap()
            pixmap.loadFromData(thumbnail_bytes)
            if not pixmap.isNull():
                thumb.set_zoom_pixmap(pixmap)
                scaled = pixmap.scaled(
                    500, 180,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                thumb.setPixmap(scaled)
                thumb.image_clicked.connect(
                    lambda image: show_image_viewer(
                        image,
                        parent=self,
                        title="Captured screenshot",
                    )
                )
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
        self.set_text(self._text + text)

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
        self._height_sync_pending = False
        self._thinking_active = False
        self._thinking_frame = 0
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(_THINKING_INTERVAL_MS)
        self._thinking_timer.timeout.connect(self._advance_thinking)
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

        # Messages live in a centered column so user and assistant cards read
        # as one thread instead of hugging opposite edges of a wide window.
        self._container = QWidget()
        container_layout = QHBoxLayout(self._container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        column = QWidget()
        column.setMaximumWidth(_COLUMN_MAX_WIDTH)
        column.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred,
        )
        # The large stretch factor lets the column take all width up to its
        # cap; only the overflow splits between the side stretches.
        container_layout.addStretch(1)
        container_layout.addWidget(column, stretch=1000)
        container_layout.addStretch(1)

        self._layout = QVBoxLayout(column)
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
        self._append_card(
            role,
            text,
            timestamp=timestamp,
            thumbnail_bytes=thumbnail_bytes,
            exchange_id=exchange_id,
            note_file_path=note_file_path,
        )
        logger.debug("Added %s message", role)

    def show_thinking(self) -> None:
        """Show a pending assistant card until the first transcript fragment."""
        if self._streaming_card is not None:
            return
        self._streaming_card = self._append_card("assistant", _THINKING_FRAMES[0])
        self._thinking_active = True
        self._thinking_frame = 0
        self._thinking_timer.start()

    def dismiss_thinking(self) -> None:
        """Remove the pending card if no answer text ever arrived."""
        if not self._thinking_active:
            return
        self._stop_thinking()
        card = self._streaming_card
        self._streaming_card = None
        if card is not None:
            self._remove_card_row(card)
        self._schedule_content_height_sync()

    def append_assistant_stream(self, text: str) -> None:
        """Append a streamed transcript fragment to the live assistant card.

        Creates the card on the first fragment of a response, or replaces the
        thinking placeholder when one is showing.
        """
        if self._streaming_card is None:
            self._streaming_card = self._append_card("assistant", text)
        elif self._thinking_active:
            self._stop_thinking()
            self._streaming_card.set_text(text)
        else:
            self._streaming_card.append_text(text)
        self._schedule_content_height_sync()

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
        self._stop_thinking()
        card = self._streaming_card
        self._streaming_card = None
        if card is None:
            return False
        card.set_text(text)
        card.set_exchange_id(exchange_id)
        card.set_note_file(note_file_path)
        self._schedule_content_height_sync()
        return True

    def abort_assistant_stream(self) -> None:
        """Detach the streaming card after a cancelled turn."""
        if self._thinking_active:
            # No answer text ever arrived; drop the placeholder entirely.
            self.dismiss_thinking()
            return
        if self._streaming_card is not None:
            self._streaming_card.mark_interrupted()
        self._streaming_card = None
        self._schedule_content_height_sync()

    def add_error_message(self, text: str, on_retry=None) -> None:
        """Add a visually distinct error row, optionally with a Retry button."""
        was_near_bottom = self._is_near_bottom()
        self._hide_empty()
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 2, 0, 2)
        row_layout.addStretch()

        card = QFrame()
        card.setObjectName("chat-error-card")
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(14, 8, 14, 8)
        card_layout.setSpacing(12)

        label = QLabel(text)
        label.setObjectName("chat-error-msg")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card_layout.addWidget(label)

        if on_retry is not None:
            retry_btn = QPushButton("Retry")
            retry_btn.setObjectName("chat-error-retry")
            retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            retry_btn.setToolTip("Ask the same question again")
            retry_btn.clicked.connect(lambda: (retry_btn.setEnabled(False), on_retry()))
            card_layout.addWidget(
                retry_btn, alignment=Qt.AlignmentFlag.AlignVCenter
            )

        row_layout.addWidget(card)
        row_layout.addStretch()
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._auto_scroll = was_near_bottom
        self._layout.addWidget(row)
        self._message_widgets.append(row)
        self._schedule_content_height_sync()

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
        self._schedule_content_height_sync()

    def clear(self) -> None:
        self._stop_thinking()
        for widget in self._message_widgets:
            self._layout.removeWidget(widget)
            widget.deleteLater()
        self._message_widgets.clear()
        self._last_card = None
        self._streaming_card = None
        self._auto_scroll = True
        self._show_empty()
        self._schedule_content_height_sync()

    def scroll_to_bottom(self) -> None:
        """Schedule a deferred scroll after layout settles."""
        self._auto_scroll = True
        QTimer.singleShot(0, self._do_scroll_to_bottom)
        QTimer.singleShot(100, self._do_scroll_to_bottom)

    # -- Private --

    def _append_card(
        self,
        role: str,
        text: str,
        timestamp: float | None = None,
        thumbnail_bytes: bytes | None = None,
        exchange_id: str = "",
        note_file_path: str | None = None,
    ) -> MessageCard:
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
        self._schedule_content_height_sync()
        return card

    def _remove_card_row(self, card: MessageCard) -> None:
        row = card.parentWidget()
        if row in self._message_widgets:
            self._message_widgets.remove(row)
            self._layout.removeWidget(row)
            row.deleteLater()
        if self._last_card is card:
            self._last_card = None
        if not self._message_widgets:
            self._show_empty()

    def _stop_thinking(self) -> None:
        self._thinking_active = False
        self._thinking_timer.stop()

    def _advance_thinking(self) -> None:
        if not self._thinking_active or self._streaming_card is None:
            self._thinking_timer.stop()
            return
        self._thinking_frame = (self._thinking_frame + 1) % len(_THINKING_FRAMES)
        self._streaming_card.set_text(_THINKING_FRAMES[self._thinking_frame])

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
        self._schedule_content_height_sync()
        super().resizeEvent(event)

    @staticmethod
    def _card_row(card: MessageCard, role: str) -> QWidget:
        row = QWidget()
        row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        # Large stretch factor: the card takes width up to its cap before the
        # alignment stretch absorbs the remainder.
        if role == "user":
            layout.addStretch(1)
            layout.addWidget(card, 1000)
        else:
            layout.addWidget(card, 1000)
            layout.addStretch(1)
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
        self._schedule_content_height_sync()
        if self._auto_scroll:
            QTimer.singleShot(0, self._do_scroll_to_bottom)

    def _do_scroll_to_bottom(self) -> None:
        sb = self._scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _schedule_content_height_sync(self) -> None:
        if self._height_sync_pending:
            return
        self._height_sync_pending = True
        QTimer.singleShot(0, self._sync_content_height)

    def _sync_content_height(self) -> None:
        """Remove stale word-wrap height from the scrollable canvas."""
        self._height_sync_pending = False
        widgets = [
            widget
            for widget in (self._empty_state, *self._message_widgets)
            if not widget.isHidden()
        ]
        # The container has a fixed height so its scroll range ends at the last
        # message. Qt can therefore shrink a newly inserted or growing row to
        # the container's old height before this method expands the container.
        # Pin each row to its current size hint first, then measure the result.
        for widget in widgets:
            widget.updateGeometry()
            if widget.layout() is not None:
                widget.layout().invalidate()
                widget.layout().activate()
            widget.setMinimumHeight(widget.sizeHint().height())
        self._layout.invalidate()
        self._layout.activate()
        margins = self._layout.contentsMargins()
        content_height = margins.top() + margins.bottom()
        content_height += sum(
            max(widget.height(), widget.sizeHint().height()) for widget in widgets
        )
        if widgets:
            content_height += self._layout.spacing() * (len(widgets) - 1)
        target = max(self._scroll.viewport().height(), content_height)
        if self._container.height() != target:
            self._container.setFixedHeight(target)
            if self._auto_scroll:
                QTimer.singleShot(0, self._do_scroll_to_bottom)
