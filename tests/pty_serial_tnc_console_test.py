#!/usr/bin/env python3
"""Regression tests for the 0E-P4 local virtual PTY TNC personality."""

from __future__ import annotations

import os
from pathlib import Path
import select
import stat
import tempfile
import threading
import time
import unittest

from ywd1278.console.local import LocalTNCCommandShell
from ywd1278.console.pty_serial import (
    MAX_COMMANDS_LIMIT,
    PTY_MODE,
    SerialLineDecoder,
    VirtualPTYTNC,
    _validate_link_path,
)
from ywd1278.monitor.policy import MonitorPolicyState


def _shell() -> LocalTNCCommandShell:
    return LocalTNCCommandShell(monitor_policy=MonitorPolicyState())


def _read_until(fd: int, needle: bytes, *, timeout: float = 2.0) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while needle not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(
                f"timed out waiting for {needle!r}; received {bytes(data)!r}"
            )
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            continue
        try:
            chunk = os.read(fd, 4096)
        except BlockingIOError:
            continue
        if not chunk:
            continue
        data.extend(chunk)
    return bytes(data)


class RunningPTY:
    def __init__(self, **kwargs) -> None:
        self.server = VirtualPTYTNC(shell_factory=_shell, poll_seconds=0.01, **kwargs)
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "RunningPTY":
        self.server.open()
        self.thread = threading.Thread(
            target=self.server.serve,
            args=(self.stop,),
            name="p4-virtual-pty-test",
            daemon=True,
        )
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        self.server.close()

    def open_client(self) -> int:
        assert self.server.slave_path is not None
        return os.open(
            self.server.slave_path,
            os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK,
        )


class SerialLineDecoderTests(unittest.TestCase):
    def test_cr_lf_crlf_backspace_and_tab(self) -> None:
        decoder = SerialLineDecoder()
        events = decoder.feed(b"VERSIOX\bN\rMCOM\nMR\x7fRPT\r\nA\tB\r")
        self.assertEqual(
            [event.line for event in events],
            ["VERSION", "MCOM", "MRPT", "A\tB"],
        )
        self.assertTrue(all(event.error is None for event in events))

    def test_invalid_control_and_nul_fail_closed_per_line(self) -> None:
        decoder = SerialLineDecoder()
        events = decoder.feed(b"VER\x01SION\rM\x00COM\rVERSION\r")
        self.assertEqual(events[0].error, "ERROR SERIAL invalid byte 1")
        self.assertEqual(events[1].error, "ERROR SERIAL NUL data not permitted")
        self.assertEqual(events[2].line, "VERSION")

    def test_oversize_line_is_discarded(self) -> None:
        decoder = SerialLineDecoder()
        events = decoder.feed((b"A" * 257) + b"\rVERSION\r")
        self.assertIn("exceeds 256 characters", events[0].error or "")
        self.assertEqual(events[1].line, "VERSION")


class VirtualPTYTests(unittest.TestCase):
    def test_link_validation_is_absolute_and_parent_must_exist(self) -> None:
        with self.assertRaises(ValueError):
            _validate_link_path("relative/tnc")
        with self.assertRaises(ValueError):
            _validate_link_path("/definitely/not/a/ywd1278-parent/tnc")

    def test_slave_is_local_tty_mode_0600_and_link_is_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            link = str(Path(tmp) / "ywd1278-tnc")
            server = VirtualPTYTNC(shell_factory=_shell, link_path=link)
            try:
                slave = server.open()
                self.assertTrue(slave.startswith("/dev/pts/"))
                self.assertTrue(os.path.exists(slave))
                self.assertTrue(os.path.islink(link))
                self.assertEqual(os.readlink(link), slave)
                mode = stat.S_IMODE(os.stat(slave).st_mode)
                self.assertEqual(mode, PTY_MODE)
                client = os.open(slave, os.O_RDWR | os.O_NOCTTY)
                try:
                    self.assertTrue(os.isatty(client))
                finally:
                    os.close(client)
            finally:
                server.close()
            self.assertFalse(os.path.lexists(link))

    def test_existing_link_path_is_never_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            link = Path(tmp) / "ywd1278-tnc"
            link.write_text("do not replace", encoding="utf-8")
            server = VirtualPTYTNC(shell_factory=_shell, link_path=str(link))
            with self.assertRaises(FileExistsError):
                server.open()
            self.assertEqual(link.read_text(encoding="utf-8"), "do not replace")

    def test_live_pty_reuses_frozen_p1_and_future_tx_commands_stay_unknown(self) -> None:
        with RunningPTY() as running:
            fd = running.open_client()
            try:
                banner = _read_until(fd, b"cmd:")
                self.assertIn(b"VIRTUAL PTY TNC CONSOLE", banner)
                self.assertIn(b"0E-P4 local pseudo-serial", banner)

                os.write(fd, b"VERSION\r")
                reply = _read_until(fd, b"cmd:")
                self.assertIn(b"YWD-1278 0.1.0-alpha0", reply)

                os.write(fd, b"MCOM\r")
                self.assertIn(b"MCOM OFF", _read_until(fd, b"cmd:"))

                os.write(fd, b"MCOM ON\r")
                reply = _read_until(fd, b"cmd:")
                self.assertIn(b"MCOM ON", reply)
                self.assertIn(b"MONITOR_GENERATION 1", reply)

                os.write(fd, b"CONNECT KJ6YWD\r")
                self.assertIn(
                    b"ERROR UNKNOWN COMMAND CONNECT",
                    _read_until(fd, b"cmd:"),
                )

                os.write(fd, b"TX hello\r")
                self.assertIn(
                    b"ERROR UNKNOWN COMMAND TX",
                    _read_until(fd, b"cmd:"),
                )
            finally:
                os.close(fd)

    def test_quit_starts_a_fresh_logical_serial_session(self) -> None:
        with RunningPTY() as running:
            fd = running.open_client()
            try:
                _read_until(fd, b"cmd:")
                os.write(fd, b"MCOM ON\r")
                _read_until(fd, b"cmd:")
                os.write(fd, b"QUIT\r")
                reply = _read_until(fd, b"cmd:")
                self.assertIn(b"BYE", reply)
                self.assertIn(b"VIRTUAL PTY TNC CONSOLE", reply)
                os.write(fd, b"MCOM\r")
                self.assertIn(b"MCOM OFF", _read_until(fd, b"cmd:"))
            finally:
                os.close(fd)

    def test_physical_slave_detach_resets_monitor_state(self) -> None:
        with RunningPTY() as running:
            first = running.open_client()
            _read_until(first, b"cmd:")
            os.write(first, b"MCOM ON\r")
            self.assertIn(b"MCOM ON", _read_until(first, b"cmd:"))
            os.close(first)

            time.sleep(0.15)
            second = running.open_client()
            try:
                banner = _read_until(second, b"cmd:")
                self.assertIn(b"VIRTUAL PTY TNC CONSOLE", banner)
                os.write(second, b"MCOM\r")
                self.assertIn(b"MCOM OFF", _read_until(second, b"cmd:"))
            finally:
                os.close(second)

    def test_command_limit_is_bounded_and_resets_session(self) -> None:
        with RunningPTY(max_commands=2) as running:
            fd = running.open_client()
            try:
                _read_until(fd, b"cmd:")
                os.write(fd, b"VERSION\r")
                _read_until(fd, b"cmd:")
                os.write(fd, b"MCOM\r")
                reply = _read_until(fd, b"cmd:")
                self.assertIn(b"MCOM OFF", reply)
                self.assertIn(b"ERROR SESSION command limit reached", reply)
                self.assertIn(b"BYE", reply)
                self.assertIn(b"VIRTUAL PTY TNC CONSOLE", reply)
            finally:
                os.close(fd)

    def test_max_command_bound_and_shell_factory_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            VirtualPTYTNC(shell_factory=_shell, max_commands=0)
        with self.assertRaises(ValueError):
            VirtualPTYTNC(shell_factory=_shell, max_commands=MAX_COMMANDS_LIMIT + 1)

        server = VirtualPTYTNC(shell_factory=lambda: object())
        with self.assertRaises(TypeError):
            server.open()
        self.assertIsNone(server.master_fd)
        self.assertIsNone(server.slave_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
