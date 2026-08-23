"""Persistent voice dock showing state, interruption, and input controls."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton
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
        "push_to_talk": "{toggle} switches to hands-free",
        "voice_activation": "{toggle} switches to push to talk",
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
        composer.setMinimumWidth(580)
        composer.setMaximumWidth(840)
        layout = QHBoxLayout(composer)
        layout.setContentsMargins(14, 10, 12, 10)
        layout.setSpacing(12)
        outer.addStretch()
        outer.addWidget(composer, stretch=1)
        outer.addStretch()

        self._orb = QLabel()
        self._orb.setObjectName("klaus-state-orb")
        self._orb.setFixedSize(38, 38)
        self._orb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._orb)

        state_column = QVBoxLayout()
        state_column.setSpacing(3)

        self._state_label = QLabel()
        self._state_label.setObjectName("klaus-state-label")
        state_column.addWidget(self._state_label)

        self._detail_label = QLabel()
        self._detail_label.setObjectName("klaus-state-detail")
        state_column.addWidget(self._detail_label)
        layout.addLayout(state_column)

        layout.addStretch()

        hint = self._HOTKEY_HINTS.get(self._mode, "").format(
            hotkey=self._hotkey, toggle=self._toggle_key,
        )
        self._hotkey_label = QLabel(hint)
        self._hotkey_label.setObjectName("klaus-hotkey-hint")
        layout.addWidget(self._hotkey_label)

        self._mode_btn = QPushButton(self._MODE_LABELS.get(self._mode, "Voice"))
        self._mode_btn.setObjectName("klaus-mode-btn")
        self._mode_btn.setFixedHeight(36)
        self._mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_btn.setToolTip("Switch voice input mode")
        self._mode_btn.clicked.connect(self.mode_toggle_clicked.emit)
        layout.addWidget(self._mode_btn)

        self._stop_btn = QPushButton("Interrupt")
        self._stop_btn.setObjectName("klaus-stop-btn")
        self._stop_btn.setFixedHeight(36)
        self._stop_btn.setMinimumWidth(108)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setToolTip("Stop this answer now")
        self._stop_btn.clicked.connect(self.stop_clicked.emit)
        self._stop_btn.setVisible(False)
        layout.addWidget(self._stop_btn)

        self._stats_label = QLabel("0 answers")
        self._stats_label.setObjectName("klaus-stats")
        layout.addWidget(self._stats_label)
        self._apply_state_label("idle")

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
        hint = self._HOTKEY_HINTS.get(mode, "").format(
            hotkey=self._hotkey, toggle=self._toggle_key,
        )
        self._hotkey_label.setText(hint)
        self._apply_state_label(self._current_state)

    def set_exchange_count(self, count: int) -> None:
        """Update the session exchange count display."""
        label = "answer" if count == 1 else "answers"
        self._stats_label.setText(f"{count} {label}")

    def set_hotkeys(self, hotkey: str, toggle_key: str) -> None:
        """Update hotkey labels shown in the status bar."""
        self._hotkey = hotkey
        self._toggle_key = toggle_key
        hint = self._HOTKEY_HINTS.get(self._mode, "").format(
            hotkey=self._hotkey, toggle=self._toggle_key,
        )
        self._hotkey_label.setText(hint)
        self._apply_state_label(self._current_state)
