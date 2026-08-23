import collections
import io
import logging
import math
import threading
import wave
from typing import Callable

import numpy as np
import sounddevice as sd
import webrtcvad

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"

FRAME_DURATION_MS = 30
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 480 samples @ 16 kHz


def to_wav_bytes(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Convert int16 numpy audio to WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


class PushToTalkRecorder:
    """Records audio while a key is held, producing a WAV buffer on release."""

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self._sample_rate = sample_rate
        self._recording = False
        self._chunks: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()

    def start_recording(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._chunks = []
            self._recording = True
            try:
                dev = sd.query_devices(kind="input")
                logger.info(
                    "Recording started (mic: %s, %d Hz)",
                    dev.get("name", "unknown"), self._sample_rate,
                )
            except Exception:
                logger.info("Recording started (%d Hz)", self._sample_rate)
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=self._audio_callback,
            )
            self._stream.start()

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.warning("Audio input status: %s", status)
        if self._recording:
            self._chunks.append(indata.copy())

    def stop_recording(self) -> bytes | None:
        """Stop recording and return WAV bytes, or None if nothing was captured."""
        with self._lock:
            if not self._recording:
                return None
            self._recording = False
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None

            if not self._chunks:
                logger.info("Recording stopped (no audio captured)")
                return None

            audio_data = np.concatenate(self._chunks, axis=0)
            duration = len(audio_data) / self._sample_rate
            logger.info("Recording stopped (%.1fs, %d samples)", duration, len(audio_data))
            return to_wav_bytes(audio_data, self._sample_rate)

    @property
    def is_recording(self) -> bool:
        return self._recording


class VoiceActivatedRecorder:
    """Continuously listens and uses webrtcvad to detect speech boundaries."""

    def __init__(
        self,
        on_speech_start: Callable[[], None],
        on_speech_end: Callable[[bytes], None],
        on_speech_discard: Callable[[str], None] | None = None,
        on_speech_maybe_end: Callable[[bytes], None] | None = None,
        on_barge_in: Callable[[np.ndarray], None] | None = None,
        sample_rate: int = SAMPLE_RATE,
        sensitivity: int = 2,
        silence_timeout: float = 1.5,
        early_silence_timeout: float = 0.0,
        min_voiced_ratio: float = 0.25,
        min_voiced_frames: int = 5,
        min_duration: float = 0.3,
        min_rms_dbfs: float = -45.0,
        min_voiced_run_frames: int = 6,
        start_trigger_ms: int = 90,
        barge_in_min_voiced_ms: int = 120,
        barge_in_rms_margin_dbfs: float = 4.0,
        device: int | None = None,
    ):
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._on_speech_discard = on_speech_discard
        self._on_speech_maybe_end = on_speech_maybe_end
        self._on_barge_in = on_barge_in
        self._sample_rate = sample_rate
        self._device = device
        self._sensitivity = max(0, min(3, sensitivity))
        self._silence_timeout = silence_timeout
        self._min_voiced_ratio = max(0.0, min(1.0, min_voiced_ratio))
        self._min_voiced_frames = max(1, min_voiced_frames)
        self._min_duration = max(0.0, min_duration)
        self._min_rms_dbfs = float(min_rms_dbfs)
        self._min_voiced_run_frames = max(1, min_voiced_run_frames)
        self._start_run_needed = max(
            1,
            math.ceil(max(0, start_trigger_ms) / FRAME_DURATION_MS),
        )

        self._vad = webrtcvad.Vad(self._sensitivity)
        self._stream: sd.InputStream | None = None
        self._lock = threading.Lock()
        self._paused = False
        self._running = False
        self._settle_frames = 0

        self._speaking = False
        self._chunks: list[np.ndarray] = []
        self._silent_frames = 0
        self._voiced_frames = 0
        self._total_frames = 0
        self._current_voiced_run = 0
        self._max_voiced_run = 0
        self._start_voiced_run = 0
        self._frames_for_timeout = int(
            self._silence_timeout / (FRAME_DURATION_MS / 1000)
        )
        frames_for_early = int(early_silence_timeout / (FRAME_DURATION_MS / 1000))
        # Speculative early end-of-speech only makes sense strictly before
        # the final timeout.
        if 0 < frames_for_early < self._frames_for_timeout:
            self._frames_for_early = frames_for_early
        else:
            self._frames_for_early = 0

        # Barge-in gate: responsive speech detection while Klaus is speaking.
        self._gated = False
        self._gate_vad = webrtcvad.Vad(min(self._sensitivity, 2))
        self._gate_run_needed = max(
            1,
            math.ceil(barge_in_min_voiced_ms / FRAME_DURATION_MS),
        )
        self._gate_rms_margin = float(barge_in_rms_margin_dbfs)
        # Output can reach the microphone after the playback callback starts.
        # Keep the gate closed long enough to measure that delayed speaker bleed.
        self._gate_calib_frames = 20  # ~600ms of playback bleed calibration
        self._gate_seed_prefix_frames = 3  # keep ~90ms before detected speech
        self._gate_calib: list[float] = []
        self._gate_floor_dbfs = self._min_rms_dbfs
        self._gate_run = 0
        gate_buffer_frames = int(1000 / FRAME_DURATION_MS)  # keep last ~1s
        self._gate_frames: collections.deque[np.ndarray] = collections.deque(
            maxlen=gate_buffer_frames
        )

        pre_buffer_ms = 300
        pre_buffer_count = int(pre_buffer_ms / FRAME_DURATION_MS)
        self._pre_buffer: collections.deque[np.ndarray] = collections.deque(
            maxlen=pre_buffer_count
        )
        self._sample_buf = np.empty(0, dtype=np.int16)

    def start(self) -> None:
        """Open the mic stream and begin VAD detection."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._paused = False
            self._speaking = False
            self._chunks = []
            self._silent_frames = 0
            self._voiced_frames = 0
            self._total_frames = 0
            self._current_voiced_run = 0
            self._max_voiced_run = 0
            self._start_voiced_run = 0
            self._pre_buffer.clear()
            self._sample_buf = np.empty(0, dtype=np.int16)

            try:
                dev = sd.query_devices(kind="input")
                logger.info(
                    "VAD started (mic: %s, %d Hz, sensitivity=%d)",
                    dev.get("name", "unknown"),
                    self._sample_rate,
                    self._sensitivity,
                )
            except Exception:
                logger.info(
                    "VAD started (%d Hz, sensitivity=%d)",
                    self._sample_rate,
                    self._sensitivity,
                )

            try:
                self._stream = sd.InputStream(
                    samplerate=self._sample_rate,
                    channels=CHANNELS,
                    dtype=DTYPE,
                    blocksize=FRAME_SIZE,
                    device=self._device,
                    callback=self._audio_callback,
                )
                self._stream.start()
            except Exception as exc:
                self._running = False
                logger.error("Failed to open mic for VAD: %s", exc)
                return

    def enter_gated_mode(self) -> None:
        """Listen for barge-in speech while Klaus plays audio.

        The mic stream stays open, but frames must pass a stricter gate
        (max-aggressiveness VAD, RMS above the calibrated playback-bleed
        floor, sustained voiced run) before on_barge_in fires. Calibration
        uses the first ~600ms of frames after entering the mode.
        """
        self._gate_calib = []
        self._gate_floor_dbfs = self._min_rms_dbfs
        self._gate_run = 0
        self._gate_frames.clear()
        self._gated = True
        logger.debug("VAD gated mode entered")

    def exit_gated_mode(self) -> None:
        self._gated = False
        logger.debug("VAD gated mode exited")

    def prime_with_seed(self, seed: np.ndarray) -> None:
        """Begin a new utterance pre-loaded with barge-in audio.

        Called after a barge-in interrupt so the user's first words (captured
        by the gate buffer while Klaus was still speaking) aren't clipped.
        """
        self._settle_frames = 0
        n_frames = max(1, len(seed) // FRAME_SIZE)
        self._chunks = [seed.astype(np.int16)]
        self._silent_frames = 0
        # The seed passed the barge-in gate, so count it as voiced.
        self._voiced_frames = n_frames
        self._total_frames = n_frames
        self._current_voiced_run = n_frames
        self._max_voiced_run = n_frames
        self._speaking = True
        logger.debug("VAD primed with %d barge-in seed frames", n_frames)
        try:
            self._on_speech_start()
        except Exception:
            logger.exception("on_speech_start callback failed")

    def stop(self) -> None:
        """Stop the stream and discard any in-progress speech."""
        with self._lock:
            self._running = False
            self._gated = False
            self._speaking = False
            self._chunks = []
            self._silent_frames = 0
            self._voiced_frames = 0
            self._total_frames = 0
            self._current_voiced_run = 0
            self._max_voiced_run = 0
            self._start_voiced_run = 0
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
            logger.info("VAD stopped")

    def pause(self) -> None:
        """Pause detection (e.g. while Klaus is speaking)."""
        self._paused = True
        if self._speaking:
            self._speaking = False
            self._chunks = []
            self._silent_frames = 0
            self._voiced_frames = 0
            self._total_frames = 0
            self._current_voiced_run = 0
            self._max_voiced_run = 0
            self._start_voiced_run = 0
        logger.debug("VAD paused")

    def resume(self, settle_ms: int = 0) -> None:
        """Resume detection after pause, optionally dropping warm-up audio."""
        self._paused = False
        self._settle_frames = max(
            0,
            math.ceil(max(0, settle_ms) / FRAME_DURATION_MS),
        )
        self._pre_buffer.clear()
        self._sample_buf = np.empty(0, dtype=np.int16)
        self._voiced_frames = 0
        self._total_frames = 0
        self._current_voiced_run = 0
        self._max_voiced_run = 0
        self._start_voiced_run = 0
        logger.debug("VAD resumed")

    def suspend_stream(self) -> None:
        """Stop the physical mic stream. Safe to call from non-callback threads.

        Use this (instead of pause) when you need to free the CoreAudio device,
        e.g. before audio playback. Call resume_stream() to reopen.
        """
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        logger.debug("VAD stream suspended")

    def resume_stream(self) -> None:
        """Reopen the physical mic stream after suspend_stream()."""
        if self._running and self._stream is None:
            try:
                self._stream = sd.InputStream(
                    samplerate=self._sample_rate,
                    channels=CHANNELS,
                    dtype=DTYPE,
                    blocksize=FRAME_SIZE,
                    device=self._device,
                    callback=self._audio_callback,
                )
                self._stream.start()
            except Exception as exc:
                logger.error("Failed to reopen mic stream: %s", exc)
                return
        logger.debug("VAD stream resumed")

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            logger.debug("VAD audio status: %s", status)
        if not self._running:
            return
        if self._paused and not self._gated:
            return

        samples = indata[:, 0].copy() if indata.ndim > 1 else indata.copy().flatten()
        self._sample_buf = np.concatenate([self._sample_buf, samples])

        while len(self._sample_buf) >= FRAME_SIZE:
            frame = self._sample_buf[:FRAME_SIZE]
            self._sample_buf = self._sample_buf[FRAME_SIZE:]
            if self._settle_frames:
                self._settle_frames -= 1
                continue
            if self._gated:
                self._process_gate_frame(frame)
            elif not self._paused:
                self._process_frame(frame)

    def _process_gate_frame(self, frame: np.ndarray) -> None:
        """Barge-in detection while Klaus is speaking (gated mode)."""
        self._gate_frames.append(frame)
        rms_dbfs = self._compute_rms_dbfs(frame)

        if len(self._gate_calib) < self._gate_calib_frames:
            self._gate_calib.append(rms_dbfs)
            if len(self._gate_calib) == self._gate_calib_frames:
                bleed = float(np.percentile(self._gate_calib, 90))
                self._gate_floor_dbfs = max(
                    self._min_rms_dbfs, bleed + self._gate_rms_margin
                )
                logger.debug(
                    "Barge-in gate calibrated (bleed=%.1f dBFS, floor=%.1f dBFS)",
                    bleed,
                    self._gate_floor_dbfs,
                )
            return

        frame_bytes = frame.astype(np.int16).tobytes()
        is_speech = self._gate_vad.is_speech(frame_bytes, self._sample_rate)
        if is_speech and rms_dbfs >= self._gate_floor_dbfs:
            self._gate_run += 1
        else:
            self._gate_run = 0

        if self._gate_run >= self._gate_run_needed:
            self._gated = False
            self._gate_run = 0
            seed_frame_count = self._gate_run_needed + self._gate_seed_prefix_frames
            seed = np.concatenate(list(self._gate_frames)[-seed_frame_count:])
            self._gate_frames.clear()
            logger.info("Barge-in detected (%.1fs of gated audio buffered)",
                        len(seed) / self._sample_rate)
            if self._on_barge_in is not None:
                try:
                    self._on_barge_in(seed)
                except Exception:
                    logger.exception("on_barge_in callback failed")

    def _process_frame(self, frame: np.ndarray) -> None:
        frame_bytes = frame.astype(np.int16).tobytes()
        is_speech = self._vad.is_speech(frame_bytes, self._sample_rate)

        if not self._speaking:
            self._pre_buffer.append(frame)
            rms_dbfs = self._compute_rms_dbfs(frame)
            if is_speech and rms_dbfs >= self._min_rms_dbfs:
                self._start_voiced_run += 1
            else:
                self._start_voiced_run = 0

            if self._start_voiced_run >= self._start_run_needed:
                buffered_frames = list(self._pre_buffer)
                self._speaking = True
                self._silent_frames = 0
                self._chunks = buffered_frames
                self._pre_buffer.clear()
                self._voiced_frames = self._start_voiced_run
                self._total_frames = len(buffered_frames)
                self._current_voiced_run = self._start_voiced_run
                self._max_voiced_run = self._start_voiced_run
                self._start_voiced_run = 0
                logger.debug(
                    "VAD: speech started after %d confirmed frames",
                    self._start_run_needed,
                )
                try:
                    self._on_speech_start()
                except Exception:
                    logger.exception("on_speech_start callback failed")
        else:
            self._chunks.append(frame)
            self._total_frames += 1
            if is_speech:
                self._voiced_frames += 1
                self._silent_frames = 0
                self._current_voiced_run += 1
                self._max_voiced_run = max(self._max_voiced_run, self._current_voiced_run)
            else:
                self._silent_frames += 1
                self._current_voiced_run = 0
                if (
                    self._frames_for_early
                    and self._silent_frames == self._frames_for_early
                    and self._on_speech_maybe_end is not None
                    and self._chunks
                ):
                    audio = np.concatenate(self._chunks)
                    try:
                        self._on_speech_maybe_end(to_wav_bytes(audio, self._sample_rate))
                    except Exception:
                        logger.exception("on_speech_maybe_end callback failed")
                if self._silent_frames >= self._frames_for_timeout:
                    self._finalize()

    def _finalize(self) -> None:
        """Package accumulated chunks into WAV and fire callback."""
        self._speaking = False
        self._silent_frames = 0
        if not self._chunks:
            return

        audio = np.concatenate(self._chunks)
        self._chunks = []
        voiced_frames = self._voiced_frames
        total_frames = self._total_frames
        max_voiced_run = self._max_voiced_run
        self._voiced_frames = 0
        self._total_frames = 0
        self._current_voiced_run = 0
        self._max_voiced_run = 0

        duration = len(audio) / self._sample_rate
        voiced_ratio = (voiced_frames / total_frames) if total_frames else 0.0
        rms_dbfs = self._compute_rms_dbfs(audio)
        logger.info(
            (
                "VAD: speech ended (%.1fs, %d samples, voiced_ratio=%.2f, "
                "max_voiced_run=%d, rms_dbfs=%.1f)"
            ),
            duration,
            len(audio),
            voiced_ratio,
            max_voiced_run,
            rms_dbfs,
        )

        if duration < self._min_duration:
            logger.debug(
                "VAD: discarding short utterance (%.1fs < %.1fs)",
                duration,
                self._min_duration,
            )
            self._emit_discard("vad_short_duration")
            self._emit_speech_end(b"")
            return

        if voiced_frames < self._min_voiced_frames:
            logger.info(
                "VAD: discarding low-voice utterance (%d voiced frames < %d)",
                voiced_frames,
                self._min_voiced_frames,
            )
            self._emit_discard("vad_low_voiced_frames")
            self._emit_speech_end(b"")
            return

        if voiced_ratio < self._min_voiced_ratio:
            logger.info(
                "VAD: discarding low-voice utterance (ratio=%.2f < %.2f)",
                voiced_ratio,
                self._min_voiced_ratio,
            )
            self._emit_discard("vad_low_voiced_ratio")
            self._emit_speech_end(b"")
            return

        if max_voiced_run < self._min_voiced_run_frames:
            logger.info(
                "VAD: quality gate discarded utterance (max_voiced_run=%d < %d)",
                max_voiced_run,
                self._min_voiced_run_frames,
            )
            self._emit_discard("quality_short_voiced_run")
            self._emit_speech_end(b"")
            return

        if rms_dbfs < self._min_rms_dbfs:
            logger.info(
                "VAD: quality gate discarded utterance (rms_dbfs=%.1f < %.1f)",
                rms_dbfs,
                self._min_rms_dbfs,
            )
            self._emit_discard("quality_low_rms")
            self._emit_speech_end(b"")
            return

        wav = to_wav_bytes(audio, self._sample_rate)
        self._emit_speech_end(wav)

    def _compute_rms_dbfs(self, audio: np.ndarray) -> float:
        """Return clip loudness in dBFS from int16 mono samples."""
        if audio.size == 0:
            return -120.0
        audio_f = audio.astype(np.float32)
        rms = float(np.sqrt(np.mean(np.square(audio_f))))
        if rms <= 0.0:
            return -120.0
        return 20.0 * float(np.log10(rms / 32768.0))

    def _emit_speech_end(self, wav: bytes) -> None:
        """Invoke on_speech_end safely from the audio thread."""
        try:
            self._on_speech_end(wav)
        except Exception:
            logger.exception("on_speech_end callback failed")

    def _emit_discard(self, reason: str) -> None:
        """Invoke on_speech_discard safely from the audio thread."""
        if self._on_speech_discard is None:
            return
        try:
            self._on_speech_discard(reason)
        except Exception:
            logger.exception("on_speech_discard callback failed")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def speculative_gap_bytes(self) -> int:
        """PCM bytes appended between the early maybe-end and finalize.

        If the finalized audio is exactly this much longer than the last
        maybe-end snapshot, no speech resumed and the speculative transcript
        is valid. Returns 0 when speculation is disabled.
        """
        if not self._frames_for_early:
            return 0
        return (self._frames_for_timeout - self._frames_for_early) * FRAME_SIZE * 2


class AudioPlayer:
    """Plays raw PCM or WAV audio through the default output device."""

    def __init__(self, sample_rate: int = 24000):
        self._sample_rate = sample_rate
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

    def play_wav_bytes(self, wav_data: bytes) -> None:
        """Play a complete WAV buffer. Blocks until playback finishes or stop() is called."""
        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            channels = wf.getnchannels()
            n_frames = wf.getnframes()
            frames = wf.readframes(n_frames)

        duration = n_frames / rate if rate else 0
        logger.debug("Playing audio (%.1fs, %d Hz)", duration, rate)

        audio = np.frombuffer(frames, dtype=np.int16)
        if channels > 1:
            audio = audio.reshape(-1, channels)

        self._stop_event.clear()
        sd.play(audio, samplerate=rate)
        while sd.get_stream().active and not self._stop_event.is_set():
            sd.sleep(50)
        if self._stop_event.is_set():
            sd.stop()

    def stop(self) -> None:
        self._stop_event.set()
        sd.stop()
