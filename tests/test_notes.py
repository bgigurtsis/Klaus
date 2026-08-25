"""Tests for Obsidian vault tools and the bundled skill."""

from __future__ import annotations

from types import SimpleNamespace

from klaus import config
from klaus.notes import NotesManager
from klaus.realtime import RealtimeBrain
from klaus.skill_loader import load_skill_instructions


class _FakeAudioOutput:
    def stop(self) -> None:
        pass


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        openai_api_key="test-key",
        voice="marin",
    )


def test_bundled_obsidian_skill_loads_without_frontmatter() -> None:
    instructions = load_skill_instructions("obsidian")

    assert instructions.startswith("# Obsidian")
    assert "Search the vault before creating a note" in instructions
    assert "name: obsidian" not in instructions


def test_system_prompt_loads_obsidian_skill_only_for_configured_vault() -> None:
    plain_prompt = config._build_system_prompt("")
    obsidian_prompt = config._build_system_prompt("", obsidian_enabled=True)

    assert "Bundled Obsidian skill" not in plain_prompt
    assert "Bundled Obsidian skill" in obsidian_prompt
    assert "Use the vault as a connected knowledge base" in obsidian_prompt


def test_new_note_keeps_properties_at_the_first_line(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))

    assert notes.set_file("Research/Entropy") == "Created note: Research/Entropy.md"
    assert notes.save_note("---\ntags: [physics]\n---\n# Entropy") == (
        "Created note: Research/Entropy.md"
    )

    note = tmp_path / "Research" / "Entropy.md"
    assert note.read_text(encoding="utf-8").startswith("---\n")


def test_existing_note_is_read_and_appended_without_overwrite(tmp_path) -> None:
    note = tmp_path / "Research" / "Entropy.md"
    note.parent.mkdir()
    note.write_text("# Entropy\n", encoding="utf-8")
    notes = NotesManager(str(tmp_path))

    assert notes.set_file("Research/Entropy.md") == (
        "Using existing note: Research/Entropy.md"
    )
    assert "# Entropy" in notes.read_note("Research/Entropy")
    assert notes.save_note("- [[Thermodynamics]]") == (
        "Appended note: Research/Entropy.md"
    )
    assert note.read_text(encoding="utf-8") == (
        "# Entropy\n\n- [[Thermodynamics]]\n"
    )


def test_search_notes_matches_paths_and_content(tmp_path) -> None:
    (tmp_path / "Physics").mkdir()
    (tmp_path / "Physics" / "Entropy.md").write_text(
        "Irreversible processes", encoding="utf-8"
    )
    (tmp_path / "Reading.md").write_text(
        "A paragraph about entropy production", encoding="utf-8"
    )
    notes = NotesManager(str(tmp_path))

    result = notes.search_notes("entropy")

    assert "Physics/Entropy.md" in result
    assert "Reading.md" in result


def test_note_paths_cannot_escape_the_vault(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))

    assert "must stay inside" in notes.set_file("../outside.md")
    assert "must be relative" in notes.read_note("/tmp/outside.md")


def test_realtime_exposes_all_obsidian_tools_for_a_configured_vault(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))
    brain = RealtimeBrain(
        notes=notes,
        audio_output=_FakeAudioOutput(),
        settings=_settings(),
    )

    names = [tool["name"] for tool in brain._tools]

    assert names == [
        "search_notes",
        "read_note",
        "set_notes_file",
        "save_note",
        "configure_note_capture",
    ]


def test_question_capture_appends_only_the_users_later_question(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))

    result = notes.configure_capture("questions", "Research/Questions")
    notes.reset_changed()
    capture_result = notes.capture_exchange(
        "Why does entropy increase?",
        "Because high-entropy macrostates have more microstates.",
        created_at=1_788_000_000,
    )

    assert result == "Automatic capture enabled for user questions: Research/Questions.md"
    assert capture_result == "Created note: Research/Questions.md"
    content = (tmp_path / "Research" / "Questions.md").read_text(encoding="utf-8")
    assert "**You:** Why does entropy increase?" in content
    assert "**Klaus:**" not in content


def test_conversation_capture_appends_the_question_and_answer(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))
    notes.configure_capture("conversation", "Study Session")
    notes.reset_changed()

    notes.capture_exchange("What is entropy?", "A measure of multiplicity.")

    content = (tmp_path / "Study Session.md").read_text(encoding="utf-8")
    assert "**You:** What is entropy?" in content
    assert "**Klaus:** A measure of multiplicity." in content


def test_capture_requires_a_current_note_and_can_be_stopped(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))

    assert notes.configure_capture("questions") == (
        "Error: No notes file set. Ask the user which file to use."
    )
    notes.configure_capture("questions", "Questions")
    assert notes.configure_capture("off") == (
        "Stopped automatic Obsidian capture for this chat."
    )
    assert notes.capture_exchange("Not saved", "Not saved") is None
