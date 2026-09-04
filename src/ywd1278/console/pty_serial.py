"""Local virtual PTY/serial personality for the 0E-P4 classic TNC console.

0E-P4 exposes the frozen 0E-P1 ``LocalTNCCommandShell`` through a kernel
pseudo-terminal slave.  The PTY is a local virtual terminal only: this module
never opens a hardware serial device, modem owner, KISS session, network
listener, database writer, GPIO, or RF/TX path.

The slave PTY is placed in raw mode and chmod 0600.  An optional stable symlink
may be created at an explicit absolute path; existing filesystem objects are
never replaced.  The symlink is removed on clean shutdown only when it still
points to this process's PTY.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import errno
import os
import select
import signal
import termios
import threading
import time
import tty
from typing import Callable

from ywd1278.console.local import MAX_COMMAND_CHARS, LocalTNCCommandShell
from ywd1278.monitor.diagnostics import DiagnosticsStatus
from ywd1278.monitor.mheard import MHeardDatabase
from ywd1278.monitor.policy import MonitorPolicyState


PTY_MODE = 0o600
READ_CHUNK_BYTES = 512
DEFAULT_MAX_COMMANDS = 1024
MAX_COMMANDS_LIMIT = 10000
DEFAULT_POLL_SECONDS = 0.05
MAX_POLL_SECONDS = 1.0
PROMPT_BYTES = b"cmd:"


@dataclass(frozen=True)
class SerialLineEvent:
    line: str | None = None
    error: str | None = None


class SerialLineDecoder:
    """Bounded ASCII line decoder for a raw local pseudo-serial byte stream."""

    def __init__(self) -> None:
        self._line = bytearray()
        self._line_error: str | None = None
        self._skip_lf = False

    def feed(self, data: bytes) -> tuple[SerialLineEvent, ...]:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")

        events: list[SerialLineEvent] = []
        for value in data:
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

            if self._line_error is not None:
                continue

            if value in (8, 127):
                if self._line:
                    self._line.pop()
                continue

            if value == 0:
                self._line.clear()
                self._line_error = "ERROR SERIAL NUL data not permitted"
                continue
            if value != 9 and not 32 <= value <= 126:
                self._line.clear()
                self._line_error = f"ERROR SERIAL invalid byte {value}"
                continue

            if len(self._line) >= MAX_COMMAND_CHARS:
                self._line.clear()
                self._line_error = (
                    f"ERROR COMMAND exceeds {MAX_COMMAND_CHARS} characters"
                )
                continue
            self._line.append(value)

        return tuple(events)

    def _finish_line(self, events: list[SerialLineEvent]) -> None:
        if self._line_error is not None:
            events.append(SerialLineEvent(error=self._line_error))
            self._line_error = None
            self._line.clear()
            return
        events.append(SerialLineEvent(line=self._line.decode("ascii")))
        self._line.clear()


def _validate_link_path(path: str | None) -> str | None:
    if path is None:
        return None
    if not isinstance(path, str) or not path:
        raise ValueError("link path must be a non-empty absolute path")
    if not os.path.isabs(path):
        raise ValueError("link path must be absolute")
    normalized = os.path.normpath(path)
    if normalized == "/":
        raise ValueError("link path must name a filesystem entry")
    parent = os.path.dirname(normalized)
    if not os.path.isdir(parent):
        raise ValueError("link parent directory must already exist")
    return normalized


def _validate_max_commands(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_COMMANDS_LIMIT:
        raise ValueError(f"max_commands must be 1..{MAX_COMMANDS_LIMIT}")
    return value


def _validate_poll_seconds(value: float) -> float:
    number = float(value)
    if not 0.0 < number <= MAX_POLL_SECONDS:
        raise ValueError(f"poll_seconds must be > 0 and <= {MAX_POLL_SECONDS:g}")
    return number


class VirtualPTYTNC:
    """Own one local PTY master and serve frozen P1 command shells on its slave."""

    def __init__(
        self,
        *,
        shell_factory: Callable[[], LocalTNCCommandShell],
        link_path: str | None = None,
        max_commands: int = DEFAULT_MAX_COMMANDS,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
    ) -> None:
        if not callable(shell_factory):
            raise TypeError("shell_factory must be callable")
        self.shell_factory = shell_factory
        self.link_path = _validate_link_path(link_path)
        self.max_commands = _validate_max_commands(max_commands)
        self.poll_seconds = _validate_poll_seconds(poll_seconds)

        self.master_fd: int | None = None
        self.slave_path: str | None = None
        self._shell: LocalTNCCommandShell | None = None
        self._decoder = SerialLineDecoder()
        self._command_count = 0
        self._opened = False

    def open(self) -> str:
        if self._opened:
            assert self.slave_path is not None
            return self.slave_path

        if self.link_path is not None and os.path.lexists(self.link_path):
            raise FileExistsError(f"refusing to replace existing link path: {self.link_path}")

        master_fd: int | None = None
        slave_fd: int | None = None
        link_created = False
        try:
            master_fd, slave_fd = os.openpty()
            slave_path = os.ttyname(slave_fd)
            tty.setraw(slave_fd, when=termios.TCSANOW)
            os.chmod(slave_path, PTY_MODE)

            shell = self.shell_factory()
            if not isinstance(shell, LocalTNCCommandShell):
                raise TypeError("shell_factory must return LocalTNCCommandShell")

            if self.link_path is not None:
                os.symlink(slave_path, self.link_path)
                link_created = True

            self.master_fd = master_fd
            self.slave_path = slave_path
            self._shell = shell
            self._decoder = SerialLineDecoder()
            self._command_count = 0
            self._opened = True
            self._write_banner()

            os.close(slave_fd)
            slave_fd = None
            return slave_path
        except Exception:
            if link_created and self.link_path is not None:
                try:
                    if os.path.islink(self.link_path):
                        os.unlink(self.link_path)
                except OSError:
                    pass
            if slave_fd is not None:
                try:
                    os.close(slave_fd)
                except OSError:
                    pass
            if master_fd is not None:
                try:
                    os.close(master_fd)
                except OSError:
                    pass
            self.master_fd = None
            self.slave_path = None
            self._shell = None
            self._opened = False
            raise

    def serve(self, stop_event: threading.Event | None = None) -> None:
        if stop_event is not None and not isinstance(stop_event, threading.Event):
            raise TypeError("stop_event must be threading.Event or None")
        if not self._opened:
            self.open()

        assert self.master_fd is not None
        had_client_activity = False

        while stop_event is None or not stop_event.is_set():
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
            for event in self._decoder.feed(data):
                self._handle_event(event)

    def close(self) -> None:
        master_fd = self.master_fd
        self.master_fd = None
        self._opened = False

        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass

        if self.link_path is not None and self.slave_path is not None:
            try:
                if os.path.islink(self.link_path):
                    target = os.readlink(self.link_path)
                    if target == self.slave_path:
                        os.unlink(self.link_path)
            except OSError:
                pass

        self.slave_path = None
        self._shell = None
        self._decoder = SerialLineDecoder()
        self._command_count = 0

    def _handle_event(self, event: SerialLineEvent) -> None:
        if event.error is not None:
            self._write_line(event.error)
            self._write(PROMPT_BYTES)
            return

        assert event.line is not None
        assert self._shell is not None
        result = self._shell.execute(event.line)
        if event.line.strip():
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

        self._write(PROMPT_BYTES)

    def _reset_after_detach(self) -> None:
        if self.master_fd is not None:
            try:
                termios.tcflush(self.master_fd, termios.TCIOFLUSH)
            except (OSError, termios.error):
                pass
        self._reset_session(write_banner=True)

    def _reset_session(self, *, write_banner: bool) -> None:
        shell = self.shell_factory()
        if not isinstance(shell, LocalTNCCommandShell):
            raise TypeError("shell_factory must return LocalTNCCommandShell")
        self._shell = shell
        self._decoder = SerialLineDecoder()
        self._command_count = 0
        if write_banner:
            self._write_banner()

    def _write_banner(self) -> None:
        assert self._shell is not None
        version = self._shell.execute("VERSION")
        version_line = version.lines[0] if version.lines else "YWD-1278 UNKNOWN"
        self._write_line(f"{version_line} VIRTUAL PTY TNC CONSOLE")
        self._write_line(
            "0E-P4 local pseudo-serial command mode; type HELP for commands."
        )
        self._write(PROMPT_BYTES)

    def _write_line(self, line: str) -> None:
        safe = line.replace("\r", "\\r").replace("\n", "\\n")
        self._write(safe.encode("ascii", "replace") + b"\r\n")

    def _write(self, payload: bytes) -> None:
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        if self.master_fd is None:
            raise RuntimeError("PTY is not open")
        view = memoryview(payload)
        while view:
            written = os.write(self.master_fd, view)
            if written <= 0:
                raise OSError("short PTY write")
            view = view[written:]

    def __enter__(self) -> "VirtualPTYTNC":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m ywd1278.console.pty_serial",
        description="YWD-1278 local virtual PTY classic TNC console",
    )
    parser.add_argument(
        "--database",
        metavar="PATH",
        help="optional qualified 0D-P3 SQLite frame log for read-only MHEARD/status",
    )
    parser.add_argument(
        "--link",
        metavar="ABSOLUTE_PATH",
        help="optional stable symlink to the generated /dev/pts/N slave",
    )
    parser.add_argument(
        "--max-commands",
        type=int,
        default=DEFAULT_MAX_COMMANDS,
        help=f"commands per logical serial session (1..{MAX_COMMANDS_LIMIT})",
    )
    args = parser.parse_args(argv)

    mheard = None
    diagnostics = None
    if args.database:
        mheard = MHeardDatabase(args.database)
        diagnostics = DiagnosticsStatus(mheard_db=mheard)

    def shell_factory() -> LocalTNCCommandShell:
        return LocalTNCCommandShell(
            diagnostics=diagnostics,
            monitor_policy=MonitorPolicyState(),
            mheard_db=mheard,
        )

    server = VirtualPTYTNC(
        shell_factory=shell_factory,
        link_path=args.link,
        max_commands=args.max_commands,
    )
    stop_event = threading.Event()

    def _request_stop(_signum, _frame) -> None:
        stop_event.set()

    previous_sigint = signal.signal(signal.SIGINT, _request_stop)
    previous_sigterm = signal.signal(signal.SIGTERM, _request_stop)
    try:
        slave_path = server.open()
        print(f"YWD1278_0E_P4_SLAVE_PTY={slave_path}", flush=True)
        if server.link_path is not None:
            print(f"YWD1278_0E_P4_STABLE_LINK={server.link_path}", flush=True)
        server.serve(stop_event)
    finally:
        server.close()
        signal.signal(signal.SIGINT, previous_sigint)
        signal.signal(signal.SIGTERM, previous_sigterm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
