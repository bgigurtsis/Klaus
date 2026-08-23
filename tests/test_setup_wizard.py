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


def test_live_model_step_defaults_to_gemini_and_exposes_effort(qt_app) -> None:
    wizard = SetupWizard()

    assert wizard._live_model_combo.currentData() == "gemini-3.1-flash-live-preview"
    assert wizard._reasoning_effort_combo.currentData() == "low"
    assert "required" in wizard._key_names["gemini"].text()
    assert "optional" in wizard._key_names["openai"].text()

    wizard._live_model_combo.setCurrentIndex(
        wizard._live_model_combo.findData("gpt-realtime-2.1-mini")
    )
    assert "required" in wizard._key_names["openai"].text()
    wizard.close()


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
    monkeypatch.setattr("klaus.config.save_mic_index", lambda _index: None)
    monkeypatch.setattr("klaus.config.mark_setup_complete", lambda: None)
    monkeypatch.setattr("klaus.config.reload", lambda: None)

    wizard._finish_setup()

    assert saved_keys == [("openai", "sk-test-openai")]
    assert saved_model == ["gpt-realtime-2.1-mini"]
    wizard.close()
