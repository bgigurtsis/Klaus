from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS app test")
def test_installer_signs_a_complete_app_bundle_and_skips_a_valid_reinstall(
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
    first_install = subprocess.run(
        [str(checkout / "scripts/install-macos-app.sh"), str(app_parent)],
        check=True,
        capture_output=True,
        text=True,
    )
    app_path = app_parent / "Klaus.app"

    verification = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(app_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    signature = subprocess.run(
        ["codesign", "-dvvv", str(app_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    second_install = subprocess.run(
        [str(checkout / "scripts/install-macos-app.sh"), str(app_parent)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Installed Klaus" in first_install.stdout
    assert verification.returncode == 0, verification.stderr
    assert "Identifier=com.bgigurtsis.klaus" in signature.stderr
    assert "Info.plist entries=" in signature.stderr
    assert "skipped reinstall" in second_install.stdout
