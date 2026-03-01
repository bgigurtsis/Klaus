"""Settings dialog for changing API keys, camera, and microphone after setup."""

from __future__ import annotations

import logging
import threading

import numpy as np
import sounddevice as sd
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

import klaus.config as config
from klaus.ui import theme

logger = logging.getLogger(__name__)

_KEY_PATTERNS: list[tuple[str, str, str, int]] = [
    ("Anthropic", "anthropic", "sk-ant-", 40),
    ("OpenAI", "openai", "sk-", 20),
    ("Tavily", "tavily", "tvly-", 20),
]


class SettingsDialog(QDialog):
    """Tabbed settings dialog accessible from the main window gear button."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(520, 380)
        self.resize(560, 420)
        self.setStyleSheet(theme.application_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        tabs = QTabWidget()
        tabs.addTab(self._build_keys_tab(), "API Keys")
        tabs.addTab(self._build_camera_tab(), "Camera")
        tabs.addTab(self._build_mic_tab(), "Microphone")
        tabs.addTab(self._build_profile_tab(), "Profile")
        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("Save")
        save_btn.setObjectName("wizard-primary-btn")
        save_btn.setFixedWidth(100)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        self._mic_stream: sd.InputStream | None = None
        self._mic_rms: float = 0.0
        self._mic_lock = threading.Lock()
        self._mic_timer = QTimer(self)
        self._mic_timer.timeout.connect(self._update_mic_meter)

    # -- API Keys tab --

    def _build_keys_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._key_edits: dict[str, QLineEdit] = {}
        self._key_indicators: dict[str, QLabel] = {}

        current_keys = {
            "anthropic": config.ANTHROPIC_API_KEY,
            "openai": config.OPENAI_API_KEY,
            "tavily": config.TAVILY_API_KEY,
        }

        for label, slug, prefix, min_len in _KEY_PATTERNS:
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
            if current_keys.get(slug):
                edit.setText(current_keys[slug])
            edit.textChanged.connect(lambda _, s=slug: self._validate_key(s))
            self._key_edits[slug] = edit
            row.addWidget(edit, stretch=1)

            indicator = QLabel("")
            indicator.setFixedWidth(24)
            indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
            indicator.setStyleSheet("background: transparent; border: none;")
            self._key_indicators[slug] = indicator
            row.addWidget(indicator)

            layout.addLayout(row)

        for slug in self._key_edits:
            self._validate_key(slug)

        layout.addStretch()
        return page

    def _validate_key(self, slug: str) -> None:
        text = self._key_edits[slug].text().strip()
        indicator = self._key_indicators[slug]
        if not text:
            indicator.setText("")
            return
        for _, s, prefix, min_len in _KEY_PATTERNS:
            if s != slug:
                continue
            if text.startswith(prefix) and len(text) >= min_len:
                indicator.setText("\u2713")
                indicator.setStyleSheet(
                    f"color: {theme.KLAUS_ACCENT}; font-size: 18px; "
                    "background: transparent; border: none;"
                )
            else:
                indicator.setText("\u2717")
                indicator.setStyleSheet(
                    f"color: {theme.ERROR_COLOR}; font-size: 18px; "
                    "background: transparent; border: none;"
                )
            break

    # -- Camera tab --

    def _build_camera_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Camera device"))

        self._camera_combo = QComboBox()
        layout.addWidget(self._camera_combo)

        from klaus.camera import enumerate_cameras
        self._camera_combo.addItem("No camera (audio only)", -1)
        try:
            cameras = enumerate_cameras()
        except Exception as exc:
            logger.warning("Failed to enumerate cameras: %s", exc)
            cameras = []
        selected = 0
        for cam in cameras:
            self._camera_combo.addItem(
                f"{cam['name']}  ({cam['width']}x{cam['height']})",
                cam["index"],
            )
            if cam["index"] == config.CAMERA_DEVICE_INDEX:
                selected = self._camera_combo.count() - 1
        if selected:
            self._camera_combo.setCurrentIndex(selected)

        layout.addStretch()
        return page

    # -- Profile tab --

    def _build_profile_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        label = QLabel("Your background")
        label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-weight: 600; "
            "background: transparent; border: none;"
        )
        layout.addWidget(label)

        hint = QLabel(
            "Describe your expertise and interests so Klaus can tailor explanations."
        )
        hint.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(hint)

        self._background_edit = QPlainTextEdit()
        self._background_edit.setPlaceholderText(
            "e.g. I'm a software engineer interested in physics and philosophy. "
            "I have a strong math background but I'm new to biology."
        )
        self._background_edit.setFixedHeight(100)
        if config.USER_BACKGROUND:
            self._background_edit.setPlainText(config.USER_BACKGROUND)
        layout.addWidget(self._background_edit)

        layout.addSpacing(8)

        vault_header = QHBoxLayout()
        vault_label = QLabel("Obsidian vault path")
        vault_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-weight: 600; "
            "background: transparent; border: none;"
        )
        vault_header.addWidget(vault_label)

        help_btn = QPushButton("?")
        help_btn.setFixedSize(22, 22)
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.setStyleSheet(
            f"QPushButton {{ background: {theme.SURFACE_OVERLAY}; "
            f"color: {theme.TEXT_SECONDARY}; border: 1px solid {theme.BORDER_DEFAULT}; "
            "border-radius: 11px; font-weight: bold; font-size: 13px; }}"
            f"QPushButton:hover {{ background: {theme.KLAUS_ACCENT}; color: {theme.TEXT_PRIMARY}; }}"
        )
        help_btn.clicked.connect(self._show_vault_help)
        vault_header.addWidget(help_btn)
        vault_header.addStretch()
        layout.addLayout(vault_header)

        vault_row = QHBoxLayout()
        self._vault_path_edit = QLineEdit()
        self._vault_path_edit.setReadOnly(True)
        self._vault_path_edit.setPlaceholderText("Not set — click Browse to select")
        if config.OBSIDIAN_VAULT_PATH:
            self._vault_path_edit.setText(config.OBSIDIAN_VAULT_PATH)
        vault_row.addWidget(self._vault_path_edit)

        browse_btn = QPushButton("Browse\u2026")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_vault_path)
        vault_row.addWidget(browse_btn)
        layout.addLayout(vault_row)

        layout.addStretch()
        return page

    def _browse_vault_path(self) -> None:
        """Open a native folder picker for the Obsidian vault directory."""
        start = self._vault_path_edit.text() or ""
        path = QFileDialog.getExistingDirectory(self, "Select Obsidian Vault Folder", start)
        if path:
            self._vault_path_edit.setText(path)

    def _show_vault_help(self) -> None:
        """Show an informational dialog explaining the Obsidian vault setting."""
        msg = QMessageBox(self)
        msg.setWindowTitle("Obsidian Notes")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(
            "Obsidian is a free app for writing and organising markdown notes "
            "locally on your computer.\n\n"
            "If you use Obsidian, Klaus can save notes, quotes, and summaries "
            "directly into your vault while you read.\n\n"
            "To find your vault folder:\n"
            "  \u2022  Open Obsidian\n"
            "  \u2022  Go to Settings \u2192 About (at the bottom)\n"
            "  \u2022  Look for the vault path listed there\n\n"
            "This is entirely optional. If you don't use Obsidian or don't "
            "want note-taking, just leave this blank."
        )
        msg.exec()

    # -- Microphone tab --

    def _build_mic_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Input device"))

        self._mic_combo = QComboBox()
        layout.addWidget(self._mic_combo)

        try:
            devices = sd.query_devices()
            selected_mic = 0
            for i, dev in enumerate(devices):
                if dev["max_input_channels"] > 0:
                    self._mic_combo.addItem(dev["name"], i)
                    if i == config.MIC_DEVICE_INDEX:
                        selected_mic = self._mic_combo.count() - 1
            if selected_mic:
                self._mic_combo.setCurrentIndex(selected_mic)
        except Exception as exc:
            logger.warning("Failed to enumerate audio devices: %s", exc)

        self._mic_meter = QProgressBar()
        self._mic_meter.setObjectName("wizard-mic-meter")
        self._mic_meter.setRange(0, 100)
        self._mic_meter.setValue(0)
        self._mic_meter.setTextVisible(False)
        self._mic_meter.setFixedHeight(20)
        layout.addWidget(QLabel("Volume level"))
        layout.addWidget(self._mic_meter)

        layout.addStretch()
        return page

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._start_mic()

    def closeEvent(self, event) -> None:
        self._stop_mic()
        super().closeEvent(event)

    def _start_mic(self) -> None:
        self._stop_mic()
        device_idx = self._mic_combo.currentData()

        def callback(indata, frames, time_info, status):
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            with self._mic_lock:
                self._mic_rms = rms

        try:
            self._mic_stream = sd.InputStream(
                samplerate=16000, channels=1, dtype="int16",
                device=device_idx, callback=callback,
            )
            self._mic_stream.start()
            self._mic_timer.start(50)
        except Exception as exc:
            logger.warning("Failed to open mic: %s", exc)

    def _stop_mic(self) -> None:
        self._mic_timer.stop()
        if self._mic_stream is not None:
            try:
                self._mic_stream.stop()
                self._mic_stream.close()
            except Exception:
                pass
            self._mic_stream = None

    def _update_mic_meter(self) -> None:
        with self._mic_lock:
            rms = self._mic_rms
        level = min(int(rms / 32768 * 800), 100)
        self._mic_meter.setValue(level)

    # -- Save --

    def _save(self) -> None:
        config.save_api_keys(
            self._key_edits["anthropic"].text().strip(),
            self._key_edits["openai"].text().strip(),
            self._key_edits["tavily"].text().strip(),
        )
        cam_idx = self._camera_combo.currentData()
        if cam_idx is not None and cam_idx >= 0:
            config.save_camera_index(cam_idx)
        mic_idx = self._mic_combo.currentData()
        if mic_idx is not None:
            config.save_mic_index(mic_idx)
        bg = self._background_edit.toPlainText().strip()
        config.save_user_background(bg)
        vault = self._vault_path_edit.text().strip()
        config.save_obsidian_vault_path(vault)
        config.reload()
        logger.info("Settings saved")
        self._stop_mic()
        self.accept()
