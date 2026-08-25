"""Voice-turn coordination: VAD callbacks, PTT, barge-in, replay, stop.

Everything that starts, cancels, or tears down a voice turn lives here,
driven by TurnState. Mutable collaborators (recorders, pipeline, brain,
input mode) are read through getters because KlausApp hot-swaps them on
device switches and settings changes.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable

import klaus.config as config
from klaus.services.question_pipeline import (
    PipelineContext,
    PipelineHooks,
    Transcription,
)
from klaus.services.turn_state import TurnState

logger = logging.getLogger(__name__)


def _format_guard_stats(stats: dict[str, int]) -> str:
    """Render guard stats as key=value pairs for one log line."""
    return " ".join(f"{key}={value}" for key, value in stats.items())


def _new_guard_stats() -> dict[str, int]:
    """Create a fresh per-session STT guard stats dict."""
    return {
        "vad_discarded": 0,
        "quality_gate_discarded": 0,
        "barge_in": 0,
        "echo_discarded": 0,
    }


_WORD_RE = re.compile(r"[a-z0-9']+")
# Keep roughly the last minute of assistant speech for echo matching.
_RECENT_ASSISTANT_CHARS = 4_000
# A transcript this similar to recent assistant speech is treated as echo.
_ECHO_OVERLAP_THRESHOLD = 0.8
# Echo can only arrive while Klaus speaks or shortly after; outside this
# window a matching transcript is a genuine question reusing the same words.
_ECHO_WINDOW_S = 6.0


def _normalize_words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


class TurnCoordinator:
    def __init__(
        self,
        *,
        turn_state: TurnState,
        speculative_stt,
        stt,
        audio_output,
        signals,
        get_vad_recorder: Callable[[], object],
        get_ptt_recorder: Callable[[], object],
        get_pipeline: Callable[[], object],
        get_brain: Callable[[], object],
        get_input_mode: Callable[[], str],
        get_current_session_id: Callable[[], str | None],
        update_exchange_count: Callable[[], None],
        wake_camera: Callable[[], None] | None = None,
    ) -> None:
        self._turn_state = turn_state
        self._speculative_stt = speculative_stt
        self._stt = stt
        self._audio_output = audio_output
        self._signals = signals
        self._get_vad_recorder = get_vad_recorder
        self._get_ptt_recorder = get_ptt_recorder
        self._get_pipeline = get_pipeline
        self._get_brain = get_brain
        self._get_input_mode = get_input_mode
        self._get_current_session_id = get_current_session_id
        self._update_exchange_count = update_exchange_count
        self._wake_camera = wake_camera
        self._guard_stats = _new_guard_stats()
        self._guard_stats_lock = threading.Lock()
        self._last_failed_wav: bytes | None = None
        self._recent_assistant_text = ""
        self._assistant_active_at = 0.0

    # -- Guard stats --

    def _session_tag(self) -> str:
        session_id = self._get_current_session_id()
        return session_id[:8] if session_id else "none"

    def reset_guard_stats(self) -> None:
        """Reset guard stats whenever the active session changes."""
        with self._guard_stats_lock:
            self._guard_stats = _new_guard_stats()
            snapshot = dict(self._guard_stats)
        logger.info(
            "STT guard stats reset (session=%s): %s",
            self._session_tag(),
            _format_guard_stats(snapshot),
        )

    def _increment_guard_stat(self, key: str, event: str, reason: str = "-") -> None:
        """Increment one guard stat and log a structured snapshot."""
        with self._guard_stats_lock:
            if key not in self._guard_stats:
                return
            self._guard_stats[key] += 1
            snapshot = dict(self._guard_stats)
        logger.info(
            "STT guard event=%s reason=%s session=%s %s",
            event,
            reason,
            self._session_tag(),
            _format_guard_stats(snapshot),
        )

    # -- Echo guard --

    def _on_assistant_text_delta(self, text: str) -> None:
        self._recent_assistant_text = (
            self._recent_assistant_text + text
        )[-_RECENT_ASSISTANT_CHARS:]
        self._assistant_active_at = time.monotonic()
        self._signals.assistant_text_delta.emit(text)

    def _is_echo_of_assistant(self, transcript: str) -> bool:
        """True when a voice transcript is Klaus's own speech from the mic."""
        if time.monotonic() - self._assistant_active_at > _ECHO_WINDOW_S:
            return False
        words = _normalize_words(transcript)
        recent_text = self._recent_assistant_text
        if not words or not recent_text:
            return False
        if len(words) < 3:
            # Too few words for overlap stats: require the exact phrase.
            recent_joined = " ".join(_normalize_words(recent_text))
            is_echo = f" {' '.join(words)} " in f" {recent_joined} "
        else:
            recent_words = set(_normalize_words(recent_text))
            overlap = sum(1 for w in words if w in recent_words) / len(words)
            is_echo = overlap >= _ECHO_OVERLAP_THRESHOLD
        if is_echo:
            self._increment_guard_stat(key="echo_discarded", event="echo_discard")
        return is_echo

    # -- VAD callbacks (audio threads) --

    def on_vad_speech_start(self) -> None:
        if self._get_input_mode() != "voice_activation":
            return
        processing, speaking = self._turn_state.snapshot()
        if speaking:
            self._audio_output.stop()
        if processing and not speaking:
            return
        self._warm_up_brain()
        self._signals.state_changed.emit("listening")

    def on_vad_speech_maybe_end(self, wav_bytes: bytes) -> None:
        """Early silence: start speculative STT on the snapshot."""
        if self._get_input_mode() != "voice_activation" or self._turn_state.processing:
            return
        self._speculative_stt.start(wav_bytes)

    def on_vad_speech_end(self, wav_bytes: bytes) -> None:
        if self._get_input_mode() != "voice_activation":
            return
        if not wav_bytes:
            self._speculative_stt.clear()
            self._signals.state_changed.emit("idle")
            return
        processing, speaking = self._turn_state.snapshot()
        if processing and not speaking:
            return
        self._get_vad_recorder().pause()
        self.start_question_thread(wav_bytes)

    def on_barge_in(self, seed) -> None:
        """The user talked over Klaus: cancel the turn, keep the seed audio."""
        if not self._turn_state.barge_in(seed):
            return
        self._increment_guard_stat(key="barge_in", event="barge_in")
        logger.info("Barge-in: interrupting playback")
        # Cancellation closes the output stream, so keep it off the audio callback.
        threading.Thread(
            target=self._get_pipeline().cancel_active,
            daemon=True,
        ).start()

    def on_vad_discard(self, reason: str) -> None:
        """Track why a VAD candidate was dropped before STT."""
        if reason.startswith("quality_"):
            self._increment_guard_stat(
                key="quality_gate_discarded", event="vad_discard", reason=reason
            )
            return
        self._increment_guard_stat(
            key="vad_discarded", event="vad_discard", reason=reason
        )

    # -- Push-to-talk --

    def on_key_down(self) -> None:
        if self._get_input_mode() != "push_to_talk":
            return
        if self._turn_state.processing:
            self._turn_state.request_cancel()
            self._get_pipeline().cancel_active()
        recorder = self._get_ptt_recorder()
        if recorder.is_recording:
            return
        recorder.start_recording()
        self._warm_up_brain()
        self._signals.state_changed.emit("listening")

    def on_key_up(self) -> None:
        if self._get_input_mode() != "push_to_talk":
            return
        recorder = self._get_ptt_recorder()
        if not recorder.is_recording:
            return
        wav_bytes = recorder.stop_recording()
        if wav_bytes is None:
            self._signals.state_changed.emit("idle")
            return

        if self._turn_state.queue_ptt_wav(wav_bytes):
            self._signals.state_changed.emit("thinking")
            return
        self.start_question_thread(wav_bytes)

    def _warm_up_brain(self) -> None:
        """Overlap the engine's connection handshake with the recording."""
        if self._wake_camera is not None:
            self._wake_camera()
        warm_up = getattr(self._get_brain(), "warm_up", None)
        if callable(warm_up):
            warm_up()

    # -- Turn execution --

    def start_question_thread(self, wav_bytes: bytes) -> None:
        cancel_event = self._turn_state.begin_turn()
        threading.Thread(
            target=self._process_question,
            args=(wav_bytes, cancel_event),
            daemon=True,
        ).start()

    def _voice_transcriber(self):
        """Build a transcriber that prefers a valid speculative transcript."""
        gap = self._get_vad_recorder().speculative_gap_bytes
        speculative = self._speculative_stt

        def transcribe(wav: bytes) -> Transcription:
            result = speculative.collect(wav, gap)
            if result is not None:
                return Transcription(result, speculative_hit=True)
            return Transcription(self._stt.transcribe(wav), speculative_hit=False)

        return transcribe

    def _process_question(
        self, wav_bytes: bytes, cancel_event: threading.Event
    ) -> None:
        input_mode = self._get_input_mode()
        vad_recorder = self._get_vad_recorder()
        voice_mode = input_mode == "voice_activation"
        barge_in_active = voice_mode and config.BARGE_IN_ENABLED
        try:
            context = PipelineContext(
                input_mode=input_mode,
                current_session_id=self._get_current_session_id(),
                # With barge-in the mic stays open (gated) during playback;
                # otherwise suspend it to free the audio device.
                suspend_input_stream=(
                    None if barge_in_active else vad_recorder.suspend_stream
                ),
                cancel_event=cancel_event,
                transcriber=self._voice_transcriber() if voice_mode else None,
                speech_ended_at=vad_recorder.last_voiced_at if voice_mode else None,
                discard_if_echo=self._is_echo_of_assistant if voice_mode else None,
            )
            hooks = PipelineHooks(
                on_state=self._signals.state_changed.emit,
                on_transcription=self._signals.transcription_ready.emit,
                on_response=self._signals.response_ready.emit,
                on_sessions_changed=self._signals.sessions_changed.emit,
                on_exchange_count_updated=self._update_exchange_count,
                on_speaking_started=self._on_pipeline_speaking_started,
                on_assistant_text_delta=self._on_assistant_text_delta,
                on_cancelled=self._on_pipeline_cancelled,
            )
            self._get_pipeline().run(wav_bytes, context=context, hooks=hooks)

        except Exception as e:
            logger.error("Processing failed: %s", e, exc_info=True)
            self._last_failed_wav = wav_bytes
            self._signals.error.emit(str(e))
            self._signals.state_changed.emit("idle")
        else:
            self._last_failed_wav = None
        finally:
            if voice_mode:
                # Keep the barge-in gate armed until the speaker buffer has
                # drained: the audible tail must not reach the ungated VAD.
                self._audio_output.wait_for_drain()
                self._assistant_active_at = time.monotonic()
            seed, queued_wav = self._turn_state.end_turn()
            if voice_mode:
                vad_recorder.exit_gated_mode()
                vad_recorder.resume_stream()
                vad_recorder.resume(settle_ms=450)
                if seed is not None:
                    vad_recorder.prime_with_seed(seed)
            if queued_wav is not None and self._get_input_mode() == "push_to_talk":
                self.start_question_thread(queued_wav)

    def _on_pipeline_speaking_started(self) -> None:
        self._turn_state.speaking_started()
        self._assistant_active_at = time.monotonic()
        if self._get_input_mode() == "voice_activation" and config.BARGE_IN_ENABLED:
            self._get_vad_recorder().enter_gated_mode()
        self._signals.state_changed.emit("speaking")

    def _on_pipeline_cancelled(self) -> None:
        self._signals.turn_cancelled.emit()

    # -- Replay and stop --

    def replay(self, text: str) -> None:
        """Speak a stored answer again (runs on a worker thread)."""
        self._turn_state.begin_replay()
        vad_recorder = self._get_vad_recorder()
        voice_mode = self._get_input_mode() == "voice_activation"
        if voice_mode and config.BARGE_IN_ENABLED:
            vad_recorder.enter_gated_mode()
        elif voice_mode:
            vad_recorder.pause()
            vad_recorder.suspend_stream()
        self._signals.state_changed.emit("speaking")
        try:
            self._get_brain().speak_text(text)
        finally:
            if voice_mode:
                self._audio_output.wait_for_drain()
            seed = self._turn_state.end_replay()
            if voice_mode:
                vad_recorder.exit_gated_mode()
                vad_recorder.resume_stream()
                vad_recorder.resume(settle_ms=450)
                if seed is not None:
                    vad_recorder.prime_with_seed(seed)
            self._signals.state_changed.emit("idle")

    def request_stop(self) -> None:
        """Stop button: cancel whatever is thinking or speaking."""
        if self._turn_state.request_cancel():
            logger.info("Stop requested via UI")
            self._get_pipeline().cancel_active()

    def retry_last_failed(self) -> bool:
        """Re-run the question whose turn last failed. Returns False if none."""
        wav_bytes = self._last_failed_wav
        if wav_bytes is None or self._turn_state.processing:
            return False
        self._last_failed_wav = None
        self.start_question_thread(wav_bytes)
        return True
