"""Tests for first-launch feature guidance."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox

from klaus.ui.setup_wizard import SetupWizard
from klaus.ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_welcome_page_explains_features_and_first_actions(qt_app) -> None:
    wizard = SetupWizard()
    labels = "\n".join(label.text() for label in wizard.findChildren(QLabel))

    assert "Read Anything" in labels
    assert "keep any app window frontmost" in labels
    assert "Ask by Voice" in labels
    assert "Remember" in labels
    assert "Save to Obsidian" in labels
    assert "Research/Agent Notes.md" in labels

    wizard.close()


def test_live_model_step_defaults_to_mini_with_high_effort(qt_app, monkeypatch) -> None:
    monkeypatch.setattr("klaus.config.LIVE_MODEL", "gpt-realtime-2.1-mini")
    monkeypatch.setattr("klaus.config.REASONING_EFFORT", "high")
    wizard = SetupWizard()

    assert wizard._live_model_combo.currentData() == "gpt-realtime-2.1-mini"
    assert wizard._reasoning_effort_combo.currentData() == "high"
    assert "required" in wizard._key_names["openai"].text()
    assert "optional" in wizard._key_names["gemini"].text()

    wizard._live_model_combo.setCurrentIndex(
        wizard._live_model_combo.findData("gpt-realtime-2.1-mini")
    )
    assert "required" in wizard._key_names["openai"].text()
    wizard.close()


def test_reading_source_step_defaults_to_audio_only(qt_app) -> None:
    wizard = SetupWizard()

    wizard._populate_cameras()

    assert wizard._camera_combo.currentData() == -1
    assert wizard._collected["camera_index"] == -1
    wizard.close()


def test_back_to_camera_step_preserves_selection(qt_app, monkeypatch):
    wizard = SetupWizard()
    started = []
    monkeypatch.setattr(wizard._camera_preview, "start", started.append)
    wizard._populate_cameras()
    wizard._camera_combo.setCurrentIndex(wizard._camera_combo.findData(-3))
    wizard._populate_cameras()
    assert wizard._camera_combo.currentData() == -3
    assert wizard._collected["camera_index"] == -3
    assert started[-1] == -3
    wizard.close()


def test_rejected_settings_devices_never_persist_the_request(qt_app, monkeypatch):
    from unittest.mock import MagicMock
    camera_save = MagicMock()
    mic_save = MagicMock()
    monkeypatch.setattr("klaus.config.set_camera_index", camera_save)
    monkeypatch.setattr("klaus.config.set_mic_index", mic_save)
    dialog = SettingsDialog(active_camera_index=-1, active_mic_device=None)
    monkeypatch.setattr(dialog, "_start_mic", lambda: None)
    monkeypatch.setattr("klaus.ui.settings_dialog.list_input_devices", lambda: [])
    dialog._populate_cameras()
    dialog._populate_mics()
    dialog.camera_device_changed.connect(lambda _requested: dialog.set_camera_selection(-1))
    dialog.mic_device_changed.connect(lambda _requested: dialog.set_mic_selection(None))
    dialog._camera_combo.setCurrentIndex(dialog._camera_combo.findData(-3))
    dialog._on_camera_changed()
    dialog._mic_combo.addItem("Test microphone", 123)
    dialog._mic_combo.setCurrentIndex(dialog._mic_combo.findData(123))
    assert dialog._camera_combo.currentData() == -1
    assert dialog._mic_combo.currentData() == -1
    camera_save.assert_not_called()
    mic_save.assert_not_called()
    dialog.close()


@pytest.mark.parametrize(
    ("model", "effort", "required_slug"),
    [
        ("gemini-3.1-flash-live-preview", "low", "gemini"),
        ("gpt-realtime-2.1", "medium", "openai"),
        ("gpt-realtime-2.1-mini", "high", "openai"),
    ],
)
def test_setup_navigation_accepts_each_model_and_effort(
    qt_app, monkeypatch, model, effort, required_slug
) -> None:
    wizard = SetupWizard()
    monkeypatch.setattr(wizard, "_start_model_download", lambda: None)
    monkeypatch.setattr(wizard, "_populate_cameras", lambda: None)
    monkeypatch.setattr(wizard, "_populate_mics", lambda: None)

    wizard._live_model_combo.setCurrentIndex(wizard._live_model_combo.findData(model))
    wizard._reasoning_effort_combo.setCurrentIndex(
        wizard._reasoning_effort_combo.findData(effort)
    )
    assert wizard._next_btn.isEnabled()
    assert "required" in wizard._key_names[required_slug].text()

    wizard._go_next()
    wizard._go_next()
    wizard._go_next()
    wizard._go_next()
    wizard._set_step(5)
    wizard._go_next()

    assert wizard._current_step == 6
    assert wizard._collected["live_model"] == model
    assert wizard._reasoning_effort_combo.currentData() == effort
    wizard.close()


def test_settings_blocks_selected_provider_without_a_key(qt_app, monkeypatch) -> None:
    dialog = SettingsDialog()
    dialog._api_key_sources = {"gemini": "missing", "openai": "env"}
    dialog._live_model_combo.setCurrentIndex(
        dialog._live_model_combo.findData("gemini-3.1-flash-live-preview")
    )

    warnings: list[tuple] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args),
    )
    dialog._save()

    assert warnings
    assert dialog._tabs.currentIndex() == dialog._keys_tab_index
    dialog.close()


def test_settings_voice_controls_fit_their_font(qt_app) -> None:
    dialog = SettingsDialog()
    dialog.show()
    qt_app.processEvents()

    assert dialog.minimumHeight() == 520
    for combo in (
        dialog._live_model_combo,
        dialog._reasoning_effort_combo,
        dialog._voice_combo,
    ):
        assert combo.height() >= combo.fontMetrics().height() + 8

    dialog.close()


def test_settings_voice_dropdowns_track_hovered_items(qt_app) -> None:
    dialog = SettingsDialog()

    for combo in (
        dialog._live_model_combo,
        dialog._reasoning_effort_combo,
        dialog._voice_combo,
    ):
        assert combo.view().hasMouseTracking()

    dialog.close()


def test_setup_persists_only_the_selected_provider_key(qt_app, monkeypatch) -> None:
    wizard = SetupWizard()
    wizard._live_model_combo.setCurrentIndex(
        wizard._live_model_combo.findData("gpt-realtime-2.1-mini")
    )
    wizard._collected["gemini"] = "AIza-test-gemini"
    wizard._collected["openai"] = "sk-test-openai"

    saved_keys: list[tuple[str, str]] = []
    saved_model: list[str] = []
    monkeypatch.setattr(
        "klaus.config.set_api_key",
        lambda slug, value: saved_keys.append((slug, value)),
    )
    monkeypatch.setattr(
        "klaus.config.save_live_model",
        lambda model: saved_model.append(model),
    )
    monkeypatch.setattr("klaus.config.save_reasoning_effort", lambda _effort: None)
    saved_cameras: list[int] = []
    monkeypatch.setattr("klaus.config.save_camera_index", saved_cameras.append)
    monkeypatch.setattr("klaus.config.save_mic_index", lambda _index: None)
    monkeypatch.setattr("klaus.config.mark_setup_complete", lambda: None)
    monkeypatch.setattr("klaus.config.reload", lambda: None)

    wizard._finish_setup()

    assert saved_keys == [("openai", "sk-test-openai")]
    assert saved_model == ["gpt-realtime-2.1-mini"]
    assert saved_cameras == [-1]
    wizard.close()


def test_model_download_progress_updates_bar_and_status(qt_app) -> None:
    wizard = SetupWizard()

    wizard._model_progress.setRange(0, 1000)
    wizard._on_model_download_progress(0.42, "model.bin")

    assert wizard._model_progress.value() == 420
    assert "42%" in wizard._model_status.text()
    wizard.close()


def test_model_download_cancel_shows_resume_hint_and_retry(qt_app) -> None:
    wizard = SetupWizard()

    wizard._on_model_download_done(False, "cancelled")

    assert "Retry resumes" in wizard._model_status.text()
    assert not wizard._model_retry_btn.isHidden()
    assert wizard._model_cancel_btn.isHidden()
    wizard.close()


def test_model_download_thread_cancel_aborts_and_reports_cancelled(qt_app) -> None:
    from klaus.ui.wizard_widgets import ModelDownloadThread

    thread = ModelDownloadThread("en")
    results: list[tuple[bool, str]] = []
    thread.finished.connect(lambda ok, err: results.append((ok, err)))

    def fake_download(language, on_progress=None):
        for i in range(10):
            on_progress(i / 10, "model.bin")

    import moonshine_voice

    original = moonshine_voice.get_model_for_language
    moonshine_voice.get_model_for_language = fake_download
    try:
        thread.cancel()
        thread.run()
    finally:
        moonshine_voice.get_model_for_language = original

    assert results == [(False, "cancelled")]
