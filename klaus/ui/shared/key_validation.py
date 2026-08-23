from __future__ import annotations

KEY_PATTERNS: list[tuple[str, str, str, int]] = [
    ("OpenAI", "openai", "sk-", 20),
]

# GPT Realtime powers the core experience.
REQUIRED_API_KEY_SLUGS: frozenset[str] = frozenset({"openai"})

KEY_URLS = {
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
