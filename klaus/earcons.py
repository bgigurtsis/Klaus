"""Short synthesized audio cues for state transitions.

Tones are generated with numpy (no asset files) as int16 mono PCM at the
TTS output rate, so they can play through the persistent TTS output stream.
"""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 24000
_AMPLITUDE = 0.18  # quiet, non-startling


def _tone(freq_hz: float, duration_ms: int, amplitude: float = _AMPLITUDE) -> np.ndarray:
    """Generate one sine tone with a short fade envelope (avoids clicks)."""
    n = int(SAMPLE_RATE * duration_ms / 1000)
    t = np.arange(n) / SAMPLE_RATE
    wave = np.sin(2 * np.pi * freq_hz * t)

    fade = max(1, int(SAMPLE_RATE * 0.008))  # 8ms fade in/out
    envelope = np.ones(n)
    envelope[:fade] = np.linspace(0.0, 1.0, fade)
    envelope[-fade:] = np.linspace(1.0, 0.0, fade)

    return (wave * envelope * amplitude * 32767).astype(np.int16)


def _silence(duration_ms: int) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * duration_ms / 1000), dtype=np.int16)


def listening_tone() -> np.ndarray:
    """Short rising blip: recording started."""
    return np.concatenate([_tone(660, 60), _tone(880, 70)])


def accept_tone() -> np.ndarray:
    """Soft double blip: question captured, Klaus is thinking."""
    return np.concatenate([_tone(880, 50), _silence(40), _tone(880, 50)])


def cancel_tone() -> np.ndarray:
    """Low tone: turn cancelled or errored."""
    return _tone(220, 130)
