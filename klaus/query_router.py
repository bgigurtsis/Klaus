from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum

import anthropic

import klaus.config as config

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


@dataclass(frozen=True)
class _LlmDecision:
    mode: RouteMode
    confidence: float
    reason: str


def default_route_decision() -> RouteDecision:
    return _decision_from_mode(
        mode=RouteMode.GENERAL_CONTEXTUAL,
        confidence=1.0,
        reason="router disabled; using default contextual behavior",
        source="default",
    )


class QueryRouter:
    """Hybrid local+LLM router for question-context policy decisions."""

    def __init__(self, client: anthropic.Anthropic):
        self._client = client

    def route(self, question: str) -> RouteDecision:
        q = question.strip()
        if not q:
            return default_route_decision()

        t0 = time.perf_counter()
        local = self._route_local(q)
        local_ms = (time.perf_counter() - t0) * 1000

        if self._is_local_confident(local):
            decision = _decision_from_mode(local.mode, local.confidence, local.reason, "local")
            logger.info(
                "Query route=%s source=local conf=%.2f margin=%.2f timing_ms(local=%.1f,total=%.1f) reason=%s",
                decision.mode.value,
                decision.confidence,
                local.margin,
                local_ms,
                local_ms,
                decision.reason,
            )
            return decision

        llm_start = time.perf_counter()
        llm = self._route_with_llm(q)
        llm_ms = (time.perf_counter() - llm_start) * 1000

        if llm and llm.confidence >= config.ROUTER_LLM_CONFIDENCE_THRESHOLD:
            decision = _decision_from_mode(llm.mode, llm.confidence, llm.reason, "llm")
            total_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "Query route=%s source=llm conf=%.2f local_conf=%.2f timing_ms(local=%.1f,llm=%.1f,total=%.1f)",
                decision.mode.value,
                decision.confidence,
                local.confidence,
                local_ms,
                llm_ms,
                total_ms,
            )
            return decision

        llm_conf = "na" if llm is None else f"{llm.confidence:.2f}"
        reason = f"fallback:low_conf(local={local.confidence:.2f},llm={llm_conf})"
        decision = _decision_from_mode(
            mode=RouteMode.STANDALONE_DEFINITION,
            confidence=0.5,
            reason=reason,
            source="fallback",
        )
        total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Query route=%s source=fallback conf=%.2f timing_ms(local=%.1f,llm=%.1f,total=%.1f) reason=%s",
            decision.mode.value,
            decision.confidence,
            local_ms,
            llm_ms,
            total_ms,
            reason,
        )
        return decision

    @staticmethod
    def _is_local_confident(local: _LocalDecision) -> bool:
        return (
            local.confidence >= config.ROUTER_LOCAL_CONFIDENCE_THRESHOLD
            and local.margin >= config.ROUTER_LOCAL_MARGIN_THRESHOLD
        )

    def _route_local(self, question: str) -> _LocalDecision:
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

    def _route_with_llm(self, question: str) -> _LlmDecision | None:
        router_system = (
            "You classify user questions for a document-camera assistant. "
            "Return JSON only with keys mode, confidence, reason. "
            "mode must be one of: standalone_definition, page_grounded_definition, general_contextual. "
            "Use standalone_definition for direct concept definitions without requested page grounding. "
            "Use page_grounded_definition for definition requests tied to page location or document references "
            "(e.g., 'definition on the far right'). "
            "Use general_contextual for general page interpretation. "
            "confidence must be between 0 and 1."
        )
        router_user = (
            "Classify this question.\n\n"
            "Examples:\n"
            "- Explain macroeconomics very concisely. => standalone_definition\n"
            "- Explain what complexity means in the definition on the far right. => page_grounded_definition\n"
            "- What does this section mean? => general_contextual\n\n"
            f"Question: {question}"
        )
        try:
            resp = self._client.messages.create(
                model=config.ROUTER_MODEL,
                max_tokens=config.ROUTER_MAX_TOKENS,
                temperature=0,
                system=router_system,
                messages=[{"role": "user", "content": router_user}],
                timeout=max(0.05, config.ROUTER_TIMEOUT_MS / 1000),
            )
        except Exception as exc:
            logger.warning("LLM query router failed: %s", exc)
            return None

        payload = _extract_json(_extract_text(resp.content).strip())
        if not payload:
            logger.warning("LLM query router returned non-JSON payload")
            return None

        mode = _parse_mode(payload.get("mode"))
        if mode is None:
            logger.warning("LLM query router returned invalid mode: %r", payload.get("mode"))
            return None

        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        reason = str(payload.get("reason", "llm-route")).strip() or "llm-route"
        return _LlmDecision(mode=mode, confidence=confidence, reason=reason)


def _signal_map(question: str) -> dict[str, bool]:
    return {name: bool(pattern.search(question)) for name, pattern in _PATTERN.items()}


def _score(signals: dict[str, bool], weights: dict[str, float]) -> float:
    return sum(weight for key, weight in weights.items() if signals.get(key))


def _confidence(top_score: float, second_score: float) -> float:
    if second_score <= 0:
        return 0.99 if top_score > 0 else 0.34
    margin = (top_score - second_score) / (top_score + second_score + 1e-6)
    return min(0.99, max(0.0, 0.5 + margin))


def _extract_text(content_blocks: list) -> str:
    return " ".join(str(getattr(block, "text", "")) for block in content_blocks if getattr(block, "text", None))


def _extract_json(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _parse_mode(raw_mode: object) -> RouteMode | None:
    if not isinstance(raw_mode, str):
        return None
    mode = raw_mode.strip().lower()
    aliases = {
        "standalone_definition": RouteMode.STANDALONE_DEFINITION,
        "standalone": RouteMode.STANDALONE_DEFINITION,
        "definition": RouteMode.STANDALONE_DEFINITION,
        "page_grounded_definition": RouteMode.PAGE_GROUNDED_DEFINITION,
        "page_grounded": RouteMode.PAGE_GROUNDED_DEFINITION,
        "page_definition": RouteMode.PAGE_GROUNDED_DEFINITION,
        "general_contextual": RouteMode.GENERAL_CONTEXTUAL,
        "contextual": RouteMode.GENERAL_CONTEXTUAL,
        "general": RouteMode.GENERAL_CONTEXTUAL,
    }
    return aliases.get(mode)


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
