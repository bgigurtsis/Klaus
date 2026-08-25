"""First-run setup wizard for Klaus.

Walks users through API key entry, reading source, microphone test, and
voice-model download. Shown on first launch; skipped once ``setup_complete``
is ``true`` in ``~/.klaus/config.toml``.

Step pages live in :mod:`klaus.ui.wizard_content_steps` and
:mod:`klaus.ui.wizard_device_steps`; shared widgets in
:mod:`klaus.ui.wizard_widgets`. This module keeps only navigation and the
final config write.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

import klaus.config as config
from klaus.ui import theme
from klaus.ui.wizard_content_steps import ContentStepsMixin
from klaus.ui.wizard_device_steps import DeviceStepsMixin
from klaus.ui.wizard_widgets import NUM_STEPS, StepIndicator

logger = logging.getLogger(__name__)


class SetupWizard(ContentStepsMixin, DeviceStepsMixin, QMainWindow):
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

        self._indicator = StepIndicator()
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
            "gemini": config.GEMINI_API_KEY,
            "openai": config.OPENAI_API_KEY,
            "live_model": config.LIVE_MODEL,
            "reasoning_effort": config.REASONING_EFFORT,
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
            self._next_btn.setEnabled(
                self._key_valid.get(self._selected_key_slug(), False)
            )
        else:
            self._next_btn.setEnabled(True)

    def closeEvent(self, event) -> None:
        self._camera_preview.stop()
        self._stop_mic_meter()
        super().closeEvent(event)

    # -- Finish --

    def _finish_setup(self) -> None:
        """Write all collected config and close the wizard."""
        import klaus.config as cfg
        model = str(self._live_model_combo.currentData())
        slug = cfg.live_model_details(model)["provider"]
        value = str(self._collected.get(slug, "")).strip()
        if value:
            cfg.set_api_key(slug, value)
        cfg.save_live_model(model)
        cfg.save_reasoning_effort(str(self._reasoning_effort_combo.currentData()))
        cam_idx = self._collected["camera_index"]
        if cam_idx != -1:
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
