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
CERT_SCRIPT = Path(__file__).parents[1] / "scripts" / "create-signing-certificate.sh"
LAUNCHER = Path(__file__).parents[1] / "packaging" / "macos" / "launcher.c"


def test_installer_does_not_ad_hoc_sign() -> None:
    script = INSTALLER.read_text()

    assert "codesign --force --deep --sign -" not in script
    assert 'codesign --force --deep --sign "$codesign_identity"' in script
    assert '[[ "$codesign_identity" == "-" ]]' in script


def test_installer_signs_with_stable_certificate_by_default() -> None:
    script = INSTALLER.read_text()

    assert 'default_identity="Klaus Code Signing"' in script
    assert "create-signing-certificate.sh" in script
    assert "certificate-app-bundle-v2" in script
    assert "signature-format" in script


def test_installer_resets_tcc_rows_when_identity_changes() -> None:
    script = INSTALLER.read_text()

    assert "tccutil reset ScreenCapture com.bgigurtsis.klaus" in script
    assert "tccutil reset Microphone com.bgigurtsis.klaus" in script
    assert "tccutil reset Camera com.bgigurtsis.klaus" in script
    assert 'previous_signature_format" != "$signature_format' in script


def test_certificate_script_creates_codesigning_identity() -> None:
    script = CERT_SCRIPT.read_text()

    assert "find-identity -v -p codesigning" in script
    assert "extendedKeyUsage = critical, codeSigning" in script
    assert "keyUsage = critical, digitalSignature" in script
    assert "-T /usr/bin/codesign" in script
    assert "set-key-partition-list" not in script


def test_launcher_forks_and_stays_responsible_process() -> None:
    launcher = LAUNCHER.read_text()

    assert "fork()" in launcher
    assert "waitpid" in launcher
    assert "EINTR" in launcher
    assert "WIFEXITED" in launcher
    assert "WIFSIGNALED" in launcher
    assert "kill(child, sig)" in launcher
    assert "execv(klaus_executable" in launcher


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS app test")
def test_opt_out_installer_uses_linker_signature_and_skips_valid_reinstall(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    checkout = tmp_path / "checkout"

    for relative_path in (
        "scripts/install-macos-app.sh",
        "scripts/create-signing-certificate.sh",
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
    environment["KLAUS_CODESIGN_IDENTITY"] = "none"
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
