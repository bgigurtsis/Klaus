import ctypes
import io
import logging
import sys
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np
from klaus.config import (
    STT_MOONSHINE_LANGUAGE,
    STT_MOONSHINE_MODEL,
)

logger = logging.getLogger(__name__)


def _preload_native_lib() -> None:
    """Pre-load moonshine.dll before PyQt6 to avoid WinError 1114 on Windows.

    PyQt6 loads DLLs that conflict with moonshine's native library if it hasn't
    been loaded first.  Calling this at import time (before PyQt6) sidesteps the
    issue entirely.
    """
    if sys.platform != "win32":
        return
    try:
        import moonshine_voice
        dll = Path(moonshine_voice.__file__).parent / "moonshine.dll"
        if dll.exists():
            ctypes.CDLL(str(dll))
    except Exception:
        pass


_preload_native_lib()


class SpeechToText:
    """Transcribes audio using Moonshine Voice (local, on-device)."""

    def __init__(self) -> None:
        self._transcriber = self._load_moonshine()

    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcribe WAV audio bytes to text."""
        return self._transcribe_moonshine(wav_bytes)

    # ------------------------------------------------------------------
    # Moonshine backend
    # ------------------------------------------------------------------

    def _load_moonshine(self) -> Any:
        """Load the Moonshine Voice transcriber, downloading the model if needed."""
        try:
            from moonshine_voice import (
                Transcriber,
                get_model_for_language,
            )
        except ImportError as exc:
            raise RuntimeError(
                "moonshine-voice is not installed. "
                "Install with `pip install moonshine-voice`."
            ) from exc

        logger.info(
            "Loading Moonshine STT (model=%s, language=%s) ...",
            STT_MOONSHINE_MODEL,
            STT_MOONSHINE_LANGUAGE,
        )
        t0 = time.monotonic()
        model_path, model_arch = get_model_for_language(
            STT_MOONSHINE_LANGUAGE
        )
        transcriber = Transcriber(
            model_path=model_path, model_arch=model_arch
        )
        elapsed = time.monotonic() - t0
        logger.info(
            "Moonshine STT ready in %.1fs (language=%s, path=%s)",
            elapsed,
            STT_MOONSHINE_LANGUAGE,
            model_path,
        )
        return transcriber

    def _transcribe_moonshine(self, wav_bytes: bytes) -> str:
        """Run Moonshine Voice on WAV bytes, return transcript text."""
        audio, sample_rate = self._decode_wav(wav_bytes)
        logger.info(
            "Transcribing audio (%.1f KB, backend=moonshine)",
            len(wav_bytes) / 1024,
        )

        transcript = self._transcriber.transcribe_without_streaming(
            audio.tolist(), sample_rate
        )

        parts = [line.text.strip() for line in transcript.lines if line.text.strip()]
        text = " ".join(parts)
        logger.info("Transcript (%d chars): %s", len(text), text[:80])
        return text

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_wav(wav_bytes: bytes) -> tuple[np.ndarray, int]:
        """Decode WAV bytes to mono float32 samples in [-1, 1] and sample rate."""
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            raw_frames = wf.readframes(wf.getnframes())

        if sample_width != 2:
            raise ValueError(f"Unsupported WAV sample width: {sample_width}")

        audio = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32)
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        return audio / 32768.0, sample_rate
