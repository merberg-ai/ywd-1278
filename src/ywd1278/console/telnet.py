"""Bounded loopback Telnet session layer for the 0E-P2 classic TNC console.

This module wraps the frozen 0E-P1 ``LocalTNCCommandShell`` without duplicating
or extending its command parser. 0E-P2 is deliberately loopback-only: the
listener accepts a literal IPv4 loopback bind address and refuses wildcard,
LAN, or public binds. Broader exposure requires a separately qualified
authentication/bind-address boundary.

The network layer is bounded by an explicit client limit, idle timeout, maximum
session lifetime, command count, receive chunk size, command-line size, and
Telnet negotiation count. It owns no modem/UART/KISS/TX/database-writer path.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import ipaddress
import socket
import socketserver
import threading
import time
from typing import Callable

from ywd1278.console.local import MAX_COMMAND_CHARS, LocalTNCCommandShell
from ywd1278.monitor.diagnostics import DiagnosticsStatus
from ywd1278.monitor.mheard import MHeardDatabase
from ywd1278.monitor.policy import MonitorPolicyState


DEFAULT_BIND_ADDRESS = "127.0.0.1"
DEFAULT_PORT = 8023
DEFAULT_MAX_CLIENTS = 4
DEFAULT_IDLE_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_SESSION_SECONDS = 3600.0
DEFAULT_MAX_COMMANDS = 1024
MAX_CLIENTS_LIMIT = 16
MAX_COMMANDS_LIMIT = 10000
MAX_TELNET_NEGOTIATIONS = 32
RECV_CHUNK_BYTES = 512
PROMPT_BYTES = b"cmd:"

_IAC = 255
_DONT = 254
_DO = 253
_WONT = 252
_WILL = 251
_SB = 250
_SE = 240
_NOP = 241
_AYT = 246
_NEGOTIATION_COMMANDS = {_DO, _DONT, _WILL, _WONT}


@dataclass(frozen=True)
class TelnetLineEvent:
    line: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class TelnetFeedResult:
    events: tuple[TelnetLineEvent, ...] = ()
    replies: bytes = b""
    fatal_error: str | None = None


class TelnetLineDecoder:
    """Small RFC-854-aware NVT line decoder with no optional Telnet features."""

    def __init__(self) -> None:
        self._line = bytearray()
        self._discard_oversize = False
        self._skip_lf = False
        self._state = "data"
        self._negotiation_command: int | None = None
        self._negotiations = 0
        self._fatal = False

    def feed(self, data: bytes) -> TelnetFeedResult:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        if self._fatal:
            return TelnetFeedResult(fatal_error="ERROR TELNET decoder already closed")

        events: list[TelnetLineEvent] = []
        replies = bytearray()

        for value in data:
            if self._state == "iac":
                if value in _NEGOTIATION_COMMANDS:
                    self._negotiation_command = value
                    self._state = "option"
                    continue
                self._state = "data"
                if value == _NOP:
                    continue
                if value == _AYT:
                    replies.extend(b"YWD-1278\r\n")
                    continue
                if value in (_SB, _SE, _IAC):
                    return self._fatal_result(
                        events,
                        replies,
                        "ERROR TELNET unsupported control sequence",
                    )
                return self._fatal_result(
                    events,
                    replies,
                    f"ERROR TELNET unsupported command {value}",
                )

            if self._state == "option":
                command = self._negotiation_command
                self._negotiation_command = None
                self._state = "data"
                assert command is not None
                self._negotiations += 1
                if self._negotiations > MAX_TELNET_NEGOTIATIONS:
                    return self._fatal_result(
                        events,
                        replies,
                        "ERROR TELNET negotiation limit exceeded",
                    )
                if command in (_DO, _DONT):
                    replies.extend((_IAC, _WONT, value))
                else:
                    replies.extend((_IAC, _DONT, value))
                continue

            if value == _IAC:
                self._skip_lf = False
                self._state = "iac"
                continue

            if self._skip_lf:
                self._skip_lf = False
                if value == 10:
                    continue

            if value == 13:
                self._finish_line(events)
                self._skip_lf = True
                continue
            if value == 10:
                self._finish_line(events)
                continue
            if value in (8, 127):
                if not self._discard_oversize and self._line:
                    self._line.pop()
                continue
            if value == 0:
                return self._fatal_result(
                    events,
                    replies,
                    "ERROR TELNET NUL data not permitted",
                )
            if value != 9 and not 32 <= value <= 126:
                return self._fatal_result(
                    events,
                    replies,
                    f"ERROR TELNET invalid NVT byte {value}",
                )

            if self._discard_oversize:
                continue
            if len(self._line) >= MAX_COMMAND_CHARS:
                self._line.clear()
                self._discard_oversize = True
                continue
            self._line.append(value)

        return TelnetFeedResult(tuple(events), bytes(replies), None)

    def _finish_line(self, events: list[TelnetLineEvent]) -> None:
        if self._discard_oversize:
            events.append(
                TelnetLineEvent(
                    error=f"ERROR COMMAND exceeds {MAX_COMMAND_CHARS} characters"
                )
            )
            self._discard_oversize = False
            self._line.clear()
            return
        events.append(TelnetLineEvent(line=self._line.decode("ascii")))
        self._line.clear()

    def _fatal_result(
        self,
        events: list[TelnetLineEvent],
        replies: bytearray,
        message: str,
    ) -> TelnetFeedResult:
        self._fatal = True
        return TelnetFeedResult(tuple(events), bytes(replies), message)


def _validate_loopback_bind(address: str) -> str:
    if not isinstance(address, str) or not address:
        raise ValueError("bind address must be a non-empty literal IPv4 address")
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ValueError("bind address must be a literal IPv4 loopback address") from exc
    if parsed.version != 4 or not parsed.is_loopback:
        raise ValueError("0E-P2 listener is restricted to IPv4 loopback addresses")
    return str(parsed)


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


class _TelnetTNCRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, TelnetTNCServer)
        sock = self.request
        assert isinstance(sock, socket.socket)

        shell = server.shell_factory()
        if not isinstance(shell, LocalTNCCommandShell):
            _send_line(sock, "ERROR SERVER invalid shell factory result")
            return

        version = shell.execute("VERSION")
        version_line = version.lines[0] if version.lines else "YWD-1278 UNKNOWN"
        if not _send_line(sock, f"{version_line} TELNET TNC CONSOLE"):
            return
        if not _send_line(
            sock,
            "0E-P2 loopback-only command mode; type HELP for commands.",
        ):
            return
        if not _send(sock, PROMPT_BYTES):
            return

        decoder = TelnetLineDecoder()
        pending: deque[TelnetLineEvent] = deque()
        started = time.monotonic()
        last_activity = started
        command_count = 0

        while True:
            while pending:
                event = pending.popleft()
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
            session_remaining = server.max_session_seconds - (now - started)
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

            decoded = decoder.feed(data)
            if decoded.replies and not _send(sock, decoded.replies):
                return
            pending.extend(decoded.events)
            if decoded.fatal_error is not None:
                _send_line(sock, decoded.fatal_error)
                _send_line(sock, "BYE")
                return


class TelnetTNCServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """Bounded IPv4-loopback threaded Telnet server for frozen P1 shells."""

    allow_reuse_address = True
    daemon_threads = True
    block_on_close = True
    address_family = socket.AF_INET
    request_queue_size = 8

    def __init__(
        self,
        server_address: tuple[str, int],
        *,
        shell_factory: Callable[[], LocalTNCCommandShell],
        max_clients: int = DEFAULT_MAX_CLIENTS,
        idle_timeout_seconds: float = DEFAULT_IDLE_TIMEOUT_SECONDS,
        max_session_seconds: float = DEFAULT_MAX_SESSION_SECONDS,
        max_commands: int = DEFAULT_MAX_COMMANDS,
    ) -> None:
        host, port = server_address
        host = _validate_loopback_bind(host)
        if type(port) is not int or not 0 <= port <= 65535:
            raise ValueError("port must be an integer in 0..65535")
        if not callable(shell_factory):
            raise TypeError("shell_factory must be callable")
        if type(max_clients) is not int or not 1 <= max_clients <= MAX_CLIENTS_LIMIT:
            raise ValueError(f"max_clients must be 1..{MAX_CLIENTS_LIMIT}")
        if type(max_commands) is not int or not 1 <= max_commands <= MAX_COMMANDS_LIMIT:
            raise ValueError(f"max_commands must be 1..{MAX_COMMANDS_LIMIT}")

        idle = _validate_positive_float(
            "idle_timeout_seconds", idle_timeout_seconds, maximum=3600.0
        )
        lifetime = _validate_positive_float(
            "max_session_seconds", max_session_seconds, maximum=86400.0
        )
        if lifetime < idle:
            raise ValueError("max_session_seconds must be >= idle_timeout_seconds")

        self.shell_factory = shell_factory
        self.max_clients = max_clients
        self.idle_timeout_seconds = idle
        self.max_session_seconds = lifetime
        self.max_commands = max_commands
        self._client_slots = threading.BoundedSemaphore(max_clients)
        super().__init__((host, port), _TelnetTNCRequestHandler)

    def verify_request(
        self,
        request: socket.socket,
        client_address: tuple[str, int],
    ) -> bool:
        del client_address
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
        prog="python -m ywd1278.console.telnet",
        description="YWD-1278 bounded loopback Telnet TNC command console",
    )
    parser.add_argument(
        "--bind",
        default=DEFAULT_BIND_ADDRESS,
        help="literal IPv4 loopback address only (default: 127.0.0.1)",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
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
    parser.add_argument(
        "--max-commands",
        type=int,
        default=DEFAULT_MAX_COMMANDS,
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
        server = TelnetTNCServer(
            (args.bind, args.port),
            shell_factory=_make_shell_factory(args.database),
            max_clients=args.max_clients,
            idle_timeout_seconds=args.idle_timeout,
            max_session_seconds=args.max_session,
            max_commands=args.max_commands,
        )
    except (TypeError, ValueError, OSError) as exc:
        parser.error(str(exc))

    host, port = server.server_address
    print(f"YWD-1278 0E-P2 Telnet console listening on {host}:{port}")
    print("Loopback-only host gate; no remote/LAN exposure is permitted in this phase.")
    try:
        with server:
            server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
