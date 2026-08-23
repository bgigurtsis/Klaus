"""Tests for the local Realtime context router."""

from unittest.mock import patch

from klaus.query_router import QueryRouter, RouteMode, _LocalDecision, local_route_decision


def test_standalone_definition_uses_local_route():
    decision = local_route_decision("Define entropy very concisely.")

    assert decision.mode == RouteMode.STANDALONE_DEFINITION
    assert decision.source == "local"
    assert decision.max_sentences == 2


def test_page_definition_uses_reading_context():
    decision = local_route_decision(
        "Explain what complexity means in the definition on the far right."
    )

    assert decision.mode == RouteMode.PAGE_GROUNDED_DEFINITION
    assert decision.use_image is True


def test_ambiguous_question_uses_contextual_default():
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
