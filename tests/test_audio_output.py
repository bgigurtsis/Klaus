"""Concurrency tests for live PCM playback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from klaus.audio_output import AudioOutput


@patch("klaus.audio_output.sd.OutputStream")
def test_old_playback_cannot_close_new_stream(output_stream) -> None:
    first_stream = MagicMock(closed=False)
    second_stream = MagicMock(closed=False)
    output_stream.side_effect = [first_stream, second_stream]
    output = AudioOutput()

    first_id = output._begin_playback()
    assert output._ensure_stream(24_000, 1, first_id) is first_stream
    second_id = output._begin_playback()
    assert output._ensure_stream(24_000, 1, second_id) is second_stream

    output._close_stream(first_id)

    first_stream.close.assert_called_once()
    second_stream.close.assert_not_called()
    assert output._stream is second_stream


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
