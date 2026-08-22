"""Tests for klaus.services.speculative_stt."""

from __future__ import annotations

from unittest.mock import MagicMock

from klaus.services.speculative_stt import SpeculativeTranscriber


class TestSpeculativeTranscriber:
    def test_collect_returns_result_when_gap_matches(self):
        transcribe = MagicMock(return_value="hello world")
        spec = SpeculativeTranscriber(transcribe)

        early_wav = b"\x00" * 100
        final_wav = b"\x00" * 148  # exactly 48 bytes of appended silence

        spec.start(early_wav)
        result = spec.collect(final_wav, expected_gap_bytes=48)

        assert result == "hello world"
        transcribe.assert_called_once_with(early_wav)

    def test_collect_rejects_mismatched_gap(self):
        transcribe = MagicMock(return_value="hello world")
        spec = SpeculativeTranscriber(transcribe)

        spec.start(b"\x00" * 100)
        result = spec.collect(b"\x00" * 200, expected_gap_bytes=48)

        assert result is None

    def test_collect_without_start_returns_none(self):
        spec = SpeculativeTranscriber(MagicMock())
        assert spec.collect(b"\x00" * 100, expected_gap_bytes=48) is None

    def test_collect_with_zero_gap_disabled(self):
        spec = SpeculativeTranscriber(MagicMock(return_value="x"))
        spec.start(b"\x00" * 100)
        assert spec.collect(b"\x00" * 100, expected_gap_bytes=0) is None

    def test_restart_supersedes_previous_speculation(self):
        transcribe = MagicMock(
            side_effect=lambda wav: "second" if len(wav) == 160 else "first"
        )
        spec = SpeculativeTranscriber(transcribe)

        spec.start(b"\x00" * 100)
        spec.start(b"\x00" * 160)
        result = spec.collect(b"\x00" * 208, expected_gap_bytes=48)

        assert result == "second"

    def test_clear_invalidates_pending_result(self):
        spec = SpeculativeTranscriber(MagicMock(return_value="x"))
        spec.start(b"\x00" * 100)
        spec.clear()
        assert spec.collect(b"\x00" * 148, expected_gap_bytes=48) is None

    def test_transcribe_failure_yields_none(self):
        transcribe = MagicMock(side_effect=RuntimeError("boom"))
        spec = SpeculativeTranscriber(transcribe)
        spec.start(b"\x00" * 100)
        assert spec.collect(b"\x00" * 148, expected_gap_bytes=48) is None
