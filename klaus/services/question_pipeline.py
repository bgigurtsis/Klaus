from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from klaus.realtime import AskCancelled
from klaus.query_router import default_route_decision

logger = logging.getLogger(__name__)


@dataclass
class TurnTimings:
    """Per-turn latency marks (perf_counter seconds), logged at turn end."""

    start: float = field(default_factory=time.perf_counter)
    transcript_ready: float | None = None
    route_ready: float | None = None
    first_text_delta: float | None = None
    first_audio: float | None = None
    turn_done: float | None = None

    def _delta_ms(self, mark: float | None) -> str:
        if mark is None:
            return "-"
        return f"{(mark - self.start) * 1000:.0f}"

    def summary(self) -> str:
        return (
            f"transcript={self._delta_ms(self.transcript_ready)}ms "
            f"route={self._delta_ms(self.route_ready)}ms "
            f"first_text_delta={self._delta_ms(self.first_text_delta)}ms "
            f"first_audio={self._delta_ms(self.first_audio)}ms "
            f"done={self._delta_ms(self.turn_done)}ms"
        )


@dataclass(frozen=True)
class PipelineContext:
    input_mode: str
    current_session_id: str | None
    suspend_input_stream: Callable[[], None] | None = None
    cancel_event: threading.Event | None = None
    transcriber: Callable[[bytes], str] | None = None


@dataclass(frozen=True)
class PipelineHooks:
    on_state: Callable[[str], None]
    on_transcription: Callable[[str, float, bytes], None]
    on_response: Callable[[str, float, str], None]
    on_sessions_changed: Callable[[], None]
    on_exchange_count_updated: Callable[[], None]
    on_speaking_started: Callable[[], None]
    on_assistant_text_delta: Callable[[str], None] | None = None
    on_cancelled: Callable[[], None] | None = None


class QuestionPipeline:
    """Execute one transcribe -> route -> answer -> persist pipeline run."""

    def __init__(self, stt, camera, brain, memory, notes) -> None:
        self._stt = stt
        self._camera = camera
        self._brain = brain
        self._memory = memory
        self._notes = notes

    def run(self, wav_bytes: bytes, *, context: PipelineContext, hooks: PipelineHooks) -> None:
        timings = TurnTimings()
        cancel_event = context.cancel_event

        logger.info("Transcribing audio...")
        transcribe = context.transcriber or self._stt.transcribe
        transcript = transcribe(wav_bytes)
        timings.transcript_ready = time.perf_counter()
        if not transcript:
            logger.info("Empty transcript, returning to idle")
            hooks.on_state("idle")
            return
        if cancel_event is not None and cancel_event.is_set():
            self._finish_cancelled(hooks, timings)
            return

        hooks.on_state("thinking")

        # Decide the route while capturing the lightweight reading context.
        route_holder: dict[str, object] = {}

        def _decide_route() -> None:
            try:
                route_holder["route"] = self._brain.decide_route(transcript)
            except Exception:
                logger.exception("Route decision failed, using default route")
                route_holder["route"] = default_route_decision()

        route_thread = threading.Thread(target=_decide_route, daemon=True)
        route_thread.start()
        thumbnail = self._camera.capture_thumbnail_bytes()
        capture_text = getattr(self._camera, "capture_text_context", None)
        eager_text = capture_text() if callable(capture_text) else None
        if not isinstance(eager_text, str) or not eager_text.strip():
            eager_text = None
        route_thread.join()
        route_decision = route_holder["route"]
        timings.route_ready = time.perf_counter()
        logger.info(
            (
                "Query route decision: mode=%s source=%s conf=%.2f "
                "image=%s history=%s memory=%s notes=%s reason=%s"
            ),
            route_decision.mode.value,
            route_decision.source,
            route_decision.confidence,
            "yes" if route_decision.use_image else "no",
            "yes" if route_decision.use_history else "no",
            "yes" if route_decision.use_memory_context else "no",
            "yes" if route_decision.use_notes_context else "no",
            route_decision.reason,
        )

        reading_text = eager_text if route_decision.use_image else None
        image_b64 = None
        if route_decision.use_image and not reading_text:
            image_b64 = self._camera.capture_base64_jpeg()
        if route_decision.use_image:
            logger.info(
                "Reading context: %s",
                "selected text"
                if reading_text
                else ("window image" if image_b64 else "unavailable"),
            )

        hooks.on_transcription(transcript, time.time(), thumbnail or b"")
        notes_context = self._build_notes_context(route_decision.use_notes_context)

        self._run_realtime_turn(
            wav_bytes=wav_bytes,
            transcript=transcript,
            image_b64=image_b64,
            reading_text=reading_text,
            notes_context=notes_context,
            route_decision=route_decision,
            context=context,
            hooks=hooks,
            timings=timings,
        )

    def cancel_active(self) -> None:
        """Cancel the active Realtime response."""
        self._brain.cancel_current()

    def _run_realtime_turn(
        self,
        *,
        wav_bytes: bytes,
        transcript: str,
        image_b64: str | None,
        reading_text: str | None,
        notes_context: str | None,
        route_decision,
        context: PipelineContext,
        hooks: PipelineHooks,
        timings: TurnTimings,
    ) -> None:
        """Run one native speech-to-speech Realtime turn."""
        received_text = False

        def on_text_delta(text: str) -> None:
            nonlocal received_text
            if not received_text:
                received_text = True
                timings.first_text_delta = time.perf_counter()
            if hooks.on_assistant_text_delta:
                hooks.on_assistant_text_delta(text)

        def on_first_audio() -> None:
            timings.first_audio = time.perf_counter()

        try:
            logger.info(
                "Sending speech turn to selected live model (route=%s, image=%s, selected_text=%s)",
                route_decision.mode.value,
                "yes" if image_b64 else "no",
                "yes" if reading_text else "no",
            )
            exchange = self._brain.ask_audio(
                wav_bytes=wav_bytes,
                question=transcript,
                image_base64=image_b64,
                reading_text=reading_text,
                notes_context=notes_context,
                on_text_delta=on_text_delta,
                on_speaking_started=hooks.on_speaking_started,
                on_first_audio=on_first_audio,
                route_decision=route_decision,
                cancel_event=context.cancel_event,
            )
        except AskCancelled:
            self._finish_cancelled(hooks, timings)
            return

        if exchange.notes_file_changed and context.current_session_id:
            self._memory.set_session_notes_file(
                context.current_session_id,
                self._notes.current_file,
            )

        exchange_id = ""
        if context.current_session_id:
            record = self._memory.save_exchange(
                session_id=context.current_session_id,
                user_text=exchange.user_text,
                assistant_text=exchange.assistant_text,
                image_base64=exchange.image_base64,
                searches=exchange.searches,
                note_file_path=(
                    self._notes.current_path if exchange.notes_file_changed else None
                ),
            )
            exchange_id = record.id

        hooks.on_response(exchange.assistant_text, time.time(), exchange_id)
        hooks.on_exchange_count_updated()
        hooks.on_sessions_changed()
        timings.turn_done = time.perf_counter()
        logger.info("Realtime turn timings: %s", timings.summary())
        hooks.on_state("idle")

    def _finish_cancelled(self, hooks: PipelineHooks, timings: TurnTimings) -> None:
        timings.turn_done = time.perf_counter()
        logger.info("Turn cancelled. Timings: %s", timings.summary())
        if hooks.on_cancelled:
            hooks.on_cancelled()
        hooks.on_state("idle")

    def _build_notes_context(self, include_notes_context: bool) -> str | None:
        if not include_notes_context:
            return None
        if self._notes.current_file:
            return f"Current notes file: {self._notes.current_file}"
        return "No notes file set for this session."
