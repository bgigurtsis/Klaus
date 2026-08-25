"""Persistent voice dock: a single-line capsule with state and controls."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PyQt6.QtCore import Qt, pyqtSignal

from klaus.ui import theme


class StatusWidget(QWidget):
    """Bottom voice dock rendered as one slim floating capsule.

    The capsule holds a state dot, a state word, a muted hint, and the
    controls on the right. While Klaus is thinking or answering the border
    tints toward the interrupt color and the right side collapses to a
    single Stop pill.
    """

    mode_toggle_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()

    _STATES = {
        "idle": {
            "push_to_talk": (
                "Push to talk",
                "Hold {hotkey} to talk",
                theme.IDLE_COLOR,
            ),
            "voice_activation": (
                "Ready",
                "Just start speaking",
                theme.SPEAKING_COLOR,
            ),
        },
        "loading": (
            "Getting ready",
            "Loading the speech model…",
            theme.THINKING_COLOR,
        ),
        "listening": (
            "Listening",
            "Finish your thought naturally",
            theme.LISTENING_COLOR,
        ),
        "thinking": (
            "Thinking",
            "Building a short spoken answer",
            theme.THINKING_COLOR,
        ),
        "speaking": (
            "Answering",
            "Speak over me to interrupt",
            theme.LISTENING_COLOR,
        ),
        "interrupted": (
            "Interrupted",
            "Go ahead with your next question",
            theme.LISTENING_COLOR,
        ),
    }

    _BUSY_STATES = ("thinking", "speaking")

    _MODE_LABELS = {
        "push_to_talk": "Push to talk",
        "voice_activation": "Hands-free",
    }

    # The mode button is labeled with the action it performs, not the
    # current mode, so the switch is unambiguous.
    _MODE_ACTIONS = {
        "push_to_talk": "Switch to hands-free",
        "voice_activation": "Switch to push to talk",
    }

    def __init__(
        self,
        hotkey: str = "F2",
        toggle_key: str = "F3",
        mode: str = "push_to_talk",
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

        capsule = QFrame()
        capsule.setObjectName("klaus-voice-composer")
        capsule.setProperty("dockState", "calm")
        capsule.setFixedHeight(52)
        capsule.setMaximumWidth(860)
        self._capsule = capsule
        row = QHBoxLayout(capsule)
        row.setContentsMargins(20, 0, 10, 0)
        row.setSpacing(12)
        outer.addStretch()
        outer.addWidget(capsule, stretch=1)
        outer.addStretch()

        self._dot = QLabel()
        self._dot.setObjectName("klaus-state-dot")
        self._dot.setFixedSize(8, 8)
        row.addWidget(self._dot)

        self._state_label = QLabel()
        self._state_label.setObjectName("klaus-state-label")
        row.addWidget(self._state_label)

        self._detail_label = QLabel()
        self._detail_label.setObjectName("klaus-state-detail")
        row.addWidget(self._detail_label)

        row.addStretch()

        self._stats_label = QLabel("0 answers")
        self._stats_label.setObjectName("klaus-stats")
        row.addWidget(self._stats_label)

        self._mode_btn = QPushButton()
        self._mode_btn.setObjectName("klaus-mode-btn")
        self._mode_btn.setFixedHeight(32)
        self._mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_btn.clicked.connect(self.mode_toggle_clicked.emit)
        row.addWidget(self._mode_btn)
        self._update_switch_hints()

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("klaus-stop-btn")
        self._stop_btn.setFixedHeight(32)
        self._stop_btn.setMinimumWidth(84)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.setToolTip("Stop this answer now")
        self._stop_btn.clicked.connect(self.stop_clicked.emit)
        self._stop_btn.setVisible(False)
        row.addWidget(self._stop_btn)

        self._apply_state("idle")

    def resizeEvent(self, event) -> None:
        self._apply_visibility()
        super().resizeEvent(event)

    def _apply_visibility(self) -> None:
        """Hide optional text, then the idle controls, before they clip."""
        width = self.width()
        busy = self._current_state in self._BUSY_STATES
        self._detail_label.setVisible(width >= 560)
        self._stats_label.setVisible(width >= 680 and not busy)
        self._mode_btn.setVisible(not busy)
        self._stop_btn.setVisible(busy)

    def _apply_state(self, state: str) -> None:
        entry = self._STATES.get(state, self._STATES["idle"])
        if isinstance(entry, dict):
            title, detail, color = entry.get(
                self._mode, ("Ready", "", theme.IDLE_COLOR)
            )
        else:
            title, detail, color = entry
        detail = detail.format(hotkey=self._hotkey, toggle=self._toggle_key)
        self._state_label.setText(title)
        self._detail_label.setText(detail)
        self._dot.setStyleSheet(f"background: {color}; border-radius: 4px;")

        busy = state in self._BUSY_STATES
        self._capsule.setProperty("dockState", "hot" if busy else "calm")
        style = self._capsule.style()
        style.unpolish(self._capsule)
        style.polish(self._capsule)
        self._apply_visibility()

    def set_state(self, state: str) -> None:
        """Update the state indicator."""
        self._current_state = state
        self._apply_state(state)

    def set_mode(self, mode: str) -> None:
        """Update the mode-switch action label and tooltips."""
        self._mode = mode
        self._update_switch_hints()
        self._apply_state(self._current_state)

    def set_exchange_count(self, count: int) -> None:
        """Update the session exchange count display."""
        label = "answer" if count == 1 else "answers"
        self._stats_label.setText(f"{count} {label}")

    def set_hotkeys(self, hotkey: str, toggle_key: str) -> None:
        """Update hotkey labels shown in the status bar."""
        self._hotkey = hotkey
        self._toggle_key = toggle_key
        self._update_switch_hints()
        self._apply_state(self._current_state)

    def _update_switch_hints(self) -> None:
        action = self._MODE_ACTIONS.get(self._mode, "Switch voice input mode")
        current = self._MODE_LABELS.get(self._mode, "Voice")
        self._mode_btn.setText(f"{self._toggle_key}  ·  {action}")
        tooltip = f"Current mode: {current}. Press {self._toggle_key} to {action.lower()}."
        self._mode_btn.setToolTip(tooltip)
