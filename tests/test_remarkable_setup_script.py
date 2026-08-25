"""Tests for the host-side Paper Pure setup bundle."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = ROOT / "scripts" / "setup-remarkable-paper-pure.sh"
PACKAGE_DIR = ROOT / "packaging" / "remarkable"
STREAM_SHA512 = (
    "c6dd3e5167a5e3a98a7bc0688a1142d3c6a53f2de07e1350dbf1ca31803dd7182eabc38"
    "ea48f7e543bd804cd92f0a8fb2d5ddb13c60ea7d08bb12ff4f93238e8"
)
LICENSE_SHA512 = (
    "814f7ff90e542338425c7e6740ff7cd151143ee5ae32b40ea492d99e9498ac85ec5e42b3"
    "3108fd065d03bf7d453866487054652a8a6f11339c6855e34be635ac"
)


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _fake_path(tmp_path: Path, *, os_version: str = "3.27.3.0") -> Path:
    commands = tmp_path / "commands"
    commands.mkdir()
    _write_executable(
        commands / "ssh",
        f"""#!/bin/sh
case "$*" in
  *"uname -m"*) echo aarch64 ;;
  *"state/osver"*) echo {os_version} ;;
  *) exit 0 ;;
esac
""",
    )
    _write_executable(commands / "scp", "#!/bin/sh\nexit 99\n")
    _write_executable(
        commands / "curl",
        """#!/bin/sh
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then
    printf fixture > "$2"
    exit 0
  fi
  shift
done
exit 2
""",
    )
    _write_executable(
        commands / "shasum",
        f"""#!/bin/sh
case "$3" in
  *goMarkableStream) echo "{STREAM_SHA512}  $3" ;;
  *LICENSE) echo "{LICENSE_SHA512}  $3" ;;
  *) exit 2 ;;
esac
""",
    )
    return commands


def test_setup_bundle_contains_valid_executable_scripts():
    scripts = [
        SETUP_SCRIPT,
        PACKAGE_DIR / "install-on-tablet.sh",
        PACKAGE_DIR / "klaus-post-install",
        PACKAGE_DIR / "klaus-pre-deinstall",
        PACKAGE_DIR / "klaus-remarkable-pairing",
        PACKAGE_DIR / "klaus-remarkable-prepare",
    ]
    for script in scripts:
        assert os.access(script, os.X_OK), script
        shell = "bash" if script == SETUP_SCRIPT else "sh"
        subprocess.run([shell, "-n", script], check=True)


def test_dry_run_checks_supported_tablet_without_copying_files(tmp_path):
    env = os.environ.copy()
    env["PATH"] = f"{_fake_path(tmp_path)}:{env['PATH']}"
    result = subprocess.run(
        [SETUP_SCRIPT, "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert "Dry run passed for Paper Pure 3.27.3.0" in result.stdout


def test_dry_run_rejects_unsupported_tablet_software(tmp_path):
    env = os.environ.copy()
    env["PATH"] = f"{_fake_path(tmp_path, os_version='3.28.0')}:{env['PATH']}"
    result = subprocess.run(
        [SETUP_SCRIPT, "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 1
    assert "supports Paper Pure software 3.27.x only" in result.stderr


def test_setup_rejects_host_option_injection_before_ssh(tmp_path):
    marker = tmp_path / "ssh-called"
    commands = tmp_path / "commands"
    commands.mkdir()
    _write_executable(commands / "ssh", f"#!/bin/sh\ntouch '{marker}'\n")
    env = os.environ.copy()
    env["PATH"] = f"{commands}:{env['PATH']}"
    result = subprocess.run(
        [SETUP_SCRIPT, "--host", "tablet;false", "--dry-run"],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 2
    assert "unsupported characters" in result.stderr
    assert not marker.exists()
