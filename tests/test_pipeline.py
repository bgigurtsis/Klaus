"""End-to-end pipeline tests -- full question-answer flow with all externals mocked."""

import io
import json
import time
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from klaus.memory import Memory
from klaus.brain import Brain, Exchange


def _make_wav_bytes(duration_ms=500, sample_rate=16000):
    n_samples = int(sample_rate * duration_ms / 1000)
    audio = np.zeros(n_samples, dtype=np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def _make_text_block(text):
    return SimpleNamespace(type="text", text=text)


def _make_tool_use_block(tool_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)


def _make_response(content_blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=content_blocks, stop_reason=stop_reason)


class TestFullPipelineNoToolUse:
    """Simulate: user speaks -> STT -> Claude (no search) -> memory -> TTS."""

    @patch("klaus.tts.sd")
    @patch("klaus.tts.OpenAI")
    @patch("klaus.stt.OpenAI")
    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_question_answer_flow(
        self,
        mock_anthropic_cls,
        mock_search_cls,
        mock_stt_openai_cls,
        mock_tts_openai_cls,
        mock_sd,
        tmp_db,
    ):
        mock_claude = MagicMock()
        mock_anthropic_cls.return_value = mock_claude
        mock_claude.messages.create.return_value = _make_response(
            [_make_text_block("A p-value represents the probability of observing your data if the null hypothesis is true.")]
        )

        mock_stt_client = MagicMock()
        mock_stt_openai_cls.return_value = mock_stt_client
        mock_stt_client.audio.transcriptions.create.return_value = "What does p-value mean?"

        tts_wav = _make_wav_bytes(duration_ms=100, sample_rate=24000)
        mock_tts_client = MagicMock()
        mock_tts_openai_cls.return_value = mock_tts_client
        mock_tts_response = MagicMock()
        mock_tts_response.content = tts_wav
        mock_tts_client.audio.speech.create.return_value = mock_tts_response

        mock_stream = MagicMock()
        mock_stream.active = False
        mock_sd.get_stream.return_value = mock_stream

        from klaus.stt import SpeechToText
        from klaus.tts import TextToSpeech
        from klaus.camera import Camera

        stt = SpeechToText()
        tts = TextToSpeech()
        brain = Brain()
        memory = Memory(db_path=tmp_db)
        camera = Camera()
        camera._frame = np.zeros((480, 640, 3), dtype=np.uint8)

        session = memory.create_session("Statistics Paper")

        wav_input = _make_wav_bytes()
        transcript = stt.transcribe(wav_input)
        assert transcript == "What does p-value mean?"

        image_b64 = camera.capture_base64_jpeg()

        exchange = brain.ask(
            question=transcript,
            image_base64=image_b64,
        )

        assert "p-value" in exchange.assistant_text.lower()
        assert exchange.searches == []

        record = memory.save_exchange(
            session_id=session.id,
            user_text=exchange.user_text,
            assistant_text=exchange.assistant_text,
            image_base64=exchange.image_base64,
        )

        exchanges = memory.get_exchanges(session.id)
        assert len(exchanges) == 1
        assert exchanges[0].user_text == "What does p-value mean?"

        tts.speak(exchange.assistant_text)
        mock_tts_client.audio.speech.create.assert_called()
        mock_sd.play.assert_called()

        assert memory.count_exchanges() == 1
        memory.close()


class TestFullPipelineWithToolUse:
    """Simulate: user speaks -> STT -> Claude (with search) -> memory -> TTS."""

    @patch("klaus.tts.sd")
    @patch("klaus.tts.OpenAI")
    @patch("klaus.stt.OpenAI")
    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_question_triggers_search(
        self,
        mock_anthropic_cls,
        mock_search_cls,
        mock_stt_openai_cls,
        mock_tts_openai_cls,
        mock_sd,
        tmp_db,
    ):
        mock_claude = MagicMock()
        mock_anthropic_cls.return_value = mock_claude

        mock_search = MagicMock()
        mock_search_cls.return_value = mock_search
        mock_search.search.return_value = "**Shannon 1948**\nhttps://example.com\nA Mathematical Theory of Communication..."

        tool_response = _make_response(
            [_make_tool_use_block("call_1", "web_search", {"query": "Shannon 1948 information theory"})],
            stop_reason="tool_use",
        )
        final_response = _make_response(
            [_make_text_block(
                "Shannon's 1948 paper introduced the concept of information entropy. "
                "It defines a mathematical framework for measuring information content."
            )]
        )
        mock_claude.messages.create.side_effect = [tool_response, final_response]

        mock_stt_client = MagicMock()
        mock_stt_openai_cls.return_value = mock_stt_client
        mock_stt_client.audio.transcriptions.create.return_value = "Who is Shannon and what did he prove?"

        tts_wav = _make_wav_bytes(duration_ms=100, sample_rate=24000)
        mock_tts_client = MagicMock()
        mock_tts_openai_cls.return_value = mock_tts_client
        mock_tts_response = MagicMock()
        mock_tts_response.content = tts_wav
        mock_tts_client.audio.speech.create.return_value = mock_tts_response

        mock_stream = MagicMock()
        mock_stream.active = False
        mock_sd.get_stream.return_value = mock_stream

        from klaus.stt import SpeechToText
        from klaus.tts import TextToSpeech

        stt = SpeechToText()
        tts = TextToSpeech()
        brain = Brain()
        memory = Memory(db_path=tmp_db)

        session = memory.create_session("Information Theory Book")

        transcript = stt.transcribe(_make_wav_bytes())
        exchange = brain.ask(question=transcript)

        assert "Shannon" in exchange.assistant_text
        assert len(exchange.searches) == 1
        assert "Shannon" in exchange.searches[0]["query"]

        record = memory.save_exchange(
            session_id=session.id,
            user_text=exchange.user_text,
            assistant_text=exchange.assistant_text,
            searches=exchange.searches,
        )

        stored = memory.get_exchanges(session.id)
        searches = json.loads(stored[0].searches_json)
        assert len(searches) == 1

        tts.speak(exchange.assistant_text)
        mock_sd.play.assert_called()

        memory.close()


class TestMultiTurnConversation:
    """Simulate a multi-turn session with memory accumulation."""

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_three_turn_conversation(self, mock_anthropic_cls, mock_search_cls, tmp_db):
        mock_claude = MagicMock()
        mock_anthropic_cls.return_value = mock_claude

        answers = [
            "Entropy measures the average information content in a message.",
            "The formula is H = negative sum of p log p, where p is the probability of each symbol.",
            "Higher entropy means more unpredictability. A fair coin has maximum entropy for a binary source.",
        ]

        mock_claude.messages.create.side_effect = [
            _make_response([_make_text_block(a)]) for a in answers
        ]

        brain = Brain()
        memory = Memory(db_path=tmp_db)
        session = memory.create_session("Information Theory")

        questions = [
            "What is entropy in information theory?",
            "What is the formula?",
            "What does high entropy mean practically?",
        ]

        for q, a in zip(questions, answers):
            exchange = brain.ask(question=q)
            assert exchange.assistant_text == a
            memory.save_exchange(session.id, exchange.user_text, exchange.assistant_text)

        assert memory.count_exchanges(session.id) == 3

        assert len(brain._history) == 6  # 3 user + 3 assistant

        # The brain passes self._history (a mutable list) to the API,
        # so by inspection time it includes all 6 entries (3 user + 3 assistant).
        # Verify the API was called 3 times and history has 6 entries.
        assert mock_claude.messages.create.call_count == 3

        summary = memory.get_recent_exchanges_summary(session.id, limit=2)
        assert "formula" in summary.lower() or "entropy" in summary.lower()

        memory.close()


class TestSessionSwitching:
    """Simulate switching between two paper sessions."""

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_switch_sessions_clears_brain_history(self, mock_anthropic_cls, mock_search_cls, tmp_db):
        mock_claude = MagicMock()
        mock_anthropic_cls.return_value = mock_claude
        mock_claude.messages.create.return_value = _make_response(
            [_make_text_block("Answer.")]
        )

        brain = Brain()
        memory = Memory(db_path=tmp_db)

        s1 = memory.create_session("Paper A")
        s2 = memory.create_session("Paper B")

        brain.ask("Question about Paper A")
        memory.save_exchange(s1.id, "Question about Paper A", "Answer.")
        assert len(brain._history) == 2

        brain.clear_history()
        assert len(brain._history) == 0

        brain.ask("Question about Paper B")
        memory.save_exchange(s2.id, "Question about Paper B", "Answer.")
        assert len(brain._history) == 2

        assert memory.count_exchanges(s1.id) == 1
        assert memory.count_exchanges(s2.id) == 1
        assert memory.count_exchanges() == 2

        memory.close()


class TestKnowledgeProfileIntegration:
    """Test that knowledge profile feeds back into brain context."""

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_knowledge_feeds_into_system_prompt(self, mock_anthropic_cls, mock_search_cls, tmp_db):
        mock_claude = MagicMock()
        mock_anthropic_cls.return_value = mock_claude
        mock_claude.messages.create.return_value = _make_response(
            [_make_text_block("Building on your understanding of entropy...")]
        )

        brain = Brain()
        memory = Memory(db_path=tmp_db)

        memory.update_knowledge("entropy", "Understands as disorder measure", "comfortable")
        memory.update_knowledge("p-value", "Knows basic definition", "learning")

        knowledge = memory.get_knowledge_summary()
        assert "entropy" in knowledge
        assert "p-value" in knowledge

        brain.ask("How does cross-entropy relate to entropy?", memory_context=knowledge)

        call_args = mock_claude.messages.create.call_args
        system = call_args.kwargs["system"]
        assert "entropy" in system
        assert "comfortable" in system

        memory.close()
