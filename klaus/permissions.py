"""Map macOS permission failures to actionable in-app guidance."""

from __future__ import annotations

from dataclasses import dataclass


SCREEN_RECORDING_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
)


@dataclass(frozen=True)
class PermissionGuidance:
    title: str
    message: str
    settings_url: str


def guidance_for_error(error: str) -> PermissionGuidance | None:
    """Return permission guidance for a known macOS error."""
    normalized = error.lower()
    if (
        "screen recording access" in normalized
        or "screen & system audio recording" in normalized
    ):
        return PermissionGuidance(
            title="Allow Screen Recording",
            message=(
                "Klaus needs Screen Recording to capture Desk View or an active "
                "window. Allow it in System Settings, then choose the source again."
            ),
            settings_url=SCREEN_RECORDING_SETTINGS_URL,
        )
    return None
