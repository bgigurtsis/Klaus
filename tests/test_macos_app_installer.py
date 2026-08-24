"""Tests for the macOS development app installer."""

from pathlib import Path


INSTALLER = Path(__file__).parents[1] / "scripts" / "install-macos-app.sh"


def test_installer_does_not_ad_hoc_sign() -> None:
    script = INSTALLER.read_text()

    assert "codesign --force --deep --sign -" not in script
    assert 'codesign --force --deep --sign "$codesign_identity"' in script
    assert '[[ "$codesign_identity" == "-" ]]' in script


def test_signing_mode_changes_build_stamp() -> None:
    script = INSTALLER.read_text()

    assert '"$source_root" "$codesign_identity" "installer-signing-v2"' in script
