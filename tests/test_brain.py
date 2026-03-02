"""Tests for klaus.brain routing and streaming behavior."""

from unittest.mock import MagicMock, patch

from klaus.brain import Brain
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


class TestSentenceLimit:
    def test_limit_sentences_caps_text(self):
        assert Brain.limit_sentences("A one. B two. C three.", 2) == "A one. B two."

    def test_limit_sentences_none_keeps_text(self):
        assert Brain.limit_sentences("A one. B two.", None) == "A one. B two."


class TestRoutingBehavior:
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
