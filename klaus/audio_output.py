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

    def __init__(
        self,
        playback_observer: Callable[[np.ndarray, int], None] | None = None,
    ) -> None:
        self._stream: sd.OutputStream | None = None
        self._stream_lock = threading.Lock()
        self._playback_id = 0
        self._stream_playback_id: int | None = None
        self._playback_observer = playback_observer

    def set_playback_observer(
        self,
        observer: Callable[[np.ndarray, int], None] | None,
    ) -> None:
        """Set the callback that receives audio written to the output stream."""
        self._playback_observer = observer

    def _report_playback(self, audio: np.ndarray, rate: int) -> None:
        observer = self._playback_observer
        if observer is None:
            return
        try:
            observer(audio, rate)
        except Exception:
            logger.exception("Playback observer failed")

    def _begin_playback(self) -> int:
        with self._stream_lock:
            self._playback_id += 1
            self._close_stream_locked()
            return self._playback_id

    def _is_current(self, playback_id: int) -> bool:
        with self._stream_lock:
            return playback_id == self._playback_id

    def _ensure_stream(
        self, rate: int, channels: int, playback_id: int
    ) -> sd.OutputStream | None:
        with self._stream_lock:
            if playback_id != self._playback_id:
                return None
            if self._stream is not None and not self._stream.closed:
                return self._stream
            self._stream = sd.OutputStream(
                samplerate=rate,
                channels=channels,
                dtype="int16",
                latency="high",
            )
            self._stream.start()
            self._stream_playback_id = playback_id
            logger.info("Opened audio output stream (%d Hz, %d ch)", rate, channels)
            return self._stream

    def _close_stream_locked(self) -> None:
        if self._stream is not None and not self._stream.closed:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            logger.info("Closed audio output stream")
        self._stream = None
        self._stream_playback_id = None

    def _close_stream(self, playback_id: int) -> None:
        with self._stream_lock:
            if self._stream_playback_id != playback_id:
                return
            self._close_stream_locked()

    def _write_audio(
        self, stream: sd.OutputStream, audio: np.ndarray, playback_id: int
    ) -> int:
        offset = 0
        while offset < len(audio) and self._is_current(playback_id):
            end = min(offset + WRITE_BLOCK_FRAMES, len(audio))
            try:
                stream.write(audio[offset:end])
            except Exception:
                if not self._is_current(playback_id):
                    logger.debug("Audio write ended during cancellation", exc_info=True)
                    break
                raise
            self._report_playback(audio[offset:end], PCM_SAMPLE_RATE)
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
        playback_id = self._begin_playback()
        first_audio = True
        try:
            while self._is_current(playback_id):
                audio = audio_queue.get()
                if audio is None:
                    break
                if audio.size == 0:
                    continue
                stream = self._ensure_stream(PCM_SAMPLE_RATE, 1, playback_id)
                if stream is None:
                    break
                if first_audio:
                    first_audio = False
                    if on_first_audio:
                        on_first_audio()
                played = self._write_audio(stream, audio, playback_id)
                if played and on_frames_played:
                    on_frames_played(played)
        finally:
            self._close_stream(playback_id)

    def play_pcm(self, audio: np.ndarray) -> None:
        """Play one PCM buffer."""
        playback_id = self._begin_playback()
        if audio.size == 0:
            return
        try:
            stream = self._ensure_stream(PCM_SAMPLE_RATE, 1, playback_id)
            if stream is not None:
                self._write_audio(stream, audio, playback_id)
        finally:
            self._close_stream(playback_id)

    def stop(self) -> None:
        """Stop playback and close the output stream."""
        with self._stream_lock:
            self._playback_id += 1
            self._close_stream_locked()
        logger.info("Audio playback interrupted")
