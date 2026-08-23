"""PCM audio playback for live-model responses and app cues."""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

PCM_SAMPLE_RATE = 24_000
WRITE_BLOCK_FRAMES = 2_048


class AudioOutput:
    """Play 24 kHz PCM audio through one persistent output stream."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._stream: sd.OutputStream | None = None
        self._stream_lock = threading.Lock()

    def _ensure_stream(self, rate: int, channels: int) -> sd.OutputStream:
        with self._stream_lock:
            if self._stream is not None and not self._stream.closed:
                return self._stream
            self._stream = sd.OutputStream(
                samplerate=rate,
                channels=channels,
                dtype="int16",
                latency="high",
            )
            self._stream.start()
            logger.info("Opened audio output stream (%d Hz, %d ch)", rate, channels)
            return self._stream

    def _close_stream(self) -> None:
        with self._stream_lock:
            if self._stream is not None and not self._stream.closed:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                logger.info("Closed audio output stream")
            self._stream = None

    def _write_audio(self, stream: sd.OutputStream, audio: np.ndarray) -> int:
        offset = 0
        while offset < len(audio) and not self._stop_event.is_set():
            end = min(offset + WRITE_BLOCK_FRAMES, len(audio))
            try:
                stream.write(audio[offset:end])
            except Exception:
                if self._stop_event.is_set():
                    logger.debug("Audio write ended during cancellation", exc_info=True)
                    break
                raise
            offset = end
        return offset

    def play_pcm_stream(
        self,
        audio_queue: queue.Queue[np.ndarray | None],
        *,
        on_first_audio: Callable[[], None] | None = None,
        on_frames_played: Callable[[int], None] | None = None,
    ) -> None:
        """Play a live 24 kHz PCM stream from the Realtime API."""
        self._stop_event.clear()
        first_audio = True
        try:
            while not self._stop_event.is_set():
                audio = audio_queue.get()
                if audio is None:
                    break
                if audio.size == 0:
                    continue
                stream = self._ensure_stream(PCM_SAMPLE_RATE, 1)
                if first_audio:
                    first_audio = False
                    if on_first_audio:
                        on_first_audio()
                played = self._write_audio(stream, audio)
                if played and on_frames_played:
                    on_frames_played(played)
        finally:
            self._close_stream()

    def play_pcm(self, audio: np.ndarray) -> None:
        """Play one PCM buffer."""
        self._stop_event.clear()
        if audio.size == 0:
            return
        try:
            stream = self._ensure_stream(PCM_SAMPLE_RATE, 1)
            self._write_audio(stream, audio)
        finally:
            self._close_stream()

    def stop(self) -> None:
        """Stop playback and close the output stream."""
        self._stop_event.set()
        self._close_stream()
        logger.info("Audio playback interrupted")
