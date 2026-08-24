"""Local HTTPS integration tests for the Paper Pure screenshot client."""

from __future__ import annotations

import datetime
import hashlib
import json
import ssl
import socket
import threading
from unittest.mock import MagicMock, patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

import numpy as np
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from PIL import Image

from klaus.remarkable_reading_source import (
    RemarkableAuthenticationError,
    RemarkableCancelledError,
    RemarkableCertificateError,
    RemarkableClient,
    RemarkableMissingServiceError,
    RemarkableNetworkError,
    RemarkableSleepingError,
    pair_tablet,
    probe_certificate,
)
import klaus.remarkable_reading_source as remarkable_module


def _certificate(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), False)
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    fingerprint = hashlib.sha256(certificate.public_bytes(serialization.Encoding.DER)).hexdigest()
    return cert_path, key_path, fingerprint


@pytest.fixture
def remarkable_server(tmp_path):
    cert_path, key_path, fingerprint = _certificate(tmp_path)
    image = Image.new("RGB", (3, 2), (25, 50, 75))
    png = BytesIO()
    image.save(png, "PNG")
    state = {"login_count": 0, "expire_once": False, "orientation": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def do_POST(self):
            if self.path != "/login":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", "0"))
            credentials = json.loads(self.rfile.read(length))
            if credentials != {"username": "klaus", "password": "pair-secret"}:
                self.send_error(401)
                return
            state["login_count"] += 1
            payload = json.dumps({"token": f"token-{state['login_count']}", "expiresIn": 300}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            if self.path == "/version":
                payload = b"klaus-paper-pure-test"
            elif self.path == "/screenshot":
                if state["expire_once"]:
                    state["expire_once"] = False
                    self.send_error(401)
                    return
                expected = f"Bearer token-{state['login_count']}"
                if self.headers.get("Authorization") != expected:
                    self.send_error(401)
                    return
                payload = png.getvalue()
            else:
                self.send_error(404)
                return
            self.send_response(200)
            if self.path == "/screenshot":
                self.send_header(
                    "X-Remarkable-Orientation", str(state["orientation"])
                )
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"https://127.0.0.1:{server.server_port}", fingerprint, state
    finally:
        server.shutdown()
        thread.join(timeout=2)


def _client(server, *, password="pair-secret", fingerprint=None):
    address, actual_fingerprint, _state = server
    return RemarkableClient(
        address,
        "klaus",
        password,
        fingerprint or actual_fingerprint,
        timeout=1,
    )


def test_pairing_checks_version_authentication_and_png(remarkable_server):
    address, fingerprint, _state = remarkable_server
    result = pair_tablet(address, "klaus", "pair-secret", timeout=1)
    assert result.certificate_sha256 == fingerprint
    assert result.version == "klaus-paper-pure-test"
    assert (result.frame_width, result.frame_height) == (3, 2)


def test_invalid_credentials_are_distinct(remarkable_server):
    with pytest.raises(RemarkableAuthenticationError):
        _client(remarkable_server, password="wrong").screenshot_png()


def test_expired_token_is_renewed(remarkable_server):
    client = _client(remarkable_server)
    client.login()
    remarkable_server[2]["expire_once"] = True
    assert client.screenshot_png().startswith(b"\x89PNG")
    assert remarkable_server[2]["login_count"] == 2


def test_png_decoding_and_orientation(remarkable_server):
    client = _client(remarkable_server)
    original = client.screenshot_frame()
    rotated = client.screenshot_frame(orientation=90)
    assert original.shape == (2, 3, 3)
    assert rotated.shape == (3, 2, 3)
    assert np.array_equal(rotated, np.rot90(original, k=3))


def test_png_uses_tablet_orientation_header(remarkable_server):
    client = _client(remarkable_server)
    original = client.screenshot_frame()
    remarkable_server[2]["orientation"] = 180
    rotated = client.screenshot_frame()
    assert np.array_equal(rotated, np.rot90(original, k=2))


def test_certificate_change_requires_repairing(remarkable_server):
    with pytest.raises(RemarkableCertificateError):
        _client(remarkable_server, fingerprint="0" * 64).version()


def test_cancelled_request_does_not_connect(remarkable_server):
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(RemarkableCancelledError):
        _client(remarkable_server).screenshot_png(cancelled)


def test_transient_network_failure_retries_once():
    response = MagicMock()
    response.status = 200
    response.read.return_value = b"version"
    response.getheaders.return_value = []
    first = MagicMock()
    first.request.side_effect = OSError("temporary loss")
    second = MagicMock()
    second.getresponse.return_value = response
    with patch.object(
        remarkable_module,
        "_PinnedHTTPSConnection",
        side_effect=[first, second],
    ) as connection_class:
        client = RemarkableClient(
            "https://tablet.local:2001",
            "klaus",
            "secret",
            "a" * 64,
            retries=1,
        )
        assert client.version() == "version"
    assert connection_class.call_count == 2


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (socket.timeout(), RemarkableSleepingError),
        (ConnectionRefusedError(), RemarkableMissingServiceError),
        (OSError("network down"), RemarkableNetworkError),
    ],
)
def test_connection_failures_have_distinct_messages(failure, expected):
    with patch("klaus.remarkable_reading_source.socket.create_connection", side_effect=failure):
        with pytest.raises(expected):
            probe_certificate("https://tablet.local:2001", timeout=0.01)
