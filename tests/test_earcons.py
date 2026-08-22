"""Tests for klaus.earcons -- synthesized state-cue tones."""

import numpy as np
import pytest

from klaus import earcons


@pytest.mark.parametrize(
    "factory",
    [earcons.listening_tone, earcons.accept_tone, earcons.cancel_tone],
)
def test_tones_are_short_int16_mono(factory):
    tone = factory()
    assert tone.dtype == np.int16
    assert tone.ndim == 1
    assert 0 < len(tone) <= earcons.SAMPLE_RATE // 2  # under 500ms
    # Quiet but audible, with no clipping.
    peak = np.abs(tone).max()
    assert 0 < peak < 32767 // 2


def test_tones_start_and_end_near_silence():
    tone = earcons.listening_tone()
    assert abs(int(tone[0])) < 500
    assert abs(int(tone[-1])) < 500
