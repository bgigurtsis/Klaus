"""Bottom status bar showing state, mode toggle, hotkey hint, and session stats."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal

from klaus.ui import theme


class StatusWidget(QWidget):
    """Bottom status bar with state indicator, mode toggle, and session stats."""

    mode_toggle_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()

    _STATES = {
        "idle": {
            "push_to_talk": ("\u25cf Idle", theme.IDLE_COLOR),
            "voice_activation": ("\u25cf Ready", theme.SPEAKING_COLOR),
        },
        "listening": ("\u25cf Listening", theme.LISTENING_COLOR),
        "thinking": ("\u25cf Thinking", theme.THINKING_COLOR),
        "speaking": ("\u25cf Speaking", theme.SPEAKING_COLOR),
    }

    _MODE_LABELS = {
        "push_to_talk": "PTT",
        "voice_activation": "Voice",
    }

    _HOTKEY_HINTS = {
        "push_to_talk": "Hold {hotkey} to speak  \u00b7  F3 to switch",
        "voice_activation": "Just speak  \u00b7  F3 to switch mode",
    }

    def __init__(
        self,
        hotkey: str = "F2",
        mode: str = "voice_activation",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("klaus-status-bar")
        self._hotkey = hotkey
        self._mode = mode
        self._current_state = "idle"
        self._init_ui()

    def _init_ui(self) -> None:
        self.setFixedHeight(theme.STATUS_BAR_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        self._state_label = QLabel()
        self._state_label.setObjectName("klaus-state-label")
        self._apply_state_label("idle")
        layout.addWidget(self._state_label)

        self._mode_btn = QPushButton(self._MODE_LABELS.get(self._mode, "Voice"))
        self._mode_btn.setObjectName("klaus-mode-btn")
        self._mode_btn.setFixedHeight(24)
        self._mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mode_btn.clicked.connect(self.mode_toggle_clicked.emit)
        layout.addWidget(self._mode_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("klaus-stop-btn")
        self._stop_btn.setFixedHeight(24)
        self._stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._stop_btn.clicked.connect(self.stop_clicked.emit)
        self._stop_btn.setVisible(False)
        layout.addWidget(self._stop_btn)

        layout.addStretch()

        hint = self._HOTKEY_HINTS.get(self._mode, "").format(hotkey=self._hotkey)
        self._hotkey_label = QLabel(hint)
        self._hotkey_label.setObjectName("klaus-hotkey-hint")
        layout.addWidget(self._hotkey_label)

        layout.addStretch()

        self._stats_label = QLabel("0 Q&A")
        self._stats_label.setObjectName("klaus-stats")
        layout.addWidget(self._stats_label)

    def _apply_state_label(self, state: str) -> None:
        entry = self._STATES.get(state, self._STATES["idle"])
        if isinstance(entry, dict):
            text, color = entry.get(self._mode, ("\u25cf Idle", theme.IDLE_COLOR))
        else:
            text, color = entry
        self._state_label.setText(text)
        # Dynamic color -- must stay as inline setStyleSheet
        self._state_label.setStyleSheet(
            f"color: {color}; font-size: {theme.FONT_SIZE_SMALL}px; font-weight: bold;"
        )

    def set_state(self, state: str) -> None:
        """Update the state indicator."""
        self._current_state = state
        self._apply_state_label(state)
        self._stop_btn.setVisible(state == "speaking")

    def set_mode(self, mode: str) -> None:
        """Update the mode button label and hotkey hint."""
        self._mode = mode
        self._mode_btn.setText(self._MODE_LABELS.get(mode, "Voice"))
        hint = self._HOTKEY_HINTS.get(mode, "").format(hotkey=self._hotkey)
        self._hotkey_label.setText(hint)
        self._apply_state_label(self._current_state)

    def set_exchange_count(self, count: int) -> None:
        """Update the session exchange count display."""
        self._stats_label.setText(f"{count} Q&A this session")
