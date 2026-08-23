"""Tests for Gemini Live request transport."""

from __future__ import annotations

import asyncio
import base64
import queue
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from google.genai import types

from klaus.gemini_live import GeminiLiveBrain


class _LiveSession:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = responses
        self.send_client_content = AsyncMock()
        self.send_realtime_input = AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def receive(self):
        for response in self._responses:
            yield response


class _AudioOutput:
    def play_pcm_stream(self, audio_queue: queue.Queue, **_kwargs) -> None:
        while audio_queue.get() is not None:
            pass

    def stop(self) -> None:
        pass


def test_turn_content_seeds_image_before_transcript() -> None:
    brain = GeminiLiveBrain(
        notes=None,
        audio_output=SimpleNamespace(stop=lambda: None),
    )
    session = AsyncMock()

    asyncio.run(
        brain._send_turn_content(
            session=session,
            types=types,
            question="What is shown?",
            image_base64=base64.b64encode(b"jpeg").decode(),
            reading_text=None,
        )
    )

    content = session.send_client_content.await_args.kwargs["turns"]
    assert session.send_client_content.await_args.kwargs["turn_complete"] is False
    assert content.parts[0].inline_data.data == b"jpeg"
    assert "What is shown?" in session.send_realtime_input.await_args.kwargs["text"]


def test_cancel_closes_active_live_session() -> None:
    stopped = threading.Event()
    audio_output = SimpleNamespace(stop=lambda: stopped.set())
    brain = GeminiLiveBrain(notes=None, audio_output=audio_output)
    closed = threading.Event()
    session = AsyncMock()
    session.close.side_effect = lambda: closed.set()
    loop = asyncio.new_event_loop()
    loop_thread = threading.Thread(target=loop.run_forever)
    loop_thread.start()
    try:
        brain._active_loop = loop
        brain._active_session = session

        brain.cancel_current()

        deadline = time.monotonic() + 1
        while not closed.is_set() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert stopped.is_set()
        assert closed.is_set()
        session.close.assert_awaited_once()
    finally:
        loop.call_soon_threadsafe(loop.stop)
        loop_thread.join(timeout=1)
        loop.close()


def test_output_transcription_streams_each_delta(monkeypatch) -> None:
    def response(text: str, *, turn_complete: bool = False) -> SimpleNamespace:
        return SimpleNamespace(
            server_content=SimpleNamespace(
                interrupted=False,
                output_transcription=SimpleNamespace(text=text),
                model_turn=SimpleNamespace(parts=[]),
                turn_complete=turn_complete,
            ),
            tool_call=None,
        )

    session = _LiveSession(
        [
            response("Stream"),
            response("ing text"),
            response(" as it arrives.", turn_complete=True),
        ]
    )
    live = SimpleNamespace(connect=lambda **_kwargs: session)
    client = SimpleNamespace(aio=SimpleNamespace(live=live))
    monkeypatch.setattr("google.genai.Client", lambda **_kwargs: client)
    brain = GeminiLiveBrain(notes=None, audio_output=_AudioOutput())
    deltas: list[str] = []

    answer = asyncio.run(
        brain._run_turn(
            question="Explain this",
            image_base64=None,
            reading_text=None,
            instructions="Answer clearly.",
            on_text_delta=deltas.append,
            on_speaking_started=None,
            on_first_audio=None,
            external_cancel_event=None,
        )
    )

    assert deltas == ["Stream", "ing text", " as it arrives."]
    assert answer == "Streaming text as it arrives."
