"""Tests for klaus.audio -- push-to-talk recording, VAD, and playback."""

import io
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from klaus.audio import (
    FRAME_SIZE,
    AudioPlayer,
    PushToTalkRecorder,
    VoiceActivatedRecorder,
    to_wav_bytes,
)


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
        audio = np.zeros((3200, 1), dtype=np.int16)
        wav_bytes = to_wav_bytes(audio, sample_rate=16000)

        buf = io.BytesIO(wav_bytes)
        with wave.open(buf, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000
            assert wf.getnframes() == 3200


def _make_vad_recorder(**kwargs):
    defaults = dict(
        on_speech_start=MagicMock(),
        on_speech_end=MagicMock(),
        silence_timeout=0.3,  # 10 frames
        min_duration=0.0,
        min_voiced_ratio=0.0,
        min_voiced_frames=1,
        min_rms_dbfs=-120.0,
        min_voiced_run_frames=1,
    )
    defaults.update(kwargs)
    return VoiceActivatedRecorder(**defaults)


class TestVoiceStartGate:
    def test_resume_settle_drops_playback_tail_before_listening(self):
        started = MagicMock()
        rec = _make_vad_recorder(on_speech_start=started, start_trigger_ms=90)
        rec._vad = MagicMock()
        rec._vad.is_speech.return_value = True
        frame = np.full(FRAME_SIZE, 1000, dtype=np.int16)
        indata = frame.reshape(-1, 1)
        rec._running = True
        rec.pause()

        rec.resume(settle_ms=90)
        for _ in range(3):
            rec._audio_callback(indata, FRAME_SIZE, None, None)

        started.assert_not_called()
        assert rec._speaking is False

        for _ in range(3):
            rec._audio_callback(indata, FRAME_SIZE, None, None)

        started.assert_called_once()
        assert rec._speaking is True

    def test_single_vad_spike_does_not_start_listening(self):
        started = MagicMock()
        rec = _make_vad_recorder(on_speech_start=started, start_trigger_ms=90)
        rec._vad = MagicMock()
        frame = np.full(FRAME_SIZE, 1000, dtype=np.int16)

        rec._vad.is_speech.side_effect = [True, False, False, False]
        for _ in range(4):
            rec._process_frame(frame)

        started.assert_not_called()
        assert rec._speaking is False

    def test_three_consecutive_voiced_frames_start_listening(self):
        started = MagicMock()
        rec = _make_vad_recorder(on_speech_start=started, start_trigger_ms=90)
        rec._vad = MagicMock()
        rec._vad.is_speech.return_value = True
        frame = np.full(FRAME_SIZE, 1000, dtype=np.int16)

        for _ in range(3):
            rec._process_frame(frame)

        started.assert_called_once()
        assert rec._speaking is True
        assert len(rec._chunks) == 3

    def test_vad_positive_frames_below_rms_floor_do_not_start(self):
        started = MagicMock()
        rec = _make_vad_recorder(
            on_speech_start=started,
            start_trigger_ms=90,
            min_rms_dbfs=-40.0,
        )
        rec._vad = MagicMock()
        rec._vad.is_speech.return_value = True
        quiet = np.full(FRAME_SIZE, 10, dtype=np.int16)

        for _ in range(6):
            rec._process_frame(quiet)

        started.assert_not_called()
        assert rec._speaking is False


class TestSpeculativeMaybeEnd:
    def test_maybe_end_fires_before_finalize_with_exact_gap(self):
        maybe: list[bytes] = []
        ended: list[bytes] = []
        rec = _make_vad_recorder(
            on_speech_end=ended.append,
            on_speech_maybe_end=maybe.append,
            early_silence_timeout=0.15,  # 5 frames
        )
        rec._vad = MagicMock()
        frame = np.full(FRAME_SIZE, 1000, dtype=np.int16)

        rec._vad.is_speech.return_value = True
        for _ in range(5):
            rec._process_frame(frame)
        rec._vad.is_speech.return_value = False
        for _ in range(5):
            rec._process_frame(frame)

        assert len(maybe) == 1
        assert not ended

        for _ in range(5):
            rec._process_frame(frame)

        assert len(ended) == 1
        assert len(ended[0]) - len(maybe[0]) == rec.speculative_gap_bytes

    def test_resumed_speech_breaks_the_gap(self):
        maybe: list[bytes] = []
        ended: list[bytes] = []
        rec = _make_vad_recorder(
            on_speech_end=ended.append,
            on_speech_maybe_end=maybe.append,
            early_silence_timeout=0.15,
        )
        rec._vad = MagicMock()
        frame = np.full(FRAME_SIZE, 1000, dtype=np.int16)

        rec._vad.is_speech.return_value = True
        for _ in range(5):
            rec._process_frame(frame)
        rec._vad.is_speech.return_value = False
        for _ in range(5):
            rec._process_frame(frame)
        assert len(maybe) == 1

        # Speech resumes, then silence to finalize.
        rec._vad.is_speech.return_value = True
        for _ in range(3):
            rec._process_frame(frame)
        rec._vad.is_speech.return_value = False
        for _ in range(10):
            rec._process_frame(frame)

        assert len(maybe) == 2  # second early snapshot fired
        assert len(ended) == 1
        # Final audio matches the *second* snapshot's gap, not the first.
        assert len(ended[0]) - len(maybe[0]) != rec.speculative_gap_bytes
        assert len(ended[0]) - len(maybe[1]) == rec.speculative_gap_bytes

    def test_disabled_when_early_timeout_not_below_final(self):
        rec = _make_vad_recorder(
            on_speech_maybe_end=MagicMock(),
            early_silence_timeout=0.5,  # >= silence_timeout of 0.3
        )
        assert rec.speculative_gap_bytes == 0


class TestBargeInGate:
    def _gated_recorder(self, barge):
        rec = _make_vad_recorder(
            on_barge_in=barge.append,
            barge_in_min_voiced_ms=90,  # 3 frames
            barge_in_rms_margin_dbfs=6.0,
            min_rms_dbfs=-60.0,
        )
        rec._gate_vad = MagicMock()
        rec._gate_vad.is_speech.return_value = True
        rec.enter_gated_mode()
        return rec

    def test_loud_speech_triggers_barge_in_after_calibration(self):
        barge: list[np.ndarray] = []
        rec = self._gated_recorder(barge)
        quiet = np.full(FRAME_SIZE, 10, dtype=np.int16)
        loud = np.full(FRAME_SIZE, 5000, dtype=np.int16)

        for _ in range(rec._gate_calib_frames):
            rec._process_gate_frame(quiet)
        assert not barge

        for _ in range(3):
            rec._process_gate_frame(loud)

        assert len(barge) == 1
        assert rec._gated is False
        assert isinstance(barge[0], np.ndarray)

    def test_default_gate_accepts_normal_interjection_quickly(self):
        barge: list[np.ndarray] = []
        rec = _make_vad_recorder(
            on_barge_in=barge.append,
            min_rms_dbfs=-60.0,
        )
        rec._gate_vad = MagicMock()
        rec._gate_vad.is_speech.return_value = True
        rec.enter_gated_mode()
        playback = np.full(FRAME_SIZE, 100, dtype=np.int16)
        speech = np.full(FRAME_SIZE, 200, dtype=np.int16)

        for _ in range(rec._gate_calib_frames):
            rec._process_gate_frame(playback)
        for _ in range(4):
            rec._process_gate_frame(speech)

        assert len(barge) == 1
        assert len(barge[0]) <= FRAME_SIZE * 7

    def test_delayed_playback_bleed_stays_inside_calibration(self):
        barge: list[np.ndarray] = []
        rec = self._gated_recorder(barge)
        silence = np.full(FRAME_SIZE, 10, dtype=np.int16)
        playback = np.full(FRAME_SIZE, 5000, dtype=np.int16)

        for _ in range(5):
            rec._process_gate_frame(silence)
        for _ in range(rec._gate_calib_frames - 5):
            rec._process_gate_frame(playback)
        for _ in range(10):
            rec._process_gate_frame(playback)

        assert not barge
        assert rec._gated is True

    def test_playback_bleed_does_not_trigger(self):
        barge: list[np.ndarray] = []
        rec = self._gated_recorder(barge)
        quiet = np.full(FRAME_SIZE, 10, dtype=np.int16)

        for _ in range(30):
            rec._process_gate_frame(quiet)

        assert not barge
        assert rec._gated is True

    def test_prime_with_seed_starts_utterance(self):
        started = MagicMock()
        rec = _make_vad_recorder(on_speech_start=started)
        seed = np.full(FRAME_SIZE * 5, 1000, dtype=np.int16)

        rec.prime_with_seed(seed)

        assert rec._speaking is True
        assert len(rec._chunks) == 1
        started.assert_called_once()


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
