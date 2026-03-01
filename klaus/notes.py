"""Obsidian vault note-taking, exposed as Claude tools."""

from __future__ import annotations

import logging
from pathlib import Path

from klaus.config import OBSIDIAN_VAULT_PATH

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


class NotesManager:
    """Manages reading/writing notes to an Obsidian vault markdown file."""

    def __init__(self, base_path: str = OBSIDIAN_VAULT_PATH):
        self._base = Path(base_path) if base_path else Path()
        self.current_file: str | None = None
        self._changed = False
        logger.info("NotesManager base path: %s", self._base)

    @property
    def changed(self) -> bool:
        """True if the notes file was changed since the last reset."""
        return self._changed

    def reset_changed(self) -> None:
        self._changed = False

    def set_file(self, relative_path: str) -> str:
        """Set the active notes file. Creates dirs and file if needed.

        Returns a confirmation message for Claude to relay.
        """
        if not self._base or not self._base.parts:
            return "Error: No Obsidian vault path configured. Set OBSIDIAN_VAULT_PATH in .env."

        relative_path = relative_path.strip().strip("/").strip("\\")
        if not relative_path.lower().endswith(".md"):
            relative_path += ".md"

        full = self._base / relative_path

        try:
            full.parent.mkdir(parents=True, exist_ok=True)
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
        return f"Notes file set to: {relative_path}"

    def save_note(self, content: str) -> str:
        """Append content to the current notes file.

        Returns a confirmation message for Claude to relay.
        """
        if not self.current_file:
            return "Error: No notes file set. Ask the user which file to use."

        full = self._base / self.current_file

        try:
            full.parent.mkdir(parents=True, exist_ok=True)
            with open(full, "a", encoding="utf-8") as f:
                f.write("\n" + content + "\n")
            logger.info("Appended note to %s (%d chars)", full, len(content))
        except OSError as e:
            logger.error("Failed to write note to %s: %s", full, e)
            return f"Error writing note: {e}"

        return f"Note saved to {self.current_file}"
