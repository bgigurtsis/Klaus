import io
import logging
import re
import threading
import queue
import wave

import numpy as np
import sounddevice as sd
from openai import OpenAI

import klaus.config as _config
from klaus.config import OPENAI_API_KEY, TTS_MODEL, TTS_SPEED, TTS_VOICE, TTS_VOICE_INSTRUCTIONS

logger = logging.getLogger(__name__)

SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')
MAX_CHUNK_CHARS = 4000


class TextToSpeech:
    """Converts text to speech using gpt-4o-mini-tts with sentence-level streaming playback."""

    def __init__(self):
        self._client = OpenAI(api_key=OPENAI_API_KEY)
        self._stop_event = threading.Event()
        self._playback_thread: threading.Thread | None = None

    def reload_client(self) -> None:
        """Recreate the OpenAI client to pick up key changes from config.reload()."""
        self._client = OpenAI(api_key=_config.OPENAI_API_KEY)

    def speak(self, text: str, on_sentence_start: callable = None) -> None:
        """Synthesize and play text. Batches into sentences for low-latency start.

        Args:
            text: The full text to speak.
            on_sentence_start: Optional callback(sentence_index, sentence_text) fired
                               before each sentence begins playback.
        """
        self._stop_event.clear()
        chunks = self._split_into_chunks(text)
        if not chunks:
            return

        logger.info(
            "TTS speaking (%d chars, %d chunks, voice=%s, model=%s)",
            len(text), len(chunks), TTS_VOICE, TTS_MODEL,
        )

        audio_queue: queue.Queue[bytes | None] = queue.Queue()

        synth_thread = threading.Thread(
            target=self._synthesize_worker,
            args=(chunks, audio_queue),
            daemon=True,
        )
        synth_thread.start()

        for i, chunk_text in enumerate(chunks):
            if self._stop_event.is_set():
                break
            wav_data = audio_queue.get()
            if wav_data is None:
                break
            if on_sentence_start:
                on_sentence_start(i, chunk_text)
            self._play_wav(wav_data)

    def speak_streaming(self, sentence_queue: queue.Queue[str | None]) -> None:
        """Play sentences as they arrive from a queue.

        Reads sentences from sentence_queue, synthesizes each via the API,
        and plays them sequentially. None in the queue signals completion.
        """
        self._stop_event.clear()
        audio_q: queue.Queue[bytes | None] = queue.Queue()

        synth_thread = threading.Thread(
            target=self._streaming_synth_worker,
            args=(sentence_queue, audio_q),
            daemon=True,
        )
        synth_thread.start()

        while not self._stop_event.is_set():
            wav_data = audio_q.get()
            if wav_data is None:
                break
            self._play_wav(wav_data)

        logger.info("TTS streaming playback finished")

    def _streaming_synth_worker(
        self,
        sentence_queue: queue.Queue[str | None],
        audio_queue: queue.Queue[bytes | None],
    ) -> None:
        """Read sentences from the input queue and synthesize them into audio."""
        idx = 0
        while not self._stop_event.is_set():
            sentence = sentence_queue.get()
            if sentence is None:
                break
            try:
                idx += 1
                logger.debug("Streaming synth chunk %d (%d chars)", idx, len(sentence))
                response = self._client.audio.speech.create(
                    model=TTS_MODEL,
                    voice=TTS_VOICE,
                    input=sentence,
                    instructions=TTS_VOICE_INSTRUCTIONS,
                    response_format="wav",
                    speed=TTS_SPEED,
                )
                audio_queue.put(response.content)
            except Exception as e:
                logger.warning("Streaming TTS synthesis failed on chunk %d: %s", idx, e)
                break
        audio_queue.put(None)

    def synthesize_to_wav(self, text: str) -> bytes:
        """Synthesize text to a single WAV buffer without playing it."""
        response = self._client.audio.speech.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=text,
            instructions=TTS_VOICE_INSTRUCTIONS,
            response_format="wav",
            speed=TTS_SPEED,
        )
        return response.content

    def _synthesize_worker(
        self, chunks: list[str], audio_queue: queue.Queue
    ) -> None:
        for i, chunk in enumerate(chunks):
            if self._stop_event.is_set():
                audio_queue.put(None)
                return
            try:
                logger.debug("Synthesizing chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))
                response = self._client.audio.speech.create(
                    model=TTS_MODEL,
                    voice=TTS_VOICE,
                    input=chunk,
                    instructions=TTS_VOICE_INSTRUCTIONS,
                    response_format="wav",
                    speed=TTS_SPEED,
                )
                audio_queue.put(response.content)
            except Exception as e:
                logger.warning("TTS synthesis failed on chunk %d: %s", i + 1, e)
                audio_queue.put(None)
                return
        audio_queue.put(None)

    def _play_wav(self, wav_data: bytes) -> None:
        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            channels = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())

        audio = np.frombuffer(frames, dtype=np.int16)
        if channels > 1:
            audio = audio.reshape(-1, channels)

        sd.play(audio, samplerate=rate)
        while sd.get_stream().active and not self._stop_event.is_set():
            sd.sleep(50)
        if self._stop_event.is_set():
            sd.stop()

    def stop(self) -> None:
        logger.info("TTS playback interrupted")
        self._stop_event.set()
        sd.stop()

    @staticmethod
    def _split_into_chunks(text: str) -> list[str]:
        """Split text into sentence-sized chunks respecting the token limit."""
        sentences = SENTENCE_SPLIT.split(text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 > MAX_CHUNK_CHARS:
                if current:
                    chunks.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip() if current else sentence
        if current:
            chunks.append(current)
        return chunks
