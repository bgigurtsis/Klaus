from __future__ import annotations

KEY_PATTERNS: list[tuple[str, str, str, int]] = [
    ("Gemini", "gemini", "AIza", 20),
    ("OpenAI", "openai", "sk-", 20),
]

KEY_URLS = {
    "gemini": "https://aistudio.google.com/app/apikey",
    "openai": "https://platform.openai.com/api-keys",
}


def validate_api_key(slug: str, text: str) -> tuple[bool, str]:
    stripped = text.strip()
    if not stripped:
        return False, ""

    for _, pattern_slug, prefix, min_len in KEY_PATTERNS:
        if pattern_slug != slug:
            continue
        if not stripped.startswith(prefix):
            return False, f"Keys typically start with {prefix}"
        if len(stripped) < min_len:
            return False, "Key seems too short"
        return True, ""

    return False, "Unknown key type"
