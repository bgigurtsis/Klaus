"""Voice-turn coordination: VAD callbacks, PTT, barge-in, replay, stop.

Everything that starts, cancels, or tears down a voice turn lives here,
driven by TurnState. Mutable collaborators (recorders, pipeline, brain,
input mode) are read through getters because KlausApp hot-swaps them on
device switches and settings changes.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import klaus.config as config
from klaus.services.question_pipeline import (
    PipelineContext,
    PipelineHooks,
    Transcription,
)
from klaus.services.turn_state import TurnState

logger = logging.getLogger(__name__)


def _new_guard_stats() -> dict[str, int]:
    """Create a fresh per-session STT guard stats dict."""
    return {
        "vad_discarded": 0,
        "quality_gate_discarded": 0,
    }


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
        self._guard_stats = _new_guard_stats()
        self._guard_stats_lock = threading.Lock()

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
            "STT guard stats reset (session=%s): vad_discarded=%d | quality_gate_discarded=%d",
            self._session_tag(),
            snapshot["vad_discarded"],
            snapshot["quality_gate_discarded"],
        )

    def _increment_guard_stat(self, key: str, event: str, reason: str = "-") -> None:
        """Increment one guard stat and log a structured snapshot."""
        with self._guard_stats_lock:
            if key not in self._guard_stats:
                return
            self._guard_stats[key] += 1
            snapshot = dict(self._guard_stats)
        logger.info(
            "STT guard event=%s reason=%s session=%s vad_discarded=%d quality_gate_discarded=%d",
            event,
            reason,
            self._session_tag(),
            snapshot["vad_discarded"],
            snapshot["quality_gate_discarded"],
        )

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
            )
            hooks = PipelineHooks(
                on_state=self._signals.state_changed.emit,
                on_transcription=self._signals.transcription_ready.emit,
                on_response=self._signals.response_ready.emit,
                on_sessions_changed=self._signals.sessions_changed.emit,
                on_exchange_count_updated=self._update_exchange_count,
                on_speaking_started=self._on_pipeline_speaking_started,
                on_assistant_text_delta=self._signals.assistant_text_delta.emit,
                on_cancelled=self._on_pipeline_cancelled,
            )
            self._get_pipeline().run(wav_bytes, context=context, hooks=hooks)

        except Exception as e:
            logger.error("Processing failed: %s", e, exc_info=True)
            self._signals.error.emit(str(e))
            self._signals.state_changed.emit("idle")
        finally:
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
