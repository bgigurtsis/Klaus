"""Obsidian vault note-taking tools."""

from __future__ import annotations

import logging
from pathlib import Path

import klaus.config as config

logger = logging.getLogger(__name__)

SET_NOTES_FILE_TOOL = {
    "name": "set_notes_file",
    "description": (
        "Set the markdown file for saving notes in the user's Obsidian vault. "
        "The path is relative to the configured vault base directory. "
        "Creates parent directories and the file if they don't exist. "
        "This persists across questions until the user changes it."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": (
                    "Relative path to the markdown file, e.g. "
                    "'Foundational Papers in Complexity Science/1st March Notes.md'. "
                    "The .md extension is added automatically if missing."
                ),
            }
        },
        "required": ["file_path"],
    },
}

SAVE_NOTE_TOOL = {
    "name": "save_note",
    "description": (
        "Append a note to the user's current notes file in Obsidian. "
        "Use this when the user asks you to save a quote, idea, definition, "
        "page reference, summary, or any other content to their notes. "
        "Format the content as markdown."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Markdown-formatted content to append to the notes file.",
            }
        },
        "required": ["content"],
    },
}

SEARCH_NOTES_TOOL = {
    "name": "search_notes",
    "description": (
        "Find existing Markdown notes in the user's Obsidian vault. "
        "Searches note paths and note text. Use this before creating a note "
        "when the user names a topic but not an exact file."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Words from the note title or content to find.",
            }
        },
        "required": ["query"],
    },
}

READ_NOTE_TOOL = {
    "name": "read_note",
    "description": (
        "Read a Markdown note from the user's Obsidian vault. "
        "Use this before appending when existing structure or content matters."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Vault-relative Markdown file path.",
            }
        },
        "required": ["file_path"],
    },
}


class NotesManager:
    """Manages reading/writing notes to an Obsidian vault markdown file."""

    def __init__(self, base_path: str | None = None):
        if base_path is None:
            base_path = config.OBSIDIAN_VAULT_PATH
        self._base = Path(base_path).expanduser() if base_path else Path()
        self.current_file: str | None = None
        self._changed = False
        logger.info("NotesManager base path: %s", self._base)

    @property
    def base_path(self) -> str:
        return str(self._base)

    @property
    def current_path(self) -> str | None:
        """Return the absolute path for the active notes file."""
        if not self.current_file or not self._base or not self._base.parts:
            return None
        base = self._base.expanduser().resolve()
        full = (base / self.current_file).resolve()
        try:
            full.relative_to(base)
        except ValueError:
            return None
        return str(full)

    @property
    def changed(self) -> bool:
        """True if the notes file was changed since the last reset."""
        return self._changed

    def reset_changed(self) -> None:
        self._changed = False

    def set_file(self, relative_path: str) -> str:
        """Set the active notes file. Creates dirs and file if needed.

        Returns a confirmation message for Klaus to relay.
        """
        if not self._base or not self._base.parts:
            return "Error: No Obsidian vault path configured. Set OBSIDIAN_VAULT_PATH in .env."

        try:
            relative_path, full = self._resolve_note_path(relative_path)
        except ValueError as exc:
            return f"Error: {exc}"

        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            created = not full.exists()
            if not full.exists():
                full.touch()
                logger.info("Created notes file: %s", full)
            else:
                logger.info("Notes file already exists: %s", full)
        except OSError as e:
            logger.error("Failed to create notes file %s: %s", full, e)
            return f"Error creating file: {e}"

        self.current_file = relative_path
        self._changed = True
        action = "Created note" if created else "Using existing note"
        return f"{action}: {relative_path}"

    def save_note(self, content: str) -> str:
        """Append content to the current notes file.

        Returns a confirmation message for Klaus to relay.
        """
        if not self.current_file:
            return "Error: No notes file set. Ask the user which file to use."

        content = content.strip()
        if not content:
            return "Error: Note content is empty."

        try:
            relative_path, full = self._resolve_note_path(self.current_file)
        except ValueError as exc:
            return f"Error: {exc}"

        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            is_empty = not full.exists() or full.stat().st_size == 0
            with open(full, "a", encoding="utf-8") as f:
                if is_empty:
                    f.write(content + "\n")
                else:
                    f.write("\n" + content + "\n")
            logger.info("Appended note to %s (%d chars)", full, len(content))
        except OSError as e:
            logger.error("Failed to write note to %s: %s", full, e)
            return f"Error writing note: {e}"

        action = "Created note" if is_empty else "Appended note"
        return f"{action}: {relative_path}"

    def search_notes(self, query: str, *, limit: int = 8) -> str:
        """Find vault notes by path or text without leaving the vault root."""
        if not self._base or not self._base.parts:
            return "Error: No Obsidian vault path configured."

        terms = [term.casefold() for term in query.split() if term.strip()]
        if not terms:
            return "Error: Search query is empty."
        if not self._base.is_dir():
            return "Error: The configured Obsidian vault does not exist."

        matches: list[tuple[int, str]] = []
        base = self._base.resolve()
        for note_path in base.rglob("*.md"):
            relative = note_path.relative_to(base)
            if any(part.startswith(".") for part in relative.parts):
                continue
            try:
                resolved = note_path.resolve()
                resolved.relative_to(base)
            except (OSError, ValueError):
                continue

            relative_text = relative.as_posix()
            path_text = relative_text.casefold()
            path_match = all(term in path_text for term in terms)
            content_match = False
            if not path_match:
                try:
                    if resolved.stat().st_size <= 1_000_000:
                        note_text = resolved.read_text(encoding="utf-8").casefold()
                        content_match = all(term in note_text for term in terms)
                except (OSError, UnicodeError):
                    continue
            if path_match or content_match:
                matches.append((0 if path_match else 1, relative_text))

        matches.sort(key=lambda item: (item[0], item[1].casefold()))
        if not matches:
            return "No matching notes found."
        selected = matches[: max(1, min(limit, 20))]
        return "Matching notes:\n" + "\n".join(f"- {path}" for _, path in selected)

    def read_note(self, relative_path: str, *, max_chars: int = 12_000) -> str:
        """Read one vault note with a bounded response size."""
        if not self._base or not self._base.parts:
            return "Error: No Obsidian vault path configured."
        try:
            relative_path, full = self._resolve_note_path(relative_path)
        except ValueError as exc:
            return f"Error: {exc}"
        if not full.is_file():
            return f"Error: Note does not exist: {relative_path}"

        try:
            content = full.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            return f"Error reading note: {exc}"
        if len(content) <= max_chars:
            return f"Note: {relative_path}\n\n{content}"

        head_chars = 2_000
        tail_chars = max_chars - head_chars
        return (
            f"Note: {relative_path}\n\n"
            f"{content[:head_chars]}\n\n[... middle omitted ...]\n\n{content[-tail_chars:]}"
        )

    def _resolve_note_path(self, relative_path: str) -> tuple[str, Path]:
        """Resolve one Markdown path and reject vault escapes."""
        cleaned = relative_path.strip().replace("\\", "/")
        if not cleaned:
            raise ValueError("Note path is empty.")

        candidate = Path(cleaned)
        if candidate.is_absolute():
            raise ValueError("Note path must be relative to the Obsidian vault.")
        if candidate.suffix.lower() != ".md":
            candidate = candidate.with_suffix(candidate.suffix + ".md")

        base = self._base.resolve()
        full = (base / candidate).resolve()
        try:
            relative = full.relative_to(base)
        except ValueError as exc:
            raise ValueError("Note path must stay inside the Obsidian vault.") from exc
        return relative.as_posix(), full
