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
    audio_output: MagicMock | None = None,
) -> TurnCoordinator:
    return TurnCoordinator(
        turn_state=turn_state,
        speculative_stt=MagicMock(),
        stt=MagicMock(),
        audio_output=audio_output if audio_output is not None else MagicMock(),
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
    """After a voice turn: wait for the speaker to drain, exit gated mode,
    resume the stream, resume VAD, then prime the barge-in seed — draining
    later would let the audible tail hit the ungated VAD, and priming
    before resume would drop the seed."""
    turn_state = TurnState()
    manager = MagicMock()
    vad_recorder = manager.vad
    audio_output = manager.audio
    pipeline = MagicMock()
    seed = np.array([1, 2, 3], dtype=np.int16)
    def run_and_barge_in(*_a, **_k):
        turn_state.speaking_started()
        turn_state.barge_in(seed)

    pipeline.run.side_effect = run_and_barge_in

    coordinator = _coordinator(
        turn_state,
        vad_recorder=vad_recorder,
        pipeline=pipeline,
        audio_output=audio_output,
    )
    cancel_event = turn_state.begin_turn()
    with patch("klaus.services.turn_coordinator.config.BARGE_IN_ENABLED", True):
        coordinator._process_question(b"wav", cancel_event)

    watched = {
        "audio.wait_for_drain",
        "vad.exit_gated_mode",
        "vad.resume_stream",
        "vad.resume",
        "vad.prime_with_seed",
    }
    ordered = [c[0] for c in manager.mock_calls if c[0] in watched]
    assert ordered == [
        "audio.wait_for_drain",
        "vad.exit_gated_mode",
        "vad.resume_stream",
        "vad.resume",
        "vad.prime_with_seed",
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


def test_ptt_turn_skips_drain_wait() -> None:
    turn_state = TurnState()
    audio_output = MagicMock()
    coordinator = _coordinator(
        turn_state,
        vad_recorder=MagicMock(),
        pipeline=MagicMock(),
        input_mode="push_to_talk",
        audio_output=audio_output,
    )

    cancel_event = turn_state.begin_turn()
    coordinator._process_question(b"wav", cancel_event)

    audio_output.wait_for_drain.assert_not_called()


def test_barge_in_during_drain_tail_seeds_next_turn() -> None:
    """A barge-in landing while the speaker tail drains (after the pipeline
    returned but before end_turn) still primes the next utterance."""
    turn_state = TurnState()
    vad_recorder = MagicMock()
    audio_output = MagicMock()
    pipeline = MagicMock()
    seed = np.array([4, 5, 6], dtype=np.int16)

    pipeline.run.side_effect = lambda *_a, **_k: turn_state.speaking_started()
    audio_output.wait_for_drain.side_effect = lambda: turn_state.barge_in(seed)

    coordinator = _coordinator(
        turn_state,
        vad_recorder=vad_recorder,
        pipeline=pipeline,
        audio_output=audio_output,
    )
    cancel_event = turn_state.begin_turn()
    with patch("klaus.services.turn_coordinator.config.BARGE_IN_ENABLED", True):
        coordinator._process_question(b"wav", cancel_event)

    vad_recorder.prime_with_seed.assert_called_once()
    np.testing.assert_array_equal(
        vad_recorder.prime_with_seed.call_args.args[0], seed
    )


def test_replay_waits_for_drain_before_resuming_mic() -> None:
    turn_state = TurnState()
    manager = MagicMock()
    coordinator = _coordinator(
        turn_state,
        vad_recorder=manager.vad,
        pipeline=MagicMock(),
        audio_output=manager.audio,
    )

    with patch("klaus.services.turn_coordinator.config.BARGE_IN_ENABLED", True):
        coordinator.replay("hello again")

    watched = {"audio.wait_for_drain", "vad.exit_gated_mode", "vad.resume_stream"}
    ordered = [c[0] for c in manager.mock_calls if c[0] in watched]
    assert ordered == [
        "audio.wait_for_drain",
        "vad.exit_gated_mode",
        "vad.resume_stream",
    ]


def test_barge_in_increments_guard_stat() -> None:
    turn_state = TurnState()
    coordinator = _coordinator(
        turn_state, vad_recorder=MagicMock(), pipeline=MagicMock()
    )
    turn_state.begin_turn()
    turn_state.speaking_started()

    coordinator.on_barge_in(np.array([1], dtype=np.int16))

    with coordinator._guard_stats_lock:
        assert coordinator._guard_stats["barge_in"] == 1


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
