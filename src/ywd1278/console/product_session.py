"""Opt-in product terminal behavior for classic converse sessions.

The frozen 0E decoders remain authoritative and strict.  These wrappers add
only product-shell hooks: bounded live-output polling, command-prompt
suppression while converse mode is active, Ctrl-C/ETX translation while the
product shell is already in converse mode, and deterministic session cleanup.
Ordinary 0E shells expose none of these hooks and retain their historical
transport behavior.
"""

from __future__ import annotations

from collections import deque
import errno
import hmac
import os
import select
import socket
import socketserver
import time
from typing import Any

from ywd1278.console.auth import (
    MAX_PASSWORD_CHARS,
    MAX_USERNAME_CHARS,
    verify_password,
)
from ywd1278.console.lan_telnet import (
    AUTH_PASSWORD_PROMPT,
    AUTH_USERNAME_PROMPT,
    _BoundedLineReader,
    AuthenticatedLanTNCServer,
)
from ywd1278.console.local import CommandResult, LocalTNCCommandShell
from ywd1278.console.pty_serial import (
    PROMPT_BYTES as PTY_PROMPT_BYTES,
    READ_CHUNK_BYTES,
    SerialLineEvent,
    VirtualPTYTNC,
)
from ywd1278.console.telnet import (
    PROMPT_BYTES,
    RECV_CHUNK_BYTES,
    TelnetLineDecoder,
    TelnetLineEvent,
    TelnetTNCServer,
)


PRODUCT_SESSION_POLL_SECONDS = 0.1
MAX_LIVE_LINES_PER_POLL = 16


def _send(sock: socket.socket, payload: bytes) -> bool:
    try:
        sock.sendall(payload)
        return True
    except (BrokenPipeError, ConnectionResetError, OSError):
        return False


def _send_line(sock: socket.socket, line: str) -> bool:
    safe = line.replace("\r", "\\r").replace("\n", "\\n")
    return _send(sock, safe.encode("ascii", "replace") + b"\r\n")


def _prompt_enabled(shell: LocalTNCCommandShell) -> bool:
    value = getattr(shell, "session_prompt_enabled", True)
    return bool(value)


def _drain_shell(shell: LocalTNCCommandShell) -> tuple[str, ...]:
    drain = getattr(shell, "session_drain_output", None)
    if not callable(drain):
        return ()
    lines = drain(maximum=MAX_LIVE_LINES_PER_POLL)
    if not isinstance(lines, tuple) or any(not isinstance(line, str) for line in lines):
        raise TypeError("session_drain_output must return tuple[str, ...]")
    return lines


def _close_shell(shell: LocalTNCCommandShell) -> None:
    closer = getattr(shell, "session_close", None)
    if callable(closer):
        closer()


def _control_etx(shell: LocalTNCCommandShell) -> CommandResult | None:
    handler = getattr(shell, "session_control_etx", None)
    if not callable(handler):
        return None
    result = handler()
    if result is not None and not isinstance(result, CommandResult):
        raise TypeError("session_control_etx must return CommandResult or None")
    return result


def _serve_product_telnet_session(
    sock: socket.socket,
    server: Any,
    shell: LocalTNCCommandShell,
    *,
    decoder: TelnetLineDecoder | None = None,
    pending: deque[TelnetLineEvent] | None = None,
    started: float | None = None,
    last_activity: float | None = None,
) -> None:
    decoder = TelnetLineDecoder() if decoder is None else decoder
    pending = deque() if pending is None else pending
    started = time.monotonic() if started is None else started
    last_activity = started if last_activity is None else last_activity
    command_count = 0

    def emit_result(result: CommandResult, *, count_command: bool) -> bool:
        nonlocal command_count
        if count_command:
            command_count += 1
        for line in result.lines:
            if not _send_line(sock, line):
                return False
        if result.close:
            return False
        if command_count >= server.max_commands:
            _send_line(sock, "ERROR SESSION command limit reached")
            _send_line(sock, "BYE")
            return False
        if _prompt_enabled(shell):
            return _send(sock, PROMPT_BYTES)
        return True

    def process_pending() -> bool:
        while pending:
            event = pending.popleft()
            if event.error is not None:
                if not _send_line(sock, event.error):
                    return False
                if _prompt_enabled(shell) and not _send(sock, PROMPT_BYTES):
                    return False
                continue
            assert event.line is not None
            result = shell.execute(event.line)
            if not emit_result(result, count_command=bool(event.line.strip())):
                return False
        return True

    def feed_bytes(data: bytes) -> bool:
        decoded = decoder.feed(data)
        if decoded.replies and not _send(sock, decoded.replies):
            return False
        pending.extend(decoded.events)
        if not process_pending():
            return False
        if decoded.fatal_error is not None:
            _send_line(sock, decoded.fatal_error)
            _send_line(sock, "BYE")
            return False
        return True

    while True:
        if not process_pending():
            return

        try:
            live_lines = _drain_shell(shell)
        except Exception as exc:
            _send_line(
                sock,
                f"ERROR SESSION RX {type(exc).__name__}: {str(exc)[:120]}",
            )
            _send_line(sock, "BYE")
            return
        for line in live_lines:
            if not _send_line(sock, line):
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

        sock.settimeout(
            min(idle_remaining, session_remaining, PRODUCT_SESSION_POLL_SECONDS)
        )
        try:
            data = sock.recv(RECV_CHUNK_BYTES)
        except socket.timeout:
            continue
        except (ConnectionResetError, OSError):
            return
        if not data:
            return
        last_activity = time.monotonic()

        # ETX remains strict decoder input unless the product shell explicitly
        # accepts it while converse mode is active. Pieces are processed in
        # order so "CONVERSE\r\x03" in one recv enters then exits cleanly.
        pieces = data.split(b"\x03")
        for index, piece in enumerate(pieces):
            if piece and not feed_bytes(piece):
                return
            if index == len(pieces) - 1:
                continue
            try:
                etx_result = _control_etx(shell)
            except Exception as exc:
                _send_line(
                    sock,
                    f"ERROR SESSION CTRL-C {type(exc).__name__}: {str(exc)[:120]}",
                )
                _send_line(sock, "BYE")
                return
            if etx_result is None:
                if not feed_bytes(b"\x03"):
                    return
            elif not emit_result(etx_result, count_command=False):
                return


class _ProductTelnetRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, ProductTelnetTNCServer)
        sock = self.request
        assert isinstance(sock, socket.socket)

        shell = server.shell_factory()
        if not isinstance(shell, LocalTNCCommandShell):
            _send_line(sock, "ERROR SERVER invalid shell factory result")
            return
        try:
            version = shell.execute("VERSION")
            version_line = version.lines[0] if version.lines else "YWD-1278 UNKNOWN"
            if not _send_line(sock, f"{version_line} TELNET TNC CONSOLE"):
                return
            if not _send_line(
                sock,
                "YWD-1278 product command/converse mode; type HELP for commands.",
            ):
                return
            if not _send(sock, PROMPT_BYTES):
                return
            _serve_product_telnet_session(sock, server, shell)
        finally:
            _close_shell(shell)


class ProductTelnetTNCServer(TelnetTNCServer):
    """Frozen loopback listener policy with product-session request handling."""

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.RequestHandlerClass = _ProductTelnetRequestHandler


class _ProductAuthenticatedRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, ProductAuthenticatedLanTNCServer)
        sock = self.request
        assert isinstance(sock, socket.socket)

        if not _send_line(sock, "YWD-1278 AUTHENTICATED LAN TNC CONSOLE"):
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
            if not _send_line(
                sock,
                f"AUTH FAIL {attempt}/{server.max_auth_attempts}",
            ):
                return

        if not authenticated:
            _send_line(sock, "ERROR AUTH attempt limit reached")
            _send_line(sock, "BYE")
            return
        if not _send_line(sock, "AUTH OK"):
            return

        # Preserve the 0E-P3 security boundary: construct no command shell
        # until credentials have succeeded.
        shell = server.shell_factory()
        if not isinstance(shell, LocalTNCCommandShell):
            _send_line(sock, "ERROR SERVER invalid shell factory result")
            return
        try:
            version = shell.execute("VERSION")
            version_line = version.lines[0] if version.lines else "YWD-1278 UNKNOWN"
            if not _send_line(
                sock,
                f"{version_line} AUTHENTICATED LAN TNC CONSOLE",
            ):
                return
            if not _send_line(
                sock,
                "YWD-1278 product command/converse mode; type HELP for commands.",
            ):
                return
            if not _send(sock, PROMPT_BYTES):
                return
            _serve_product_telnet_session(
                sock,
                server,
                shell,
                decoder=reader.decoder,
                pending=reader.pending,
                last_activity=reader.last_activity,
            )
        finally:
            _close_shell(shell)


class ProductAuthenticatedLanTNCServer(AuthenticatedLanTNCServer):
    """Frozen private-LAN/auth policy with product-session request handling."""

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.RequestHandlerClass = _ProductAuthenticatedRequestHandler


class ProductVirtualPTYTNC(VirtualPTYTNC):
    """Frozen local PTY ownership with product converse session hooks."""

    def serve(self, stop_event=None) -> None:  # type: ignore[no-untyped-def]
        import threading

        if stop_event is not None and not isinstance(stop_event, threading.Event):
            raise TypeError("stop_event must be threading.Event or None")
        if not self._opened:
            self.open()

        assert self.master_fd is not None
        had_client_activity = False

        while stop_event is None or not stop_event.is_set():
            try:
                self._drain_live_output()
            except OSError as exc:
                if exc.errno == errno.EIO:
                    if had_client_activity:
                        self._reset_after_detach()
                        had_client_activity = False
                    time.sleep(self.poll_seconds)
                    continue
                raise

            try:
                readable, _, _ = select.select(
                    [self.master_fd], [], [], self.poll_seconds
                )
            except (OSError, ValueError):
                if self.master_fd is None:
                    return
                raise
            if not readable:
                continue

            try:
                data = os.read(self.master_fd, READ_CHUNK_BYTES)
            except OSError as exc:
                if exc.errno == errno.EIO:
                    if had_client_activity:
                        self._reset_after_detach()
                        had_client_activity = False
                    time.sleep(self.poll_seconds)
                    continue
                if exc.errno == errno.EBADF and self.master_fd is None:
                    return
                raise

            if not data:
                if had_client_activity:
                    self._reset_after_detach()
                    had_client_activity = False
                continue

            had_client_activity = True
            pieces = data.split(b"\x03")
            for index, piece in enumerate(pieces):
                if piece:
                    for event in self._decoder.feed(piece):
                        self._handle_event(event)
                if index == len(pieces) - 1:
                    continue
                assert self._shell is not None
                result = _control_etx(self._shell)
                if result is None:
                    for event in self._decoder.feed(b"\x03"):
                        self._handle_event(event)
                else:
                    self._handle_result(result, count_command=False)

    def _handle_event(self, event: SerialLineEvent) -> None:
        if event.error is not None:
            self._write_line(event.error)
            self._write_prompt_if_enabled()
            return

        assert event.line is not None
        assert self._shell is not None
        result = self._shell.execute(event.line)
        self._handle_result(result, count_command=bool(event.line.strip()))

    def _handle_result(self, result: CommandResult, *, count_command: bool) -> None:
        if count_command:
            self._command_count += 1
        for line in result.lines:
            self._write_line(line)
        if result.close:
            self._reset_session(write_banner=True)
            return
        if self._command_count >= self.max_commands:
            self._write_line("ERROR SESSION command limit reached")
            self._write_line("BYE")
            self._reset_session(write_banner=True)
            return
        self._write_prompt_if_enabled()

    def _write_prompt_if_enabled(self) -> None:
        assert self._shell is not None
        if _prompt_enabled(self._shell):
            self._write(PTY_PROMPT_BYTES)

    def _drain_live_output(self) -> None:
        shell = self._shell
        if shell is None:
            return
        try:
            lines = _drain_shell(shell)
        except Exception as exc:
            self._write_line(
                f"ERROR SESSION RX {type(exc).__name__}: {str(exc)[:120]}"
            )
            self._reset_session(write_banner=True)
            return
        for line in lines:
            self._write_line(line)

    def _reset_session(self, *, write_banner: bool) -> None:
        old_shell = self._shell
        if old_shell is not None:
            _close_shell(old_shell)
        super()._reset_session(write_banner=write_banner)

    def close(self) -> None:
        shell = self._shell
        if shell is not None:
            _close_shell(shell)
        super().close()


__all__ = [
    "MAX_LIVE_LINES_PER_POLL",
    "PRODUCT_SESSION_POLL_SECONDS",
    "ProductAuthenticatedLanTNCServer",
    "ProductTelnetTNCServer",
    "ProductVirtualPTYTNC",
]
