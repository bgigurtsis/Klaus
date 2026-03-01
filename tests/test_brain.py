"""Tests for klaus.brain -- Claude vision + tool use integration."""

from unittest.mock import MagicMock, patch, PropertyMock
from types import SimpleNamespace

import pytest

from klaus.brain import Brain, Exchange


def _make_text_block(text):
    return SimpleNamespace(type="text", text=text)


def _make_tool_use_block(tool_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=tool_input)


def _make_response(content_blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=content_blocks, stop_reason=stop_reason)


class TestBuildUserContent:
    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_text_only(self, mock_anthropic_cls, mock_search_cls):
        brain = Brain()
        content = brain._build_user_content("What is this?", image_base64=None)
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "What is this?"

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_with_image(self, mock_anthropic_cls, mock_search_cls):
        brain = Brain()
        content = brain._build_user_content("Explain this.", image_base64="abc123")
        assert len(content) == 2
        assert content[0]["type"] == "image"
        assert content[0]["source"]["data"] == "abc123"
        assert content[0]["source"]["media_type"] == "image/jpeg"
        assert content[1]["type"] == "text"


class TestExtractText:
    def test_single_text_block(self):
        blocks = [_make_text_block("Hello world.")]
        assert Brain._extract_text(blocks) == "Hello world."

    def test_multiple_text_blocks(self):
        blocks = [_make_text_block("Part one."), _make_text_block("Part two.")]
        assert Brain._extract_text(blocks) == "Part one. Part two."

    def test_mixed_blocks(self):
        blocks = [
            _make_text_block("Before tool."),
            _make_tool_use_block("t1", "web_search", {"query": "test"}),
            _make_text_block("After tool."),
        ]
        assert Brain._extract_text(blocks) == "Before tool. After tool."

    def test_no_text_blocks(self):
        blocks = [_make_tool_use_block("t1", "web_search", {"query": "test"})]
        assert Brain._extract_text(blocks) == ""


class TestAskNoToolUse:
    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_simple_question(self, mock_anthropic_cls, mock_search_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_response(
            [_make_text_block("The answer is 42.")]
        )

        brain = Brain()
        exchange = brain.ask("What is the meaning of life?")

        assert isinstance(exchange, Exchange)
        assert exchange.user_text == "What is the meaning of life?"
        assert exchange.assistant_text == "The answer is 42."
        assert exchange.searches == []
        mock_client.messages.create.assert_called_once()

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_question_with_image(self, mock_anthropic_cls, mock_search_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_response(
            [_make_text_block("I see a diagram of...")]
        )

        brain = Brain()
        exchange = brain.ask("What is this figure?", image_base64="imgdata")

        assert exchange.image_base64 == "imgdata"
        call_args = mock_client.messages.create.call_args
        messages = call_args.kwargs["messages"]
        user_msg = messages[0]
        assert user_msg["role"] == "user"
        image_block = [b for b in user_msg["content"] if b["type"] == "image"]
        assert len(image_block) == 1
        assert image_block[0]["source"]["data"] == "imgdata"


class TestAskWithToolUse:
    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_single_tool_call(self, mock_anthropic_cls, mock_search_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_search = MagicMock()
        mock_search_cls.return_value = mock_search
        mock_search.search.return_value = "Bayes theorem states..."

        tool_response = _make_response(
            [_make_tool_use_block("call_1", "web_search", {"query": "Bayes theorem"})],
            stop_reason="tool_use",
        )
        final_response = _make_response(
            [_make_text_block("Bayes theorem is a way to update probabilities.")]
        )
        mock_client.messages.create.side_effect = [tool_response, final_response]

        brain = Brain()
        exchange = brain.ask("What is Bayes theorem?")

        assert "Bayes theorem is a way to update probabilities" in exchange.assistant_text
        assert len(exchange.searches) == 1
        assert exchange.searches[0]["query"] == "Bayes theorem"
        mock_search.search.assert_called_once_with("Bayes theorem")
        assert mock_client.messages.create.call_count == 2

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_multiple_tool_calls(self, mock_anthropic_cls, mock_search_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        mock_search = MagicMock()
        mock_search_cls.return_value = mock_search
        mock_search.search.side_effect = ["Result 1", "Result 2"]

        tool_response_1 = _make_response(
            [_make_tool_use_block("c1", "web_search", {"query": "query 1"})],
            stop_reason="tool_use",
        )
        tool_response_2 = _make_response(
            [_make_tool_use_block("c2", "web_search", {"query": "query 2"})],
            stop_reason="tool_use",
        )
        final_response = _make_response([_make_text_block("Combined answer.")])

        mock_client.messages.create.side_effect = [
            tool_response_1, tool_response_2, final_response
        ]

        brain = Brain()
        exchange = brain.ask("Complex question")

        assert exchange.assistant_text == "Combined answer."
        assert len(exchange.searches) == 2
        assert mock_client.messages.create.call_count == 3


class TestHistoryManagement:
    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_history_accumulates(self, mock_anthropic_cls, mock_search_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_response(
            [_make_text_block("Answer.")]
        )

        brain = Brain()
        brain.ask("Question 1")
        brain.ask("Question 2")

        assert len(brain._history) == 4  # 2 user + 2 assistant

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_clear_history(self, mock_anthropic_cls, mock_search_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_response(
            [_make_text_block("Answer.")]
        )

        brain = Brain()
        brain.ask("Question")
        assert len(brain._history) > 0

        brain.clear_history()
        assert brain._history == []

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_trim_history(self, mock_anthropic_cls, mock_search_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_response(
            [_make_text_block("Answer.")]
        )

        brain = Brain()
        for i in range(15):
            brain.ask(f"Question {i}")

        assert len(brain._history) == 30  # 15 pairs
        brain.trim_history(max_turns=5)
        assert len(brain._history) == 10  # 5 pairs

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_trim_no_op_when_under_limit(self, mock_anthropic_cls, mock_search_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_response(
            [_make_text_block("Answer.")]
        )

        brain = Brain()
        brain.ask("Q")
        brain.trim_history(max_turns=20)
        assert len(brain._history) == 2


class TestMemoryContext:
    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_memory_context_appended_to_system(self, mock_anthropic_cls, mock_search_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_response(
            [_make_text_block("Answer.")]
        )

        brain = Brain()
        brain.ask("Q", memory_context="User knows about entropy.")

        call_args = mock_client.messages.create.call_args
        system = call_args.kwargs["system"]
        assert "User knows about entropy." in system

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_no_memory_context(self, mock_anthropic_cls, mock_search_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_response(
            [_make_text_block("Answer.")]
        )

        brain = Brain()
        brain.ask("Q", memory_context=None)

        call_args = mock_client.messages.create.call_args
        system = call_args.kwargs["system"]
        assert "Context from previous sessions" not in system
