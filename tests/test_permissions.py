from klaus.permissions import SCREEN_RECORDING_SETTINGS_URL, guidance_for_error


def test_screen_recording_failure_has_actionable_guidance() -> None:
    guidance = guidance_for_error(
        "Allow Klaus under System Settings > Privacy & Security > "
        "Screen & System Audio Recording, then restart Klaus."
    )

    assert guidance is not None
    assert guidance.title == "Allow Screen Recording"
    assert "already enabled" in guidance.message
    assert "quit and reopen Klaus" in guidance.message
    assert guidance.settings_url == SCREEN_RECORDING_SETTINGS_URL


def test_unrelated_failure_has_no_permission_guidance() -> None:
    assert guidance_for_error("camera unavailable") is None
