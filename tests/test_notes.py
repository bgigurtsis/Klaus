"""Tests for Obsidian vault tools and the bundled skill."""

from __future__ import annotations

import json
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
    assert "Search the vault for the conversation topic" in instructions
    assert "Do not make the user invent a filename" in instructions
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


def test_save_note_can_create_a_safe_topic_named_file(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))

    result = notes.save_note(
        "# Entropy and Time\n\n- Entropy gives time an arrow.",
        suggested_title="Entropy and Time",
    )

    note = tmp_path / "Klaus Notes" / "Entropy and Time.md"
    assert result == "Created note: Klaus Notes/Entropy and Time.md"
    assert "time an arrow" in note.read_text(encoding="utf-8")
    assert notes.current_file == "Klaus Notes/Entropy and Time.md"


def test_inferred_note_title_cannot_create_nested_or_unsafe_paths(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))

    notes.save_note("Safe content", suggested_title="../../Research: Entropy?")

    assert notes.current_file == "Klaus Notes/Research Entropy.md"
    assert (tmp_path / "Klaus Notes" / "Research Entropy.md").is_file()


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
        "save_screenshot",
        "save_chat_summary",
        "configure_note_capture",
    ]


def test_realtime_save_tool_can_create_an_inferred_note(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))
    brain = RealtimeBrain(
        notes=notes,
        audio_output=_FakeAudioOutput(),
        settings=_settings(),
    )

    result = brain._run_tool(
        {
            "name": "save_note",
            "arguments": json.dumps(
                {
                    "content": "# Bayesian Updating",
                    "suggested_title": "Bayesian Updating",
                }
            ),
        }
    )

    assert result == "Created note: Klaus Notes/Bayesian Updating.md"


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

    assert "Infer a concise suggested_title" in notes.configure_capture("questions")
    notes.configure_capture("questions", "Questions")
    assert notes.configure_capture("off") == (
        "Stopped automatic Obsidian capture for this chat."
    )
    assert notes.capture_exchange("Not saved", "Not saved") is None


def test_capture_can_create_an_inferred_topic_note(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))

    result = notes.configure_capture(
        "conversation",
        suggested_title="Complexity Science Reading Session",
    )

    assert result.endswith(
        "Klaus Notes/Complexity Science Reading Session.md"
    )
    inferred_note = (
        tmp_path / "Klaus Notes" / "Complexity Science Reading Session.md"
    )
    assert inferred_note.is_file()


def test_save_screenshot_creates_attachment_and_embeds_it(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))
    notes.set_pending_screenshot(b"jpeg-bytes")

    result = notes.save_screenshot("Example diagram", "Research/Examples")

    attachments = list((tmp_path / "Attachments" / "Klaus").glob("*.jpg"))
    assert len(attachments) == 1
    assert attachments[0].read_bytes() == b"jpeg-bytes"
    content = (tmp_path / "Research" / "Examples.md").read_text(encoding="utf-8")
    assert "Example diagram" in content
    assert f"![[Attachments/Klaus/{attachments[0].name}]]" in content
    assert result.startswith("Saved screenshot: Attachments/Klaus/")


def test_screenshot_attachment_path_cannot_escape_through_a_symlink(
    tmp_path,
) -> None:
    vault = tmp_path / "Vault"
    outside = tmp_path / "Outside"
    vault.mkdir()
    outside.mkdir()
    (vault / "Attachments").symlink_to(outside, target_is_directory=True)
    notes = NotesManager(str(vault))
    notes.set_pending_screenshot(b"jpeg")

    result = notes.save_screenshot(file_path="Examples")

    assert "must stay inside" in result
    assert list(outside.iterdir()) == []


def test_automatic_capture_can_include_screenshots(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))
    result = notes.configure_capture(
        "conversation",
        "Study Session",
        include_screenshots=True,
    )
    notes.reset_changed()

    notes.capture_exchange("Explain this", "It is a diagram.", screenshot=b"jpeg")

    content = (tmp_path / "Study Session.md").read_text(encoding="utf-8")
    assert "with screenshots" in result
    assert "![[Attachments/Klaus/" in content


def test_chat_summary_stops_capture(tmp_path) -> None:
    notes = NotesManager(str(tmp_path))
    notes.configure_capture("conversation", "Study Session")
    notes.reset_changed()

    result = notes.save_chat_summary(
        "### Key ideas\n\n- Entropy measures multiplicity."
    )

    content = (tmp_path / "Study Session.md").read_text(encoding="utf-8")
    assert "## Session summary -" in content
    assert "### Key ideas" in content
    assert notes.capture_mode == "off"
    assert notes.capture_changed is True
    assert result == (
        "Saved chat summary and stopped automatic capture: Study Session.md"
    )
