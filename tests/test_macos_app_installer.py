"""Tests for the macOS development app installer."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


INSTALLER = Path(__file__).parents[1] / "scripts" / "install-macos-app.sh"


def test_installer_does_not_ad_hoc_sign() -> None:
    script = INSTALLER.read_text()

    assert "codesign --force --deep --sign -" not in script
    assert 'codesign --force --deep --sign "$codesign_identity"' in script
    assert '[[ "$codesign_identity" == "-" ]]' in script


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS app test")
def test_default_installer_uses_linker_signature_and_skips_valid_reinstall(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    checkout = tmp_path / "checkout"

    for relative_path in (
        "scripts/install-macos-app.sh",
        "packaging/macos/launcher.c",
        "packaging/macos/Info.plist",
        "klaus/ui/icon.png",
    ):
        destination = checkout / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repository / relative_path, destination)

    bin_directory = checkout / ".venv/bin"
    bin_directory.mkdir(parents=True)
    python_executable = bin_directory / "python"
    python_executable.write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n"
    )
    python_executable.chmod(0o755)
    klaus_executable = bin_directory / "klaus"
    klaus_executable.write_text("#!/bin/sh\nexit 0\n")
    klaus_executable.chmod(0o755)

    app_parent = tmp_path / "Applications"
    environment = os.environ.copy()
    environment.pop("KLAUS_CODESIGN_IDENTITY", None)
    first_install = subprocess.run(
        [str(checkout / "scripts/install-macos-app.sh"), str(app_parent)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    executable = app_parent / "Klaus.app/Contents/MacOS/Klaus"

    verification = subprocess.run(
        ["codesign", "--verify", "--strict", "--ignore-resources", str(executable)],
        check=False,
        capture_output=True,
        text=True,
    )
    signature = subprocess.run(
        ["codesign", "-dvvv", str(executable)],
        check=False,
        capture_output=True,
        text=True,
    )
    second_install = subprocess.run(
        [str(checkout / "scripts/install-macos-app.sh"), str(app_parent)],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert "Installed Klaus" in first_install.stdout
    assert verification.returncode == 0, verification.stderr
    assert "linker-signed" in signature.stderr
    assert "skipped reinstall" in second_install.stdout
