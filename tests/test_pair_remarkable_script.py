"""Tests for the manual Paper Pure pairing helper."""

from __future__ import annotations

import hashlib
import json
import re
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "pair-remarkable.py"
INSTALLER = Path(__file__).parents[1] / "scripts" / "install-remarkable-paperpure.sh"


def test_pairing_helper_forwards_credentials_without_printing_password():
    temporary_dir = tempfile.TemporaryDirectory(prefix="klaus-manual-pair-", dir="/tmp")
    socket_path = Path(temporary_dir.name) / "pairing.sock"
    received: list[dict[str, str]] = []
    ready = threading.Event()

    def server() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(socket_path))
            listener.listen(1)
            ready.set()
            connection, _ = listener.accept()
            with connection:
                request = connection.recv(16 * 1024).split(b"\n", 1)[0]
                received.append(json.loads(request))
                connection.sendall(
                    b'{"ok":true,"message":"Paired Paper Pure with Klaus."}\n'
                )

    thread = threading.Thread(target=server)
    thread.start()
    assert ready.wait(timeout=2)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--socket",
            str(socket_path),
            "--address",
            "https://10.11.99.1:2001",
        ],
        input=(
            b"A harmless tablet login banner.\n"
            b'{"username":"klaus","password":"private-password"}\n'
        ),
        capture_output=True,
        check=False,
    )
    thread.join(timeout=2)
    temporary_dir.cleanup()

    assert result.returncode == 0
    assert result.stdout == b"Paired Paper Pure with Klaus.\n"
    assert b"private-password" not in result.stdout + result.stderr
    assert received == [
        {
            "address": "https://10.11.99.1:2001",
            "username": "klaus",
            "password": "private-password",
        }
    ]


def test_pairing_helper_check_rejects_missing_socket(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check",
            "--socket",
            str(tmp_path / "missing.sock"),
        ],
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1


def test_standalone_installer_checksums_match_support_files():
    installer = INSTALLER.read_text(encoding="utf-8")
    expected_files = {
        "tablet_installer": Path("packaging/remarkable/install-tablet.sh"),
        "tablet_prepare": Path("packaging/remarkable/klaus-remarkable-prepare"),
        "tablet_service": Path("packaging/remarkable/klaus-remarkable.service"),
        "pairing_client": Path("scripts/pair-remarkable.py"),
    }

    for name, relative_path in expected_files.items():
        match = re.search(rf'^{name}_sha256="([0-9a-f]{{64}})"$', installer, re.MULTILINE)
        assert match is not None
        contents = (INSTALLER.parents[1] / relative_path).read_bytes()
        assert match.group(1) == hashlib.sha256(contents).hexdigest()
