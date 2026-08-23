"""Persistent voice dock showing state, interruption, and input controls."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal

from klaus.ui import theme


class StatusWidget(QWidget):
    """Bottom voice dock with clear turn state and interruption controls."""

    mode_toggle_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()

    _STATES = {
        "idle": {
            "push_to_talk": (
                "Ready when you are",
                "Hold {hotkey} to ask a question",
                theme.IDLE_COLOR,
                "\u25cf",
            ),
            "voice_activation": (
                "Ready for your question",
                "Just start speaking. You can interrupt any answer.",
                theme.SPEAKING_COLOR,
                "\u25cf",
            ),
        },
        "listening": (
            "Listening",
            "Finish your thought naturally",
            theme.LISTENING_COLOR,
            "\u223f",
        ),
        "thinking": (
            "Thinking with your reading",
            "Klaus is building a short spoken answer",
            theme.THINKING_COLOR,
            "\u2726",
        ),
        "speaking": (
            "Answering",
            "Speak to interrupt, or use the button",
            theme.SPEAKING_COLOR,
            "\u223f",
        ),
        "interrupted": (
            "Interrupted",
            "Go ahead with your next question",
            theme.LISTENING_COLOR,
            "\u21b3",
        ),
    }

    _MODE_LABELS = {
        "push_to_talk": "Push to talk",
        "voice_activation": "Hands-free",
    }

    _HOTKEY_HINTS = {
        "push_to_talk": "Switch to hands-free",
        "voice_activation": "Switch to push to talk",
    }

    def __init__(
        self,
        hotkey: str = "F2",
        toggle_key: str = "F3",
        mode: str = "voice_activation",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("klaus-status-bar")
        self._hotkey = hotkey
        self._toggle_key = toggle_key
        self._mode = mode
        self._current_state = "idle"
        self._init_ui()

    def _init_ui(self) -> None:
        self.setFixedHeight(theme.STATUS_BAR_HEIGHT)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(28, 8, 28, 16)

        composer = QFrame()
        composer.setObjectName("klaus-voice-composer")
        composer.setMinimumWidth(0)
        composer.setMaximumWidth(1040)
        self._composer = composer
        self._composer_layout = QGridLayout(composer)
        self._composer_layout.setContentsMargins(14, 10, 12, 10)
        self._composer_layout.setHorizontalSpacing(12)
        self._composer_layout.setVerticalSpacing(8)
        outer.addStretch()
        outer.addWidget(composer, stretch=1)
        outer.addStretch()

        self._orb = QLabel()
        self._orb.setObjectName("klaus-state-orb")
        self._orb.setFixedSize(38, 38)
        self._orb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._state_group = QWidget()
        self._state_group.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred,
        )

        state_column = QVBoxLayout(self._state_group)
        state_column.setContentsMargins(0, 0, 0, 0)
        state_column.setSpacing(3)

        self._state_label = QLabel()
        self._state_label.setObjectName("klaus-state-label")
        state_column.addWidget(self._state_label)

        self._detail_label = QLabel()
        self._detail_label.setObjectName("klaus-state-detail")
        state_column.addWidget(self._detail_label)
        self._hotkey_group = QWidget()
        hotkey_cluster = QHBoxLayout(self._hotkey_group)
        hotkey_cluster.setContentsMargins(0, 0, 0, 0)
        hotkey_cluster.setSpacing(7)
        self._hotkey_keycap = QLabel(self._toggle_key)
        self._hotkey_keycap.setObjectName("klaus-hotkey-keycap")
        self._hotkey_keycap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hotkey_keycap.setMaximumWidth(110)
        self._resize_hotkey_keycap()
        hotkey_cluster.addWidget(self._hotkey_keycap)

        self._hotkey_label = QLabel(self._HOTKEY_HINTS.get(self._mode, ""))
        self._hotkey_label.setObjectName("klaus-hotkey-hint")
        hotkey_cluster.addWidget(self._hotkey_label)

        self._mode_btn = QPushButton(self._MODE_LABELS.get(self._mode, "Voice"))
        self._mode_btn.setObjectName("klaus-mode-btn")
        self._mode_btn.setFixedHeight(36)
        self._mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_btn.setToolTip("Switch voice input mode")
        self._mode_btn.clicked.connect(self.mode_toggle_clicked.emit)

        self._stop_btn = QPushButton("Interrupt")
        self._stop_btn.setObjectName("klaus-stop-btn")
        self._stop_btn.setFixedHeight(36)
        self._stop_btn.setMinimumWidth(108)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setToolTip("Stop this answer now")
        self._stop_btn.clicked.connect(self.stop_clicked.emit)
        self._stop_btn.setVisible(False)

        self._stats_label = QLabel("0 answers")
        self._stats_label.setObjectName("klaus-stats")
        self._compact_layout: bool | None = None
        self._apply_responsive_layout(force=True)
        self._apply_state_label("idle")

    def resizeEvent(self, event) -> None:
        self._apply_responsive_layout()
        super().resizeEvent(event)

    def _apply_responsive_layout(self, force: bool = False) -> None:
        """Reflow the voice controls before they can clip."""
        compact = self.width() < 1040
        if not force and compact == self._compact_layout:
            self._apply_compact_visibility()
            return
        self._compact_layout = compact
        layout = self._composer_layout
        for widget in (
            self._orb,
            self._state_group,
            self._hotkey_group,
            self._mode_btn,
            self._stop_btn,
            self._stats_label,
        ):
            layout.removeWidget(widget)

        if compact:
            self.setFixedHeight(138)
            layout.addWidget(self._orb, 0, 0)
            layout.addWidget(self._state_group, 0, 1, 1, 3)
            layout.addWidget(self._hotkey_group, 1, 0, 1, 2)
            layout.addWidget(self._mode_btn, 1, 2)
            layout.addWidget(self._stop_btn, 1, 3)
            layout.addWidget(self._stats_label, 1, 4)
            layout.setColumnStretch(1, 1)
        else:
            self.setFixedHeight(theme.STATUS_BAR_HEIGHT)
            layout.addWidget(self._orb, 0, 0)
            layout.addWidget(self._state_group, 0, 1)
            layout.addWidget(self._hotkey_group, 0, 2)
            layout.addWidget(self._mode_btn, 0, 3)
            layout.addWidget(self._stop_btn, 0, 4)
            layout.addWidget(self._stats_label, 0, 5)
            layout.setColumnStretch(1, 1)
        self._apply_compact_visibility()

    def _apply_compact_visibility(self) -> None:
        width = self.width()
        self._detail_label.setVisible(width >= 470)
        self._hotkey_label.setVisible(width >= 540)
        self._stats_label.setVisible(width >= 620)

    def _apply_state_label(self, state: str) -> None:
        entry = self._STATES.get(state, self._STATES["idle"])
        if isinstance(entry, dict):
            title, detail, color, symbol = entry.get(
                self._mode,
                ("Ready", "", theme.IDLE_COLOR, "\u25cf"),
            )
        else:
            title, detail, color, symbol = entry
        detail = detail.format(hotkey=self._hotkey, toggle=self._toggle_key)
        self._state_label.setText(title)
        self._detail_label.setText(detail)
        self._state_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        self._orb.setText(symbol)
        self._orb.setStyleSheet(
            f"color: {color}; background: {theme.SURFACE_RAISED}; "
            f"border: 1px solid {color}; border-radius: 19px;"
        )

    def set_state(self, state: str) -> None:
        """Update the state indicator."""
        self._current_state = state
        self._apply_state_label(state)
        self._stop_btn.setVisible(state in ("thinking", "speaking"))

    def set_mode(self, mode: str) -> None:
        """Update the mode button label and hotkey hint."""
        self._mode = mode
        self._mode_btn.setText(self._MODE_LABELS.get(mode, "Voice"))
        self._hotkey_label.setText(self._HOTKEY_HINTS.get(mode, ""))
        self._apply_state_label(self._current_state)

    def set_exchange_count(self, count: int) -> None:
        """Update the session exchange count display."""
        label = "answer" if count == 1 else "answers"
        self._stats_label.setText(f"{count} {label}")

    def set_hotkeys(self, hotkey: str, toggle_key: str) -> None:
        """Update hotkey labels shown in the status bar."""
        self._hotkey = hotkey
        self._toggle_key = toggle_key
        self._hotkey_keycap.setText(self._toggle_key)
        self._resize_hotkey_keycap()
        self._hotkey_label.setText(self._HOTKEY_HINTS.get(self._mode, ""))
        self._apply_state_label(self._current_state)

    def _resize_hotkey_keycap(self) -> None:
        """Keep the full shortcut visible inside its padded keycap."""
        text_width = self._hotkey_keycap.fontMetrics().horizontalAdvance(
            self._hotkey_keycap.text()
        )
        self._hotkey_keycap.setMinimumWidth(min(110, max(52, text_width + 24)))
