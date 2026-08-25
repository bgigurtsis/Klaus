"""Map macOS permission failures to actionable in-app guidance."""

from __future__ import annotations

from dataclasses import dataclass


SCREEN_RECORDING_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
)
MICROPHONE_SETTINGS_URL = (
    "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
)

MIC_UNAVAILABLE_MESSAGE = (
    "Could not open this microphone. Check that it is connected, and that "
    "Klaus is allowed under System Settings > Privacy & Security > Microphone."
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
                "window. If Klaus is already enabled in System Settings, turn it "
                "off and on. Then quit and reopen Klaus before choosing the source "
                "again."
            ),
            settings_url=SCREEN_RECORDING_SETTINGS_URL,
        )
    if "microphone" in normalized or "input device" in normalized:
        return PermissionGuidance(
            title="Microphone Unavailable",
            message=MIC_UNAVAILABLE_MESSAGE,
            settings_url=MICROPHONE_SETTINGS_URL,
        )
    return None
