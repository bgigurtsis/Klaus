from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

_PATTERN = {
    "definition": re.compile(
        r"\b(define|definition|what is|what's|who is|meaning|what does .* mean|explain what .* means)\b"
    ),
    "explain": re.compile(r"\bexplain\b"),
    "concision": re.compile(r"\b(very concisely|concisely|briefly|in short|quickly|quick summary)\b"),
    "doc_ref": re.compile(
        r"\b(page|paper|book|text|paragraph|section|definition|figure|table|equation|line|column|caption|graph|chart)\b"
    ),
    "deictic": re.compile(r"\b(this|that|here|there|above|below)\b"),
    "spatial": re.compile(r"\b(left|right|far right|far left|top|bottom|upper|lower|middle|center)\b"),
    "on_page": re.compile(
        r"\b(on|in|from)\s+the\s+([a-z]+\s+){0,3}(page|paragraph|section|figure|table|equation|left|right|top|bottom)\b"
    ),
    "general": re.compile(
        r"\b(summarize|walk me through|what is happening|what does this section mean|what does that section mean)\b"
    ),
}

_POLICY = {
    "standalone": {
        "use_image": False,
        "use_history": False,
        "use_memory_context": False,
        "use_notes_context": False,
        "max_sentences": 2,
        "history_turn_window": 0,
        "turn_instruction": (
            "Return a direct standalone definition in at most two sentences. "
            "Do not reference the page unless explicitly asked."
        ),
    },
    "page_definition": {
        "use_image": True,
        "use_history": True,
        "use_memory_context": False,
        "use_notes_context": False,
        "max_sentences": 2,
        "history_turn_window": 2,
        "turn_instruction": (
            "Answer the definition request using the relevant page location. "
            "Keep the answer to at most two sentences."
        ),
    },
    "contextual": {
        "use_image": True,
        "use_history": True,
        "use_memory_context": True,
        "use_notes_context": True,
        "max_sentences": None,
        "history_turn_window": 0,
        "turn_instruction": None,
    },
}


class RouteMode(str, Enum):
    STANDALONE_DEFINITION = "standalone_definition"
    PAGE_GROUNDED_DEFINITION = "page_grounded_definition"
    GENERAL_CONTEXTUAL = "general_contextual"


@dataclass(frozen=True)
class RouteDecision:
    mode: RouteMode
    confidence: float
    reason: str
    use_image: bool
    use_history: bool
    use_memory_context: bool
    use_notes_context: bool
    max_sentences: int | None
    history_turn_window: int
    turn_instruction: str | None
    source: str = "local"


@dataclass(frozen=True)
class _LocalDecision:
    mode: RouteMode
    confidence: float
    margin: float
    reason: str
    scores: dict[RouteMode, float]


def default_route_decision() -> RouteDecision:
    return _decision_from_mode(
        mode=RouteMode.GENERAL_CONTEXTUAL,
        confidence=1.0,
        reason="router disabled; using default contextual behavior",
        source="default",
    )


def local_route_decision(question: str) -> RouteDecision:
    """Route without an extra model call for the Realtime voice path."""
    q = question.strip()
    if not q:
        return default_route_decision()
    local = QueryRouter._route_local(q)
    if local.confidence < 0.55:
        return default_route_decision()
    return _decision_from_mode(
        local.mode,
        local.confidence,
        local.reason,
        "local",
    )


class QueryRouter:
    """Local question-context policy decisions."""

    @staticmethod
    def _route_local(question: str) -> _LocalDecision:
        q = question.lower().strip()
        signals = _signal_map(q)

        definition = _score(signals, {
            "definition": 0.55,
            "explain": 0.18,
            "concision": 0.16,
        })
        page = _score(signals, {
            "doc_ref": 0.30,
            "deictic": 0.22,
            "spatial": 0.25,
            "on_page": 0.24,
        })
        contextual = 0.24 + _score(signals, {
            "general": 0.44,
            "deictic": 0.16,
            "doc_ref": 0.10,
        })

        standalone_score = (definition * 1.12) - (page * 0.68)
        if signals["concision"]:
            standalone_score += 0.08

        page_definition_score = page
        if definition > 0.60:
            page_definition_score += (definition - 0.60) * 1.25
        if signals["spatial"] and signals["doc_ref"]:
            page_definition_score += 0.22

        contextual_score = contextual + (page * 0.70)
        if definition > 0.75 and page > 0.35:
            contextual_score -= 0.16

        scores: dict[RouteMode, float] = {
            RouteMode.STANDALONE_DEFINITION: max(0.0, standalone_score),
            RouteMode.PAGE_GROUNDED_DEFINITION: max(0.0, page_definition_score),
            RouteMode.GENERAL_CONTEXTUAL: max(0.0, contextual_score),
        }

        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_mode, top_score = ordered[0]
        second_score = ordered[1][1]
        margin = top_score - second_score
        confidence = _confidence(top_score, second_score)
        if top_mode == RouteMode.PAGE_GROUNDED_DEFINITION and signals["spatial"] and signals["doc_ref"]:
            confidence = max(confidence, 0.86)

        reasons = [
            name
            for name in ("definition", "doc_ref", "spatial", "concision")
            if signals[name]
        ]
        reason = f"local:{top_mode.value}:{'+'.join(reasons) or 'default'}"
        return _LocalDecision(top_mode, confidence, margin, reason, scores)

def _signal_map(question: str) -> dict[str, bool]:
    return {name: bool(pattern.search(question)) for name, pattern in _PATTERN.items()}


def _score(signals: dict[str, bool], weights: dict[str, float]) -> float:
    return sum(weight for key, weight in weights.items() if signals.get(key))


def _confidence(top_score: float, second_score: float) -> float:
    if second_score <= 0:
        return 0.99 if top_score > 0 else 0.34
    margin = (top_score - second_score) / (top_score + second_score + 1e-6)
    return min(0.99, max(0.0, 0.5 + margin))


def _decision_from_mode(
    mode: RouteMode,
    confidence: float,
    reason: str,
    source: str,
) -> RouteDecision:
    policy_key = {
        RouteMode.STANDALONE_DEFINITION: "standalone",
        RouteMode.PAGE_GROUNDED_DEFINITION: "page_definition",
        RouteMode.GENERAL_CONTEXTUAL: "contextual",
    }[mode]
    policy = _POLICY[policy_key]
    return RouteDecision(
        mode=mode,
        confidence=max(0.0, min(1.0, confidence)),
        reason=reason,
        use_image=policy["use_image"],
        use_history=policy["use_history"],
        use_memory_context=policy["use_memory_context"],
        use_notes_context=policy["use_notes_context"],
        max_sentences=policy["max_sentences"],
        history_turn_window=policy["history_turn_window"],
        turn_instruction=policy["turn_instruction"],
        source=source,
    )
