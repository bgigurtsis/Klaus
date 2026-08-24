"""Pinned HTTPS screenshot client for reMarkable Paper Pure."""

from __future__ import annotations

import hashlib
import http.client
import json
import socket
import ssl
import threading
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlsplit

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError


class RemarkableError(RuntimeError):
    """Base error for the Paper Pure reading source."""


class RemarkableAuthenticationError(RemarkableError):
    """The streamer rejected the configured credentials."""


class RemarkableCertificateError(RemarkableError):
    """The tablet certificate does not match the paired certificate."""


class RemarkableMissingServiceError(RemarkableError):
    """The tablet answered, but goMarkableStream was unavailable."""


class RemarkableNetworkError(RemarkableError):
    """The tablet could not be reached over the network."""


class RemarkableSleepingError(RemarkableError):
    """The tablet did not respond before the request timeout."""


class RemarkableCancelledError(RemarkableError):
    """The caller cancelled a tablet request."""


class RemarkableImageError(RemarkableError):
    """The screenshot response was not a valid PNG image."""


@dataclass(frozen=True)
class PairingResult:
    address: str
    username: str
    certificate_sha256: str
    version: str
    frame_width: int
    frame_height: int


def normalize_address(address: str) -> str:
    value = address.strip().rstrip("/")
    if "://" not in value:
        value = f"https://{value}"
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Enter an HTTPS tablet address")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Enter the tablet address without a path")
    return f"https://{parsed.netloc}"


def _target(address: str) -> tuple[str, int]:
    parsed = urlsplit(normalize_address(address))
    return str(parsed.hostname), int(parsed.port or 443)


def probe_certificate(address: str, timeout: float = 5.0) -> str:
    """Return the server certificate SHA-256 fingerprint after a TLS handshake."""
    host, port = _target(address)
    context = ssl._create_unverified_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                certificate = tls.getpeercert(binary_form=True)
    except socket.timeout as exc:
        raise RemarkableSleepingError("The tablet may be asleep") from exc
    except ConnectionRefusedError as exc:
        raise RemarkableMissingServiceError("The Klaus tablet service is not running") from exc
    except OSError as exc:
        raise RemarkableNetworkError("Klaus cannot reach the tablet") from exc
    return hashlib.sha256(certificate).hexdigest()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, port: int, fingerprint: str, timeout: float):
        super().__init__(
            host,
            port,
            timeout=timeout,
            context=ssl._create_unverified_context(),
        )
        self._fingerprint = fingerprint.lower().replace(":", "")

    def connect(self) -> None:
        super().connect()
        certificate = self.sock.getpeercert(binary_form=True) if self.sock else b""
        actual = hashlib.sha256(certificate).hexdigest()
        if actual != self._fingerprint:
            self.close()
            raise RemarkableCertificateError(
                "The tablet certificate changed. Pair the tablet again."
            )


class RemarkableClient:
    """Authenticate and fetch current-screen PNGs from goMarkableStream."""

    def __init__(
        self,
        address: str,
        username: str,
        password: str,
        certificate_sha256: str,
        *,
        timeout: float = 5.0,
        retries: int = 1,
    ) -> None:
        self.address = normalize_address(address)
        self.username = username.strip()
        self._password = password
        self._fingerprint = certificate_sha256.strip().lower().replace(":", "")
        self._timeout = timeout
        self._retries = max(0, int(retries))
        self._token = ""
        self._token_lock = threading.Lock()

    def _check_cancelled(self, cancel_event: threading.Event | None) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise RemarkableCancelledError("The tablet request was cancelled")

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        self._check_cancelled(cancel_event)
        host, port = _target(self.address)
        for attempt in range(self._retries + 1):
            connection = _PinnedHTTPSConnection(host, port, self._fingerprint, self._timeout)
            try:
                connection.request(method, path, body=body, headers=headers or {})
                response = connection.getresponse()
                payload = response.read()
                self._check_cancelled(cancel_event)
                return response.status, dict(response.getheaders()), payload
            except RemarkableCertificateError:
                raise
            except socket.timeout as exc:
                if attempt >= self._retries:
                    raise RemarkableSleepingError("The tablet may be asleep") from exc
            except ConnectionRefusedError as exc:
                raise RemarkableMissingServiceError(
                    "The Klaus tablet service is not running"
                ) from exc
            except (OSError, http.client.HTTPException) as exc:
                if attempt >= self._retries:
                    raise RemarkableNetworkError("Klaus lost its connection to the tablet") from exc
            finally:
                connection.close()
        raise RemarkableNetworkError("Klaus lost its connection to the tablet")

    def login(self, cancel_event: threading.Event | None = None) -> None:
        body = json.dumps(
            {"username": self.username, "password": self._password}
        ).encode("utf-8")
        status, _, payload = self._request(
            "POST",
            "/login",
            body=body,
            headers={"Content-Type": "application/json"},
            cancel_event=cancel_event,
        )
        if status in {401, 403}:
            raise RemarkableAuthenticationError("The tablet username or password is invalid")
        if status != 200:
            raise RemarkableMissingServiceError(
                f"The Klaus tablet service returned HTTP {status}"
            )
        try:
            token = str(json.loads(payload)["token"]).strip()
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RemarkableMissingServiceError(
                "The Klaus tablet service returned an invalid login response"
            ) from exc
        if not token:
            raise RemarkableMissingServiceError(
                "The Klaus tablet service returned an empty login token"
            )
        with self._token_lock:
            self._token = token

    def _authenticated_request(
        self,
        path: str,
        cancel_event: threading.Event | None = None,
    ) -> bytes:
        with self._token_lock:
            token = self._token
        if not token:
            self.login(cancel_event)
            with self._token_lock:
                token = self._token
        status, _, payload = self._request(
            "GET",
            path,
            headers={"Authorization": f"Bearer {token}"},
            cancel_event=cancel_event,
        )
        if status in {401, 403}:
            self.login(cancel_event)
            with self._token_lock:
                token = self._token
            status, _, payload = self._request(
                "GET",
                path,
                headers={"Authorization": f"Bearer {token}"},
                cancel_event=cancel_event,
            )
        if status in {401, 403}:
            raise RemarkableAuthenticationError("The tablet username or password is invalid")
        if status != 200:
            raise RemarkableMissingServiceError(
                f"The Klaus tablet service returned HTTP {status}"
            )
        return payload

    def version(self, cancel_event: threading.Event | None = None) -> str:
        status, _, payload = self._request("GET", "/version", cancel_event=cancel_event)
        if status != 200:
            raise RemarkableMissingServiceError(
                f"The Klaus tablet service returned HTTP {status}"
            )
        return payload.decode("utf-8", errors="replace").strip()

    def screenshot_png(self, cancel_event: threading.Event | None = None) -> bytes:
        payload = self._authenticated_request("/screenshot", cancel_event)
        if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RemarkableImageError("The tablet returned an invalid screenshot")
        return payload

    def screenshot_frame(
        self,
        *,
        orientation: int = 0,
        cancel_event: threading.Event | None = None,
    ) -> np.ndarray:
        payload = self.screenshot_png(cancel_event)
        try:
            rgb = np.asarray(Image.open(BytesIO(payload)).convert("RGB"))
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise RemarkableImageError("The tablet returned a corrupt screenshot") from exc
        frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        rotations = {
            0: None,
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }
        if orientation not in rotations:
            raise ValueError("orientation must be 0, 90, 180, or 270")
        rotation = rotations[orientation]
        return cv2.rotate(frame, rotation) if rotation is not None else frame


def pair_tablet(
    address: str,
    username: str,
    password: str,
    *,
    timeout: float = 5.0,
) -> PairingResult:
    """Verify version, login, and screenshot decoding before saving settings."""
    normalized = normalize_address(address)
    fingerprint = probe_certificate(normalized, timeout)
    client = RemarkableClient(
        normalized,
        username,
        password,
        fingerprint,
        timeout=timeout,
    )
    version = client.version()
    frame = client.screenshot_frame()
    height, width = frame.shape[:2]
    return PairingResult(normalized, username.strip(), fingerprint, version, width, height)


class RemarkableReadingSource:
    """Expose Paper Pure screenshots through the Klaus reading-source contract."""

    def __init__(self, client: RemarkableClient, *, orientation: int = 0) -> None:
        self._client = client
        self._orientation = orientation
        self._waiting_message = "Waiting for the reMarkable Paper Pure"

    def start(self) -> None:
        self.capture_frame()

    def capture_frame(self) -> np.ndarray | None:
        try:
            frame = self._client.screenshot_frame(orientation=self._orientation)
        except RemarkableError as exc:
            self._waiting_message = str(exc)
            return None
        self._waiting_message = "Waiting for the reMarkable Paper Pure"
        return frame

    def capture_selected_text(self) -> None:
        return None

    @property
    def waiting_message(self) -> str:
        return self._waiting_message
