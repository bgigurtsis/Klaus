import io
import logging
import wave
from typing import Any

import numpy as np
from openai import OpenAI
from klaus.config import (
    OPENAI_API_KEY,
    STT_LOCAL_PRECHECK_ENABLED,
    STT_LOCAL_PRECHECK_LANGUAGE,
    STT_LOCAL_PRECHECK_MIN_CHARS,
    STT_LOCAL_PRECHECK_MODEL,
    STT_MODEL,
)

logger = logging.getLogger(__name__)


class SpeechToText:
    """Transcribes audio using OpenAI gpt-4o-mini-transcribe."""

    def __init__(self):
        self._client = OpenAI(api_key=OPENAI_API_KEY)
        self._last_used_cloud = False
        self._local_precheck_enabled = STT_LOCAL_PRECHECK_ENABLED
        self._local_precheck_model_name = STT_LOCAL_PRECHECK_MODEL
        self._local_precheck_language = STT_LOCAL_PRECHECK_LANGUAGE.strip() or None
        self._local_precheck_min_chars = max(0, STT_LOCAL_PRECHECK_MIN_CHARS)
        self._local_precheck_model: Any | None = None

        if self._local_precheck_enabled:
            self._local_precheck_model = self._load_local_precheck_model()

    @property
    def last_used_cloud(self) -> bool:
        """Whether the most recent transcribe call hit OpenAI STT."""
        return self._last_used_cloud

    def transcribe(self, wav_bytes: bytes) -> str:
        """Send WAV audio bytes to gpt-4o-mini-transcribe, return the transcribed text."""
        self._last_used_cloud = False

        if self._local_precheck_model is not None and not self._passes_local_precheck(wav_bytes):
            logger.info("Local STT precheck rejected clip, skipping OpenAI transcription")
            return ""

        logger.info("Transcribing audio (%.1f KB, model=%s)", len(wav_bytes) / 1024, STT_MODEL)
        buf = io.BytesIO(wav_bytes)
        buf.name = "recording.wav"

        self._last_used_cloud = True
        result = self._client.audio.transcriptions.create(
            model=STT_MODEL,
            file=buf,
            response_format="text",
        )
        text = result.strip() if isinstance(result, str) else result.text.strip()
        logger.info("Transcript (%d chars): %s", len(text), text[:80])
        return text

    def _load_local_precheck_model(self) -> Any | None:
        """Load optional local Whisper model used as an STT precheck gate."""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.warning(
                (
                    "Local STT precheck enabled but faster-whisper is not installed. "
                    "Install with `pip install faster-whisper` to enable it."
                )
            )
            self._local_precheck_enabled = False
            return None

        try:
            model = WhisperModel(
                self._local_precheck_model_name,
                device="cpu",
                compute_type="int8",
            )
        except (RuntimeError, ValueError, OSError) as exc:
            logger.warning(
                "Failed to load local STT precheck model '%s': %s",
                self._local_precheck_model_name,
                exc,
            )
            self._local_precheck_enabled = False
            return None

        logger.info(
            "Local STT precheck enabled (model=%s, min_chars=%d, language=%s)",
            self._local_precheck_model_name,
            self._local_precheck_min_chars,
            self._local_precheck_language or "auto",
        )
        return model

    def _passes_local_precheck(self, wav_bytes: bytes) -> bool:
        """Return True when local precheck detects likely speech content."""
        try:
            audio = self._wav_bytes_to_float32(wav_bytes)
            segments, _ = self._local_precheck_model.transcribe(
                audio,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                language=self._local_precheck_language,
                condition_on_previous_text=False,
                without_timestamps=True,
            )
            preview = " ".join(seg.text.strip() for seg in segments).strip()
        except (RuntimeError, ValueError, OSError) as exc:
            logger.warning("Local STT precheck failed, falling back to OpenAI STT: %s", exc)
            return True

        content_chars = self._content_char_count(preview)
        if content_chars < self._local_precheck_min_chars:
            logger.info(
                "Local STT precheck rejected clip (%d chars < %d)",
                content_chars,
                self._local_precheck_min_chars,
            )
            return False

        logger.debug("Local STT precheck accepted clip (%d chars)", content_chars)
        return True

    @staticmethod
    def _wav_bytes_to_float32(wav_bytes: bytes) -> np.ndarray:
        """Decode WAV bytes to mono float32 samples in [-1, 1]."""
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frame_count = wf.getnframes()
            raw_frames = wf.readframes(frame_count)

        if sample_width != 2:
            raise ValueError(f"Unsupported WAV sample width: {sample_width}")

        audio = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32)
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        return audio / 32768.0

    @staticmethod
    def _content_char_count(text: str) -> int:
        """Count alphanumeric chars, ignoring punctuation-only noise."""
        return sum(1 for ch in text if ch.isalnum())
