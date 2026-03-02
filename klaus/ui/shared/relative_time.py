from __future__ import annotations

import time


def format_relative_time(ts: float) -> str:
    delta = time.time() - ts
    if delta < 60:
        return "just now"
    if delta < 3600:
        mins = int(delta / 60)
        return f"{mins}m ago"
    if delta < 86400:
        hours = int(delta / 3600)
        return f"{hours}h ago"
    days = int(delta / 86400)
    if days == 1:
        return "yesterday"
    return f"{days}d ago"


def format_relative_time_with_tooltip(ts: float) -> tuple[str, str]:
    full = time.strftime("%I:%M %p", time.localtime(ts))
    return format_relative_time(ts), full
