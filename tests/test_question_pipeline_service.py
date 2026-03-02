from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from klaus.services.question_pipeline import (
    PipelineContext,
    PipelineHooks,
    QuestionPipeline,
)


def _route(**kwargs):
    defaults = dict(
        mode=SimpleNamespace(value="general_contextual"),
        source="local",
        confidence=0.9,
        use_image=True,
        use_history=True,
        use_memory_context=True,
        use_notes_context=True,
        reason="test",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestQuestionPipeline:
    def test_empty_transcript_returns_idle(self):
        stt = MagicMock()
        stt.transcribe.return_value = ""
        pipeline = QuestionPipeline(
            stt=stt,
            camera=MagicMock(),
            brain=MagicMock(),
            memory=MagicMock(),
            notes=MagicMock(),
            tts=MagicMock(),
        )
        states: list[str] = []

        pipeline.run(
            b"wav",
            context=PipelineContext(
                input_mode="push_to_talk",
                current_session_id=None,
                suspend_input_stream=MagicMock(),
            ),
            hooks=PipelineHooks(
                on_state=states.append,
                on_transcription=MagicMock(),
                on_response=MagicMock(),
                on_sessions_changed=MagicMock(),
                on_exchange_count_updated=MagicMock(),
                on_speaking_started=MagicMock(),
            ),
        )

        assert states == ["idle"]

    def test_success_path_emits_callbacks_and_persists_exchange(self):
        stt = MagicMock()
        stt.transcribe.return_value = "What is entropy?"

        camera = MagicMock()
        camera.capture_thumbnail_bytes.return_value = b"thumb"
        camera.capture_base64_jpeg.return_value = "img"

        brain = MagicMock()
        brain.decide_route.return_value = _route()
        exchange = SimpleNamespace(
            notes_file_changed=False,
            assistant_text="Entropy is a state measure.",
            user_text="What is entropy?",
            image_base64="img",
            searches=[],
        )

        def ask_side_effect(**kwargs):
            kwargs["on_sentence"]("Entropy is a state measure.")
            return exchange

        brain.ask.side_effect = ask_side_effect

        memory = MagicMock()
        memory.get_knowledge_summary.return_value = "memory"
        memory.save_exchange.return_value = SimpleNamespace(id="ex-1")

        notes = MagicMock()
        notes.current_file = "notes.md"

        tts = MagicMock()
        tts.speak_streaming.side_effect = lambda sentence_q: sentence_q.get()

        pipeline = QuestionPipeline(
            stt=stt,
            camera=camera,
            brain=brain,
            memory=memory,
            notes=notes,
            tts=tts,
        )

        states: list[str] = []
        responses: list[tuple[str, float, str]] = []
        speaking = MagicMock()

        pipeline.run(
            b"wav",
            context=PipelineContext(
                input_mode="push_to_talk",
                current_session_id="session-1",
                suspend_input_stream=MagicMock(),
            ),
            hooks=PipelineHooks(
                on_state=states.append,
                on_transcription=MagicMock(),
                on_response=lambda text, ts, exid: responses.append((text, ts, exid)),
                on_sessions_changed=MagicMock(),
                on_exchange_count_updated=MagicMock(),
                on_speaking_started=speaking,
            ),
        )

        assert states[0] == "thinking"
        assert states[-1] == "idle"
        speaking.assert_called_once()
        memory.save_exchange.assert_called_once()
        assert responses and responses[0][2] == "ex-1"
