"""Tests for the host-side Paper Pure setup bundle."""

from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import tempfile
import threading
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


def test_tablet_upgrade_restarts_service_and_bumps_package_revision():
    post_install = (PACKAGE_DIR / "klaus-post-install").read_text()
    tablet_installer = (PACKAGE_DIR / "install-on-tablet.sh").read_text()

    assert "systemctl restart klaus-remarkable.service" in post_install
    assert "klaus-remarkable-0.1.0-r16.apk" in tablet_installer
    assert "klaus-remarkable-0.1.0-r15.apk" not in tablet_installer


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


def test_setup_pairs_over_wifi_instead_of_usb(tmp_path):
    commands = _fake_path(tmp_path)
    _write_executable(
        commands / "ssh",
        """#!/bin/sh
case "$*" in
  *"uname -m"*) echo aarch64 ;;
  *"test -x /home/root/.vellum/bin/vellum"*) exit 0 ;;
  *"vellum list -I"*) echo rmppure-1 ;;
  *"state/osver"*) echo 3.27.3.0 ;;
  *"cat /home/root/.config/klaus-remarkable/service.env"*)
    printf 'RK_SERVER_USERNAME=klaus\nRK_SERVER_PASSWORD=private-password\n' ;;
  *"hostname 2>/dev/null"*) echo reMarkable ;;
  *"ip -4 -o addr show scope global"*)
    printf '2: wlan0 inet 192.168.1.44/24 scope global wlan0\n' ;;
  *) exit 0 ;;
esac
""",
    )
    _write_executable(commands / "scp", "#!/bin/sh\nexit 0\n")

    temporary_data = tempfile.TemporaryDirectory(prefix="klaus-setup-", dir="/tmp")
    data_dir = Path(temporary_data.name)
    socket_path = data_dir / "remanager-pairing.sock"
    captured: list[dict[str, str]] = []
    ready = threading.Event()

    def serve_pairing() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(socket_path))
            server.listen(1)
            ready.set()
            connection, _ = server.accept()
            with connection:
                request = connection.makefile("rb").readline()
                captured.append(json.loads(request))
                response = {"ok": True, "message": "Paired over Wi-Fi."}
                connection.sendall(json.dumps(response).encode() + b"\n")

    server_thread = threading.Thread(target=serve_pairing)
    server_thread.start()
    assert ready.wait(timeout=2)
    env = os.environ.copy()
    env["PATH"] = f"{commands}:{env['PATH']}"
    env["KLAUS_DATA_DIR"] = str(data_dir)
    result = subprocess.run(
        [SETUP_SCRIPT],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    server_thread.join(timeout=2)

    assert not server_thread.is_alive()
    assert captured[0]["address"] == "https://reMarkable.local.:2001"
    assert "after USB-C is disconnected" in result.stdout
    temporary_data.cleanup()
