#!/usr/bin/env python3
"""0F-P8 host qualification for sustained product CONVERSE behavior."""

from __future__ import annotations

from types import SimpleNamespace
import socket
import threading
import time
import unittest

from ywd1278.ax25 import Address, parse_frame
from ywd1278.console.classic_tx import ClassicTXSubmitResult
from ywd1278.console.product_session import _serve_product_telnet_session
from ywd1278.monitor.policy import MonitorPolicyState
from ywd1278.service.product_beacon_console import ThreadSafeProductBeaconCoordinator
from ywd1278.service.product_converse_console import ProductConverseCommandShell


class FakeMonitor:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.closed = 0

    def read_available(self, *, maximum: int | None = None):
        if maximum is None:
            maximum = len(self.lines)
        selected = self.lines[:maximum]
        del self.lines[:maximum]
        return [SimpleNamespace(line=line) for line in selected]

    def close(self) -> None:
        self.closed += 1


class ProductConverseP8Tests(unittest.TestCase):
    def make_shell(self):
        calls: list[bytes] = []
        source = Address.parse("KJ6YWD-10")
        monitors: list[FakeMonitor] = []

        def submit(frame_no_fcs: bytes) -> ClassicTXSubmitResult:
            calls.append(bytes(frame_no_fcs))
            return ClassicTXSubmitResult(True, len(calls), "accepted")

        def open_monitor() -> FakeMonitor:
            monitor = FakeMonitor()
            monitors.append(monitor)
            return monitor

        beacon = ThreadSafeProductBeaconCoordinator(
            source=source,
            paclen=128,
            tx_enabled=True,
            tx_submitter=submit,
        )
        shell = ProductConverseCommandShell(
            source=source,
            paclen=128,
            tx_enabled=True,
            tx_submitter=submit,
            beacon=beacon,
            live_monitor_factory=open_monitor,
            diagnostics=None,
            monitor_policy=MonitorPolicyState(),
            mheard_db=None,
        )
        return shell, calls, monitors

    def assert_ui(self, raw: bytes, *, destination: str, path: list[str], info: bytes) -> None:
        parsed = parse_frame(raw, has_fcs=False)
        self.assertEqual(str(parsed["source"]), "KJ6YWD-10")
        self.assertEqual(str(parsed["destination"]), destination)
        self.assertEqual([str(hop) for hop in parsed["path"]], path)
        self.assertEqual(parsed["frame_type"], "UI")
        self.assertEqual(parsed["pid"], 0xF0)
        self.assertEqual(parsed["info"], info)

    def test_sustained_converse_uses_current_unproto_destination_and_via(self) -> None:
        shell, calls, monitors = self.make_shell()

        configured = shell.execute("UNPROTO JIM VIA YWDNOD")
        self.assertEqual(configured.lines, ("UNPROTO DEST=JIM VIA=YWDNOD",))
        entered = shell.execute("CONVERSE")
        self.assertTrue(shell.tx_snapshot.converse_mode)
        self.assertFalse(shell.session_prompt_enabled)
        self.assertTrue(any("CTRL-C" in line for line in entered.lines))

        for line in ("hello one", "hello two", "hello three"):
            result = shell.execute(line)
            self.assertIn("TX QUEUED REQUEST=", result.lines[0])

        self.assertEqual(len(calls), 3)
        for raw, info in zip(calls, (b"hello one", b"hello two", b"hello three")):
            self.assert_ui(raw, destination="JIM", path=["YWDNOD"], info=info)

        monitors[-1].lines.append("KJ6YWD>JIM:live between tx")
        self.assertEqual(
            shell.session_drain_output(),
            ("RX KJ6YWD>JIM:live between tx",),
        )

        escaped = shell.execute("/CMD")
        self.assertEqual(escaped.lines, ("COMMAND MODE",))
        self.assertFalse(shell.tx_snapshot.converse_mode)
        self.assertTrue(shell.session_prompt_enabled)
        self.assertEqual(len(calls), 3)

        reconfigured = shell.execute("UNPROTO JIM2 VIA YWD2")
        self.assertEqual(reconfigured.lines, ("UNPROTO DEST=JIM2 VIA=YWD2",))
        shell.execute("CONVERSE")
        shell.execute("after reconfigure")
        self.assertEqual(len(calls), 4)
        self.assert_ui(
            calls[-1],
            destination="JIM2",
            path=["YWD2"],
            info=b"after reconfigure",
        )

        ctrl_c = shell.session_control_etx()
        self.assertIsNotNone(ctrl_c)
        assert ctrl_c is not None
        self.assertEqual(ctrl_c.lines, ("COMMAND MODE",))
        self.assertFalse(shell.tx_snapshot.converse_mode)
        self.assertEqual(len(calls), 4)

    def test_telnet_ctrl_c_discards_partial_converse_line_and_restores_clean_cmd(self) -> None:
        shell, calls, _monitors = self.make_shell()
        server = SimpleNamespace(
            max_commands=100,
            idle_timeout_seconds=5.0,
            max_session_seconds=10.0,
        )
        server_sock, client_sock = socket.socketpair()
        client_sock.settimeout(1.0)
        thread = threading.Thread(
            target=_serve_product_telnet_session,
            args=(server_sock, server, shell),
            daemon=True,
        )
        thread.start()

        def recv_until(marker: bytes, *, timeout: float = 2.0) -> bytes:
            deadline = time.monotonic() + timeout
            data = bytearray()
            while marker not in data:
                if time.monotonic() >= deadline:
                    self.fail(f"timeout waiting for {marker!r}; got {bytes(data)!r}")
                try:
                    chunk = client_sock.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                data.extend(chunk)
            return bytes(data)

        try:
            client_sock.sendall(b"UNPROTO JIM VIA YWDNOD\r")
            reply = recv_until(b"cmd:")
            self.assertIn(b"UNPROTO DEST=JIM VIA=YWDNOD\r\n", reply)

            client_sock.sendall(b"CONVERSE\r")
            entered = recv_until(b"LIVE RX DISPLAY ENABLED; PRE-CONVERSE HISTORY NOT REPLAYED\r\n")
            self.assertNotIn(b"cmd:", entered)

            client_sock.sendall(b"first p8 line\rsecond p8 line\r")
            reply = recv_until(b"TX QUEUED REQUEST=2")
            self.assertNotIn(b"cmd:", reply)
            self.assertEqual(len(calls), 2)
            self.assert_ui(calls[0], destination="JIM", path=["YWDNOD"], info=b"first p8 line")
            self.assert_ui(calls[1], destination="JIM", path=["YWDNOD"], info=b"second p8 line")

            client_sock.sendall(b"/CMD\r")
            escaped = recv_until(b"cmd:")
            self.assertIn(b"COMMAND MODE\r\ncmd:", escaped)
            self.assertEqual(len(calls), 2)

            client_sock.sendall(b"CONVERSE\r")
            recv_until(b"LIVE RX DISPLAY ENABLED; PRE-CONVERSE HISTORY NOT REPLAYED\r\n")

            # This unfinished text must be thrown away when Ctrl-C is accepted.
            client_sock.sendall(b"THIS MUST NOT LEAK\x03")
            ctrl_c = recv_until(b"cmd:")
            self.assertIn(b"COMMAND MODE\r\ncmd:", ctrl_c)
            self.assertEqual(len(calls), 2)

            client_sock.sendall(b"UNPROTO JIM3 VIA YWD3\r")
            clean = recv_until(b"cmd:")
            self.assertIn(b"UNPROTO DEST=JIM3 VIA=YWD3\r\n", clean)
            self.assertNotIn(b"UNKNOWN", clean)
            self.assertNotIn(b"THIS MUST NOT LEAK", clean)

            client_sock.sendall(b"CONVERSE\r")
            recv_until(b"LIVE RX DISPLAY ENABLED; PRE-CONVERSE HISTORY NOT REPLAYED\r\n")
            client_sock.sendall(b"after ctrl-c\r")
            recv_until(b"TX QUEUED REQUEST=3")
            self.assertEqual(len(calls), 3)
            self.assert_ui(calls[-1], destination="JIM3", path=["YWD3"], info=b"after ctrl-c")

            client_sock.sendall(b"/CMD\r")
            recv_until(b"cmd:")
        finally:
            try:
                client_sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client_sock.close()
            server_sock.close()
            thread.join(timeout=2.0)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(calls), 3)

        print("YWD1278_0F_P8_SUSTAINED_PRODUCT_CONVERSE_HOST=PASS")
        print("UNPROTO_DEST=JIM")
        print("UNPROTO_VIA=YWDNOD")
        print("MULTILINE_CONVERSE=PASS")
        print("PRINTABLE_CMD_ESCAPE=PASS")
        print("CTRL_C_ESCAPE=PASS")
        print("CTRL_C_PARTIAL_LINE_DISCARD=PASS")
        print("DYNAMIC_UNPROTO_RECONFIGURE=PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
