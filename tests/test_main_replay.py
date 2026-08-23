"""Tests for replay audio behavior in the app coordinator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from klaus.main import KlausApp


def test_realtime_replay_keeps_spoken_interruption_enabled() -> None:
    app = KlausApp.__new__(KlausApp)
    app._input_mode = "voice_activation"
    app._brain = MagicMock()
    app._vad_recorder = MagicMock()
    app._signals = MagicMock()
    seed = np.array([1, 2, 3], dtype=np.int16)
    app._brain.speak_text.side_effect = lambda _text: setattr(
        app, "_barge_in_seed", seed
    )

    with patch("klaus.main.config.BARGE_IN_ENABLED", True):
        KlausApp._replay_audio(app, "Repeat this answer.")

    app._brain.speak_text.assert_called_once_with("Repeat this answer.")
    app._vad_recorder.enter_gated_mode.assert_called_once()
    app._vad_recorder.pause.assert_not_called()
    app._vad_recorder.exit_gated_mode.assert_called_once()
    app._vad_recorder.resume_stream.assert_called_once()
    app._vad_recorder.resume.assert_called_once()
    app._vad_recorder.prime_with_seed.assert_called_once_with(seed)


def test_realtime_replay_pauses_voice_detection_when_interruption_is_disabled() -> None:
    app = KlausApp.__new__(KlausApp)
    app._input_mode = "voice_activation"
    app._brain = MagicMock()
    app._vad_recorder = MagicMock()
    app._signals = MagicMock()

    with patch("klaus.main.config.BARGE_IN_ENABLED", False):
        KlausApp._replay_audio(app, "Repeat this answer.")

    app._vad_recorder.enter_gated_mode.assert_not_called()
    app._vad_recorder.pause.assert_called_once()
    app._vad_recorder.prime_with_seed.assert_not_called()
