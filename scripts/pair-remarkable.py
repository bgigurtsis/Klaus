#!/usr/bin/env python3
"""Forward tablet credentials to a running Klaus process without displaying them."""

from __future__ import annotations

import argparse
import json
import socket
import stat
import sys
from pathlib import Path

MAX_RESPONSE_BYTES = 16 * 1024


def socket_is_available(path: Path) -> bool:
    """Return whether the pairing socket exists with the expected type."""
    try:
        return stat.S_ISSOCK(path.stat().st_mode)
    except FileNotFoundError:
        return False


def pair(path: Path, address: str, payload: bytes) -> str:
    """Send credentials from standard input to the private Klaus socket."""
    lines = [line for line in payload.splitlines() if line.strip()]
    if not lines:
        raise ValueError("The tablet did not return pairing credentials.")
    credentials = json.loads(lines[-1])
    if not isinstance(credentials, dict):
        raise ValueError("The tablet returned invalid pairing credentials.")
    username = credentials.get("username")
    password = credentials.get("password")
    if not isinstance(username, str) or not username:
        raise ValueError("The tablet did not return a pairing username.")
    if not isinstance(password, str) or not password:
        raise ValueError("The tablet did not return a pairing password.")

    request = json.dumps(
        {"address": address, "username": username, "password": password}
    ).encode("utf-8") + b"\n"

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(40)
        client.connect(str(path))
        client.sendall(request)
        response = bytearray()
        while len(response) <= MAX_RESPONSE_BYTES:
            chunk = client.recv(min(4096, MAX_RESPONSE_BYTES + 1 - len(response)))
            if not chunk:
                break
            response.extend(chunk)
            if b"\n" in chunk:
                break

    if len(response) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Klaus returned an oversized pairing response.")
    result = json.loads(bytes(response).split(b"\n", 1)[0])
    if not isinstance(result, dict) or not result.get("ok"):
        message = result.get("message") if isinstance(result, dict) else None
        raise RuntimeError(message or "Klaus could not pair with Paper Pure.")
    return str(result.get("message") or "Paired Paper Pure with Klaus.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--address")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if args.check:
        return 0 if socket_is_available(args.socket) else 1
    if not args.address:
        parser.error("--address is required unless --check is used")
    if not socket_is_available(args.socket):
        print("Open Klaus, then run the installer again.", file=sys.stderr)
        return 1

    try:
        message = pair(args.socket, args.address, sys.stdin.buffer.read())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
