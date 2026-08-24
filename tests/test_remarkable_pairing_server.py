"""Tests for the private reManager-to-Klaus pairing bridge."""

from __future__ import annotations

import json
import socket
import stat
import tempfile
from pathlib import Path

from klaus.remarkable_pairing_server import RemarkablePairingServer
from klaus.remarkable_reading_source import PairingResult


def _request(path: Path, payload: dict[str, str]) -> dict[str, object]:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(path))
        client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
        response = client.makefile("rb").readline()
    return json.loads(response)


def test_pairing_bridge_uses_private_socket_and_never_returns_password(monkeypatch):
    temporary_dir = tempfile.TemporaryDirectory(prefix="klaus-pairing-", dir="/tmp")
    socket_path = Path(temporary_dir.name) / "pairing.sock"
    saved: list[tuple[str, str, str, str]] = []
    paired: list[str] = []
    monkeypatch.setattr("klaus.remarkable_pairing_server.config.reload", lambda: None)

    def pairer(address: str, username: str, password: str) -> PairingResult:
        assert password == "private-password"
        return PairingResult(address, username, "a" * 64, "test", 1404, 1872)

    server = RemarkablePairingServer(
        socket_path=socket_path,
        pairer=pairer,
        saver=lambda *values: saved.append(values),
        on_paired=paired.append,
    )
    server.start()
    try:
        assert stat.S_IMODE(socket_path.stat().st_mode) == 0o600
        response = _request(
            socket_path,
            {
                "address": "https://10.11.99.1:2001",
                "username": "klaus",
                "password": "private-password",
            },
        )
    finally:
        server.stop()

    assert response["ok"] is True
    assert "private-password" not in json.dumps(response)
    assert saved == [
        ("https://10.11.99.1:2001", "klaus", "private-password", "a" * 64)
    ]
    assert paired == ["Paired Paper Pure (1404 x 1872) with Klaus."]
    assert not socket_path.exists()
    temporary_dir.cleanup()


def test_pairing_bridge_rejects_incomplete_requests(monkeypatch):
    temporary_dir = tempfile.TemporaryDirectory(prefix="klaus-pairing-", dir="/tmp")
    socket_path = Path(temporary_dir.name) / "pairing.sock"
    monkeypatch.setattr("klaus.remarkable_pairing_server.config.reload", lambda: None)
    server = RemarkablePairingServer(socket_path=socket_path)
    server.start()
    try:
        response = _request(socket_path, {"address": "https://tablet"})
    finally:
        server.stop()

    assert response == {"ok": False, "message": "Pairing request is missing username"}
    temporary_dir.cleanup()
