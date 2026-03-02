from __future__ import annotations

KEY_PATTERNS: list[tuple[str, str, str, int]] = [
    ("Anthropic", "anthropic", "sk-ant-", 40),
    ("OpenAI", "openai", "sk-", 20),
    ("Tavily", "tavily", "tvly-", 20),
]

KEY_URLS = {
    "anthropic": "https://console.anthropic.com/settings/keys",
    "openai": "https://platform.openai.com/api-keys",
    "tavily": "https://app.tavily.com/home",
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
