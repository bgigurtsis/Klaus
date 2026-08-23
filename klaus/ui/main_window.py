"""Klaus main application window."""

from __future__ import annotations

import logging

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
)
from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent

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

_QT_SHIFTED_VARIANTS: dict[int, int] = {
    ord("±"): ord("§"),
}


def resolve_qt_key(key_name: str) -> int:
    """Map a config key name (e.g. ``'F2'``) to a ``Qt.Key`` value."""
    lower = key_name.lower()
    if lower in _QT_KEY_MAP:
        return _QT_KEY_MAP[lower]
    if len(key_name) == 1:
        return ord(key_name.upper())
    raise ValueError(f"Unknown hotkey for Qt: {key_name!r}")


def hotkey_action_for_keypress(
    *,
    key: int,
    shift_pressed: bool,
    ptt_key: int,
    toggle_key: int,
) -> str | None:
    """Return ``ptt_down``, ``toggle``, or ``None`` for a key press."""
    effective_key = _QT_SHIFTED_VARIANTS.get(key, key) if shift_pressed else key

    if effective_key != ptt_key and effective_key != toggle_key:
        return None

    if ptt_key == toggle_key and effective_key == ptt_key:
        return "toggle" if shift_pressed else "ptt_down"

    if effective_key == toggle_key:
        return "toggle"
    if effective_key == ptt_key:
        return "ptt_down"
    return None


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
        self._ptt_key_armed = False
        self.setWindowTitle("Klaus")
        self.setMinimumSize(980, 640)
        self.resize(1180, 760)

        self.setStyleSheet(theme.application_stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # -- Codex-style shell: persistent sidebar + focused thread --
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel: camera + session list
        left_panel = QWidget()
        left_panel.setObjectName("klaus-sidebar")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(14)

        identity_row = QHBoxLayout()
        identity_row.setContentsMargins(2, 0, 0, 0)
        identity_row.setSpacing(9)

        brand_mark = QLabel("K")
        brand_mark.setObjectName("klaus-brand-mark")
        brand_mark.setFixedSize(32, 32)
        brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        identity_row.addWidget(brand_mark)

        title = QLabel("Klaus")
        title.setObjectName("klaus-title")
        identity_row.addWidget(title)
        identity_row.addStretch()

        settings_btn = QPushButton("\u2699")
        settings_btn.setObjectName("klaus-settings-btn")
        settings_btn.setFixedSize(32, 32)
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setToolTip("Settings")
        settings_btn.clicked.connect(self.settings_requested.emit)
        identity_row.addWidget(settings_btn)
        left_layout.addLayout(identity_row)

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

        # Right panel: active thread + voice composer
        right_panel = QWidget()
        right_panel.setObjectName("klaus-thread")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        thread_header = QWidget()
        thread_header.setObjectName("klaus-header")
        thread_header.setFixedHeight(theme.HEADER_HEIGHT)
        thread_header_layout = QHBoxLayout(thread_header)
        thread_header_layout.setContentsMargins(24, 0, 22, 0)

        self._session_title_label = QLabel("Untitled reading session")
        self._session_title_label.setObjectName("klaus-session-title")
        thread_header_layout.addWidget(self._session_title_label)
        thread_header_layout.addStretch()

        model_name = "GPT Realtime" if config.VOICE_ENGINE == "realtime" else "Legacy voice"
        model_pill = QLabel(model_name)
        model_pill.setObjectName("klaus-model-pill")
        model_pill.setToolTip(
            config.REALTIME_MODEL if config.VOICE_ENGINE == "realtime" else "Claude + OpenAI TTS"
        )
        model_pill.setFixedHeight(28)
        thread_header_layout.addWidget(model_pill)
        right_layout.addWidget(thread_header)

        self.chat_widget = ChatWidget()
        self.chat_widget.replay_requested.connect(self.replay_requested.emit)
        right_layout.addWidget(self.chat_widget, stretch=1)

        self.status_widget = StatusWidget(
            hotkey=config.PUSH_TO_TALK_KEY,
            toggle_key=config.TOGGLE_KEY,
        )
        self.status_widget.mode_toggle_clicked.connect(
            self.mode_toggle_requested.emit
        )
        self.status_widget.stop_clicked.connect(self.stop_requested.emit)
        right_layout.addWidget(self.status_widget)

        splitter.addWidget(right_panel)

        splitter.setSizes([318, 862])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter, stretch=1)

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

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
        return self.session_panel.current_id

    # -- In-app keyboard shortcuts (no Accessibility permission needed) --

    def set_hotkeys(self, ptt_key: str, toggle_key: str) -> None:
        """Configure which keys trigger PTT and mode toggle via Qt events."""
        self._qt_ptt_key = resolve_qt_key(ptt_key)
        self._qt_toggle_key = resolve_qt_key(toggle_key)
        self._ptt_key_armed = False
        toggle_hint = toggle_key
        if ptt_key == toggle_key and len(toggle_key) == 1:
            toggle_hint = f"Shift+{toggle_key}"
        self.status_widget.set_hotkeys(ptt_key, toggle_hint)
        logger.info(
            "Qt in-app hotkeys configured (ptt=%s, toggle=%s)", ptt_key, toggle_key,
        )

    def _handle_hotkey_press(self, event: QKeyEvent) -> bool:
        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        action = hotkey_action_for_keypress(
            key=key,
            shift_pressed=shift,
            ptt_key=self._qt_ptt_key,
            toggle_key=self._qt_toggle_key,
        )
        if action is None:
            return False
        if event.isAutoRepeat():
            return True
        if action == "ptt_down":
            self._ptt_key_armed = True
            self.ptt_key_pressed.emit()
        else:
            self._ptt_key_armed = False
            self.toggle_key_pressed.emit()
        return True

    def _handle_hotkey_release(self, event: QKeyEvent) -> bool:
        key = _QT_SHIFTED_VARIANTS.get(event.key(), event.key())
        is_hotkey = key in {self._qt_ptt_key, self._qt_toggle_key}
        if not is_hotkey:
            return False
        if event.isAutoRepeat():
            return True
        if key == self._qt_ptt_key and self._ptt_key_armed:
            self._ptt_key_armed = False
            self.ptt_key_released.emit()
        return True

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Catch hotkeys before a focused child widget can consume them."""
        if (
            isinstance(watched, QWidget)
            and watched.window() is self
            and isinstance(event, QKeyEvent)
        ):
            if event.type() == QEvent.Type.KeyPress:
                return self._handle_hotkey_press(event)
            if event.type() == QEvent.Type.KeyRelease:
                return self._handle_hotkey_release(event)
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._handle_hotkey_press(event):
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if not self._handle_hotkey_release(event):
            super().keyReleaseEvent(event)
