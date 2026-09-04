#!/usr/bin/env python3
"""Regression tests for the 0E-P5 safe TNC2/MFJ-style vocabulary adapter."""

from __future__ import annotations

import os
import select
import socket
import threading
import time
import unittest

from ywd1278.console.classic import ClassicTNCCommandShell, make_classic_shell
from ywd1278.console.local import LocalTNCCommandShell
from ywd1278.console.pty_serial import VirtualPTYTNC
from ywd1278.console.telnet import TelnetTNCServer


def _shell() -> ClassicTNCCommandShell:
    return make_classic_shell()


def _read_fd_until(fd: int, needle: bytes, *, timeout: float = 2.0) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while needle not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"timeout waiting for {needle!r}: {bytes(data)!r}")
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            continue
        chunk = os.read(fd, 4096)
        if chunk:
            data.extend(chunk)
    return bytes(data)


def _read_socket_until(sock: socket.socket, needle: bytes, *, timeout: float = 2.0) -> bytes:
    deadline = time.monotonic() + timeout
    data = bytearray()
    while needle not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(f"timeout waiting for {needle!r}: {bytes(data)!r}")
        sock.settimeout(remaining)
        chunk = sock.recv(4096)
        if not chunk:
            raise AssertionError(f"socket closed waiting for {needle!r}: {bytes(data)!r}")
        data.extend(chunk)
    return bytes(data)


class ClassicVocabularyTests(unittest.TestCase):
    def test_shell_is_a_frozen_p1_subclass(self) -> None:
        shell = _shell()
        self.assertIsInstance(shell, LocalTNCCommandShell)
        self.assertIsInstance(shell, ClassicTNCCommandShell)

    def test_p1_exact_commands_remain_unchanged(self) -> None:
        shell = _shell()
        self.assertEqual(shell.execute("VERSION").lines, ("YWD-1278 0.1.0-alpha0",))
        self.assertEqual(shell.execute("MCOM").lines, ("MCOM OFF",))
        self.assertEqual(shell.execute("MCON").lines, ("MCON OFF",))
        self.assertEqual(shell.execute("MRPT").lines, ("MRPT ON",))
        self.assertEqual(shell.execute("MHEARD").lines, ("MHEARD UNAVAILABLE",))

    def test_explicit_safe_aliases(self) -> None:
        shell = _shell()
        self.assertEqual(shell.execute("VER").lines, shell.execute("VERSION").lines)
        self.assertEqual(shell.execute("STAT").lines, shell.execute("STATUS").lines)
        self.assertEqual(shell.execute("HEAL").lines, shell.execute("HEALTH").lines)
        self.assertEqual(shell.execute("MH").lines, shell.execute("MHEARD").lines)
        self.assertEqual(shell.execute("MH 7").lines, shell.execute("MHEARD 7").lines)

    def test_display_is_bounded_to_real_monitor_parameters(self) -> None:
        shell = _shell()
        self.assertEqual(
            shell.execute("DISPLAY").lines,
            ("DISPLAY MONITOR", "MCOM OFF", "MCON OFF", "MRPT ON"),
        )
        shell.execute("MCOM ON")
        shell.execute("MCON ON")
        shell.execute("MRPT OFF")
        self.assertEqual(
            shell.execute("DISP MONITOR").lines,
            ("DISPLAY MONITOR", "MCOM ON", "MCON ON", "MRPT OFF"),
        )
        self.assertEqual(
            shell.execute("DISPLAY TIMING").lines,
            ("ERROR DISPLAY supports MONITOR only in 0E-P5",),
        )
        self.assertEqual(
            shell.execute("DISPLAY MONITOR EXTRA").lines,
            ("ERROR DISPLAY expects at most MONITOR",),
        )

    def test_help_documents_classic_surface(self) -> None:
        lines = _shell().execute("HELP").lines
        joined = "\n".join(lines)
        for token in ("DISPLAY [MONITOR]", "MH [1-100]", "VER", "STAT", "HEAL"):
            self.assertIn(token, joined)
        self.assertIn("ambiguous abbreviations are not accepted", joined)
        self.assertIn("TX/link/config legacy commands remain deferred", joined)

    def test_tx_link_and_config_commands_are_recognized_but_inert(self) -> None:
        shell = _shell()
        expected = {
            "CONNECT KJ6YWD": "OWNER=0G",
            "CONVERSE": "OWNER=0F",
            "UNPROTO CQ VIA WIDE1-1": "OWNER=0F",
            "BEACON EVERY 10": "OWNER=0F",
            "BTEXT hello": "OWNER=0F",
            "TX hello": "OWNER=LATER-TX-COMMAND",
            "SEND hello": "OWNER=LATER-TX-COMMAND",
            "TRANSMIT hello": "OWNER=LATER-TX-COMMAND",
            "XMITOK ON": "OWNER=LATER-TX-ENABLE-CONTROL",
            "TXDELAY 30": "OWNER=LATER-TNC-PARAMETER-CONTROL",
            "PERSIST 63": "OWNER=LATER-TNC-PARAMETER-CONTROL",
            "SLOTTIME 10": "OWNER=LATER-TNC-PARAMETER-CONTROL",
            "MYCALL KJ6YWD": "OWNER=LATER-CONFIG",
            "MONITOR ON": "OWNER=LATER-MONITOR-GATE",
            "KISS ON": "OWNER=LATER-KISS-MODE-CONTROL",
        }
        for line, marker in expected.items():
            with self.subTest(line=line):
                result = shell.execute(line)
                self.assertFalse(result.close)
                self.assertEqual(len(result.lines), 1)
                self.assertIn("NOT AVAILABLE IN 0E-P5", result.lines[0])
                self.assertIn(marker, result.lines[0])

    def test_destructive_legacy_commands_are_explicitly_disabled(self) -> None:
        shell = _shell()
        self.assertIn("read-only MHEARD boundary", shell.execute("MHCLEAR").lines[0])
        self.assertIn("reset control disabled", shell.execute("RESET").lines[0])
        self.assertIn("restart control disabled", shell.execute("RESTART").lines[0])
        self.assertIn("shell escape disabled", shell.execute("SHELL").lines[0])

    def test_ambiguous_or_unknown_abbreviations_fail_closed(self) -> None:
        shell = _shell()
        for line in ("D", "C", "CON", "MCO", "M", "XMIT", "UNP", "FOOBAR"):
            with self.subTest(line=line):
                self.assertEqual(
                    shell.execute(line).lines,
                    (f"ERROR UNKNOWN COMMAND {line}",),
                )

    def test_frozen_p2_telnet_accepts_classic_subclass(self) -> None:
        server = TelnetTNCServer(
            ("127.0.0.1", 0),
            shell_factory=_shell,
            max_clients=1,
            idle_timeout_seconds=2.0,
            max_session_seconds=5.0,
            max_commands=20,
        )
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            with socket.create_connection(server.server_address, timeout=2.0) as client:
                banner = _read_socket_until(client, b"cmd:")
                self.assertIn(b"TELNET TNC CONSOLE", banner)
                client.sendall(b"DISP\r")
                reply = _read_socket_until(client, b"cmd:")
                self.assertIn(b"DISPLAY MONITOR", reply)
                self.assertIn(b"MCOM OFF", reply)
                client.sendall(b"CONNECT KJ6YWD\r")
                reply = _read_socket_until(client, b"cmd:")
                self.assertIn(b"ERROR CONNECT NOT AVAILABLE IN 0E-P5; OWNER=0G", reply)
                client.sendall(b"QUIT\r")
                self.assertIn(b"BYE", _read_socket_until(client, b"BYE"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2.0)

    def test_frozen_p4_real_pty_accepts_classic_subclass_and_resets(self) -> None:
        server = VirtualPTYTNC(shell_factory=_shell, poll_seconds=0.01)
        stop = threading.Event()
        thread: threading.Thread | None = None
        first: int | None = None
        second: int | None = None
        try:
            slave = server.open()
            self.assertTrue(slave.startswith("/dev/pts/"))
            thread = threading.Thread(target=server.serve, args=(stop,), daemon=True)
            thread.start()

            first = os.open(slave, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            _read_fd_until(first, b"cmd:")
            os.write(first, b"MCOM ON\r")
            self.assertIn(b"MCOM ON", _read_fd_until(first, b"cmd:"))
            os.write(first, b"DISP\r")
            self.assertIn(b"MCOM ON", _read_fd_until(first, b"cmd:"))
            os.write(first, b"TX hello\r")
            self.assertIn(
                b"ERROR TX NOT AVAILABLE IN 0E-P5; OWNER=LATER-TX-COMMAND",
                _read_fd_until(first, b"cmd:"),
            )
            os.close(first)
            first = None
            time.sleep(0.15)

            second = os.open(slave, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            _read_fd_until(second, b"cmd:")
            os.write(second, b"DISP\r")
            self.assertIn(b"MCOM OFF", _read_fd_until(second, b"cmd:"))
        finally:
            if first is not None:
                os.close(first)
            if second is not None:
                os.close(second)
            stop.set()
            if thread is not None:
                thread.join(timeout=2.0)
            server.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
