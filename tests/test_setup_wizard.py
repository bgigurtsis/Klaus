"""Tests for first-launch feature guidance."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QApplication, QLabel

from klaus.ui.setup_wizard import SetupWizard


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
