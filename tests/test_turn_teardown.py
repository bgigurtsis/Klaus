"""Turn-teardown sequencing tests for the coordinator."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, call, patch

import numpy as np

from klaus.services.turn_coordinator import TurnCoordinator
from klaus.services.turn_state import TurnState


def _coordinator(
    turn_state: TurnState,
    *,
    vad_recorder: MagicMock,
    pipeline: MagicMock,
    input_mode: str = "voice_activation",
) -> TurnCoordinator:
    return TurnCoordinator(
        turn_state=turn_state,
        speculative_stt=MagicMock(),
        stt=MagicMock(),
        audio_output=MagicMock(),
        signals=MagicMock(),
        get_vad_recorder=lambda: vad_recorder,
        get_ptt_recorder=MagicMock(),
        get_pipeline=lambda: pipeline,
        get_brain=MagicMock(),
        get_input_mode=lambda: input_mode,
        get_current_session_id=lambda: None,
        update_exchange_count=MagicMock(),
    )


def test_voice_turn_teardown_restores_mic_in_order() -> None:
    """After a voice turn: exit gated mode, resume the stream, resume VAD,
    then prime the barge-in seed — priming before resume would drop it."""
    turn_state = TurnState()
    vad_recorder = MagicMock()
    pipeline = MagicMock()
    seed = np.array([1, 2, 3], dtype=np.int16)
    def run_and_barge_in(*_a, **_k):
        turn_state.speaking_started()
        turn_state.barge_in(seed)

    pipeline.run.side_effect = run_and_barge_in

    coordinator = _coordinator(turn_state, vad_recorder=vad_recorder, pipeline=pipeline)
    cancel_event = turn_state.begin_turn()
    with patch("klaus.services.turn_coordinator.config.BARGE_IN_ENABLED", True):
        coordinator._process_question(b"wav", cancel_event)

    ordered = [
        c
        for c in vad_recorder.mock_calls
        if c[0]
        in {"exit_gated_mode", "resume_stream", "resume", "prime_with_seed"}
    ]
    assert [c[0] for c in ordered] == [
        "exit_gated_mode",
        "resume_stream",
        "resume",
        "prime_with_seed",
    ]
    assert not turn_state.processing


def test_ptt_teardown_starts_queued_question() -> None:
    turn_state = TurnState()
    vad_recorder = MagicMock()
    pipeline = MagicMock()
    coordinator = _coordinator(
        turn_state, vad_recorder=vad_recorder, pipeline=pipeline, input_mode="push_to_talk"
    )

    cancel_event = turn_state.begin_turn()
    assert turn_state.queue_ptt_wav(b"queued")
    started: list[bytes] = []
    coordinator.start_question_thread = lambda wav: started.append(wav)

    coordinator._process_question(b"first", cancel_event)

    assert started == [b"queued"]
    vad_recorder.exit_gated_mode.assert_not_called()


def test_failing_turn_still_ends_turn_state() -> None:
    turn_state = TurnState()
    vad_recorder = MagicMock()
    pipeline = MagicMock()
    pipeline.run.side_effect = RuntimeError("boom")
    coordinator = _coordinator(turn_state, vad_recorder=vad_recorder, pipeline=pipeline)

    cancel_event = turn_state.begin_turn()
    coordinator._process_question(b"wav", cancel_event)

    assert not turn_state.processing
    vad_recorder.resume_stream.assert_called_once()
