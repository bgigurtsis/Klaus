from __future__ import annotations

import threading

import numpy as np

from klaus.services.turn_state import TurnState


def test_begin_turn_returns_fresh_event_and_marks_processing():
    state = TurnState()
    event = state.begin_turn()

    assert state.processing is True
    assert state.speaking is False
    assert not event.is_set()


def test_cancel_targets_current_turn_not_stale_event():
    state = TurnState()
    old_event = state.begin_turn()
    state.end_turn()

    new_event = state.begin_turn()
    assert state.request_cancel() is True

    assert new_event.is_set()
    assert not old_event.is_set()


def test_request_cancel_reports_inactive_when_no_turn():
    state = TurnState()
    assert state.request_cancel() is False


def test_end_turn_consumes_seed_and_queued_wav_atomically():
    state = TurnState()
    state.begin_turn()
    state.speaking_started()
    assert state.barge_in(np.array([1, 2, 3])) is True
    state.queue_ptt_wav(b"queued")

    seed, wav = state.end_turn()

    assert seed is not None
    assert wav == b"queued"
    assert state.end_turn() == (None, None)
    assert state.processing is False
    assert state.speaking is False


def test_barge_in_rejected_when_not_speaking():
    state = TurnState()
    state.begin_turn()

    assert state.barge_in(np.array([1])) is False
    seed, _ = state.end_turn()
    assert seed is None


def test_barge_in_after_end_turn_does_not_leak_seed():
    state = TurnState()
    state.begin_turn()
    state.speaking_started()
    state.end_turn()

    assert state.barge_in(np.array([1])) is False
    seed, _ = state.end_turn()
    assert seed is None


def test_replay_lifecycle_clears_prior_seed():
    state = TurnState()
    state.begin_turn()
    state.speaking_started()
    state.barge_in(np.array([1]))
    state.end_turn()

    event = state.begin_replay()
    assert state.speaking is True
    assert not event.is_set()

    state.barge_in(np.array([2]))
    seed = state.end_replay()
    assert seed is not None
    assert state.speaking is False


def test_snapshot_returns_both_flags():
    state = TurnState()
    state.begin_turn()
    state.speaking_started()

    assert state.snapshot() == (True, True)
    state.end_turn()
    assert state.snapshot() == (False, False)


def test_concurrent_stop_and_new_turn_never_loses_cancel():
    """A stop that observes an active turn must always land on that turn."""
    state = TurnState()
    iterations = 200

    for _ in range(iterations):
        event = state.begin_turn()

        stopper = threading.Thread(target=state.request_cancel)
        stopper.start()
        stopper.join()

        assert event.is_set()
        state.end_turn()


def test_concurrent_barge_in_and_teardown_is_atomic():
    """Barge-in racing end_turn either seeds that turn or is rejected."""
    state = TurnState()

    for _ in range(200):
        state.begin_turn()
        state.speaking_started()
        results: list[bool] = []

        def do_barge_in() -> None:
            results.append(state.barge_in(np.array([1])))

        barge_thread = threading.Thread(target=do_barge_in)
        barge_thread.start()
        seed, _ = state.end_turn()
        barge_thread.join()

        accepted = results[0]
        if accepted:
            leftover, _ = state.end_turn()
            assert (seed is not None) or (leftover is not None)
        else:
            assert seed is None
            assert state.end_turn() == (None, None)
