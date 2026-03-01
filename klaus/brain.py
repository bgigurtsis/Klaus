from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import anthropic

import klaus.config as config
from klaus.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from klaus.notes import NotesManager, SET_NOTES_FILE_TOOL, SAVE_NOTE_TOOL
from klaus.search import WebSearch, TOOL_DEFINITION

logger = logging.getLogger(__name__)

_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')


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
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self._search = WebSearch()
        self._notes = notes
        self._history: list[dict] = []
        self._tools: list[dict] = [TOOL_DEFINITION]
        if self._notes is not None:
            self._tools.extend([SET_NOTES_FILE_TOOL, SAVE_NOTE_TOOL])

    def ask(
        self,
        question: str,
        image_base64: str | None = None,
        memory_context: str | None = None,
        notes_context: str | None = None,
        on_sentence: Callable[[str], None] | None = None,
    ) -> Exchange:
        """Send a question (with optional page image) to Claude and return the exchange.

        Handles the tool-use loop: if Claude calls web_search, set_notes_file,
        or save_note, we execute the tool and feed results back until Claude
        produces a final text answer.

        If on_sentence is provided, streams the response and calls on_sentence
        with each complete sentence as it arrives from Claude.
        """
        logger.info(
            "Asking Claude (model=%s, image=%s, memory=%s, history=%d msgs, streaming=%s)",
            CLAUDE_MODEL,
            "yes" if image_base64 else "no",
            "yes" if memory_context else "no",
            len(self._history),
            "yes" if on_sentence else "no",
        )

        user_content = self._build_user_content(question, image_base64)
        self._history.append({"role": "user", "content": user_content})
        self._strip_old_images()

        system = config.SYSTEM_PROMPT
        if memory_context:
            system += (
                "\n\nContext from previous sessions:\n" + memory_context
            )
        if notes_context:
            system += "\n\n" + notes_context

        context_parts = ["system_prompt"]
        if memory_context:
            context_parts.append("memory")
        if notes_context:
            context_parts.append(f"notes({notes_context})")
        if image_base64:
            context_parts.append("image")
        logger.info(
            "Context sent to Claude: [%s], %d history message(s), system prompt %d chars",
            ", ".join(context_parts),
            len(self._history),
            len(system),
        )

        if self._notes:
            self._notes.reset_changed()

        searches_performed: list[dict] = []
        max_tool_rounds = 5

        for round_num in range(max_tool_rounds):
            response, text_buf = self._stream_round(
                system, searches_performed, on_sentence,
            )

            if response.stop_reason == "tool_use":
                logger.info("Tool round %d/%d", round_num + 1, max_tool_rounds)
                tool_results = self._handle_tool_calls(
                    response.content, searches_performed
                )
                self._history.append(
                    {"role": "assistant", "content": response.content}
                )
                self._history.append(
                    {"role": "user", "content": tool_results}
                )
            else:
                if on_sentence and text_buf.strip():
                    on_sentence(text_buf.strip())

                assistant_text = self._extract_text(response.content)
                logger.info(
                    "Claude responded (%d chars, stop=%s)",
                    len(assistant_text), response.stop_reason,
                )
                self._history.append(
                    {"role": "assistant", "content": response.content}
                )
                notes_changed = self._notes.changed if self._notes else False
                return Exchange(
                    user_text=question,
                    assistant_text=assistant_text,
                    image_base64=image_base64,
                    searches=searches_performed,
                    notes_file_changed=notes_changed,
                )

        if on_sentence and text_buf.strip():
            on_sentence(text_buf.strip())

        assistant_text = self._extract_text(response.content)
        logger.warning(
            "Claude hit max tool rounds (%d), returning partial response (%d chars)",
            max_tool_rounds, len(assistant_text),
        )
        self._history.append(
            {"role": "assistant", "content": response.content}
        )
        notes_changed = self._notes.changed if self._notes else False
        return Exchange(
            user_text=question,
            assistant_text=assistant_text,
            image_base64=image_base64,
            searches=searches_performed,
            notes_file_changed=notes_changed,
        )

    def _stream_round(
        self,
        system: str,
        searches_performed: list[dict],
        on_sentence: Callable[[str], None] | None,
    ) -> tuple[anthropic.types.Message, str]:
        """Execute one Claude round with streaming.

        Returns (final_message, remaining_text_buffer).
        Calls on_sentence for each complete sentence detected during streaming.
        """
        text_buf = ""
        with self._client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=system,
            messages=self._history,
            tools=self._tools,
        ) as stream:
            for event in stream:
                if (
                    event.type == "content_block_delta"
                    and hasattr(event.delta, "text")
                ):
                    text_buf += event.delta.text
                    if on_sentence:
                        sentences, text_buf = _extract_sentences(text_buf)
                        for s in sentences:
                            on_sentence(s)
            response = stream.get_final_message()
        return response, text_buf

    def _build_user_content(
        self, question: str, image_base64: str | None
    ) -> list[dict]:
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
                searches_performed.append(
                    {"query": query, "result": search_result}
                )
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
        return " ".join(parts)

    def _strip_old_images(self) -> None:
        """Remove image blocks from all but the most recent user message."""
        found_latest = False
        stripped = 0
        for msg in reversed(self._history):
            if msg["role"] != "user":
                continue
            has_image = any(
                isinstance(b, dict) and b.get("type") == "image"
                for b in msg["content"]
            )
            if not has_image:
                continue
            if not found_latest:
                found_latest = True
                continue
            msg["content"] = [
                b for b in msg["content"]
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
