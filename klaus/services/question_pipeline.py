from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineContext:
    input_mode: str
    current_session_id: str | None
    suspend_input_stream: Callable[[], None] | None = None


@dataclass(frozen=True)
class PipelineHooks:
    on_state: Callable[[str], None]
    on_transcription: Callable[[str, float, bytes], None]
    on_response: Callable[[str, float, str], None]
    on_sessions_changed: Callable[[], None]
    on_exchange_count_updated: Callable[[], None]
    on_speaking_started: Callable[[], None]


class QuestionPipeline:
    """Execute one transcribe -> route -> answer -> persist pipeline run."""

    def __init__(self, stt, camera, brain, memory, notes, tts) -> None:
        self._stt = stt
        self._camera = camera
        self._brain = brain
        self._memory = memory
        self._notes = notes
        self._tts = tts

    def run(self, wav_bytes: bytes, *, context: PipelineContext, hooks: PipelineHooks) -> None:
        logger.info("Transcribing audio...")
        transcript = self._stt.transcribe(wav_bytes)
        if not transcript:
            logger.info("Empty transcript, returning to idle")
            hooks.on_state("idle")
            return

        hooks.on_state("thinking")

        thumbnail = self._camera.capture_thumbnail_bytes()
        route_decision = self._brain.decide_route(transcript)
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

        image_b64 = None
        if route_decision.use_image:
            logger.info("Capturing page image from camera...")
            image_b64 = self._camera.capture_base64_jpeg()
            logger.info("Page image: %s", "captured" if image_b64 else "unavailable")
        else:
            logger.info(
                "Skipping full page image capture for route mode=%s",
                route_decision.mode.value,
            )

        hooks.on_transcription(transcript, time.time(), thumbnail or b"")
        memory_context = self._memory.get_knowledge_summary() if route_decision.use_memory_context else None
        notes_context = self._build_notes_context(route_decision.use_notes_context)

        sentence_queue: queue.Queue[str | None] = queue.Queue()
        first_sentence = threading.Event()
        tts_thread: threading.Thread | None = None

        def on_sentence(text: str) -> None:
            sentence_queue.put(text)
            if first_sentence.is_set():
                return
            first_sentence.set()
            hooks.on_speaking_started()

        try:
            if context.input_mode == "voice_activation" and context.suspend_input_stream:
                context.suspend_input_stream()

            tts_thread = threading.Thread(
                target=self._tts.speak_streaming,
                args=(sentence_queue,),
                daemon=True,
            )
            tts_thread.start()

            logger.info(
                "Sending to Claude (route=%s, image=%s, memory=%s, notes=%s)",
                route_decision.mode.value,
                "yes" if image_b64 else "no",
                "yes" if memory_context else "no",
                "yes" if notes_context else "no",
            )
            exchange = self._brain.ask(
                question=transcript,
                image_base64=image_b64,
                memory_context=memory_context,
                notes_context=notes_context,
                on_sentence=on_sentence,
                route_decision=route_decision,
            )
        finally:
            sentence_queue.put(None)

        if exchange.notes_file_changed and context.current_session_id:
            self._memory.set_session_notes_file(
                context.current_session_id,
                self._notes.current_file,
            )

        logger.info("Claude responded (%d chars), saving exchange", len(exchange.assistant_text))

        exchange_id = ""
        if context.current_session_id:
            record = self._memory.save_exchange(
                session_id=context.current_session_id,
                user_text=exchange.user_text,
                assistant_text=exchange.assistant_text,
                image_base64=exchange.image_base64,
                searches=exchange.searches,
            )
            exchange_id = record.id

        hooks.on_response(exchange.assistant_text, time.time(), exchange_id)
        hooks.on_exchange_count_updated()
        hooks.on_sessions_changed()

        if tts_thread is not None:
            tts_thread.join()

        logger.info("Playback complete, idle")
        hooks.on_state("idle")

    def _build_notes_context(self, include_notes_context: bool) -> str | None:
        if not include_notes_context:
            return None
        if self._notes.current_file:
            return f"Current notes file: {self._notes.current_file}"
        return "No notes file set for this session."
