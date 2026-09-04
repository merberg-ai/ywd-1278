#!/usr/bin/env python3
"""0E-P2 bounded loopback Telnet command-console regression tests."""

from __future__ import annotations

from pathlib import Path
import socket
import sys
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ywd1278.console.local import MAX_COMMAND_CHARS, LocalTNCCommandShell  # noqa: E402
from ywd1278.console.telnet import (  # noqa: E402
    MAX_TELNET_NEGOTIATIONS,
    TelnetLineDecoder,
    TelnetTNCServer,
)

IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250


def recv_until(sock: socket.socket, marker: bytes, *, timeout: float = 2.0) -> bytes:
    sock.settimeout(timeout)
    data = bytearray()
    while marker not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


class RunningServer:
    def __init__(self, **kwargs: object) -> None:
        self.server = TelnetTNCServer(
            ("127.0.0.1", 0),
            shell_factory=lambda: LocalTNCCommandShell(version="net-test"),
            **kwargs,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> TelnetTNCServer:
        self.thread.start()
        return self.server

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2.0)
        if self.thread.is_alive():
            raise AssertionError("test Telnet server thread did not stop")


class TelnetLineDecoderTests(unittest.TestCase):
    def test_crlf_backspace_and_multiple_lines(self):
        decoder = TelnetLineDecoder()
        result = decoder.feed(b"VERSX\x08ION\r\nMCOM\n")
        self.assertIsNone(result.fatal_error)
        self.assertEqual(result.replies, b"")
        self.assertEqual(
            tuple(event.line for event in result.events),
            ("VERSION", "MCOM"),
        )

    def test_oversized_line_is_bounded_discarded_then_recovers(self):
        decoder = TelnetLineDecoder()
        result = decoder.feed(b"A" * (MAX_COMMAND_CHARS + 80) + b"\r\nVERSION\r\n")
        self.assertIsNone(result.fatal_error)
        self.assertEqual(
            result.events[0].error,
            f"ERROR COMMAND exceeds {MAX_COMMAND_CHARS} characters",
        )
        self.assertEqual(result.events[1].line, "VERSION")

    def test_telnet_option_negotiation_is_refused_but_session_data_survives(self):
        decoder = TelnetLineDecoder()
        result = decoder.feed(bytes((IAC, WILL, 1, IAC, DO, 3)) + b"VERSION\r\n")
        self.assertIsNone(result.fatal_error)
        self.assertEqual(
            result.replies,
            bytes((IAC, DONT, 1, IAC, WONT, 3)),
        )
        self.assertEqual(result.events[0].line, "VERSION")

    def test_malformed_or_unsupported_telnet_control_fails_closed(self):
        decoder = TelnetLineDecoder()
        result = decoder.feed(bytes((IAC, SB)))
        self.assertEqual(result.fatal_error, "ERROR TELNET unsupported control sequence")
        self.assertEqual(
            decoder.feed(b"VERSION\r\n").fatal_error,
            "ERROR TELNET decoder already closed",
        )

    def test_negotiation_count_is_bounded(self):
        decoder = TelnetLineDecoder()
        result = decoder.feed(bytes((IAC, WILL, 1)) * (MAX_TELNET_NEGOTIATIONS + 1))
        self.assertEqual(result.fatal_error, "ERROR TELNET negotiation limit exceeded")

    def test_nul_and_non_nvt_control_fail_closed(self):
        self.assertEqual(
            TelnetLineDecoder().feed(b"VER\x00SION").fatal_error,
            "ERROR TELNET NUL data not permitted",
        )
        self.assertEqual(
            TelnetLineDecoder().feed(b"VER\x01SION").fatal_error,
            "ERROR TELNET invalid NVT byte 1",
        )


class TelnetTNCServerTests(unittest.TestCase):
    def test_listener_rejects_non_loopback_and_non_literal_binds(self):
        for address in ("0.0.0.0", "192.168.1.5", "8.8.8.8", "::1", "localhost"):
            with self.subTest(address=address):
                with self.assertRaises(ValueError):
                    TelnetTNCServer(
                        (address, 0),
                        shell_factory=lambda: LocalTNCCommandShell(),
                    )

        server = TelnetTNCServer(
            ("127.0.0.1", 0),
            shell_factory=lambda: LocalTNCCommandShell(),
        )
        try:
            self.assertEqual(server.server_address[0], "127.0.0.1")
        finally:
            server.server_close()

    def test_live_loopback_session_reuses_frozen_p1_parser(self):
        with RunningServer() as server:
            client = socket.create_connection(server.server_address, timeout=2.0)
            try:
                banner = recv_until(client, b"cmd:")
                self.assertIn(b"YWD-1278 net-test TELNET TNC CONSOLE\r\n", banner)
                self.assertIn(b"0E-P2 loopback-only command mode", banner)

                client.sendall(b"VERSION\r\n")
                self.assertIn(b"YWD-1278 net-test\r\n", recv_until(client, b"cmd:"))

                client.sendall(b"CONNECT KJ6YWD\r\n")
                self.assertIn(
                    b"ERROR UNKNOWN COMMAND CONNECT\r\n",
                    recv_until(client, b"cmd:"),
                )

                client.sendall(b"MCOM ON\r\n")
                changed = recv_until(client, b"cmd:")
                self.assertIn(b"MCOM ON\r\n", changed)
                self.assertIn(b"MONITOR_GENERATION 1\r\n", changed)

                client.sendall(b"QUIT\r\n")
                self.assertIn(b"BYE\r\n", recv_until(client, b"BYE\r\n"))
            finally:
                client.close()

    def test_monitor_policy_is_session_local_across_disconnect_reconnect(self):
        with RunningServer() as server:
            first = socket.create_connection(server.server_address, timeout=2.0)
            recv_until(first, b"cmd:")
            first.sendall(b"MCOM ON\r\n")
            self.assertIn(b"MCOM ON\r\n", recv_until(first, b"cmd:"))
            first.sendall(b"QUIT\r\n")
            recv_until(first, b"BYE\r\n")
            first.close()

            second = socket.create_connection(server.server_address, timeout=2.0)
            try:
                recv_until(second, b"cmd:")
                second.sendall(b"MCOM\r\n")
                self.assertIn(b"MCOM OFF\r\n", recv_until(second, b"cmd:"))
                second.sendall(b"QUIT\r\n")
            finally:
                second.close()

    def test_telnet_negotiation_reply_and_command_can_share_one_packet(self):
        with RunningServer() as server:
            client = socket.create_connection(server.server_address, timeout=2.0)
            try:
                recv_until(client, b"cmd:")
                client.sendall(bytes((IAC, WILL, 1)) + b"VERSION\r\n")
                response = recv_until(client, b"cmd:")
                self.assertIn(bytes((IAC, DONT, 1)), response)
                self.assertIn(b"YWD-1278 net-test\r\n", response)
                client.sendall(b"QUIT\r\n")
            finally:
                client.close()

    def test_client_limit_fails_closed_without_disturbing_active_session(self):
        with RunningServer(max_clients=1) as server:
            first = socket.create_connection(server.server_address, timeout=2.0)
            try:
                recv_until(first, b"cmd:")
                second = socket.create_connection(server.server_address, timeout=2.0)
                try:
                    rejected = recv_until(second, b"\r\n")
                    self.assertIn(b"BUSY maximum Telnet clients reached\r\n", rejected)
                finally:
                    second.close()

                first.sendall(b"VERSION\r\n")
                self.assertIn(b"YWD-1278 net-test\r\n", recv_until(first, b"cmd:"))
                first.sendall(b"QUIT\r\n")
            finally:
                first.close()

    def test_idle_timeout_closes_session(self):
        with RunningServer(idle_timeout_seconds=0.15, max_session_seconds=1.0) as server:
            client = socket.create_connection(server.server_address, timeout=2.0)
            try:
                recv_until(client, b"cmd:")
                response = recv_until(client, b"BYE\r\n", timeout=1.5)
                self.assertIn(b"ERROR SESSION idle timeout\r\n", response)
                self.assertIn(b"BYE\r\n", response)
            finally:
                client.close()

    def test_command_count_limit_is_bounded(self):
        with RunningServer(max_commands=2) as server:
            client = socket.create_connection(server.server_address, timeout=2.0)
            try:
                recv_until(client, b"cmd:")
                client.sendall(b"VERSION\r\n")
                recv_until(client, b"cmd:")
                client.sendall(b"MCOM\r\n")
                response = recv_until(client, b"BYE\r\n")
                self.assertIn(b"MCOM OFF\r\n", response)
                self.assertIn(b"ERROR SESSION command limit reached\r\n", response)
                self.assertIn(b"BYE\r\n", response)
            finally:
                client.close()

    def test_bad_telnet_control_closes_without_reaching_parser(self):
        with RunningServer() as server:
            client = socket.create_connection(server.server_address, timeout=2.0)
            try:
                recv_until(client, b"cmd:")
                client.sendall(bytes((IAC, SB)))
                response = recv_until(client, b"BYE\r\n")
                self.assertIn(b"ERROR TELNET unsupported control sequence\r\n", response)
                self.assertIn(b"BYE\r\n", response)
            finally:
                client.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
