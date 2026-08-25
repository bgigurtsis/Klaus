"""Setup-wizard device steps: reading source, microphone, model download.

Mixin for SetupWizard. Builders add pages to ``self._stack`` and store the
widgets they need as attributes on the wizard.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QComboBox,
    QLabel,
    QProgressBar,
    QPushButton,
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
from klaus.permissions import MIC_UNAVAILABLE_MESSAGE
from klaus.reading_source import REMARKABLE_PAPER_PURE_SOURCE_INDEX
from klaus.ui import theme
from klaus.ui.desk_view_setup import launch_desk_view_setup
from klaus.ui.remarkable_pairing import open_remarkable_pairing
from klaus.ui.shared.mic_level_monitor import MicLevelMonitor
from klaus.ui.wizard_widgets import CameraPreview, ModelDownloadThread


class DeviceStepsMixin:
    """Reading-source, microphone, and model-download pages."""

    # -- Step 3: Reading source --

    def _build_step_camera(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(48, 24, 48, 16)
        layout.setSpacing(12)

        heading = QLabel("Choose how you are reading")
        heading.setStyleSheet(
            f"font-size: 22px; font-weight: bold; color: {theme.TEXT_PRIMARY}; "
            "background: transparent; border: none;"
        )
        layout.addWidget(heading)

        self._camera_combo = QComboBox()
        self._camera_combo.currentIndexChanged.connect(self._on_camera_changed)
        layout.addWidget(self._camera_combo)

        self._camera_preview = CameraPreview()
        layout.addWidget(self._camera_preview, alignment=Qt.AlignmentFlag.AlignCenter)

        tip = QLabel(
            "Audio only: keep No reading source selected.\n"
            "Physical paper: Klaus opens Apple's Desk View setup for you.\n"
            "On screen: keep any app window frontmost and select text when useful.\n"
            "Paper Pure: run the setup script in the Klaus README before pairing."
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
        self._camera_combo.addItem("No reading source (audio only)", -1)
        cameras = list_camera_devices()
        for cam in cameras:
            self._camera_combo.addItem(format_camera_label(cam), cam.index)
        self._camera_combo.blockSignals(False)
        self._on_camera_changed()

    def _on_camera_changed(self) -> None:
        idx = self._camera_combo.currentData()
        if idx is None:
            idx = -1
        self._collected["camera_index"] = idx
        if idx != -1:
            if idx == -2:
                launch_desk_view_setup(self)
            if idx == REMARKABLE_PAPER_PURE_SOURCE_INDEX:
                if not open_remarkable_pairing(self):
                    self._camera_combo.setCurrentIndex(0)
                    return
            self._camera_preview.start(idx)
        else:
            self._camera_preview.stop()

    # -- Step 4: Microphone --

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

        self._mic_error_label = QLabel(MIC_UNAVAILABLE_MESSAGE)
        self._mic_error_label.setWordWrap(True)
        self._mic_error_label.setStyleSheet(
            f"color: {theme.ERROR_COLOR}; background: transparent; border: none;"
        )
        self._mic_error_label.setVisible(False)
        layout.addWidget(self._mic_error_label)

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
            self._mic_error_label.setVisible(False)
            self._mic_timer.start(50)
        else:
            self._mic_meter.setValue(0)
            self._mic_error_label.setVisible(True)

    def _stop_mic_meter(self) -> None:
        self._mic_timer.stop()
        self._mic_monitor.stop()

    def _update_mic_meter(self) -> None:
        self._mic_meter.setValue(self._mic_monitor.level_percent())

    # -- Step 5: Voice model download --

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
            "Klaus uses a local speech model to show your question quickly and "
            "filter noise before the live model answers.\nThis one-time download is about 245 MB."
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

        self._model_cancel_btn = QPushButton("Cancel")
        self._model_cancel_btn.setObjectName("wizard-link-btn")
        self._model_cancel_btn.setFixedWidth(120)
        self._model_cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._model_cancel_btn.clicked.connect(self._cancel_model_download)
        self._model_cancel_btn.setVisible(False)
        layout.addWidget(self._model_cancel_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()
        self._stack.addWidget(page)
        self._download_thread: ModelDownloadThread | None = None

    def _start_model_download(self) -> None:
        self._model_retry_btn.setVisible(False)
        self._model_cancel_btn.setVisible(True)
        self._model_progress.setRange(0, 1000)
        self._model_progress.setValue(0)
        self._model_status.setText("Downloading...")
        self._model_status.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
            "background: transparent; border: none;"
        )
        self._next_btn.setVisible(False)

        from klaus.config import STT_MOONSHINE_LANGUAGE
        self._download_thread = ModelDownloadThread(STT_MOONSHINE_LANGUAGE)
        self._download_thread.progress.connect(self._on_model_download_progress)
        self._download_thread.finished.connect(self._on_model_download_done)
        self._download_thread.start()

    def _cancel_model_download(self) -> None:
        if self._download_thread is not None:
            self._download_thread.cancel()
        self._model_cancel_btn.setEnabled(False)

    def _on_model_download_progress(self, fraction: float, _name: str) -> None:
        self._model_progress.setValue(int(fraction * 1000))
        self._model_status.setText(f"Downloading... {int(fraction * 100)}%")

    def _on_model_download_done(self, success: bool, error: str) -> None:
        self._model_cancel_btn.setVisible(False)
        self._model_cancel_btn.setEnabled(True)
        if success:
            self._model_progress.setRange(0, 1)
            self._model_progress.setValue(1)
            self._model_status.setText("Model ready")
            self._model_status.setStyleSheet(
                f"color: {theme.KLAUS_ACCENT}; font-size: {theme.FONT_SIZE_CAPTION}px; "
                "background: transparent; border: none;"
            )
            QTimer.singleShot(600, lambda: self._set_step(5))
        elif error == "cancelled":
            self._model_progress.setRange(0, 1)
            self._model_progress.setValue(0)
            self._model_status.setText(
                "Download cancelled. Completed files are kept, so Retry resumes."
            )
            self._model_status.setStyleSheet(
                f"color: {theme.TEXT_MUTED}; font-size: {theme.FONT_SIZE_CAPTION}px; "
                "background: transparent; border: none;"
            )
            self._model_retry_btn.setVisible(True)
        else:
            self._model_progress.setRange(0, 1)
            self._model_progress.setValue(0)
            self._model_status.setText(f"Download failed: {error}")
            self._model_status.setStyleSheet(
                f"color: {theme.ERROR_COLOR}; font-size: {theme.FONT_SIZE_CAPTION}px; "
                "background: transparent; border: none;"
            )
            self._model_retry_btn.setVisible(True)
