"""Authenticated private-LAN Telnet console for 0E-P3.

0E-P3 preserves the frozen 0E-P2 Telnet decoder and frozen 0E-P1 command
parser. It adds a separate authentication/bind boundary that may listen only on
literal IPv4 loopback or RFC1918 addresses. Non-loopback sessions must pass the
same mandatory authentication gate as loopback sessions before a P1 shell is
ever constructed.

Telnet provides no transport encryption. This phase is therefore private-LAN
only and must not be exposed through WAN forwarding, public interfaces, or
untrusted networks.
"""

from __future__ import annotations

import argparse
from collections import deque
import hmac
import ipaddress
import socket
import socketserver
import threading
import time
from typing import Callable

from ywd1278.console.auth import (
    CredentialRecord,
    MAX_PASSWORD_CHARS,
    MAX_USERNAME_CHARS,
    load_credential_file,
    verify_password,
)
from ywd1278.console.local import LocalTNCCommandShell
from ywd1278.console.telnet import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    DEFAULT_MAX_CLIENTS,
    DEFAULT_MAX_COMMANDS,
    DEFAULT_MAX_SESSION_SECONDS,
    DEFAULT_PORT,
    MAX_CLIENTS_LIMIT,
    MAX_COMMANDS_LIMIT,
    PROMPT_BYTES,
    RECV_CHUNK_BYTES,
    TelnetLineDecoder,
    TelnetLineEvent,
)
from ywd1278.monitor.diagnostics import DiagnosticsStatus
from ywd1278.monitor.mheard import MHeardDatabase
from ywd1278.monitor.policy import MonitorPolicyState


DEFAULT_BIND_ADDRESS = "127.0.0.1"
DEFAULT_AUTH_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_AUTH_ATTEMPTS = 3
MAX_AUTH_ATTEMPTS_LIMIT = 5
AUTH_USERNAME_PROMPT = b"Username:"
AUTH_PASSWORD_PROMPT = b"Password:"

_RFC1918_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


def _is_allowed_private_ipv4(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    if parsed.version != 4:
        return False
    return parsed.is_loopback or any(parsed in network for network in _RFC1918_NETWORKS)


def validate_lan_bind(address: str) -> str:
    if not isinstance(address, str) or not address:
        raise ValueError("bind address must be a non-empty literal IPv4 address")
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ValueError("bind address must be a literal IPv4 address") from exc
    if parsed.version != 4:
        raise ValueError("0E-P3 listener supports IPv4 only")
    normalized = str(parsed)
    if not _is_allowed_private_ipv4(normalized):
        raise ValueError("0E-P3 listener is restricted to loopback or RFC1918 IPv4 addresses")
    return normalized


def validate_client_address(address: str) -> bool:
    return _is_allowed_private_ipv4(address)


def _validate_positive_float(name: str, value: float, *, maximum: float) -> float:
    number = float(value)
    if not 0.0 < number <= maximum:
        raise ValueError(f"{name} must be > 0 and <= {maximum:g}")
    return number


def _send(sock: socket.socket, payload: bytes) -> bool:
    try:
        sock.sendall(payload)
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def _send_line(sock: socket.socket, line: str) -> bool:
    safe = line.replace("\r", "\\r").replace("\n", "\\n")
    return _send(sock, safe.encode("ascii", "replace") + b"\r\n")


class _BoundedLineReader:
    """Deadline-aware line reader using the frozen P2 Telnet decoder."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.decoder = TelnetLineDecoder()
        self.pending: deque[TelnetLineEvent] = deque()
        self.last_activity = time.monotonic()

    def read_line(self, *, deadline: float) -> tuple[str | None, str | None]:
        while True:
            while self.pending:
                event = self.pending.popleft()
                if event.error is not None:
                    return None, event.error
                assert event.line is not None
                return event.line, None

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, "ERROR AUTH timeout"
            self.sock.settimeout(remaining)
            try:
                data = self.sock.recv(RECV_CHUNK_BYTES)
            except socket.timeout:
                return None, "ERROR AUTH timeout"
            except (ConnectionResetError, OSError):
                return None, "ERROR CONNECTION closed"
            if not data:
                return None, "ERROR CONNECTION closed"
            self.last_activity = time.monotonic()

            decoded = self.decoder.feed(data)
            if decoded.replies and not _send(self.sock, decoded.replies):
                return None, "ERROR CONNECTION closed"
            self.pending.extend(decoded.events)
            if decoded.fatal_error is not None:
                return None, decoded.fatal_error


class _AuthenticatedTNCRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, AuthenticatedLanTNCServer)
        sock = self.request
        assert isinstance(sock, socket.socket)

        if not _send_line(sock, "YWD-1278 0E-P3 AUTHENTICATED LAN TNC CONSOLE"):
            return
        if not _send_line(sock, "Private-LAN Telnet; transport is NOT encrypted."):
            return

        reader = _BoundedLineReader(sock)
        auth_deadline = time.monotonic() + server.auth_timeout_seconds
        authenticated = False

        for attempt in range(1, server.max_auth_attempts + 1):
            if not _send(sock, AUTH_USERNAME_PROMPT):
                return
            username, error = reader.read_line(deadline=auth_deadline)
            if error is not None:
                _send_line(sock, error)
                _send_line(sock, "BYE")
                return
            assert username is not None
            if len(username) > MAX_USERNAME_CHARS:
                username = ""

            if not _send(sock, AUTH_PASSWORD_PROMPT):
                return
            password, error = reader.read_line(deadline=auth_deadline)
            if error is not None:
                _send_line(sock, error)
                _send_line(sock, "BYE")
                return
            assert password is not None
            if len(password) > MAX_PASSWORD_CHARS:
                password = ""

            username_ok = hmac.compare_digest(
                username.encode("ascii", "ignore"),
                server.credential.username.encode("ascii"),
            )
            password_ok = verify_password(password, server.credential.password_hash)
            password = ""

            if username_ok and password_ok:
                authenticated = True
                break
            if not _send_line(sock, f"AUTH FAIL {attempt}/{server.max_auth_attempts}"):
                return

        if not authenticated:
            _send_line(sock, "ERROR AUTH attempt limit reached")
            _send_line(sock, "BYE")
            return

        if not _send_line(sock, "AUTH OK"):
            return

        # Important security boundary: no P1 shell exists before authentication.
        shell = server.shell_factory()
        if not isinstance(shell, LocalTNCCommandShell):
            _send_line(sock, "ERROR SERVER invalid shell factory result")
            return

        version = shell.execute("VERSION")
        version_line = version.lines[0] if version.lines else "YWD-1278 UNKNOWN"
        if not _send_line(sock, f"{version_line} AUTHENTICATED LAN TNC CONSOLE"):
            return
        if not _send_line(sock, "0E-P3 private-LAN command mode; type HELP for commands."):
            return
        if not _send(sock, PROMPT_BYTES):
            return

        session_started = time.monotonic()
        last_activity = reader.last_activity
        command_count = 0

        while True:
            while reader.pending:
                event = reader.pending.popleft()
                if event.error is not None:
                    if not _send_line(sock, event.error):
                        return
                else:
                    assert event.line is not None
                    result = shell.execute(event.line)
                    if event.line.strip():
                        command_count += 1
                    for line in result.lines:
                        if not _send_line(sock, line):
                            return
                    if result.close:
                        return
                    if command_count >= server.max_commands:
                        _send_line(sock, "ERROR SESSION command limit reached")
                        _send_line(sock, "BYE")
                        return
                if not _send(sock, PROMPT_BYTES):
                    return

            now = time.monotonic()
            idle_remaining = server.idle_timeout_seconds - (now - last_activity)
            session_remaining = server.max_session_seconds - (now - session_started)
            if idle_remaining <= 0:
                _send_line(sock, "ERROR SESSION idle timeout")
                _send_line(sock, "BYE")
                return
            if session_remaining <= 0:
                _send_line(sock, "ERROR SESSION lifetime limit reached")
                _send_line(sock, "BYE")
                return

            sock.settimeout(min(idle_remaining, session_remaining))
            try:
                data = sock.recv(RECV_CHUNK_BYTES)
            except socket.timeout:
                continue
            except (ConnectionResetError, OSError):
                return
            if not data:
                return
            last_activity = time.monotonic()

            decoded = reader.decoder.feed(data)
            if decoded.replies and not _send(sock, decoded.replies):
                return
            reader.pending.extend(decoded.events)
            if decoded.fatal_error is not None:
                _send_line(sock, decoded.fatal_error)
                _send_line(sock, "BYE")
                return


class AuthenticatedLanTNCServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Bounded authenticated Telnet server for loopback/RFC1918 IPv4 only."""

    allow_reuse_address = True
    daemon_threads = True
    block_on_close = True
    address_family = socket.AF_INET
    request_queue_size = 8

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        credential: CredentialRecord,
        shell_factory: Callable[[], LocalTNCCommandShell],
        max_clients: int = DEFAULT_MAX_CLIENTS,
        idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT_SECONDS,
        max_session_seconds: float = DEFAULT_MAX_SESSION_SECONDS,
        max_commands: int = DEFAULT_MAX_COMMANDS,
        auth_timeout_seconds: float = DEFAULT_AUTH_TIMEOUT_SECONDS,
        max_auth_attempts: int = DEFAULT_MAX_AUTH_ATTEMPTS,
    ) -> None:
        host, port = server_address
        host = validate_lan_bind(host)
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("port must be an integer in 0..65535")
        if not isinstance(credential, CredentialRecord):
            raise TypeError("credential must be a CredentialRecord")
        if not callable(shell_factory):
            raise TypeError("shell_factory must be callable")
        if type(max_clients) is not int or not 1 <= max_clients <= MAX_CLIENTS_LIMIT:
            raise ValueError(f"max_clients must be 1..{MAX_CLIENTS_LIMIT}")
        if type(max_commands) is not int or not 1 <= max_commands <= MAX_COMMANDS_LIMIT:
            raise ValueError(f"max_commands must be 1..{MAX_COMMANDS_LIMIT}")
        if type(max_auth_attempts) is not int or not 1 <= max_auth_attempts <= MAX_AUTH_ATTEMPTS_LIMIT:
            raise ValueError(f"max_auth_attempts must be 1..{MAX_AUTH_ATTEMPTS_LIMIT}")

        idle = _validate_positive_float(
            "idle_timeout_seconds", idle_timeout_seconds, maximum=3600.0
        )
        lifetime = _validate_positive_float(
            "max_session_seconds", max_session_seconds, maximum=86400.0
        )
        auth_timeout = _validate_positive_float(
            "auth_timeout_seconds", auth_timeout_seconds, maximum=300.0
        )
        if lifetime < idle:
            raise ValueError("max_session_seconds must be >= idle_timeout_seconds")

        self.credential = credential
        self.shell_factory = shell_factory
        self.max_clients = max_clients
        self.idle_timeout_seconds = idle
        self.max_session_seconds = lifetime
        self.max_commands = max_commands
        self.auth_timeout_seconds = auth_timeout
        self.max_auth_attempts = max_auth_attempts
        self._client_slots = threading.BoundedSemaphore(max_clients)
        super().__init__((host, port), _AuthenticatedTNCRequestHandler)

    def verify_request(
        self,
        request: socket.socket,
        client_address: tuple[str, int],
    ) -> bool:
        client_host, _client_port = client_address
        if not validate_client_address(client_host):
            _send_line(request, "ERROR ACCESS private IPv4 clients only")
            return False
        if self._client_slots.acquire(blocking=False):
            return True
        _send_line(request, "BUSY maximum Telnet clients reached")
        return False

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        try:
            super().process_request(request, client_address)
        except Exception:
            self._client_slots.release()
            raise

    def process_request_thread(
        self,
        request: socket.socket,
        client_address: tuple[str, int],
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._client_slots.release()


def _make_shell_factory(database_path: str | None) -> Callable[[], LocalTNCCommandShell]:
    def factory() -> LocalTNCCommandShell:
        mheard = MHeardDatabase(database_path) if database_path else None
        diagnostics = DiagnosticsStatus(mheard_db=mheard) if mheard is not None else None
        return LocalTNCCommandShell(
            diagnostics=diagnostics,
            monitor_policy=MonitorPolicyState(),
            mheard_db=mheard,
        )

    return factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m ywd1278.console.lan_telnet",
        description="YWD-1278 authenticated private-LAN Telnet TNC command console",
    )
    parser.add_argument(
        "--bind",
        default=DEFAULT_BIND_ADDRESS,
        help="literal IPv4 loopback or RFC1918 address (default: 127.0.0.1)",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--auth-file", required=True, metavar="PATH")
    parser.add_argument("--max-clients", type=int, default=DEFAULT_MAX_CLIENTS)
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=DEFAULT_IDLE_TIMEOUT_SECONDS,
        metavar="SECONDS",
    )
    parser.add_argument(
        "--max-session",
        type=float,
        default=DEFAULT_MAX_SESSION_SECONDS,
        metavar="SECONDS",
    )
    parser.add_argument("--max-commands", type=int, default=DEFAULT_MAX_COMMANDS)
    parser.add_argument(
        "--auth-timeout",
        type=float,
        default=DEFAULT_AUTH_TIMEOUT_SECONDS,
        metavar="SECONDS",
    )
    parser.add_argument(
        "--max-auth-attempts",
        type=int,
        default=DEFAULT_MAX_AUTH_ATTEMPTS,
    )
    parser.add_argument(
        "--database",
        metavar="PATH",
        help="optional qualified 0D-P3 SQLite frame log for read-only MHEARD/status",
    )
    args = parser.parse_args(argv)

    if not 1 <= args.port <= 65535:
        parser.error("--port must be 1..65535")

    try:
        credential = load_credential_file(args.auth_file)
        server = AuthenticatedLanTNCServer(
            (args.bind, args.port),
            credential=credential,
            shell_factory=_make_shell_factory(args.database),
            max_clients=args.max_clients,
            idle_timeout_seconds=args.idle_timeout,
            max_session_seconds=args.max_session,
            max_commands=args.max_commands,
            auth_timeout_seconds=args.auth_timeout,
            max_auth_attempts=args.max_auth_attempts,
        )
    except (TypeError, ValueError, OSError) as exc:
        parser.error(str(exc))

    host, port = server.server_address
    print(f"YWD-1278 0E-P3 authenticated Telnet console listening on {host}:{port}")
    print("Private-LAN only. Telnet is plaintext: do not expose this listener to WAN/public networks.")
    try:
        with server:
            server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
