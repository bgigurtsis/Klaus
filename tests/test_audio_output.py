"""Concurrency and lifetime tests for live PCM playback."""

from __future__ import annotations

import queue
import time
from unittest.mock import MagicMock, patch

import numpy as np

from klaus.audio_output import DRAIN_MARGIN_S, AudioOutput


@patch("klaus.audio_output.sd.OutputStream")
def test_stream_stays_open_across_playbacks(output_stream) -> None:
    stream = MagicMock(closed=False)
    output_stream.return_value = stream
    output = AudioOutput()

    output.play_pcm(np.arange(100, dtype=np.int16))
    output.play_pcm(np.arange(100, dtype=np.int16))

    output_stream.assert_called_once()
    stream.close.assert_not_called()


@patch("klaus.audio_output.sd.OutputStream")
def test_stop_invalidates_current_playback(output_stream) -> None:
    stream = MagicMock(closed=False)
    output_stream.return_value = stream
    output = AudioOutput()
    playback_id = output._begin_playback()
    output._ensure_stream(24_000, 1, playback_id)

    output.stop()

    assert output._is_current(playback_id) is False
    stream.close.assert_called_once()


@patch("klaus.audio_output.sd.OutputStream")
def test_cue_is_skipped_while_response_stream_plays(output_stream) -> None:
    stream = MagicMock(closed=False)
    output_stream.return_value = stream
    output = AudioOutput()

    response_id = output._begin_playback()
    with output._stream_lock:
        output._stream_playback_active = True

    output.play_pcm(np.arange(100, dtype=np.int16))

    # The cue neither wrote audio nor invalidated the response playback.
    stream.write.assert_not_called()
    assert output._is_current(response_id) is True


@patch("klaus.audio_output.sd.OutputStream")
def test_stream_playback_reopens_after_stop(output_stream) -> None:
    first = MagicMock(closed=False)
    second = MagicMock(closed=False)
    output_stream.side_effect = [first, second]
    output = AudioOutput()

    output.play_pcm(np.arange(100, dtype=np.int16))
    output.stop()

    audio_queue: queue.Queue = queue.Queue()
    audio_queue.put(np.arange(100, dtype=np.int16))
    audio_queue.put(None)
    output.play_pcm_stream(audio_queue)

    first.close.assert_called_once()
    second.write.assert_called()
    second.close.assert_not_called()


@patch("klaus.audio_output.sd.OutputStream")
def test_written_audio_is_reported_to_playback_observer(output_stream) -> None:
    stream = MagicMock(closed=False)
    output_stream.return_value = stream
    observer = MagicMock()
    output = AudioOutput(playback_observer=observer)
    audio = np.arange(1_000, dtype=np.int16)

    output.play_pcm(audio)

    observer.assert_called_once()
    reported, rate = observer.call_args.args
    np.testing.assert_array_equal(reported, audio)
    assert rate == 24_000


@patch("klaus.audio_output.sd.OutputStream")
def test_write_sets_drain_deadline_from_stream_latency(output_stream) -> None:
    stream = MagicMock(closed=False, latency=0.3)
    output_stream.return_value = stream
    output = AudioOutput()

    before = time.monotonic()
    output.play_pcm(np.arange(100, dtype=np.int16))
    after = time.monotonic()

    assert output._stream_latency == 0.3
    assert before + 0.3 + DRAIN_MARGIN_S <= output._drain_deadline
    assert output._drain_deadline <= after + 0.3 + DRAIN_MARGIN_S


@patch("klaus.audio_output.sd.OutputStream")
def test_wait_for_drain_returns_immediately_when_nothing_written(
    output_stream,
) -> None:
    output = AudioOutput()

    start = time.monotonic()
    output.wait_for_drain(timeout=1.0)

    assert time.monotonic() - start < 0.1


@patch("klaus.audio_output.sd.OutputStream")
def test_stop_clears_drain_deadline(output_stream) -> None:
    stream = MagicMock(closed=False, latency=0.9)
    output_stream.return_value = stream
    output = AudioOutput()
    output.play_pcm(np.arange(100, dtype=np.int16))
    assert output._drain_deadline > time.monotonic()

    output.stop()

    start = time.monotonic()
    output.wait_for_drain(timeout=1.0)
    assert time.monotonic() - start < 0.1


@patch("klaus.audio_output.sd.OutputStream")
def test_wait_for_drain_respects_timeout(output_stream) -> None:
    output = AudioOutput()
    output._drain_deadline = time.monotonic() + 30.0

    start = time.monotonic()
    output.wait_for_drain(timeout=0.1)

    elapsed = time.monotonic() - start
    assert 0.05 <= elapsed < 0.5


@patch("klaus.audio_output.sd.OutputStream")
def test_unreadable_stream_latency_falls_back(output_stream) -> None:
    stream = MagicMock(closed=False, latency="high")
    output_stream.return_value = stream
    output = AudioOutput()

    output.play_pcm(np.arange(100, dtype=np.int16))

    assert output._stream_latency == 0.5


@patch("klaus.audio_output.sd.OutputStream")
def test_extreme_stream_latency_is_clamped(output_stream) -> None:
    stream = MagicMock(closed=False, latency=5.0)
    output_stream.return_value = stream
    output = AudioOutput()

    output.play_pcm(np.arange(100, dtype=np.int16))

    assert output._stream_latency == 1.0
