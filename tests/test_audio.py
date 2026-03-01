"""Tests for klaus.audio -- push-to-talk recording and playback."""

import io
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from klaus.audio import PushToTalkRecorder, AudioPlayer


class TestPushToTalkRecorder:
    def test_not_recording_by_default(self):
        rec = PushToTalkRecorder()
        assert rec.is_recording is False

    def test_stop_recording_when_not_started(self):
        rec = PushToTalkRecorder()
        result = rec.stop_recording()
        assert result is None

    @patch("klaus.audio.sd.InputStream")
    def test_start_recording(self, mock_stream_cls):
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream

        rec = PushToTalkRecorder()
        rec.start_recording()

        assert rec.is_recording is True
        mock_stream.start.assert_called_once()

    @patch("klaus.audio.sd.InputStream")
    def test_start_recording_twice_is_idempotent(self, mock_stream_cls):
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream

        rec = PushToTalkRecorder()
        rec.start_recording()
        rec.start_recording()

        assert mock_stream_cls.call_count == 1

    @patch("klaus.audio.sd.InputStream")
    def test_stop_recording_returns_wav(self, mock_stream_cls):
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream

        rec = PushToTalkRecorder()
        rec.start_recording()
        rec._chunks = [np.zeros((1600, 1), dtype=np.int16)]
        wav_bytes = rec.stop_recording()

        assert wav_bytes is not None
        assert rec.is_recording is False

        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 1600

    @patch("klaus.audio.sd.InputStream")
    def test_stop_recording_no_chunks(self, mock_stream_cls):
        mock_stream = MagicMock()
        mock_stream_cls.return_value = mock_stream

        rec = PushToTalkRecorder()
        rec.start_recording()
        result = rec.stop_recording()

        assert result is None

    def test_audio_callback_stores_chunks(self):
        rec = PushToTalkRecorder()
        rec._recording = True

        fake_data = np.random.randint(-1000, 1000, (160, 1), dtype=np.int16)
        rec._audio_callback(fake_data, 160, None, None)
        rec._audio_callback(fake_data, 160, None, None)

        assert len(rec._chunks) == 2

    def test_audio_callback_ignores_when_not_recording(self):
        rec = PushToTalkRecorder()
        rec._recording = False

        fake_data = np.random.randint(-1000, 1000, (160, 1), dtype=np.int16)
        rec._audio_callback(fake_data, 160, None, None)

        assert len(rec._chunks) == 0

    def test_to_wav_bytes_produces_valid_wav(self):
        rec = PushToTalkRecorder(sample_rate=16000)
        audio = np.zeros((3200, 1), dtype=np.int16)
        wav_bytes = rec._to_wav_bytes(audio)

        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 3200


class TestAudioPlayer:
    def _make_wav(self, n_frames=4800, sample_rate=24000):
        audio = np.zeros(n_frames, dtype=np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio.tobytes())
        return buf.getvalue()

    @patch("klaus.audio.sd")
    def test_play_wav_bytes(self, mock_sd):
        mock_stream = MagicMock()
        mock_stream.active = False
        mock_sd.get_stream.return_value = mock_stream

        player = AudioPlayer()
        player.play_wav_bytes(self._make_wav())

        mock_sd.play.assert_called_once()

    @patch("klaus.audio.sd")
    def test_stop(self, mock_sd):
        player = AudioPlayer()
        player.stop()
        assert player._stop_event.is_set()
        mock_sd.stop.assert_called_once()
