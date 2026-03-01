"""Tests for klaus.stt -- speech-to-text via OpenAI."""

import io
import wave
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


class TestSpeechToText:
    @patch("klaus.stt.OpenAI")
    def test_transcribe_returns_string(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "  Hello world  "

        stt = SpeechToText()
        result = stt.transcribe(_make_wav_bytes())

        assert result == "Hello world"
        mock_client.audio.transcriptions.create.assert_called_once()

    @patch("klaus.stt.OpenAI")
    def test_transcribe_returns_object_with_text(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_result = MagicMock()
        mock_result.text = "  Some transcription  "
        mock_result.strip = MagicMock(side_effect=AttributeError)
        mock_client.audio.transcriptions.create.return_value = mock_result

        stt = SpeechToText()
        result = stt.transcribe(_make_wav_bytes())

        assert result == "Some transcription"

    @patch("klaus.stt.OpenAI")
    def test_transcribe_passes_correct_model(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "test"

        stt = SpeechToText()
        stt.transcribe(_make_wav_bytes())

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini-transcribe"
        assert call_kwargs["response_format"] == "text"

    @patch("klaus.stt.OpenAI")
    def test_transcribe_sends_wav_file(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.audio.transcriptions.create.return_value = "test"

        stt = SpeechToText()
        wav = _make_wav_bytes()
        stt.transcribe(wav)

        call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
        file_arg = call_kwargs["file"]
        assert file_arg.name == "recording.wav"
