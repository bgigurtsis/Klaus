"""Speculative speech-to-text that runs during the VAD silence window.

The recorder fires ``on_speech_maybe_end`` after a short early silence
threshold, well before the final silence timeout. Starting STT on that
snapshot lets transcription overlap the remaining silence wait. At finalize,
the speculative transcript is valid only if no speech resumed after the
snapshot, which the caller verifies by the exact PCM-length gap between the
snapshot and the finalized audio (silence frames accumulate deterministically
at one frame per 30ms).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class SpeculativeTranscriber:
    """Runs STT on probable end-of-speech audio ahead of the final timeout."""

    def __init__(self, transcribe: Callable[[bytes], str]) -> None:
        self._transcribe = transcribe
        self._lock = threading.Lock()
        self._generation = 0
        self._wav: bytes | None = None
        self._thread: threading.Thread | None = None
        self._result: str | None = None

    def start(self, wav_bytes: bytes) -> None:
        """Kick off speculative transcription for an early-silence snapshot."""
        with self._lock:
            self._generation += 1
            generation = self._generation
            self._wav = wav_bytes
            self._result = None
            self._thread = threading.Thread(
                target=self._worker, args=(wav_bytes, generation), daemon=True
            )
            thread = self._thread
        thread.start()

    def _worker(self, wav_bytes: bytes, generation: int) -> None:
        try:
            result = self._transcribe(wav_bytes)
        except Exception:
            logger.exception("Speculative transcription failed")
            result = None
        with self._lock:
            if generation == self._generation:
                self._result = result

    def collect(self, final_wav: bytes, expected_gap_bytes: int) -> str | None:
        """Return the speculative transcript if it matches the final audio.

        Valid only when the finalized audio is exactly ``expected_gap_bytes``
        longer than the speculative snapshot (i.e. only silence was appended
        after the snapshot). Returns None when there is no valid speculation;
        the caller should transcribe final_wav normally.
        """
        with self._lock:
            wav = self._wav
            thread = self._thread
        if wav is None or thread is None or expected_gap_bytes <= 0:
            return None
        if len(final_wav) - len(wav) != expected_gap_bytes:
            logger.debug(
                "Speculative transcript invalid (gap=%d, expected=%d)",
                len(final_wav) - len(wav),
                expected_gap_bytes,
            )
            self.clear()
            return None

        thread.join()
        with self._lock:
            result = self._result
        self.clear()
        if result is not None:
            logger.info("Using speculative transcript (%d chars)", len(result))
        return result

    def clear(self) -> None:
        """Invalidate any pending speculation (discarded utterance, etc.)."""
        with self._lock:
            self._generation += 1
            self._wav = None
            self._thread = None
            self._result = None
