"""Tests for query routing policy decisions."""

from unittest.mock import MagicMock, patch

from klaus.query_router import (
    QueryRouter,
    RouteMode,
    _LlmDecision,
    _LocalDecision,
    local_route_decision,
)


def _low_conf_local(mode: RouteMode = RouteMode.GENERAL_CONTEXTUAL) -> _LocalDecision:
    return _LocalDecision(
        mode=mode,
        confidence=0.55,
        margin=0.05,
        reason="low confidence local",
        scores={
            RouteMode.STANDALONE_DEFINITION: 0.9,
            RouteMode.PAGE_GROUNDED_DEFINITION: 0.86,
            RouteMode.GENERAL_CONTEXTUAL: 0.91,
        },
    )


class TestQueryRouter:
    def test_realtime_local_route_does_not_need_an_llm_client(self):
        decision = local_route_decision("Define entropy very concisely.")

        assert decision.mode == RouteMode.STANDALONE_DEFINITION
        assert decision.source == "local"
        assert decision.max_sentences == 2

    def test_realtime_low_confidence_route_uses_safe_contextual_default(self):
        low_confidence = _LocalDecision(
            mode=RouteMode.STANDALONE_DEFINITION,
            confidence=0.54,
            margin=0.01,
            reason="ambiguous",
            scores={},
        )

        with patch.object(QueryRouter, "_route_local", return_value=low_confidence):
            decision = local_route_decision("Could you clarify?")

        assert decision.mode == RouteMode.GENERAL_CONTEXTUAL
        assert decision.source == "default"
        assert decision.use_image is True

    def test_local_high_confidence_standalone(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = AssertionError(
            "LLM router should not be called"
        )
        router = QueryRouter(mock_client)

        decision = router.route("Explain macroeconomics very concisely.")

        assert decision.mode == RouteMode.STANDALONE_DEFINITION
        assert decision.source == "local"
        assert decision.max_sentences == 2

    def test_local_infers_page_grounded_definition_from_spatial_reference(self):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = AssertionError(
            "LLM router should not be called"
        )
        router = QueryRouter(mock_client)

        decision = router.route(
            "Explain what complexity means in the definition on the far right."
        )

        assert decision.mode == RouteMode.PAGE_GROUNDED_DEFINITION
        assert decision.source == "local"
        assert decision.use_image is True

    def test_low_confidence_path_uses_llm_router(self):
        router = QueryRouter(MagicMock())

        with patch.object(router, "_route_local", return_value=_low_conf_local()):
            with patch.object(
                router,
                "_route_with_llm",
                return_value=_LlmDecision(
                    mode=RouteMode.GENERAL_CONTEXTUAL,
                    confidence=0.84,
                    reason="llm confident",
                ),
            ) as mock_llm:
                decision = router.route("Explain it.")

        mock_llm.assert_called_once()
        assert decision.mode == RouteMode.GENERAL_CONTEXTUAL
        assert decision.source == "llm"

    def test_llm_failure_falls_back_to_standalone_definition(self):
        router = QueryRouter(MagicMock())

        with patch.object(router, "_route_local", return_value=_low_conf_local()):
            with patch.object(router, "_route_with_llm", return_value=None):
                decision = router.route("Can you clarify?")

        assert decision.mode == RouteMode.STANDALONE_DEFINITION
        assert decision.source == "fallback"
        assert decision.max_sentences == 2
