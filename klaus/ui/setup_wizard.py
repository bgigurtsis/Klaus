"""First-run setup wizard for Klaus.

Walks users through API key entry, camera selection, microphone test, and
voice-model download. Shown on first launch; skipped once ``setup_complete``
is ``true`` in ``~/.klaus/config.toml``.
"""

from __future__ import annotations

import logging

import cv2
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QDesktopServices, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import klaus.config as config
from klaus.device_catalog import (
    format_camera_label,
    format_mic_label,
    list_camera_devices,
    list_input_devices,
)
from klaus.ui import theme
from klaus.ui.shared.key_validation import KEY_PATTERNS, KEY_URLS, validate_api_key
from klaus.ui.shared.mic_level_monitor import MicLevelMonitor

logger = logging.getLogger(__name__)

STEP_TITLES = ["Welcome", "API Keys", "Camera", "Microphone", "Voice Model", "About You", "Done"]
NUM_STEPS = len(STEP_TITLES)

# ---------------------------------------------------------------------------
# Step indicator (row of dots)
# ---------------------------------------------------------------------------

class _StepIndicator(QWidget):
    """Row of dots showing which setup step is active."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dots: list[QLabel] = []
        for i in range(NUM_STEPS):
            dot = QLabel("\u25cf")
            dot.setObjectName("wizard-dot")
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            dot.setFixedSize(18, 18)
            self._dots.append(dot)
            layout.addWidget(dot)
        self.set_step(0)

    def set_step(self, index: int) -> None:
        for i, dot in enumerate(self._dots):
            if i < index:
                dot.setStyleSheet(f"color: {theme.KLAUS_ACCENT}; font-size: 12px;")
            elif i == index:
                dot.setStyleSheet(f"color: {theme.USER_ACCENT}; font-size: 16px;")
            else:
                dot.setStyleSheet(f"color: {theme.TEXT_MUTED}; font-size: 12px;")


# ---------------------------------------------------------------------------
# Model download thread
# ---------------------------------------------------------------------------

class _ModelDownloadThread(QThread):
    """Downloads the Moonshine STT model in a background thread."""
    finished = pyqtSignal(bool, str)  # success, error_message

    def __init__(self, language: str):
        super().__init__()
        self._language = language

    def run(self) -> None:
        try:
            from moonshine_voice import get_model_for_language
            get_model_for_language(self._language)
            self.finished.emit(True, "")
        except Exception as exc:
            self.finished.emit(False, str(exc))


# ---------------------------------------------------------------------------
# Camera preview helper
# ---------------------------------------------------------------------------

class _CameraPreview(QWidget):
    """Small live preview of a camera, used during setup."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setFixedSize(320, 240)
        self._label.setStyleSheet(
            f"background: {theme.SURFACE}; border: 1px solid {theme.BORDER_MUTED}; "
            f"border-radius: 8px; color: {theme.TEXT_MUTED};"
        )
        self._label.setText("No preview")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label, alignment=Qt.AlignmentFlag.AlignCenter)

        self._cap: cv2.VideoCapture | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_frame)
        self._backend = cv2.CAP_DSHOW if __import__("sys").platform == "win32" else cv2.CAP_ANY

    def start(self, device_index: int) -> None:
        self.stop()
        self._cap = cv2.VideoCapture(device_index, self._backend)
        if self._cap.isOpened():
            self._timer.start(66)
        else:
            self._label.setText("Cannot open camera")
            self._cap.release()
            self._cap = None

    def stop(self) -> None:
        self._timer.stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._label.clear()
        self._label.setText("No preview")

    def _update_frame(self) -> None:
        if self._cap is None:
            return
        ret, frame = self._cap.read()
        if not ret:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        scale = min(320 / w, 240 / h)
        new_w, new_h = int(w * scale), int(h * scale)
        rgb = cv2.resize(rgb, (new_w, new_h))
        img = QImage(rgb.data, new_w, new_h, new_w * ch, QImage.Format.Format_RGB888)
        self._label.setPixmap(QPixmap.fromImage(img))


# ---------------------------------------------------------------------------
# Main wizard window
# ---------------------------------------------------------------------------

class SetupWizard(QMainWindow):
    """First-run setup wizard shown before the main Klaus window."""

    setup_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Klaus Setup")
        self.setMinimumSize(640, 520)
        self.resize(700, 560)
        self.setStyleSheet(theme.application_stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._indicator = _StepIndicator()
        root.addWidget(self._indicator)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, stretch=1)

        self._nav = QWidget()
        nav_layout = QHBoxLayout(self._nav)
        nav_layout.setContentsMargins(24, 8, 24, 16)
        self._back_btn = QPushButton("Back")
        self._back_btn.setObjectName("wizard-back-btn")
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn = QPushButton("Next")
        self._next_btn.setObjectName("wizard-next-btn")
        self._next_btn.clicked.connect(self._go_next)
        nav_layout.addWidget(self._back_btn)
        nav_layout.addStretch()
        nav_layout.addWidget(self._next_btn)
        root.addWidget(self._nav)

        self._collected: dict = {
            "anthropic": "",
            "openai": "",
            "tavily": "",
            "camera_index": -1,
            "mic_index": -1,
            "user_background": "",
            "obsidian_vault_path": "",
        }

        self._build_step_welcome()
        self._build_step_api_keys()
        self._build_step_camera()
        self._build_step_mic()
        self._build_step_model()
        self._build_step_about_you()
        self._build_step_done()

        self._set_step(0)

    # -- Navigation --

    def _set_step(self, index: int) -> None:
        self._current_step = index
        self._stack.setCurrentIndex(index)
        self._indicator.set_step(index)
        self._back_btn.setVisible(index > 0 and index < NUM_STEPS - 1)
        self._next_btn.setVisible(index < NUM_STEPS - 1)
        if index == 0:
            self._next_btn.setVisible(False)
            self._back_btn.setVisible(False)
        self._update_next_enabled()

        if index == 2:
            self._populate_cameras()
        elif index == 3:
            self._populate_mics()
            self._start_mic_meter()
        elif index == 4:
            self._start_model_download()

    def _go_next(self) -> None:
        if self._current_step == 3:
            self._stop_mic_meter()
        if self._current_step == 2:
            self._camera_preview.stop()
        if self._current_step == 5:
            self._collected["user_background"] = self._background_edit.toPlainText().strip()
            self._collected["obsidian_vault_path"] = self._vault_path_edit.text().strip()
        self._set_step(self._current_step + 1)

    def _go_back(self) -> None:
        if self._current_step == 3:
            self._stop_mic_meter()
        if self._current_step == 2:
            self._camera_preview.stop()
        self._set_step(self._current_step - 1)

    def _update_next_enabled(self) -> None:
        if self._current_step == 1:
            all_valid = all(
                self._key_valid.get(slug, False) for _, slug, _, _ in KEY_PATTERNS
            )
            self._next_btn.setEnabled(all_valid)
        else:
            self._next_btn.setEnabled(True)

    def closeEvent(self, event) -> None:
        self._camera_preview.stop()
        self._stop_mic_meter()
        super().closeEvent(event)

    # -----------------------------------------------------------------------
    # Step 1 -- Welcome
    # -----------------------------------------------------------------------

    def _build_step_welcome(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 22, 36, 20)
        layout.setSpacing(12)

        title = QLabel("Welcome to Klaus")
        title.setObjectName("wizard-welcome-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(
            "Ask questions out loud while you read. Klaus captures the page context when you "
            "finish speaking, uses Claude to answer your question, and speaks the answer back to you concisely."
        )
        subtitle.setObjectName("wizard-welcome-subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        card_specs = [
            (
                "How It Works",
                "Ask Klaus questions about what you're reading. It uses a local STT model "
                "to parse what you're saying, combined with the picture of the page "
                "to provide context to Claude.",
            ),
            (
                "Getting Better Answers",
                "By default Klaus is very concise and to the point. It is designed, "
                "so you can ask follow up questions quikcly. If you want more detail "
                "say so or reference the part you want explained.",
            ),
            (
                "Tool use",
                "Optionally connect your Obsidian vault and ask Klaus to save notes "
                "directly to your vault while you browse. Klaus will also search "
                "the web using Tavily verify its response. ",
            ),
        ]

        cards_col = QVBoxLayout()
        cards_col.setContentsMargins(0, 2, 0, 0)
        cards_col.setSpacing(12)
        for card_title, card_body in card_specs:
            cards_col.addWidget(self._build_welcome_card(card_title, card_body))
        layout.addLayout(cards_col)

        footer = QLabel("You can change any setup choices later in Settings.")
        footer.setObjectName("wizard-welcome-footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)

        layout.addSpacing(6)

        btn = QPushButton("Get Started")
        btn.setObjectName("wizard-primary-btn")
        btn.setFixedWidth(200)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self._set_step(1))
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

        self._stack.addWidget(page)

    def _build_welcome_card(self, title: str, body: str) -> QWidget:
        card = QWidget()
        card.setObjectName("wizard-welcome-card")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("wizard-welcome-card-title")
        title_label.setWordWrap(True)
        card_layout.addWidget(title_label)

        body_label = QLabel(body)
        body_label.setObjectName("wizard-welcome-card-body")
        body_label.setWordWrap(True)
        card_layout.addWidget(body_label)

        card_layout.addStretch(1)
        return card

    # -----------------------------------------------------------------------
    # Step 2 -- API Keys
    # -----------------------------------------------------------------------

    def _build_step_api_keys(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 24, 48, 16)
        layout.setSpacing(8)

        heading = QLabel("Enter your API keys")
        heading.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {theme.TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        layout.addWidget(heading)
        layout.addSpacing(8)

        self._key_edits: dict[str, QLineEdit] = {}
        self._key_indicators: dict[str, QLabel] = {}
        self._key_hints: dict[str, QLabel] = {}
        self._key_valid: dict[str, bool] = {}

        for label, slug, prefix, min_len in KEY_PATTERNS:
            row = QHBoxLayout()
            row.setSpacing(8)

            name = QLabel(label)
            name.setFixedWidth(90)
            name.setStyleSheet(
                f"color: {theme.TEXT_SECONDARY}; font-weight: 600; "
                "background: transparent; border: none;"
            )
            row.addWidget(name)

            edit = QLineEdit()
            edit.setPlaceholderText(f"{prefix}...")
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            edit.setMinimumWidth(300)
            edit.textChanged.connect(lambda _, s=slug: self._validate_key(s))
            self._key_edits[slug] = edit
            row.addWidget(edit, stretch=1)

            indicator = QLabel("")
            indicator.setFixedWidth(24)
            indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
            indicator.setStyleSheet("background: transparent; border: none;")
            self._key_indicators[slug] = indicator
            row.addWidget(indicator)

            link = QPushButton("Get a key")
            link.setObjectName("wizard-link-btn")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.setFixedWidth(80)
            url = KEY_URLS[slug]
            link.clicked.connect(
                lambda _, u=url: QDesktopServices.openUrl(
                    __import__("PyQt6.QtCore", fromlist=["QUrl"]).QUrl(u)
                )
            )
            row.addWidget(link)

            layout.addLayout(row)

            hint = QLabel("")
            hint.setStyleSheet(
                f"color: {theme.ERROR_COLOR}; font-size: {theme.FONT_SIZE_CAPTION}px; "
                "background: transparent; border: none; padding-left: 98px;"
            )
            hint.setVisible(False)
            self._key_hints[slug] = hint
            layout.addWidget(hint)
            self._key_valid[slug] = False

        layout.addStretch()

        footer = QLabel(
            "Your keys are stored locally in ~/.klaus/config.toml\n"
            "and never leave your machine."
        )
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(footer)

        self._stack.addWidget(page)

    def _validate_key(self, slug: str) -> None:
        text = self._key_edits[slug].text().strip()
        indicator = self._key_indicators[slug]
        hint = self._key_hints[slug]

        if not text:
            indicator.setText("")
            hint.setVisible(False)
            self._key_valid[slug] = False
            self._update_next_enabled()
            return

        is_valid, message = validate_api_key(slug, text)
        if not is_valid:
            indicator.setText("\u2717")
            indicator.setStyleSheet(
                f"color: {theme.ERROR_COLOR}; font-size: 18px; "
                "background: transparent; border: none;"
            )
            hint.setText(message)
            hint.setVisible(bool(message))
            self._key_valid[slug] = False
        else:
            indicator.setText("\u2713")
            indicator.setStyleSheet(
                f"color: {theme.KLAUS_ACCENT}; font-size: 18px; "
                "background: transparent; border: none;"
            )
            hint.setVisible(False)
            self._key_valid[slug] = True
            self._collected[slug] = text

        self._update_next_enabled()

    # -----------------------------------------------------------------------
    # Step 3 -- Camera
    # -----------------------------------------------------------------------

    def _build_step_camera(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 24, 48, 16)
        layout.setSpacing(12)

        heading = QLabel("Select your camera")
        heading.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {theme.TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        layout.addWidget(heading)

        self._camera_combo = QComboBox()
        self._camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        layout.addWidget(self._camera_combo)

        self._camera_preview = _CameraPreview()
        layout.addWidget(self._camera_preview, alignment=Qt.AlignmentFlag.AlignCenter)

        tip = QLabel(
            "For best results, position your camera above your reading area\n"
            "pointing down. A phone on a tripod works well."
        )
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(tip)
        layout.addStretch()

        self._stack.addWidget(page)

    def _populate_cameras(self) -> None:
        self._camera_combo.blockSignals(True)
        self._camera_combo.clear()
        self._camera_combo.addItem("No camera (audio only)", -1)
        cameras = list_camera_devices()
        for cam in cameras:
            self._camera_combo.addItem(format_camera_label(cam), cam.index)
        if cameras:
            self._camera_combo.setCurrentIndex(1)
        self._camera_combo.blockSignals(False)
        self._on_camera_changed()

    def _on_camera_changed(self) -> None:
        idx = self._camera_combo.currentData()
        if idx is None:
            idx = -1
        self._collected["camera_index"] = idx
        if idx >= 0:
            self._camera_preview.start(idx)
        else:
            self._camera_preview.stop()

    # -----------------------------------------------------------------------
    # Step 4 -- Microphone
    # -----------------------------------------------------------------------

    def _build_step_mic(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 24, 48, 16)
        layout.setSpacing(12)

        heading = QLabel("Test your microphone")
        heading.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {theme.TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        layout.addWidget(heading)

        self._mic_combo = QComboBox()
        self._mic_combo.currentIndexChanged.connect(self._on_mic_changed)
        layout.addWidget(self._mic_combo)

        meter_label = QLabel("Volume level")
        meter_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_SMALL}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(meter_label)

        self._mic_meter = QProgressBar()
        self._mic_meter.setObjectName("wizard-mic-meter")
        self._mic_meter.setRange(0, 100)
        self._mic_meter.setValue(0)
        self._mic_meter.setTextVisible(False)
        self._mic_meter.setFixedHeight(20)
        layout.addWidget(self._mic_meter)

        hint = QLabel("Speak to see the meter respond. This confirms your mic is working.")
        hint.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(hint)

        layout.addStretch()
        self._stack.addWidget(page)

        self._mic_monitor = MicLevelMonitor()
        self._mic_timer = QTimer(self)
        self._mic_timer.timeout.connect(self._update_mic_meter)

    def _populate_mics(self) -> None:
        self._mic_combo.blockSignals(True)
        self._mic_combo.clear()
        self._mic_combo.addItem("System default microphone", -1)
        for mic in list_input_devices():
            self._mic_combo.addItem(format_mic_label(mic), mic.index)
        selected_device = int(self._collected.get("mic_index", config.MIC_DEVICE_INDEX))
        selected = 0
        if selected_device >= 0:
            for i in range(self._mic_combo.count()):
                if self._mic_combo.itemData(i) == selected_device:
                    selected = i
                    break
        self._mic_combo.setCurrentIndex(selected)
        self._mic_combo.blockSignals(False)
        self._collected["mic_index"] = self._mic_combo.currentData() or -1

    def _selected_mic_device(self) -> int | None:
        mic_idx = self._mic_combo.currentData()
        if mic_idx is None:
            return None
        mic_idx = int(mic_idx)
        if mic_idx < 0:
            return None
        return mic_idx

    def _on_mic_changed(self) -> None:
        mic_idx = self._mic_combo.currentData()
        if mic_idx is None:
            mic_idx = -1
        self._collected["mic_index"] = int(mic_idx)
        self._start_mic_meter()

    def _start_mic_meter(self) -> None:
        self._stop_mic_meter()
        device_idx = self._selected_mic_device()
        if self._mic_monitor.start(device_idx):
            self._mic_timer.start(50)

    def _stop_mic_meter(self) -> None:
        self._mic_timer.stop()
        self._mic_monitor.stop()

    def _update_mic_meter(self) -> None:
        self._mic_meter.setValue(self._mic_monitor.level_percent())

    # -----------------------------------------------------------------------
    # Step 5 -- Voice model download
    # -----------------------------------------------------------------------

    def _build_step_model(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 24, 48, 16)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        heading = QLabel("Voice recognition model")
        heading.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {theme.TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)

        self._model_info = QLabel(
            "Klaus needs to download a speech recognition model (~245 MB).\n"
            "This is a one-time download."
        )
        self._model_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._model_info.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_BODY}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self._model_info)

        self._model_progress = QProgressBar()
        self._model_progress.setObjectName("wizard-model-progress")
        self._model_progress.setRange(0, 0)
        self._model_progress.setFixedWidth(400)
        self._model_progress.setFixedHeight(20)
        layout.addWidget(self._model_progress, alignment=Qt.AlignmentFlag.AlignCenter)

        self._model_status = QLabel("")
        self._model_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._model_status.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self._model_status)

        self._model_retry_btn = QPushButton("Retry")
        self._model_retry_btn.setObjectName("wizard-primary-btn")
        self._model_retry_btn.setFixedWidth(120)
        self._model_retry_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model_retry_btn.clicked.connect(self._start_model_download)
        self._model_retry_btn.setVisible(False)
        layout.addWidget(self._model_retry_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        self._stack.addWidget(page)
        self._download_thread: _ModelDownloadThread | None = None

    def _start_model_download(self) -> None:
        self._model_retry_btn.setVisible(False)
        self._model_progress.setRange(0, 0)
        self._model_status.setText("Downloading...")
        self._model_status.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none;"
        )
        self._next_btn.setVisible(False)

        from klaus.config import STT_MOONSHINE_LANGUAGE
        self._download_thread = _ModelDownloadThread(STT_MOONSHINE_LANGUAGE)
        self._download_thread.finished.connect(self._on_model_download_done)
        self._download_thread.start()

    def _on_model_download_done(self, success: bool, error: str) -> None:
        if success:
            self._model_progress.setRange(0, 1)
            self._model_progress.setValue(1)
            self._model_status.setText("Model ready")
            self._model_status.setStyleSheet(
                f"color: {theme.KLAUS_ACCENT}; font-size: {theme.FONT_SIZE_CAPTION}px; "
                "background: transparent; border: none;"
            )
            QTimer.singleShot(600, lambda: self._set_step(5))
        else:
            self._model_progress.setRange(0, 1)
            self._model_progress.setValue(0)
            self._model_status.setText(f"Download failed: {error}")
            self._model_status.setStyleSheet(
                f"color: {theme.ERROR_COLOR}; font-size: {theme.FONT_SIZE_CAPTION}px; "
                "background: transparent; border: none;"
            )
            self._model_retry_btn.setVisible(True)

    # -----------------------------------------------------------------------
    # Step 6 -- About You (optional)
    # -----------------------------------------------------------------------

    def _build_step_about_you(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 24, 48, 16)
        layout.setSpacing(12)

        heading = QLabel("Tell Klaus about yourself")
        heading.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {theme.TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        layout.addWidget(heading)

        subtitle = QLabel(
            "This helps Klaus tailor explanations to your background.\n"
            "You can skip this or change it later in settings."
        )
        subtitle.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_BODY}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(subtitle)

        layout.addSpacing(4)

        self._background_edit = QPlainTextEdit()
        self._background_edit.setPlaceholderText(
            "e.g. I'm a software engineer interested in physics and philosophy. "
            "I have a strong math background but I'm new to biology."
        )
        self._background_edit.setFixedHeight(100)
        layout.addWidget(self._background_edit)

        layout.addSpacing(12)

        vault_header = QHBoxLayout()
        vault_label = QLabel("Obsidian vault path")
        vault_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-weight: 600; "
            "background: transparent; border: none;"
        )
        vault_header.addWidget(vault_label)

        help_btn = QPushButton("?")
        help_btn.setFixedSize(18, 18)
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.setToolTip(
            "Set your vault root, then ask Klaus: "
            "\"Save this to Folder/Note.md\" and it will create/append the note."
        )
        help_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {theme.TEXT_SECONDARY}; "
            "border: none; padding: 0px; font-weight: bold; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {theme.KLAUS_ACCENT}; }}"
        )
        help_btn.clicked.connect(self._show_vault_help)
        vault_header.addWidget(help_btn)
        vault_header.addStretch()
        layout.addLayout(vault_header)

        vault_row = QHBoxLayout()
        self._vault_path_edit = QLineEdit()
        self._vault_path_edit.setReadOnly(True)
        self._vault_path_edit.setPlaceholderText("Optional — click Browse to select")
        vault_row.addWidget(self._vault_path_edit)

        browse_btn = QPushButton("Browse\u2026")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_vault_path)
        vault_row.addWidget(browse_btn)
        layout.addLayout(vault_row)

        skip_btn = QPushButton("Skip")
        skip_btn.setObjectName("wizard-link-btn")
        skip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        skip_btn.setFixedWidth(60)
        skip_btn.clicked.connect(lambda: self._set_step(NUM_STEPS - 1))
        layout.addWidget(skip_btn, alignment=Qt.AlignmentFlag.AlignRight)

        layout.addStretch()
        self._stack.addWidget(page)

    def _browse_vault_path(self) -> None:
        """Open a native folder picker for the Obsidian vault directory."""
        path = QFileDialog.getExistingDirectory(
            self, "Select Obsidian Vault Folder",
        )
        if path:
            self._vault_path_edit.setText(path)

    def _show_vault_help(self) -> None:
        """Show an informational dialog explaining the Obsidian vault setting."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Obsidian Notes")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            "Set this to your Obsidian vault root folder.\n\n"
            "Then ask Klaus to save to a file in a folder, for example:\n"
            "  \"Save this to Research/Agent Notes.md\"\n\n"
            "Klaus will create missing folders/files and append the note.\n\n"
            "Leave this blank if you do not use Obsidian."
        )
        msg.exec()

    # -----------------------------------------------------------------------
    # Step 7 -- Done
    # -----------------------------------------------------------------------

    def _build_step_done(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        heading = QLabel("You're all set.")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {theme.TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        layout.addWidget(heading)

        instructions = QLabel(
            "Just start speaking, or hold F2 to use push-to-talk.\n"
            "Press F3 to switch modes."
        )
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: {theme.FONT_SIZE_BODY}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(instructions)

        layout.addSpacing(24)

        btn = QPushButton("Start using Klaus")
        btn.setObjectName("wizard-primary-btn")
        btn.setFixedWidth(220)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._finish_setup)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._stack.addWidget(page)

    def _finish_setup(self) -> None:
        """Write all collected config and close the wizard."""
        import klaus.config as cfg
        cfg.save_api_keys(
            self._collected["anthropic"],
            self._collected["openai"],
            self._collected["tavily"],
        )
        cam_idx = self._collected["camera_index"]
        if cam_idx >= 0:
            cfg.save_camera_index(cam_idx)
        mic_idx = int(self._collected.get("mic_index", -1))
        cfg.save_mic_index(mic_idx)
        bg = self._collected.get("user_background", "")
        if bg:
            cfg.save_user_background(bg)
        vault = self._collected.get("obsidian_vault_path", "")
        if vault:
            cfg.save_obsidian_vault_path(vault)
        cfg.mark_setup_complete()
        cfg.reload()
        logger.info("Setup wizard completed")
        QApplication.instance().quit()
