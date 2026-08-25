"""Tests for klaus.stt -- speech-to-text via Moonshine Voice."""

import io
import wave
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from klaus.stt import SpeechToText


def _make_wav_bytes(duration_ms=500, sample_rate=16000):
    n_samples = int(sample_rate * duration_ms / 1000)
    audio = np.zeros(n_samples, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def _make_transcript(texts: list[str]):
    """Build a fake Transcript with TranscriptLine-like objects."""
    lines = [
        SimpleNamespace(text=t, is_complete=True) for t in texts
    ]
    return SimpleNamespace(lines=lines)


def _patch_moonshine():
    """Patch moonshine_voice imports inside _load_moonshine."""
    mock_transcriber_cls = MagicMock()
    mock_transcriber = MagicMock()
    mock_transcriber_cls.return_value = mock_transcriber
    mock_get_model = MagicMock(return_value=("/fake/model", "5"))

    patcher = patch.dict("sys.modules", {
        "moonshine_voice": MagicMock(
            Transcriber=mock_transcriber_cls,
            get_model_for_language=mock_get_model,
        ),
    })
    return patcher, mock_transcriber


class TestSpeechToText:
    def test_transcribe_returns_string(self):
        patcher, mock_transcriber = _patch_moonshine()
        mock_transcriber.transcribe_without_streaming.return_value = _make_transcript(
            ["Hello world"]
        )
        with patcher:
            stt = SpeechToText()
            result = stt.transcribe(_make_wav_bytes())

        assert result == "Hello world"
        mock_transcriber.transcribe_without_streaming.assert_called_once()

    def test_transcribe_joins_multiple_lines(self):
        patcher, mock_transcriber = _patch_moonshine()
        mock_transcriber.transcribe_without_streaming.return_value = _make_transcript(
            ["First line.", "Second line."]
        )
        with patcher:
            stt = SpeechToText()
            result = stt.transcribe(_make_wav_bytes())

        assert result == "First line. Second line."

    def test_transcribe_strips_whitespace(self):
        patcher, mock_transcriber = _patch_moonshine()
        mock_transcriber.transcribe_without_streaming.return_value = _make_transcript(
            ["  padded text  "]
        )
        with patcher:
            stt = SpeechToText()
            result = stt.transcribe(_make_wav_bytes())

        assert result == "padded text"

    def test_transcribe_empty_lines_ignored(self):
        patcher, mock_transcriber = _patch_moonshine()
        mock_transcriber.transcribe_without_streaming.return_value = _make_transcript(
            ["", "  ", "actual text"]
        )
        with patcher:
            stt = SpeechToText()
            result = stt.transcribe(_make_wav_bytes())

        assert result == "actual text"

    def test_transcribe_no_lines_returns_empty(self):
        patcher, mock_transcriber = _patch_moonshine()
        mock_transcriber.transcribe_without_streaming.return_value = _make_transcript([])
        with patcher:
            stt = SpeechToText()
            result = stt.transcribe(_make_wav_bytes())

        assert result == ""


class TestModelDownloadRetry:
    def test_transient_download_failure_is_retried(self, monkeypatch):
        monkeypatch.setattr("klaus.stt.time.sleep", lambda _s: None)
        patcher, _ = _patch_moonshine()
        with patcher:
            stt = SpeechToText()
        calls = []

        def flaky(language, **kwargs):
            calls.append(language)
            if len(calls) < 3:
                raise OSError("connection reset")
            return ("/fake/model", "5")

        assert stt._get_model_with_retry(flaky, {}) == ("/fake/model", "5")
        assert len(calls) == 3

    def test_persistent_download_failure_raises_runtime_error(self, monkeypatch):
        monkeypatch.setattr("klaus.stt.time.sleep", lambda _s: None)
        patcher, _ = _patch_moonshine()
        with patcher:
            stt = SpeechToText()

        def always_fails(language, **kwargs):
            raise OSError("no route to host")

        with pytest.raises(RuntimeError, match="Moonshine speech model"):
            stt._get_model_with_retry(always_fails, {})
