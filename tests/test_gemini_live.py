"""Tests for Gemini Live request transport."""

from __future__ import annotations

import asyncio
import threading
import time
import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

from google.genai import types

from klaus.gemini_live import GeminiLiveBrain


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
