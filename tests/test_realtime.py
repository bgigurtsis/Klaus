"""Tests for the OpenAI Realtime speech-to-speech path."""

from __future__ import annotations

import base64
import io
import json
import wave
from types import SimpleNamespace

import numpy as np
import pytest

import klaus.config as config
from klaus.query_router import RouteDecision, RouteMode
from klaus.realtime import RealtimeBrain, wav_to_pcm24k


def _wav_bytes(samples: np.ndarray, *, sample_rate: int, channels: int = 1) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(samples.astype(np.int16).tobytes())
    return output.getvalue()


def _route() -> RouteDecision:
    return RouteDecision(
        mode=RouteMode.GENERAL_CONTEXTUAL,
        confidence=1.0,
        reason="test",
        use_image=True,
        use_history=True,
        use_memory_context=True,
        use_notes_context=True,
        max_sentences=None,
        history_turn_window=0,
        turn_instruction=None,
        source="test",
    )


class _FakeWebSocket:
    def __init__(self, events: list[dict]) -> None:
        self.events = [json.dumps(event) for event in events]
        self.sent: list[dict] = []
        self.timeout: float | None = None
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def send(self, payload: str) -> None:
        self.sent.append(json.loads(payload))

    def recv(self) -> str:
        return self.events.pop(0)

    def close(self) -> None:
        self.closed = True


class _FakeAudioOutput:
    def __init__(self) -> None:
        self.chunks: list[np.ndarray] = []
        self.stopped = False

    def play_pcm_stream(
        self, audio_queue, *, on_first_audio=None, on_frames_played=None
    ) -> None:
        first = True
        while True:
            chunk = audio_queue.get()
            if chunk is None:
                return
            self.chunks.append(chunk.copy())
            if first:
                first = False
                if on_first_audio:
                    on_first_audio()
            if on_frames_played:
                on_frames_played(len(chunk))

    def stop(self) -> None:
        self.stopped = True


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        openai_api_key="test-key",
        live_model="gpt-realtime-2.1",
        reasoning_effort="low",
        voice="marin",
    )


def test_wav_to_pcm24k_resamples_stereo_to_mono() -> None:
    left = np.arange(480, dtype=np.int16)
    right = left + 100
    stereo = np.column_stack((left, right))

    pcm = np.frombuffer(
        wav_to_pcm24k(_wav_bytes(stereo, sample_rate=48_000, channels=2)),
        dtype=np.int16,
    )

    assert len(pcm) == 240
    assert pcm[0] == 50
    assert pcm[-1] == 529


def test_wav_to_pcm24k_rejects_non_pcm16() -> None:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(1)
        wav_file.setframerate(24_000)
        wav_file.writeframes(b"\x80" * 10)

    with pytest.raises(ValueError, match="16-bit PCM"):
        wav_to_pcm24k(output.getvalue())


def test_session_update_uses_current_ga_schema() -> None:
    brain = RealtimeBrain(
        notes=None,
        audio_output=_FakeAudioOutput(),
        settings=_settings(),
    )

    event = brain._session_update("Answer briefly.")

    assert event["type"] == "session.update"
    session = event["session"]
    assert session["type"] == "realtime"
    assert session["model"] == "gpt-realtime-2.1"
    assert session["reasoning"] == {"effort": "low"}
    assert session["output_modalities"] == ["audio"]
    assert session["audio"]["input"] == {
        "format": {"type": "audio/pcm", "rate": 24_000},
        "turn_detection": None,
    }
    assert session["audio"]["output"]["format"] == {
        "type": "audio/pcm",
        "rate": 24_000,
    }
    assert session["audio"]["output"]["voice"] == "marin"


def test_audio_turn_streams_pcm_and_prefers_selected_text() -> None:
    raw_pcm = np.array([10, 20, 30], dtype=np.int16).tobytes()
    websocket = _FakeWebSocket(
        [
            {
                "type": "response.output_item.added",
                "item": {"type": "message", "id": "item-1"},
            },
            {"type": "response.content_part.added", "content_index": 0},
            {
                "type": "response.output_audio.delta",
                "delta": base64.b64encode(raw_pcm).decode("ascii"),
            },
            {
                "type": "response.output_audio_transcript.delta",
                "delta": "A useful answer.",
            },
            {
                "type": "response.done",
                "response": {"status": "completed", "output": []},
            },
        ]
    )
    factory_calls: list[tuple[str, dict]] = []

    def websocket_factory(url: str, **kwargs):
        factory_calls.append((url, kwargs))
        return websocket

    audio_output = _FakeAudioOutput()
    brain = RealtimeBrain(
        notes=None,
        audio_output=audio_output,
        settings=_settings(),
        websocket_factory=websocket_factory,
    )
    sentences: list[str] = []
    speaking: list[bool] = []

    exchange = brain.ask_audio(
        wav_bytes=_wav_bytes(np.array([1, 2, 3], dtype=np.int16), sample_rate=24_000),
        question="Explain this passage",
        image_base64="unused-image",
        reading_text="Exact selected passage",
        on_sentence=sentences.append,
        on_speaking_started=lambda: speaking.append(True),
        route_decision=_route(),
    )

    assert factory_calls[0][0].endswith("model=gpt-realtime-2.1")
    assert factory_calls[0][1]["header"] == ["Authorization: Bearer test-key"]
    assert exchange.assistant_text == "A useful answer."
    assert exchange.user_text == "Explain this passage"
    assert sentences == ["A useful answer."]
    assert speaking == [True]
    assert np.array_equal(audio_output.chunks[0], np.array([10, 20, 30], dtype=np.int16))

    input_event = next(
        event for event in websocket.sent if event["type"] == "conversation.item.create"
    )
    content = input_event["item"]["content"]
    assert content[0]["type"] == "input_text"
    assert "Exact selected passage" in content[0]["text"]
    assert content[1]["type"] == "input_audio"
    assert all(part["type"] != "input_image" for part in content)


def test_cancel_truncates_audio_at_played_position() -> None:
    websocket = _FakeWebSocket([])
    brain = RealtimeBrain(
        notes=None,
        audio_output=_FakeAudioOutput(),
        settings=_settings(),
    )
    brain._ws = websocket
    brain._response_active = True
    brain._last_item_id = "item-1"
    brain._last_content_index = 2
    brain._played_frames = 12_000

    brain.cancel_current()

    assert websocket.sent == [
        {"type": "response.cancel"},
        {
            "type": "conversation.item.truncate",
            "item_id": "item-1",
            "content_index": 2,
            "audio_end_ms": 500,
        },
    ]


def test_replay_uses_out_of_band_realtime_audio() -> None:
    raw_pcm = np.array([40, 50, 60], dtype=np.int16).tobytes()
    websocket = _FakeWebSocket(
        [
            {
                "type": "response.output_audio.delta",
                "delta": base64.b64encode(raw_pcm).decode("ascii"),
            },
            {
                "type": "response.done",
                "response": {
                    "status": "completed",
                    "metadata": {"purpose": "replay"},
                },
            },
        ]
    )
    audio_output = _FakeAudioOutput()
    brain = RealtimeBrain(
        notes=None,
        audio_output=audio_output,
        settings=_settings(),
        websocket_factory=lambda *_args, **_kwargs: websocket,
    )

    brain.speak_text("The exact prior answer.")

    response_event = next(
        event for event in websocket.sent if event["type"] == "response.create"
    )
    response = response_event["response"]
    assert response["conversation"] == "none"
    assert response["metadata"] == {"purpose": "replay"}
    assert response["output_modalities"] == ["audio"]
    assert response["input"] == []
    assert "The exact prior answer." in response["instructions"]
    assert np.array_equal(audio_output.chunks[0], np.array([40, 50, 60], dtype=np.int16))
