from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from klaus.brain import AskCancelled
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
        camera.capture_text_context.return_value = None

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
        tts.speak_streaming.side_effect = lambda sentence_q, **kwargs: sentence_q.get()

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

    def test_selected_pdf_text_is_preferred_over_window_image(self):
        stt = MagicMock()
        stt.transcribe.return_value = "Explain this passage"
        camera = MagicMock()
        camera.capture_thumbnail_bytes.return_value = b"thumb"
        camera.capture_text_context.return_value = "Exact selected PDF text"

        brain = MagicMock()
        brain.decide_route.return_value = _route()
        brain.ask.return_value = SimpleNamespace(
            notes_file_changed=False,
            assistant_text="Explanation.",
            user_text="Explain this passage",
            image_base64=None,
            searches=[],
        )
        memory = MagicMock()
        memory.save_exchange.return_value = SimpleNamespace(id="ex-2")
        tts = MagicMock()
        tts.speak_streaming.side_effect = lambda sentence_q, **kwargs: sentence_q.get()
        pipeline = QuestionPipeline(stt, camera, brain, memory, MagicMock(), tts)

        pipeline.run(
            b"wav",
            context=PipelineContext(
                input_mode="push_to_talk",
                current_session_id="session-1",
            ),
            hooks=PipelineHooks(
                on_state=MagicMock(),
                on_transcription=MagicMock(),
                on_response=MagicMock(),
                on_sessions_changed=MagicMock(),
                on_exchange_count_updated=MagicMock(),
                on_speaking_started=MagicMock(),
            ),
        )

        camera.capture_base64_jpeg.assert_not_called()
        assert brain.ask.call_args.kwargs["reading_text"] == "Exact selected PDF text"
        assert brain.ask.call_args.kwargs["image_base64"] is None

    def test_realtime_brain_owns_reasoning_and_audio_playback(self):
        stt = MagicMock()
        stt.transcribe.return_value = "Explain this"
        camera = MagicMock()
        camera.capture_thumbnail_bytes.return_value = b"thumb"
        camera.capture_text_context.return_value = "Selected passage"

        brain = MagicMock()
        brain.handles_audio = True
        brain.decide_route.return_value = _route()
        exchange = SimpleNamespace(
            notes_file_changed=False,
            assistant_text="A direct explanation.",
            user_text="Explain this",
            image_base64=None,
            searches=[],
        )

        def ask_audio_side_effect(**kwargs):
            kwargs["on_sentence"]("A direct explanation.")
            kwargs["on_speaking_started"]()
            kwargs["on_first_audio"]()
            return exchange

        brain.ask_audio.side_effect = ask_audio_side_effect
        memory = MagicMock()
        memory.save_exchange.return_value = SimpleNamespace(id="ex-realtime")
        tts = MagicMock()
        speaking = MagicMock()

        pipeline = QuestionPipeline(
            stt=stt,
            camera=camera,
            brain=brain,
            memory=memory,
            notes=MagicMock(),
            tts=tts,
        )
        pipeline.run(
            b"wav-audio",
            context=PipelineContext(
                input_mode="voice_activation",
                current_session_id="session-1",
            ),
            hooks=PipelineHooks(
                on_state=MagicMock(),
                on_transcription=MagicMock(),
                on_response=MagicMock(),
                on_sessions_changed=MagicMock(),
                on_exchange_count_updated=MagicMock(),
                on_speaking_started=speaking,
                on_assistant_sentence=MagicMock(),
            ),
        )

        assert brain.ask_audio.call_args.kwargs["wav_bytes"] == b"wav-audio"
        assert brain.ask_audio.call_args.kwargs["reading_text"] == "Selected passage"
        tts.speak_streaming.assert_not_called()
        speaking.assert_called_once()
        memory.save_exchange.assert_called_once()

    def test_realtime_brain_receives_audio_and_selected_pdf_text(self):
        stt = MagicMock()
        stt.transcribe.return_value = "Explain this passage"
        camera = MagicMock()
        camera.capture_thumbnail_bytes.return_value = b"thumb"
        camera.capture_text_context.return_value = "Exact selected PDF text"

        brain = MagicMock()
        brain.handles_audio = True
        brain.decide_route.return_value = _route()
        brain.ask_audio.return_value = SimpleNamespace(
            notes_file_changed=False,
            assistant_text="Explanation.",
            user_text="Explain this passage",
            image_base64=None,
            searches=[],
        )
        memory = MagicMock()
        memory.save_exchange.return_value = SimpleNamespace(id="ex-realtime")
        pipeline = QuestionPipeline(
            stt,
            camera,
            brain,
            memory,
            MagicMock(current_file=""),
            MagicMock(),
        )

        response = MagicMock()
        pipeline.run(
            b"wav",
            context=PipelineContext(
                input_mode="voice_activation",
                current_session_id="session-1",
            ),
            hooks=PipelineHooks(
                on_state=MagicMock(),
                on_transcription=MagicMock(),
                on_response=response,
                on_sessions_changed=MagicMock(),
                on_exchange_count_updated=MagicMock(),
                on_speaking_started=MagicMock(),
            ),
        )

        camera.capture_base64_jpeg.assert_not_called()
        assert brain.ask_audio.call_args.kwargs["wav_bytes"] == b"wav"
        assert brain.ask_audio.call_args.kwargs["question"] == "Explain this passage"
        assert (
            brain.ask_audio.call_args.kwargs["reading_text"]
            == "Exact selected PDF text"
        )
        assert brain.ask_audio.call_args.kwargs["image_base64"] is None
        memory.save_exchange.assert_called_once()
        response.assert_called_once()

    def test_cancelled_ask_skips_persistence_and_reports_cancel(self):
        stt = MagicMock()
        stt.transcribe.return_value = "What is entropy?"

        camera = MagicMock()
        camera.capture_thumbnail_bytes.return_value = b"thumb"
        camera.capture_base64_jpeg.return_value = "img"

        brain = MagicMock()
        brain.decide_route.return_value = _route()
        brain.ask.side_effect = AskCancelled()

        memory = MagicMock()
        tts = MagicMock()
        tts.speak_streaming.side_effect = lambda sentence_q, **kwargs: sentence_q.get()

        pipeline = QuestionPipeline(
            stt=stt,
            camera=camera,
            brain=brain,
            memory=memory,
            notes=MagicMock(),
            tts=tts,
        )

        states: list[str] = []
        cancelled = MagicMock()

        pipeline.run(
            b"wav",
            context=PipelineContext(
                input_mode="voice_activation",
                current_session_id="session-1",
                cancel_event=threading.Event(),
            ),
            hooks=PipelineHooks(
                on_state=states.append,
                on_transcription=MagicMock(),
                on_response=MagicMock(),
                on_sessions_changed=MagicMock(),
                on_exchange_count_updated=MagicMock(),
                on_speaking_started=MagicMock(),
                on_cancelled=cancelled,
            ),
        )

        cancelled.assert_called_once()
        memory.save_exchange.assert_not_called()
        tts.stop.assert_called_once()
        assert states[-1] == "idle"

    def test_transcriber_override_is_used_instead_of_stt(self):
        stt = MagicMock()
        transcriber = MagicMock(return_value="")

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
                input_mode="voice_activation",
                current_session_id=None,
                transcriber=transcriber,
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

        transcriber.assert_called_once_with(b"wav")
        stt.transcribe.assert_not_called()
        assert states == ["idle"]
