"""Thread-safe owner of the per-turn flags shared across Klaus's threads.

The Qt main thread (key handlers, Stop button), the VAD audio-callback
thread, the audio-output callback thread (barge-in), and the pipeline worker
thread all read and mutate the same turn flags. TurnState puts them behind
one lock so a cancel always targets the current turn's event and a barge-in
seed cannot be dropped or double-applied while a turn tears down.
"""

from __future__ import annotations

import threading

import numpy as np


class TurnState:
    """Turn lifecycle flags, cancel event, and cross-turn handoff buffers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._processing = False
        self._speaking = False
        self._cancel_event = threading.Event()
        self._barge_in_seed: np.ndarray | None = None
        self._queued_ptt_wav: bytes | None = None

    # -- Reads --

    @property
    def processing(self) -> bool:
        with self._lock:
            return self._processing

    @property
    def speaking(self) -> bool:
        with self._lock:
            return self._speaking

    @property
    def has_queued_ptt_wav(self) -> bool:
        with self._lock:
            return self._queued_ptt_wav is not None

    def snapshot(self) -> tuple[bool, bool]:
        """Return (processing, speaking) read atomically."""
        with self._lock:
            return self._processing, self._speaking

    # -- Turn lifecycle --

    def begin_turn(self) -> threading.Event:
        """Mark a question turn active and return its fresh cancel event.

        Called before the worker thread spawns, so a stop request arriving
        from any thread after this point targets this turn's event.
        """
        with self._lock:
            self._processing = True
            self._cancel_event = threading.Event()
            return self._cancel_event

    def end_turn(self) -> tuple[np.ndarray | None, bytes | None]:
        """Clear the turn flags and consume the cross-turn buffers.

        Returns (barge_in_seed, queued_ptt_wav) atomically, so a barge-in
        landing after this call is rejected (speaking is already False)
        rather than leaking into a turn that no longer exists.
        """
        with self._lock:
            self._processing = False
            self._speaking = False
            seed, self._barge_in_seed = self._barge_in_seed, None
            wav, self._queued_ptt_wav = self._queued_ptt_wav, None
            return seed, wav

    def begin_replay(self) -> threading.Event:
        """Mark a replay (speaking only) active and return its cancel event."""
        with self._lock:
            self._speaking = True
            self._barge_in_seed = None
            self._cancel_event = threading.Event()
            return self._cancel_event

    def end_replay(self) -> np.ndarray | None:
        """Clear the speaking flag and consume any barge-in seed."""
        with self._lock:
            self._speaking = False
            seed, self._barge_in_seed = self._barge_in_seed, None
            return seed

    def speaking_started(self) -> None:
        with self._lock:
            self._speaking = True

    # -- Signals into the current turn --

    def request_cancel(self) -> bool:
        """Set the current turn's cancel event.

        Returns True when a turn or replay was active. When nothing is
        active the event is still set (harmless: it belongs to a finished
        turn) and False tells the caller there was nothing to cancel.
        """
        with self._lock:
            active = self._processing or self._speaking
            self._cancel_event.set()
            return active

    def barge_in(self, seed: np.ndarray | None) -> bool:
        """Record a barge-in during playback and cancel the turn.

        Returns False when Klaus is not speaking — the barge-in is rejected
        instead of seeding a turn that already ended.
        """
        with self._lock:
            if not self._speaking:
                return False
            self._barge_in_seed = seed
            self._cancel_event.set()
            return True

    def queue_ptt_wav(self, wav_bytes: bytes) -> bool:
        """Hold a PTT recording finished while a turn is still processing.

        Returns False when no turn is processing — the caller should start
        the question immediately instead of queueing it.
        """
        with self._lock:
            if not self._processing:
                return False
            self._queued_ptt_wav = wav_bytes
            return True
