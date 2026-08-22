"""Tests for klaus.brain routing and streaming behavior."""

import threading
from unittest.mock import MagicMock, patch

import pytest

import klaus.config as config
from klaus.brain import AskCancelled, Brain, _split_first_clause
from klaus.query_router import RouteDecision, RouteMode


def _route(mode: RouteMode, **kwargs) -> RouteDecision:
    defaults = dict(
        confidence=0.9,
        reason="test",
        use_image=True,
        use_history=True,
        use_memory_context=True,
        use_notes_context=True,
        max_sentences=None,
        history_turn_window=0,
        turn_instruction=None,
        source="test",
    )
    defaults.update(kwargs)
    return RouteDecision(mode=mode, **defaults)


def _standalone_route() -> RouteDecision:
    return _route(
        RouteMode.STANDALONE_DEFINITION,
        use_image=False,
        use_history=False,
        use_memory_context=False,
        use_notes_context=False,
        max_sentences=2,
        turn_instruction="At most two sentences.",
    )


def _page_definition_route() -> RouteDecision:
    return _route(
        RouteMode.PAGE_GROUNDED_DEFINITION,
        use_memory_context=False,
        use_notes_context=False,
        max_sentences=2,
        history_turn_window=2,
        turn_instruction="Use page grounding and stay concise.",
    )


def _general_route() -> RouteDecision:
    return _route(RouteMode.GENERAL_CONTEXTUAL)


class TestFirstClauseSplit:
    def test_no_split_before_minimum_length(self):
        assert _split_first_clause("Short clause, more") is None

    def test_splits_at_first_boundary_past_minimum(self):
        buf = (
            "This is a fairly long opening clause that keeps going and going, "
            "then continues"
        )
        clause, remainder = _split_first_clause(buf)
        assert clause.endswith(",")
        assert remainder == "then continues"

    def test_no_boundary_returns_none(self):
        assert _split_first_clause("A" * 200) is None


class TestCancellation:
    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_preset_cancel_aborts_before_request(
        self, mock_anthropic_cls, mock_search_cls
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        brain = Brain()
        cancel = threading.Event()
        cancel.set()

        with pytest.raises(AskCancelled):
            brain.ask("Question", route_decision=_general_route(), cancel_event=cancel)

        mock_client.messages.stream.assert_not_called()
        assert brain._history == []

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_mid_stream_cancel_leaves_history_untouched(
        self, mock_anthropic_cls, mock_search_cls, anthropic_stream_tools
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.stream.return_value = anthropic_stream_tools.stream(
            anthropic_stream_tools.response("One. Two."),
            [
                anthropic_stream_tools.delta("One. "),
                anthropic_stream_tools.delta("Two. "),
            ],
        )

        brain = Brain()
        cancel = threading.Event()

        def on_sentence(_text: str) -> None:
            cancel.set()

        with pytest.raises(AskCancelled):
            brain.ask(
                "Question",
                on_sentence=on_sentence,
                route_decision=_general_route(),
                cancel_event=cancel,
            )

        assert brain._history == []


class TestModelSelection:
    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_standalone_definition_uses_definition_model(
        self, mock_anthropic_cls, mock_search_cls, anthropic_stream_tools
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.stream.return_value = anthropic_stream_tools.stream(
            anthropic_stream_tools.response("A definition."),
            [anthropic_stream_tools.delta("A definition.")],
        )

        brain = Brain()
        brain.ask("Define entropy", route_decision=_standalone_route())

        call = mock_client.messages.stream.call_args
        assert call.kwargs["model"] == config.DEFINITION_MODEL

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_general_route_uses_main_model(
        self, mock_anthropic_cls, mock_search_cls, anthropic_stream_tools
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.stream.return_value = anthropic_stream_tools.stream(
            anthropic_stream_tools.response("Answer."),
            [anthropic_stream_tools.delta("Answer.")],
        )

        brain = Brain()
        brain.ask("What does this mean?", route_decision=_general_route())

        call = mock_client.messages.stream.call_args
        assert call.kwargs["model"] == config.CLAUDE_MODEL


class TestFirstClauseStreaming:
    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_first_clause_emitted_before_sentence_end(
        self, mock_anthropic_cls, mock_search_cls, anthropic_stream_tools
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        text = (
            "This is a fairly long opening clause that keeps going and going, "
            "then it finishes the sentence."
        )
        mock_client.messages.stream.return_value = anthropic_stream_tools.stream(
            anthropic_stream_tools.response(text),
            [anthropic_stream_tools.delta(text)],
        )

        spoken: list[str] = []
        brain = Brain()
        brain.ask(
            "Question",
            on_sentence=spoken.append,
            route_decision=_general_route(),
        )

        assert spoken[0] == (
            "This is a fairly long opening clause that keeps going and going,"
        )
        assert spoken[-1] == "then it finishes the sentence."


class TestSentenceLimit:
    def test_limit_sentences_caps_text(self):
        assert Brain.limit_sentences("A one. B two. C three.", 2) == "A one. B two."

    def test_limit_sentences_none_keeps_text(self):
        assert Brain.limit_sentences("A one. B two.", None) == "A one. B two."


class TestRoutingBehavior:
    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_selected_reading_text_replaces_image_context(
        self, mock_anthropic_cls, mock_search_cls, anthropic_stream_tools
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.stream.return_value = anthropic_stream_tools.stream(
            anthropic_stream_tools.response("Answer."),
            [anthropic_stream_tools.delta("Answer.")],
        )
        brain = Brain()

        exchange = brain.ask(
            "Explain this",
            image_base64="fallback-image",
            reading_text="Exact selected PDF text",
            route_decision=_general_route(),
        )

        content = mock_client.messages.stream.call_args.kwargs["messages"][-1]["content"]
        assert exchange.image_base64 is None
        assert not any(block["type"] == "image" for block in content)
        assert "Exact selected PDF text" in content[0]["text"]
        assert content[-1]["text"] == "Explain this"

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_standalone_route_suppresses_context_and_caps_output(
        self,
        mock_anthropic_cls,
        mock_search_cls,
        anthropic_stream_tools,
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.stream.return_value = anthropic_stream_tools.stream(
            response=anthropic_stream_tools.response(
                "Sentence one. Sentence two. Sentence three."
            ),
            events=[
                anthropic_stream_tools.delta(
                    "Sentence one. Sentence two. Sentence three."
                )
            ],
        )

        spoken: list[str] = []
        brain = Brain()
        exchange = brain.ask(
            question="Define entropy",
            image_base64="img-data",
            memory_context="Known topics",
            notes_context="Current notes file: x.md",
            on_sentence=spoken.append,
            route_decision=_standalone_route(),
        )

        assert exchange.image_base64 is None
        assert exchange.assistant_text == "Sentence one. Sentence two."
        assert spoken == ["Sentence one.", "Sentence two."]

        call = mock_client.messages.stream.call_args
        system = call.kwargs["system"]
        messages = call.kwargs["messages"]

        assert "Known topics" not in system
        assert "Current notes file" not in system
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert len([b for b in messages[0]["content"] if b["type"] == "image"]) == 0

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_page_grounded_route_keeps_image_and_windowed_history(
        self,
        mock_anthropic_cls,
        mock_search_cls,
        anthropic_stream_tools,
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.stream.side_effect = [
            anthropic_stream_tools.stream(
                anthropic_stream_tools.response("A1."),
                [anthropic_stream_tools.delta("A1.")],
            ),
            anthropic_stream_tools.stream(
                anthropic_stream_tools.response("A2."),
                [anthropic_stream_tools.delta("A2.")],
            ),
            anthropic_stream_tools.stream(
                anthropic_stream_tools.response("A3."),
                [anthropic_stream_tools.delta("A3.")],
            ),
            anthropic_stream_tools.stream(
                anthropic_stream_tools.response("Grounded one. Grounded two."),
                [anthropic_stream_tools.delta("Grounded one. Grounded two.")],
            ),
        ]

        brain = Brain()
        general = _general_route()
        brain.ask("Q1", image_base64="img1", route_decision=general)
        brain.ask("Q2", image_base64="img2", route_decision=general)
        brain.ask("Q3", image_base64="img3", route_decision=general)

        exchange = brain.ask(
            question="Explain complexity in the definition on the far right",
            image_base64="img4",
            memory_context="Memory should be omitted",
            notes_context="Notes should be omitted",
            route_decision=_page_definition_route(),
        )

        assert exchange.image_base64 == "img4"

        call = mock_client.messages.stream.call_args_list[-1]
        messages = call.kwargs["messages"]
        system = call.kwargs["system"]

        assert len(messages) == 5
        assert len([b for b in messages[-1]["content"] if b["type"] == "image"]) == 1
        assert "Memory should be omitted" not in system
        assert "Notes should be omitted" not in system

    @patch("klaus.brain.WebSearch")
    @patch("klaus.brain.anthropic.Anthropic")
    def test_general_route_keeps_contextual_behavior(
        self,
        mock_anthropic_cls,
        mock_search_cls,
        anthropic_stream_tools,
    ):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.stream.side_effect = [
            anthropic_stream_tools.stream(
                anthropic_stream_tools.response("First."),
                [anthropic_stream_tools.delta("First.")],
            ),
            anthropic_stream_tools.stream(
                anthropic_stream_tools.response("Second."),
                [anthropic_stream_tools.delta("Second.")],
            ),
        ]

        brain = Brain()
        general = _general_route()
        brain.ask("First question", image_base64="img1", route_decision=general)
        exchange = brain.ask(
            question="Second question",
            image_base64="img2",
            memory_context="User knows entropy",
            notes_context="Current notes file: notes.md",
            route_decision=general,
        )

        assert exchange.image_base64 == "img2"

        call = mock_client.messages.stream.call_args_list[-1]
        messages = call.kwargs["messages"]
        system = call.kwargs["system"]

        assert len(messages) == 3
        assert "User knows entropy" in system
        assert "Current notes file: notes.md" in system
        assert len([b for b in messages[-1]["content"] if b["type"] == "image"]) == 1
