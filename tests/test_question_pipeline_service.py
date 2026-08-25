from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

from klaus.notes import NotesManager
from klaus.realtime import AskCancelled
from klaus.services.question_pipeline import (
    PipelineContext,
    PipelineHooks,
    QuestionPipeline,
    TimingsAggregator,
    Transcription,
    TurnTimings,
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
    memory.set_session_notes_capture_screenshots.assert_called_once_with(
        "session-1", False
    )


def test_screenshot_request_saves_full_image_to_obsidian(tmp_path):
    stt = MagicMock()
    stt.transcribe.return_value = "Take a screenshot and save it to Examples"
    camera = MagicMock()
    camera.capture_thumbnail_bytes.return_value = b"thumb"
    camera.capture_text_context.return_value = None
    camera.capture_base64_jpeg.return_value = "anBlZw=="
    brain = MagicMock()
    brain.decide_route.return_value = _route(use_image=False)
    notes = NotesManager(str(tmp_path))

    def ask_audio(**_kwargs):
        notes.reset_changed()
        result = notes.save_screenshot("Current example", "Examples")
        assert result.startswith("Saved screenshot:")
        return SimpleNamespace(
            notes_file_changed=True,
            assistant_text="Saved the screenshot.",
            user_text="Take a screenshot and save it to Examples",
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

    attachment = next((tmp_path / "Attachments" / "Klaus").glob("*.jpg"))
    assert attachment.read_bytes() == b"jpeg"
    assert "![[Attachments/Klaus/" in (tmp_path / "Examples.md").read_text(
        encoding="utf-8"
    )


def test_end_chat_summary_receives_stored_history_and_stops_capture(tmp_path):
    stt = MagicMock()
    stt.transcribe.return_value = "End this chat and save a summary"
    camera = MagicMock()
    camera.capture_thumbnail_bytes.return_value = b"thumb"
    camera.capture_text_context.return_value = None
    brain = MagicMock()
    brain.decide_route.return_value = _route(use_image=False)
    notes = NotesManager(str(tmp_path))
    notes.configure_capture("conversation", "Study Session")
    memory = MagicMock()
    memory.get_exchanges.return_value = [
        SimpleNamespace(user_text="What is entropy?", assistant_text="Multiplicity."),
    ]
    memory.save_exchange.return_value = SimpleNamespace(id="exchange-1")

    def ask_audio(**kwargs):
        assert "What is entropy?" in kwargs["notes_context"]
        notes.reset_changed()
        notes.save_chat_summary("### Key ideas\n\n- Entropy tracks multiplicity.")
        return SimpleNamespace(
            notes_file_changed=True,
            assistant_text="Saved the chat summary.",
            user_text="End this chat and save a summary",
            image_base64=None,
            searches=[],
        )

    brain.ask_audio.side_effect = ask_audio

    _pipeline(stt, camera, brain, memory=memory, notes=notes).run(
        b"wav",
        context=PipelineContext(input_mode="push_to_talk", current_session_id="session-1"),
        hooks=_hooks(),
    )

    content = (tmp_path / "Study Session.md").read_text(encoding="utf-8")
    assert "Entropy tracks multiplicity" in content
    assert notes.capture_mode == "off"


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


def test_turn_timings_summary_includes_extended_marks():
    timings = TurnTimings(start=10.0, speech_ended_at=9.8)
    timings.transcript_ready = 10.1
    timings.route_ready = 10.15
    timings.first_text_delta = 10.6
    timings.first_audio = 10.9
    timings.turn_done = 12.0
    timings.image_capture_ms = 42.0
    timings.connect_ms = 310.0
    timings.speculative_hit = True

    summary = timings.summary()

    assert "vad_wait=200ms" in summary
    assert "transcript=100ms" in summary
    assert "spec=hit" in summary
    assert "image_capture=42ms" in summary
    assert "connect=310ms" in summary
    assert "first_audio=900ms" in summary
    assert "done=2000ms" in summary


def test_turn_timings_summary_marks_missing_values_with_dash():
    summary = TurnTimings(start=10.0).summary()

    assert "vad_wait=-ms" in summary
    assert "spec=-" in summary
    assert "connect=-ms" in summary
    assert "image_capture=-ms" in summary


def test_transcription_hit_flag_reaches_timings(caplog):
    stt = MagicMock()
    camera = MagicMock()
    camera.capture_thumbnail_bytes.return_value = b"thumb"
    camera.capture_text_context.return_value = None
    brain = MagicMock()
    brain.decide_route.return_value = _route(use_image=False)
    brain.ask_audio.return_value = SimpleNamespace(
        notes_file_changed=False,
        assistant_text="Answer",
        user_text="Question",
        image_base64=None,
        searches=[],
    )

    with caplog.at_level("INFO", logger="klaus.services.question_pipeline"):
        _pipeline(stt, camera, brain).run(
            b"wav",
            context=PipelineContext(
                input_mode="voice_activation",
                current_session_id=None,
                transcriber=lambda _wav: Transcription("Question", speculative_hit=True),
            ),
            hooks=_hooks(),
        )

    stt.transcribe.assert_not_called()
    assert any("spec=hit" in record.getMessage() for record in caplog.records)


def test_timings_aggregator_logs_percentiles(caplog):
    aggregator = TimingsAggregator(log_every=3)
    for delta in (0.1, 0.2, 0.3):
        timings = TurnTimings(start=0.0)
        timings.transcript_ready = delta
        timings.first_audio = delta * 2
        timings.turn_done = delta * 3
        with caplog.at_level("INFO", logger="klaus.services.question_pipeline"):
            aggregator.record(timings)

    messages = [r.getMessage() for r in caplog.records if "Turn latency" in r.getMessage()]
    assert len(messages) == 1
    assert "transcript p50=200ms" in messages[0]
    assert "first_audio p50=400ms" in messages[0]
    assert "done p50=600ms" in messages[0]


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
