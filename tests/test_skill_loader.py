"""Tests for the bundled-skill loader."""

from __future__ import annotations

import pytest

from klaus.skill_loader import load_skill_instructions


def test_bundled_obsidian_skill_loads_without_frontmatter():
    body = load_skill_instructions("obsidian")
    assert body
    assert not body.startswith("---")
    assert "name:" not in body.splitlines()[0]


def test_missing_skill_raises():
    with pytest.raises(FileNotFoundError):
        load_skill_instructions("does-not-exist")


def test_skill_without_frontmatter_is_rejected(monkeypatch, tmp_path):
    skill_dir = tmp_path / "skills" / "bare"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("no frontmatter here", encoding="utf-8")
    monkeypatch.setattr("klaus.skill_loader.files", lambda _pkg: tmp_path)

    with pytest.raises(ValueError, match="no YAML frontmatter"):
        load_skill_instructions("bare")


def test_skill_with_unterminated_frontmatter_is_rejected(monkeypatch, tmp_path):
    skill_dir = tmp_path / "skills" / "broken"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: broken\nbody", encoding="utf-8")
    monkeypatch.setattr("klaus.skill_loader.files", lambda _pkg: tmp_path)

    with pytest.raises(ValueError, match="invalid YAML frontmatter"):
        load_skill_instructions("broken")
