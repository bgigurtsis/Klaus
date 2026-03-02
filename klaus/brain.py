from __future__ import annotations

import copy
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import anthropic

import klaus.config as config
from klaus.config import CLAUDE_MODEL
from klaus.notes import NotesManager, SAVE_NOTE_TOOL, SET_NOTES_FILE_TOOL
from klaus.query_router import QueryRouter, RouteDecision, default_route_decision
from klaus.search import TOOL_DEFINITION, WebSearch

logger = logging.getLogger(__name__)

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_SENTENCE_CHUNK = re.compile(r"[^.!?]+(?:[.!?]+|$)")


def _extract_sentences(buf: str) -> tuple[list[str], str]:
    """Split buffer into complete sentences and a remaining fragment.

    Returns (complete_sentences, leftover_buffer).
    """
    parts = _SENTENCE_END.split(buf)
    if len(parts) <= 1:
        return [], buf
    complete = [p.strip() for p in parts[:-1] if p.strip()]
    remainder = parts[-1]
    return complete, remainder


@dataclass
class Exchange:
    """A single Q&A turn in a conversation."""

    user_text: str
    assistant_text: str
    image_base64: str | None = None
    searches: list[dict] = field(default_factory=list)
    notes_file_changed: bool = False


class Brain:
    """Manages conversation with Claude, including vision and tool use."""

    def __init__(self, notes: NotesManager | None = None):
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._search = WebSearch()
        self._notes = notes
        self._history: list[dict] = []
        self._tools: list[dict] = []
        self._rebuild_tools()
        self._router = QueryRouter(self._client)

    def reload_clients(self) -> None:
        """Recreate API clients to pick up key changes from config.reload()."""
        self._client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._search = WebSearch()
        self._router = QueryRouter(self._client)

    def set_notes_manager(self, notes: NotesManager | None) -> None:
        self._notes = notes
        self._rebuild_tools()

    def _rebuild_tools(self) -> None:
        self._tools = [TOOL_DEFINITION]
        if self._notes is not None:
            self._tools.extend([SET_NOTES_FILE_TOOL, SAVE_NOTE_TOOL])

    def decide_route(self, question: str) -> RouteDecision:
        """Classify the question into a context routing policy."""
        if not config.ENABLE_QUERY_ROUTER:
            return default_route_decision()
        return self._router.route(question)

    def ask(
        self,
        question: str,
        image_base64: str | None = None,
        memory_context: str | None = None,
        notes_context: str | None = None,
        on_sentence: Callable[[str], None] | None = None,
        route_decision: RouteDecision | None = None,
    ) -> Exchange:
        """Send a question to Claude and return the exchange.

        Route decisions control whether image/history/memory/notes are sent,
        and optionally enforce a sentence cap for concise definitions.
        """
        route = route_decision or default_route_decision()
        effective_image = image_base64 if route.use_image else None
        effective_memory = memory_context if route.use_memory_context else None
        effective_notes = notes_context if route.use_notes_context else None

        logger.info(
            (
                "Asking Claude (model=%s, route=%s/%s, conf=%.2f, "
                "image=%s, memory=%s, notes=%s, history=%s, streaming=%s)"
            ),
            CLAUDE_MODEL,
            route.mode.value,
            route.source,
            route.confidence,
            "yes" if effective_image else "no",
            "yes" if effective_memory else "no",
            "yes" if effective_notes else "no",
            "yes" if route.use_history else "no",
            "yes" if on_sentence else "no",
        )

        user_content = self._build_user_content(question, effective_image)
        request_messages = self._build_request_messages(user_content, route)

        system = config.SYSTEM_PROMPT
        if effective_memory:
            system += "\n\nContext from previous sessions:\n" + effective_memory
        if effective_notes:
            system += "\n\n" + effective_notes
        system += "\n\nRemember: three sentences is a ceiling, not a floor. Answer directly, then stop."
        if route.turn_instruction:
            system += "\n\nTurn-specific instruction: " + route.turn_instruction
        if route.max_sentences:
            system += (
                f"\n\nHard limit for this turn: respond in no more than "
                f"{route.max_sentences} sentences."
            )

        context_parts = ["system_prompt", f"route={route.mode.value}"]
        if effective_memory:
            context_parts.append("memory")
        if effective_notes:
            context_parts.append("notes")
        if effective_image:
            context_parts.append("image")
        logger.info(
            (
                "Context sent to Claude: [%s], request history=%d msg(s), "
                "full history=%d msg(s), system prompt %d chars"
            ),
            ", ".join(context_parts),
            len(request_messages),
            len(self._history),
            len(system),
        )

        if self._notes:
            self._notes.reset_changed()

        searches_performed: list[dict] = []
        max_tool_rounds = 5
        emitted_sentences = 0

        response = None
        text_buf = ""
        for round_num in range(max_tool_rounds):
            response, text_buf, emitted_sentences = self._stream_round(
                system=system,
                messages=request_messages,
                on_sentence=on_sentence,
                max_sentences=route.max_sentences,
                emitted_sentences=emitted_sentences,
            )

            if response.stop_reason == "tool_use":
                logger.info("Tool round %d/%d", round_num + 1, max_tool_rounds)
                tool_results = self._handle_tool_calls(response.content, searches_performed)
                request_messages.append({"role": "assistant", "content": response.content})
                request_messages.append({"role": "user", "content": tool_results})
                continue

            emitted_sentences = self._emit_final_fragment(
                text_buf=text_buf,
                on_sentence=on_sentence,
                max_sentences=route.max_sentences,
                emitted_sentences=emitted_sentences,
            )

            assistant_text = self._extract_text(response.content)
            assistant_text = self.limit_sentences(assistant_text, route.max_sentences)
            logger.info(
                "Claude responded (%d chars, stop=%s)",
                len(assistant_text),
                response.stop_reason,
            )
            self._append_turn_to_history(user_content, assistant_text)
            notes_changed = self._notes.changed if self._notes else False
            return Exchange(
                user_text=question,
                assistant_text=assistant_text,
                image_base64=effective_image,
                searches=searches_performed,
                notes_file_changed=notes_changed,
            )

        if response is None:
            response_content = []
        else:
            response_content = response.content
        emitted_sentences = self._emit_final_fragment(
            text_buf=text_buf,
            on_sentence=on_sentence,
            max_sentences=route.max_sentences,
            emitted_sentences=emitted_sentences,
        )

        assistant_text = self._extract_text(response_content)
        assistant_text = self.limit_sentences(assistant_text, route.max_sentences)
        logger.warning(
            "Claude hit max tool rounds (%d), returning partial response (%d chars)",
            max_tool_rounds,
            len(assistant_text),
        )
        self._append_turn_to_history(user_content, assistant_text)
        notes_changed = self._notes.changed if self._notes else False
        return Exchange(
            user_text=question,
            assistant_text=assistant_text,
            image_base64=effective_image,
            searches=searches_performed,
            notes_file_changed=notes_changed,
        )

    def _stream_round(
        self,
        system: str,
        messages: list[dict],
        on_sentence: Callable[[str], None] | None,
        max_sentences: int | None,
        emitted_sentences: int,
    ) -> tuple[anthropic.types.Message, str, int]:
        """Execute one Claude round with streaming.

        Returns (final_message, remaining_text_buffer, emitted_sentence_count).
        """
        text_buf = ""
        with self._client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=system,
            messages=messages,
            tools=self._tools,
        ) as stream:
            for event in stream:
                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                    text_buf += event.delta.text
                    if on_sentence:
                        sentences, text_buf = _extract_sentences(text_buf)
                        for sentence in sentences:
                            if max_sentences is None or emitted_sentences < max_sentences:
                                on_sentence(sentence)
                                emitted_sentences += 1
            response = stream.get_final_message()
        return response, text_buf, emitted_sentences

    @staticmethod
    def limit_sentences(text: str, max_sentences: int | None) -> str:
        """Hard-limit text to at most max_sentences sentences."""
        clean = text.strip()
        if not clean or max_sentences is None or max_sentences < 1:
            return clean

        parts = [chunk.strip() for chunk in _SENTENCE_CHUNK.findall(clean) if chunk.strip()]
        if len(parts) <= max_sentences:
            return clean
        return " ".join(parts[:max_sentences]).strip()

    def _emit_final_fragment(
        self,
        text_buf: str,
        on_sentence: Callable[[str], None] | None,
        max_sentences: int | None,
        emitted_sentences: int,
    ) -> int:
        if not on_sentence:
            return emitted_sentences
        final_fragment = text_buf.strip()
        if not final_fragment:
            return emitted_sentences
        if max_sentences is not None and emitted_sentences >= max_sentences:
            return emitted_sentences
        on_sentence(final_fragment)
        return emitted_sentences + 1

    def _build_request_messages(
        self,
        user_content: list[dict],
        route: RouteDecision,
    ) -> list[dict]:
        messages: list[dict] = []
        if route.use_history and self._history:
            history_slice = self._history
            if route.history_turn_window > 0:
                history_slice = self._history[-(route.history_turn_window * 2):]
            messages.extend(copy.deepcopy(history_slice))
        messages.append({"role": "user", "content": copy.deepcopy(user_content)})
        return messages

    def _append_turn_to_history(self, user_content: list[dict], assistant_text: str) -> None:
        self._history.append({"role": "user", "content": copy.deepcopy(user_content)})
        self._history.append(
            {
                "role": "assistant",
                "content": [{"type": "text", "text": assistant_text}],
            }
        )
        self._strip_old_images()

    def _build_user_content(self, question: str, image_base64: str | None) -> list[dict]:
        content: list[dict] = []
        if image_base64:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_base64,
                    },
                }
            )
        content.append({"type": "text", "text": question})
        return content

    def _handle_tool_calls(
        self,
        content_blocks: list,
        searches_performed: list[dict],
    ) -> list[dict]:
        """Execute any tool_use blocks and build tool_result messages."""
        results: list[dict] = []
        for block in content_blocks:
            if block.type != "tool_use":
                continue

            if block.name == "web_search":
                query = block.input.get("query", "")
                logger.info("Claude requested web_search: '%s'", query)
                search_result = self._search.search(query)
                searches_performed.append({"query": query, "result": search_result})
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": search_result,
                    }
                )

            elif block.name == "set_notes_file" and self._notes:
                file_path = block.input.get("file_path", "")
                logger.info("Claude requested set_notes_file: '%s'", file_path)
                result_text = self._notes.set_file(file_path)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    }
                )

            elif block.name == "save_note" and self._notes:
                content = block.input.get("content", "")
                logger.info("Claude requested save_note (%d chars)", len(content))
                result_text = self._notes.save_note(content)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    }
                )

        return results

    @staticmethod
    def _extract_text(content_blocks: list) -> str:
        parts: list[str] = []
        for block in content_blocks:
            if hasattr(block, "text"):
                parts.append(block.text)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return " ".join(parts).strip()

    def _strip_old_images(self) -> None:
        """Remove image blocks from all but the most recent user message."""
        found_latest = False
        stripped = 0
        for msg in reversed(self._history):
            if msg["role"] != "user":
                continue
            has_image = any(
                isinstance(b, dict) and b.get("type") == "image" for b in msg["content"]
            )
            if not has_image:
                continue
            if not found_latest:
                found_latest = True
                continue
            msg["content"] = [
                b
                for b in msg["content"]
                if not (isinstance(b, dict) and b.get("type") == "image")
            ]
            stripped += 1
        if stripped:
            logger.info("Stripped images from %d older message(s)", stripped)

    def clear_history(self) -> None:
        self._history.clear()

    def get_history_for_display(self) -> list[Exchange]:
        """Reconstruct exchanges from the raw history for display purposes."""
        exchanges: list[Exchange] = []
        i = 0
        while i < len(self._history):
            msg = self._history[i]
            if msg["role"] == "user":
                user_text = ""
                image = None
                for block in msg["content"]:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            user_text = block["text"]
                        elif block.get("type") == "image":
                            image = block["source"]["data"]
                if i + 1 < len(self._history):
                    next_msg = self._history[i + 1]
                    if next_msg["role"] == "assistant":
                        assistant_text = self._extract_text(next_msg["content"])
                        exchanges.append(
                            Exchange(
                                user_text=user_text,
                                assistant_text=assistant_text,
                                image_base64=image,
                            )
                        )
            i += 1
        return exchanges

    def trim_history(self, max_turns: int = 20) -> None:
        """Keep only the last N user/assistant turn pairs to manage context size."""
        if len(self._history) <= max_turns * 2:
            return
        self._history = self._history[-(max_turns * 2):]
