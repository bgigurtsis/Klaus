"""Tests for the manual Paper Pure pairing helper."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import threading
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "pair-remarkable.py"


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
