"""Private local bridge for one-click Paper Pure pairing from reManager."""

from __future__ import annotations

import json
import os
import socket
import stat
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import klaus.config as config
from klaus.remarkable_reading_source import PairingResult, pair_tablet

MAX_REQUEST_BYTES = 16 * 1024
SOCKET_NAME = "remanager-pairing.sock"


def pairing_socket_path() -> Path:
    """Return the private socket used by reManager and Klaus."""
    return config.DATA_DIR / SOCKET_NAME


class RemarkablePairingServer:
    """Accept credentials from the local reManager process without a clipboard."""

    def __init__(
        self,
        *,
        socket_path: Path | None = None,
        pairer: Callable[[str, str, str], PairingResult] = pair_tablet,
        saver: Callable[[str, str, str, str], None] = config.save_remarkable_connection,
        on_paired: Callable[[str], None] | None = None,
    ) -> None:
        self.socket_path = socket_path or pairing_socket_path()
        self._pairer = pairer
        self._saver = saver
        self._on_paired = on_paired
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._pairing_lock = threading.Lock()

    def start(self) -> None:
        """Start the local pairing server."""
        if self._thread and self._thread.is_alive():
            return
        self.socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.socket_path.parent, 0o700)
        if self.socket_path.exists() or self.socket_path.is_symlink():
            mode = self.socket_path.lstat().st_mode
            if not stat.S_ISSOCK(mode):
                raise RuntimeError(f"Pairing socket path is not a socket: {self.socket_path}")
            self.socket_path.unlink()

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        listener.listen(1)
        listener.settimeout(0.5)
        self._socket = listener
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the server and remove its socket."""
        self._stop_event.set()
        listener = self._socket
        self._socket = None
        if listener is not None:
            listener.close()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)
        self._thread = None
        try:
            if self.socket_path.exists() and stat.S_ISSOCK(self.socket_path.lstat().st_mode):
                self.socket_path.unlink()
        except FileNotFoundError:
            pass

    def _serve(self) -> None:
        listener = self._socket
        if listener is None:
            return
        while not self._stop_event.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                connection.settimeout(35)
                self._handle_connection(connection)

    def _handle_connection(self, connection: socket.socket) -> None:
        try:
            get_peer_credentials = getattr(connection, "getpeereid", None)
            if get_peer_credentials is not None:
                peer_user_id, _ = get_peer_credentials()
                if peer_user_id != os.getuid():
                    raise PermissionError("Pairing request came from another user")
            request = self._read_request(connection)
            address = self._required_string(request, "address", 512)
            username = self._required_string(request, "username", 256)
            password = self._required_string(request, "password", 4096, strip=False)
            with self._pairing_lock:
                result = self._pairer(address, username, password)
                self._saver(
                    result.address,
                    result.username,
                    password,
                    result.certificate_sha256,
                )
                config.reload()
            message = (
                f"Paired Paper Pure ({result.frame_width} x {result.frame_height}) "
                "with Klaus."
            )
            self._send_response(connection, {"ok": True, "message": message})
            if self._on_paired is not None:
                self._on_paired(message)
        except Exception as exc:
            self._send_response(connection, {"ok": False, "message": str(exc)})

    @staticmethod
    def _read_request(connection: socket.socket) -> dict[str, Any]:
        chunks = bytearray()
        while len(chunks) <= MAX_REQUEST_BYTES:
            chunk = connection.recv(min(4096, MAX_REQUEST_BYTES + 1 - len(chunks)))
            if not chunk:
                break
            chunks.extend(chunk)
            if b"\n" in chunk:
                break
        if len(chunks) > MAX_REQUEST_BYTES:
            raise ValueError("Pairing request is too large")
        line = bytes(chunks).split(b"\n", 1)[0]
        request = json.loads(line.decode("utf-8"))
        if not isinstance(request, dict):
            raise ValueError("Pairing request must be an object")
        return request

    @staticmethod
    def _required_string(
        request: dict[str, Any], name: str, maximum: int, *, strip: bool = True
    ) -> str:
        value = request.get(name)
        if not isinstance(value, str):
            raise ValueError(f"Pairing request is missing {name}")
        parsed = value.strip() if strip else value
        if not parsed or len(parsed) > maximum:
            raise ValueError(f"Pairing request has an invalid {name}")
        return parsed

    @staticmethod
    def _send_response(connection: socket.socket, response: dict[str, Any]) -> None:
        try:
            connection.sendall(json.dumps(response).encode("utf-8") + b"\n")
        except OSError:
            pass
