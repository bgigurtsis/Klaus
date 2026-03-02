"""Shared UI helpers reused across setup/settings/chat widgets."""

from klaus.ui.shared.key_validation import KEY_PATTERNS, KEY_URLS, validate_api_key
from klaus.ui.shared.mic_level_monitor import MicLevelMonitor
from klaus.ui.shared.relative_time import (
    format_relative_time,
    format_relative_time_with_tooltip,
)

__all__ = [
    "KEY_PATTERNS",
    "KEY_URLS",
    "MicLevelMonitor",
    "format_relative_time",
    "format_relative_time_with_tooltip",
    "validate_api_key",
]
