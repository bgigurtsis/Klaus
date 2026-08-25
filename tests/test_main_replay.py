"""Tests for replay audio behavior in the turn coordinator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from klaus.services.turn_coordinator import TurnCoordinator
from klaus.services.turn_state import TurnState


def _make_coordinator(
    turn_state: TurnState,
    *,
    vad_recorder: MagicMock,
    brain: MagicMock,
) -> TurnCoordinator:
    return TurnCoordinator(
        turn_state=turn_state,
        speculative_stt=MagicMock(),
        stt=MagicMock(),
        audio_output=MagicMock(),
        signals=MagicMock(),
        get_vad_recorder=lambda: vad_recorder,
        get_ptt_recorder=MagicMock(),
        get_pipeline=MagicMock(),
        get_brain=lambda: brain,
        get_input_mode=lambda: "voice_activation",
        get_current_session_id=lambda: None,
        update_exchange_count=MagicMock(),
    )


def test_realtime_replay_keeps_spoken_interruption_enabled() -> None:
    turn_state = TurnState()
    brain = MagicMock()
    vad_recorder = MagicMock()
    seed = np.array([1, 2, 3], dtype=np.int16)
    brain.speak_text.side_effect = lambda _text: turn_state.barge_in(seed)

    coordinator = _make_coordinator(turn_state, vad_recorder=vad_recorder, brain=brain)
    with patch("klaus.services.turn_coordinator.config.BARGE_IN_ENABLED", True):
        coordinator.replay("Repeat this answer.")

    brain.speak_text.assert_called_once_with("Repeat this answer.")
    vad_recorder.enter_gated_mode.assert_called_once()
    vad_recorder.pause.assert_not_called()
    vad_recorder.exit_gated_mode.assert_called_once()
    vad_recorder.resume_stream.assert_called_once()
    vad_recorder.resume.assert_called_once()
    vad_recorder.prime_with_seed.assert_called_once_with(seed)


def test_realtime_replay_pauses_voice_detection_when_interruption_is_disabled() -> None:
    turn_state = TurnState()
    brain = MagicMock()
    vad_recorder = MagicMock()

    coordinator = _make_coordinator(turn_state, vad_recorder=vad_recorder, brain=brain)
    with patch("klaus.services.turn_coordinator.config.BARGE_IN_ENABLED", False):
        coordinator.replay("Repeat this answer.")

    vad_recorder.enter_gated_mode.assert_not_called()
    vad_recorder.pause.assert_called_once()
    vad_recorder.suspend_stream.assert_called_once()
    vad_recorder.prime_with_seed.assert_not_called()


def test_speech_start_warms_up_brain() -> None:
    turn_state = TurnState()
    brain = MagicMock()
    vad_recorder = MagicMock()

    coordinator = _make_coordinator(turn_state, vad_recorder=vad_recorder, brain=brain)
    coordinator.on_vad_speech_start()

    brain.warm_up.assert_called_once()
