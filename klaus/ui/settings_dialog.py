"""Settings dialog for API keys, reading source, microphone, and profile."""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
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
from klaus.ui.shared.key_validation import (
    KEY_PATTERNS,
    validate_api_key,
)
from klaus.ui.shared.mic_level_monitor import MicLevelMonitor
from klaus.ui.remarkable_pairing import open_remarkable_pairing
from klaus.reading_source import REMARKABLE_PAPER_PURE_SOURCE_INDEX

logger = logging.getLogger(__name__)


class SettingsDialog(QDialog):
    """Tabbed settings dialog accessible from the main window gear button."""

    camera_device_changed = pyqtSignal(int)
    mic_device_changed = pyqtSignal(object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        active_camera_index: int | None = None,
        active_mic_device: int | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(700, 520)
        self.resize(760, 560)
        self.setStyleSheet(theme.application_stylesheet())
        self._active_camera_index = active_camera_index
        self._active_mic_device = active_mic_device

        self._camera_index_by_device: dict[int, int] = {}
        self._mic_index_by_device: dict[int, int] = {}
        self._camera_populated = False
        self._mic_populated = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        self._tabs = QTabWidget()
        self._tabs.tabBar().setElideMode(Qt.TextElideMode.ElideNone)
        self._tabs.tabBar().setExpanding(False)
        self._tabs.addTab(self._build_voice_tab(), "Voice")
        self._keys_tab_index = self._tabs.addTab(self._build_keys_tab(), "API Key")
        self._camera_tab_index = self._tabs.addTab(self._build_camera_tab(), "Reading")
        self._mic_tab_index = self._tabs.addTab(self._build_mic_tab(), "Microphone")
        self._tabs.addTab(self._build_profile_tab(), "Profile")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("Save")
        save_btn.setObjectName("wizard-primary-btn")
        save_btn.setFixedWidth(100)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

        self._mic_monitor = MicLevelMonitor()
        self._mic_timer = QTimer(self)
        self._mic_timer.timeout.connect(self._update_mic_meter)

    # -- API Keys tab --

    def _build_voice_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 18, 6, 8)
        layout.setSpacing(10)

        model_label = QLabel("Conversation model")
        model_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-weight: 600; "
            "background: transparent; border: none;"
        )
        layout.addWidget(model_label)
        self._live_model_combo = QComboBox()
        self._enable_combo_popup_hover(self._live_model_combo)
        for model, details in config.LIVE_MODELS.items():
            self._live_model_combo.addItem(details["label"], model)
        selected_model = self._live_model_combo.findData(config.LIVE_MODEL)
        self._live_model_combo.setCurrentIndex(max(0, selected_model))
        self._live_model_combo.currentIndexChanged.connect(self._on_live_model_changed)
        layout.addWidget(self._live_model_combo)

        self._model_info = QLabel()
        self._model_info.setWordWrap(True)
        self._model_info.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self._model_info)

        layout.addWidget(QLabel("Reasoning effort"))
        self._reasoning_effort_combo = QComboBox()
        self._enable_combo_popup_hover(self._reasoning_effort_combo)
        for effort in ("low", "medium", "high"):
            self._reasoning_effort_combo.addItem(effort.capitalize(), effort)
        selected_effort = self._reasoning_effort_combo.findData(config.REASONING_EFFORT)
        self._reasoning_effort_combo.setCurrentIndex(max(0, selected_effort))
        layout.addWidget(self._reasoning_effort_combo)

        effort_hint = QLabel("Higher effort may improve difficult answers, but it can take longer.")
        effort_hint.setWordWrap(True)
        effort_hint.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(effort_hint)

        layout.addSpacing(8)
        layout.addWidget(QLabel("Voice"))
        self._voice_combo = QComboBox()
        self._enable_combo_popup_hover(self._voice_combo)
        self._populate_voices(config.LIVE_MODEL)
        layout.addWidget(self._voice_combo)
        self._on_live_model_changed()

        self._barge_in_check = QCheckBox("Let me interrupt by speaking")
        self._barge_in_check.setChecked(config.BARGE_IN_ENABLED)
        layout.addWidget(self._barge_in_check)
        hint = QLabel(
            "Klaus stops playback and trims unheard audio from the conversation."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none; padding-left: 22px;"
        )
        layout.addWidget(hint)
        layout.addStretch()
        return page

    def _on_live_model_changed(self) -> None:
        model = str(self._live_model_combo.currentData())
        details = config.live_model_details(model)
        self._model_info.setText(
            "Gemini Live includes Google Search grounding. GPT Live does not offer web "
            "search in Klaus."
            if details["provider"] == "gemini"
            else "GPT Live does not offer web search in Klaus. Choose Gemini Live for "
            "Google Search grounding."
        )
        self._populate_voices(model)

    def _populate_voices(self, model: str) -> None:
        current_voice = self._voice_combo.currentData()
        voices = (
            ("Kore",)
            if config.live_model_details(model)["provider"] == "gemini"
            else (
                "cedar", "marin", "coral", "nova", "alloy", "ash", "ballad",
                "echo", "fable", "onyx", "sage", "shimmer", "verse",
            )
        )
        preferred = current_voice or config.VOICE
        self._voice_combo.blockSignals(True)
        self._voice_combo.clear()
        for voice in voices:
            self._voice_combo.addItem(voice.capitalize(), voice)
        selected = self._voice_combo.findData(preferred)
        self._voice_combo.setCurrentIndex(max(0, selected))
        self._voice_combo.blockSignals(False)

    def _build_keys_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 18, 6, 8)
        layout.setSpacing(10)

        self._key_edits: dict[str, QLineEdit] = {}
        self._key_indicators: dict[str, QLabel] = {}
        self._key_clear_checks: dict[str, QCheckBox] = {}
        self._api_key_sources = config.get_api_key_sources()

        for label, slug, prefix, _min_len in KEY_PATTERNS:
            row = QHBoxLayout()
            row.setSpacing(8)

            name = QLabel(label + "  optional")
            name.setFixedWidth(135)
            name.setStyleSheet(
                f"color: {theme.TEXT_SECONDARY}; font-weight: 600; "
                "background: transparent; border: none;"
            )
            row.addWidget(name)

            edit = QLineEdit()
            source = self._api_key_sources.get(slug, "missing")
            edit.setPlaceholderText(self._api_key_placeholder(prefix, source))
            edit.setEchoMode(QLineEdit.EchoMode.Password)
            edit.textChanged.connect(lambda _, s=slug: self._on_key_text_changed(s))
            self._key_edits[slug] = edit
            row.addWidget(edit, stretch=1)

            indicator = QLabel("")
            indicator.setFixedWidth(24)
            indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
            indicator.setStyleSheet("background: transparent; border: none;")
            self._key_indicators[slug] = indicator
            row.addWidget(indicator)

            clear_box = QCheckBox("Clear")
            clear_box.stateChanged.connect(lambda _, s=slug: self._on_key_clear_toggled(s))
            self._key_clear_checks[slug] = clear_box
            row.addWidget(clear_box)

            layout.addLayout(row)

            source_hint = QLabel(self._api_key_source_hint(source))
            source_hint.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
                "background: transparent; border: none; padding-left: 98px;"
            )
            layout.addWidget(source_hint)

        for slug in self._key_edits:
            self._validate_key(slug)

        layout.addStretch()
        return page

    @staticmethod
    def _api_key_placeholder(prefix: str, source: str) -> str:
        if source == "keychain":
            return "Stored in Apple Keychain; enter new key to replace"
        if source == "env":
            return "Set by environment variable; enter key to persist locally"
        if source == "config":
            return "Stored in config.toml fallback; enter new key to replace"
        return f"{prefix}..."

    @staticmethod
    def _api_key_source_hint(source: str) -> str:
        if source == "keychain":
            return "Currently stored in Apple Keychain."
        if source == "env":
            return "Currently provided by environment variable."
        if source == "config":
            return "Currently stored in config.toml fallback."
        return "No stored value."

    def _on_key_text_changed(self, slug: str) -> None:
        text = self._key_edits[slug].text().strip()
        clear_box = self._key_clear_checks[slug]
        if text and clear_box.isChecked():
            clear_box.blockSignals(True)
            clear_box.setChecked(False)
            clear_box.blockSignals(False)
        self._validate_key(slug)

    def _on_key_clear_toggled(self, slug: str) -> None:
        if self._key_clear_checks[slug].isChecked():
            edit = self._key_edits[slug]
            edit.blockSignals(True)
            edit.clear()
            edit.blockSignals(False)
        self._validate_key(slug)

    def _validate_key(self, slug: str) -> None:
        clear_checked = self._key_clear_checks[slug].isChecked()
        text = self._key_edits[slug].text().strip()
        indicator = self._key_indicators[slug]
        if clear_checked:
            indicator.setText("")
            return
        if not text:
            indicator.setText("")
            return
        is_valid, _ = validate_api_key(slug, text)
        if is_valid:
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

    # -- Camera tab --

    def _build_camera_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 18, 6, 8)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Reading source"))

        self._camera_combo = QComboBox()
        self._camera_combo.activated.connect(self._on_camera_changed)
        self._enable_combo_popup_hover(self._camera_combo)
        layout.addWidget(self._camera_combo)

        hint = QLabel(
            "Choose no source for audio-only questions, Desk View for paper, "
            "Active window for a Mac app, or pair a Paper Pure."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(hint)

        tablet_row = QHBoxLayout()
        self._remarkable_status = QLabel()
        self._refresh_remarkable_status()
        tablet_row.addWidget(self._remarkable_status, stretch=1)
        pair_button = QPushButton("Pair manually...")
        pair_button.clicked.connect(self._pair_remarkable)
        tablet_row.addWidget(pair_button)
        layout.addLayout(tablet_row)

        layout.addStretch()
        return page

    def _populate_cameras(self) -> None:
        self._camera_combo.blockSignals(True)
        self._camera_combo.clear()
        self._camera_index_by_device = {-1: 0}
        self._camera_combo.addItem("No reading source (audio only)", -1)
        try:
            cameras = list_camera_devices()
        except Exception as exc:
            logger.warning("Failed to enumerate cameras: %s", exc)
            cameras = []

        for cam in cameras:
            self._camera_combo.addItem(format_camera_label(cam), cam.index)
            self._camera_index_by_device[cam.index] = self._camera_combo.count() - 1

        if self._active_camera_index is not None:
            selected_device = int(self._active_camera_index)
        else:
            selected_device = config.CAMERA_DEVICE_INDEX
        selected_combo = self._camera_index_by_device.get(selected_device, 0)
        self._camera_combo.setCurrentIndex(selected_combo)
        self._camera_combo.blockSignals(False)

    def set_camera_selection(self, device_index: int) -> None:
        self._active_camera_index = int(device_index)
        combo_index = self._camera_index_by_device.get(device_index)
        if combo_index is None:
            return
        self._camera_combo.blockSignals(True)
        self._camera_combo.setCurrentIndex(combo_index)
        self._camera_combo.blockSignals(False)

    def _on_camera_changed(self, _index: int | None = None) -> None:
        cam_idx = self._camera_combo.currentData()
        if cam_idx is None:
            cam_idx = -1
        cam_idx = int(cam_idx)
        if (
            cam_idx == REMARKABLE_PAPER_PURE_SOURCE_INDEX
            and not config.REMARKABLE_CERTIFICATE_SHA256
            and not self._pair_remarkable()
        ):
            self.set_camera_selection(self._active_camera_index or -1)
            return
        self._active_camera_index = cam_idx
        config.set_camera_index(cam_idx, persist=True)
        self.camera_device_changed.emit(cam_idx)

    def _refresh_remarkable_status(self) -> None:
        if config.REMARKABLE_CERTIFICATE_SHA256:
            text = f"Paired: {config.REMARKABLE_USERNAME} at {config.REMARKABLE_ADDRESS}"
        else:
            text = "Paper Pure is not paired"
        self._remarkable_status.setText(text)

    def _pair_remarkable(self) -> bool:
        paired = open_remarkable_pairing(self)
        if paired:
            self._refresh_remarkable_status()
        return paired

    # -- Profile tab --

    def _build_profile_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 18, 6, 8)
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
        help_btn.setFixedSize(18, 18)
        help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        help_btn.setToolTip(
            "Set your vault root, then ask Klaus: "
            "\"Save this to Folder/Note.md\" and it will create/append the note."
        )
        help_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {theme.TEXT_SECONDARY}; "
            "border: none; padding: 0px; font-weight: bold; font-size: 14px; }"
            "\n"
            f"QPushButton:hover {{ color: {theme.KLAUS_ACCENT}; }}"
        )
        help_btn.clicked.connect(self._show_vault_help)
        vault_header.addWidget(help_btn)
        vault_header.addStretch()
        layout.addLayout(vault_header)

        vault_row = QHBoxLayout()
        self._vault_path_edit = QLineEdit()
        self._vault_path_edit.setReadOnly(True)
        self._vault_path_edit.setPlaceholderText("Not set. Click Browse to select")
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
            "Set this to your Obsidian vault root folder.\n\n"
            "Then ask Klaus to save to a file in a folder, for example:\n"
            "  \"Save this to Research/Agent Notes.md\"\n\n"
            "Klaus will create missing folders/files and append the note.\n\n"
            "Leave this blank if you do not use Obsidian."
        )
        msg.exec()

    # -- Microphone tab --

    def _build_mic_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 18, 6, 8)
        layout.setSpacing(10)

        layout.addWidget(QLabel("Input device"))

        self._mic_combo = QComboBox()
        self._mic_combo.currentIndexChanged.connect(self._on_mic_changed)
        self._enable_combo_popup_hover(self._mic_combo)
        layout.addWidget(self._mic_combo)

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
        self._on_tab_changed(self._tabs.currentIndex())

    def closeEvent(self, event) -> None:
        self._stop_mic()
        super().closeEvent(event)

    def _on_tab_changed(self, index: int) -> None:
        if index == self._camera_tab_index and not self._camera_populated:
            self._populate_cameras()
            self._camera_populated = True

        if index == self._mic_tab_index:
            if not self._mic_populated:
                self._populate_mics()
                self._mic_populated = True
            self._start_mic()
        else:
            self._stop_mic()

    def _start_mic(self) -> None:
        self._stop_mic()
        device_idx = self._selected_mic_device()
        if self._mic_monitor.start(device_idx):
            self._mic_timer.start(50)

    def _populate_mics(self) -> None:
        self._mic_combo.blockSignals(True)
        self._mic_combo.clear()
        self._mic_index_by_device = {-1: 0}
        self._mic_combo.addItem("System default microphone", -1)
        for mic in list_input_devices():
            self._mic_combo.addItem(format_mic_label(mic), mic.index)
            self._mic_index_by_device[mic.index] = self._mic_combo.count() - 1

        if self._active_mic_device is not None:
            selected_device = int(self._active_mic_device)
        else:
            selected_device = config.MIC_DEVICE_INDEX
        selected_combo = self._mic_index_by_device.get(selected_device, 0)
        self._mic_combo.setCurrentIndex(selected_combo)
        self._mic_combo.blockSignals(False)

    def _selected_mic_device(self) -> int | None:
        mic_idx = self._mic_combo.currentData()
        if mic_idx is None:
            return None
        mic_idx = int(mic_idx)
        if mic_idx < 0:
            return None
        return mic_idx

    def set_mic_selection(self, device: int | None) -> None:
        self._active_mic_device = None if device is None else int(device)
        requested = -1 if device is None else int(device)
        combo_index = self._mic_index_by_device.get(requested)
        if combo_index is None:
            return
        self._mic_combo.blockSignals(True)
        self._mic_combo.setCurrentIndex(combo_index)
        self._mic_combo.blockSignals(False)
        self._start_mic()

    def _on_mic_changed(self) -> None:
        mic_idx = self._mic_combo.currentData()
        if mic_idx is None:
            mic_idx = -1
        mic_idx = int(mic_idx)
        self._active_mic_device = None if mic_idx < 0 else mic_idx
        config.set_mic_index(mic_idx, persist=True)
        self._start_mic()
        self.mic_device_changed.emit(None if mic_idx < 0 else mic_idx)

    def _stop_mic(self) -> None:
        self._mic_timer.stop()
        self._mic_monitor.stop()

    def _update_mic_meter(self) -> None:
        self._mic_meter.setValue(self._mic_monitor.level_percent())

    @staticmethod
    def _enable_combo_popup_hover(combo: QComboBox) -> None:
        view = QListView()
        view.setMouseTracking(True)
        combo.setView(view)

    # -- Save --

    def _save(self) -> None:
        selected_model = str(self._live_model_combo.currentData())
        selected_slug = config.live_model_details(selected_model)["provider"]
        selected_key = self._key_edits[selected_slug].text().strip()
        selected_cleared = self._key_clear_checks[selected_slug].isChecked()
        selected_source = self._api_key_sources.get(selected_slug, "missing")
        if selected_cleared or (not selected_key and selected_source == "missing"):
            self._tabs.setCurrentIndex(self._keys_tab_index)
            provider = "Gemini" if selected_slug == "gemini" else "OpenAI"
            QMessageBox.warning(
                self,
                "API key required",
                f"{provider} needs an API key for the selected live model.",
            )
            return

        for label, slug, _prefix, _min_len in KEY_PATTERNS:
            if self._key_clear_checks[slug].isChecked():
                config.clear_api_key(slug)
                continue

            text = self._key_edits[slug].text().strip()
            if not text:
                continue

            is_valid, message = validate_api_key(slug, text)
            if not is_valid:
                self._tabs.setCurrentIndex(self._keys_tab_index)
                QMessageBox.warning(self, "Invalid API key", f"{label}: {message}")
                return
            config.set_api_key(slug, text)

        bg = self._background_edit.toPlainText().strip()
        config.save_user_background(bg)
        vault = self._vault_path_edit.text().strip()
        config.save_obsidian_vault_path(vault)
        voice = self._voice_combo.currentData()
        config.save_voice(str(voice))
        config.save_live_model(str(self._live_model_combo.currentData()))
        config.save_reasoning_effort(str(self._reasoning_effort_combo.currentData()))
        config.save_barge_in_enabled(self._barge_in_check.isChecked())
        config.reload()
        logger.info("Settings saved")
        self._stop_mic()
        self.accept()
