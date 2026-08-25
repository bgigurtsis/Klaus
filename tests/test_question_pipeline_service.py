from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from klaus.notes import NotesManager
from klaus.realtime import AskCancelled
from klaus.services.question_pipeline import PipelineContext, PipelineHooks, QuestionPipeline


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


def _hooks(**overrides):
    values = dict(
        on_state=MagicMock(),
        on_transcription=MagicMock(),
        on_response=MagicMock(),
        on_sessions_changed=MagicMock(),
        on_exchange_count_updated=MagicMock(),
        on_speaking_started=MagicMock(),
    )
    values.update(overrides)
    return PipelineHooks(**values)


def _pipeline(stt, camera, brain, memory=None, notes=None):
    return QuestionPipeline(
        stt=stt,
        camera=camera,
        brain=brain,
        memory=memory or MagicMock(),
        notes=notes or MagicMock(current_file="", current_path=""),
    )


def test_empty_transcript_returns_idle():
    stt = MagicMock()
    stt.transcribe.return_value = ""
    states: list[str] = []

    _pipeline(stt, MagicMock(), MagicMock()).run(
        b"wav",
        context=PipelineContext(input_mode="push_to_talk", current_session_id=None),
        hooks=_hooks(on_state=states.append),
    )

    assert states == ["idle"]


def test_realtime_turn_persists_exchange_and_streams_answer():
    stt = MagicMock()
    stt.transcribe.return_value = "Explain this"
    camera = MagicMock()
    camera.capture_thumbnail_bytes.return_value = b"thumb"
    camera.capture_text_context.return_value = "Selected passage"
    brain = MagicMock()
    brain.decide_route.return_value = _route()
    exchange = SimpleNamespace(
        notes_file_changed=False,
        assistant_text="A direct explanation.",
        user_text="Explain this",
        image_base64=None,
        searches=[],
    )

    def ask_audio(**kwargs):
        kwargs["on_text_delta"]("A direct explanation.")
        kwargs["on_speaking_started"]()
        kwargs["on_first_audio"]()
        return exchange

    brain.ask_audio.side_effect = ask_audio
    memory = MagicMock()
    memory.save_exchange.return_value = SimpleNamespace(id="exchange-1")
    response = MagicMock()
    speaking = MagicMock()
    text_delta = MagicMock()
    suspend_input = MagicMock()
    suspend_input.side_effect = brain.ask_audio.assert_not_called

    _pipeline(stt, camera, brain, memory=memory).run(
        b"wav-audio",
        context=PipelineContext(
            input_mode="voice_activation",
            current_session_id="session-1",
            suspend_input_stream=suspend_input,
        ),
        hooks=_hooks(
            on_response=response,
            on_speaking_started=speaking,
            on_assistant_text_delta=text_delta,
        ),
    )

    assert brain.ask_audio.call_args.kwargs["wav_bytes"] == b"wav-audio"
    assert brain.ask_audio.call_args.kwargs["reading_text"] == "Selected passage"
    speaking.assert_called_once()
    text_delta.assert_called_once_with("A direct explanation.")
    suspend_input.assert_called_once_with()
    memory.save_exchange.assert_called_once()
    response.assert_called_once()


def test_selected_text_avoids_window_image_capture():
    stt = MagicMock()
    stt.transcribe.return_value = "Explain this passage"
    camera = MagicMock()
    camera.capture_thumbnail_bytes.return_value = b"thumb"
    camera.capture_text_context.return_value = "Exact selected text"
    brain = MagicMock()
    brain.decide_route.return_value = _route()
    brain.ask_audio.return_value = SimpleNamespace(
        notes_file_changed=False,
        assistant_text="Explanation.",
        user_text="Explain this passage",
        image_base64=None,
        searches=[],
    )

    _pipeline(stt, camera, brain).run(
        b"wav",
        context=PipelineContext(input_mode="voice_activation", current_session_id=None),
        hooks=_hooks(),
    )

    camera.capture_base64_jpeg.assert_not_called()
    assert brain.ask_audio.call_args.kwargs["reading_text"] == "Exact selected text"


def test_active_capture_appends_completed_turn_and_links_note(tmp_path):
    stt = MagicMock()
    stt.transcribe.return_value = "What is entropy?"
    camera = MagicMock()
    camera.capture_thumbnail_bytes.return_value = b"thumb"
    camera.capture_text_context.return_value = None
    brain = MagicMock()
    brain.decide_route.return_value = _route(use_image=False)
    brain.ask_audio.return_value = SimpleNamespace(
        notes_file_changed=False,
        assistant_text="A measure of multiplicity.",
        user_text="What is entropy?",
        image_base64=None,
        searches=[],
    )
    memory = MagicMock()
    memory.save_exchange.return_value = SimpleNamespace(id="exchange-1")
    notes = NotesManager(str(tmp_path))
    notes.configure_capture("conversation", "Study Session")
    notes.reset_changed()

    _pipeline(stt, camera, brain, memory=memory, notes=notes).run(
        b"wav",
        context=PipelineContext(input_mode="push_to_talk", current_session_id="session-1"),
        hooks=_hooks(),
    )

    content = (tmp_path / "Study Session.md").read_text(encoding="utf-8")
    assert "**You:** What is entropy?" in content
    assert "**Klaus:** A measure of multiplicity." in content
    assert memory.save_exchange.call_args.kwargs["note_file_path"] == str(
        tmp_path / "Study Session.md"
    )


def test_capture_configuration_turn_is_persisted_but_not_captured(tmp_path):
    stt = MagicMock()
    stt.transcribe.return_value = "Save everything I ask to Questions"
    camera = MagicMock()
    camera.capture_thumbnail_bytes.return_value = b"thumb"
    camera.capture_text_context.return_value = None
    brain = MagicMock()
    brain.decide_route.return_value = _route(use_image=False)
    notes = NotesManager(str(tmp_path))

    def ask_audio(**_kwargs):
        notes.reset_changed()
        notes.configure_capture("questions", "Questions")
        return SimpleNamespace(
            notes_file_changed=True,
            assistant_text="I will save later questions to Questions.md.",
            user_text="Save everything I ask to Questions",
            image_base64=None,
            searches=[],
        )

    brain.ask_audio.side_effect = ask_audio
    memory = MagicMock()
    memory.save_exchange.return_value = SimpleNamespace(id="exchange-1")

    _pipeline(stt, camera, brain, memory=memory, notes=notes).run(
        b"wav",
        context=PipelineContext(input_mode="push_to_talk", current_session_id="session-1"),
        hooks=_hooks(),
    )

    assert (tmp_path / "Questions.md").read_text(encoding="utf-8") == ""
    memory.set_session_notes_file.assert_called_once_with("session-1", "Questions.md")
    memory.set_session_notes_capture_mode.assert_called_once_with(
        "session-1", "questions"
    )


def test_cancelled_realtime_turn_skips_persistence():
    stt = MagicMock()
    stt.transcribe.return_value = "What is entropy?"
    camera = MagicMock()
    camera.capture_thumbnail_bytes.return_value = b"thumb"
    camera.capture_base64_jpeg.return_value = "img"
    brain = MagicMock()
    brain.decide_route.return_value = _route()
    brain.ask_audio.side_effect = AskCancelled()
    memory = MagicMock()
    states: list[str] = []
    cancelled = MagicMock()

    _pipeline(stt, camera, brain, memory=memory).run(
        b"wav",
        context=PipelineContext(
            input_mode="voice_activation",
            current_session_id="session-1",
            cancel_event=threading.Event(),
        ),
        hooks=_hooks(on_state=states.append, on_cancelled=cancelled),
    )

    cancelled.assert_called_once()
    memory.save_exchange.assert_not_called()
    assert states[-1] == "idle"


def test_cancel_active_calls_realtime_brain():
    brain = MagicMock()
    pipeline = _pipeline(MagicMock(), MagicMock(), brain)

    pipeline.cancel_active()

    brain.cancel_current.assert_called_once()


def test_tablet_capture_runs_after_transcription_and_persists_chat_thumbnail():
    order: list[str] = []
    stt = MagicMock()
    stt.transcribe.side_effect = lambda _wav: order.append("transcribe") or "Read this"
    camera = MagicMock(should_persist_images=False)
    camera.capture_thumbnail_bytes.return_value = b"preview"
    camera.capture_text_context.side_effect = lambda: order.append("fresh screenshot")
    camera.capture_base64_jpeg.return_value = "tablet-image"
    brain = MagicMock()
    brain.decide_route.return_value = _route()
    brain.ask_audio.return_value = SimpleNamespace(
        notes_file_changed=False,
        assistant_text="Answer",
        user_text="Read this",
        image_base64="tablet-image",
        searches=[],
    )
    memory = MagicMock()
    memory.save_exchange.return_value = SimpleNamespace(id="exchange-1")

    _pipeline(stt, camera, brain, memory=memory).run(
        b"wav",
        context=PipelineContext(input_mode="push_to_talk", current_session_id="session-1"),
        hooks=_hooks(),
    )

    assert order == ["transcribe", "fresh screenshot"]
    assert brain.ask_audio.call_args.kwargs["image_base64"] == "tablet-image"
    assert memory.save_exchange.call_args.kwargs["image_base64"] is None
    assert memory.save_exchange.call_args.kwargs["thumbnail_bytes"] == b"preview"
