"""Load bundled model skills from the installed Klaus package."""

from __future__ import annotations

from importlib.resources import files


def load_skill_instructions(skill_name: str) -> str:
    """Return a bundled skill body without its YAML frontmatter."""
    skill_file = files("klaus").joinpath("skills", skill_name, "SKILL.md")
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"Bundled skill has no YAML frontmatter: {skill_name}")

    try:
        _, _, body = text.split("---\n", 2)
    except ValueError as exc:
        raise ValueError(f"Bundled skill has invalid YAML frontmatter: {skill_name}") from exc
    return body.strip()
