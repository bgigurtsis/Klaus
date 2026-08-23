"""Tests for Gemini Live request transport."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

from google import genai
from google.genai import live, types


def test_screenshot_uses_video_realtime_input() -> None:
    client = genai.Client(api_key="test-key")
    websocket = AsyncMock()
    session = live.AsyncSession(client._api_client, websocket)

    asyncio.run(
        session.send_realtime_input(
            video=types.Blob(data=b"jpeg", mime_type="image/jpeg")
        )
    )

    payload = json.loads(websocket.send.await_args.args[0])
    realtime_input = payload["realtime_input"]
    assert "video" in realtime_input
    assert "media_chunks" not in realtime_input
