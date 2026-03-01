"""Tests for klaus.tts -- text-to-speech chunking and synthesis."""

import io
import wave
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

from klaus.tts import TextToSpeech, SENTENCE_SPLIT, MAX_CHUNK_CHARS


def _make_wav_bytes(duration_ms=100, sample_rate=24000):
    """Generate a minimal valid WAV file for testing."""
    n_samples = int(sample_rate * duration_ms / 1000)
    audio = np.zeros(n_samples, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


class TestSplitIntoChunks:
    def test_single_sentence(self):
        chunks = TextToSpeech._split_into_chunks("Hello world.")
        assert chunks == ["Hello world."]

    def test_multiple_sentences(self):
        text = "First sentence. Second sentence. Third sentence."
        chunks = TextToSpeech._split_into_chunks(text)
        assert chunks == ["First sentence. Second sentence. Third sentence."]

    def test_empty_text(self):
        assert TextToSpeech._split_into_chunks("") == []
        assert TextToSpeech._split_into_chunks("   ") == []

    def test_whitespace_only(self):
        assert TextToSpeech._split_into_chunks("  \n\t  ") == []

    def test_no_punctuation(self):
        chunks = TextToSpeech._split_into_chunks("Just a fragment without ending punctuation")
        assert len(chunks) == 1

    def test_exclamation_and_question_marks(self):
        text = "Is this working? Yes it is! Great."
        chunks = TextToSpeech._split_into_chunks(text)
        assert len(chunks) == 1
        assert "Is this working?" in chunks[0]

    def test_long_text_splits_at_chunk_boundary(self):
        sentence = "A" * 2000 + ". "
        text = sentence * 3  # ~6000 chars, should split
        chunks = TextToSpeech._split_into_chunks(text)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk) <= MAX_CHUNK_CHARS

    def test_single_very_long_sentence(self):
        text = "A" * 5000 + "."
        chunks = TextToSpeech._split_into_chunks(text)
        assert len(chunks) >= 1

    def test_preserves_all_content(self):
        text = "First sentence. Second sentence. Third sentence."
        chunks = TextToSpeech._split_into_chunks(text)
        rejoined = " ".join(chunks)
        for word in ["First", "Second", "Third"]:
            assert word in rejoined


class TestSpeakWithMock:
    @patch("klaus.tts.sd")
    @patch("klaus.tts.OpenAI")
    def test_speak_calls_api_and_plays(self, mock_openai_cls, mock_sd):
        wav_data = _make_wav_bytes()

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = wav_data
        mock_client.audio.speech.create.return_value = mock_response

        mock_stream = MagicMock()
        mock_stream.active = False
        mock_sd.get_stream.return_value = mock_stream

        tts = TextToSpeech()
        tts.speak("Hello world.")

        mock_client.audio.speech.create.assert_called()
        mock_sd.play.assert_called()

    @patch("klaus.tts.sd")
    @patch("klaus.tts.OpenAI")
    def test_speak_empty_text_does_nothing(self, mock_openai_cls, mock_sd):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        tts = TextToSpeech()
        tts.speak("")

        mock_client.audio.speech.create.assert_not_called()
        mock_sd.play.assert_not_called()

    @patch("klaus.tts.sd")
    @patch("klaus.tts.OpenAI")
    def test_speak_fires_callback(self, mock_openai_cls, mock_sd):
        wav_data = _make_wav_bytes()

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = wav_data
        mock_client.audio.speech.create.return_value = mock_response

        mock_stream = MagicMock()
        mock_stream.active = False
        mock_sd.get_stream.return_value = mock_stream

        tts = TextToSpeech()
        callback = MagicMock()
        tts.speak("Hello world.", on_sentence_start=callback)

        callback.assert_called()

    @patch("klaus.tts.sd")
    @patch("klaus.tts.OpenAI")
    def test_synthesize_to_wav(self, mock_openai_cls, mock_sd):
        wav_data = _make_wav_bytes()

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = wav_data
        mock_client.audio.speech.create.return_value = mock_response

        tts = TextToSpeech()
        result = tts.synthesize_to_wav("Test text.")

        assert result == wav_data
        mock_client.audio.speech.create.assert_called_once()

    def test_stop_sets_event(self):
        with patch("klaus.tts.OpenAI"), patch("klaus.tts.sd"):
            tts = TextToSpeech()
            tts.stop()
            assert tts._stop_event.is_set()
