#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import socket
import tempfile
import threading
import time
import unittest

from ywd1278.ax25 import Address
from ywd1278.console.classic_tx import ClassicTXSubmitResult
from ywd1278.console.product_session import _serve_product_telnet_session
from ywd1278.monitor.policy import MonitorPolicyState
from ywd1278.node.persistent_mailbox import PersistentMailboxStore
from ywd1278.service.node_mailbox_config import ProductNodeMailboxConfig
from ywd1278.service.product_beacon_console import ThreadSafeProductBeaconCoordinator
from ywd1278.service.product_mailbox_console import ProductMailboxCommandShell


LOCAL = Address.parse("KJ6YWD-10")


class FakeMonitor:
    def read_available(self, *, maximum: int | None = None):
        _ = maximum
        return []

    def close(self) -> None:
        pass


class ProductMailboxConsoleP4c2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ywd-0i-p4c2-mbox-")
        self.addCleanup(self.temp.cleanup)
        self.store = PersistentMailboxStore(Path(self.temp.name) / "mailbox.sqlite3")
        self.calls: list[bytes] = []

    def config(self, *, enabled: bool = True) -> ProductNodeMailboxConfig:
        return ProductNodeMailboxConfig(
            node_enabled=enabled,
            local=LOCAL if enabled else None,
            alias="YWDNOD",
            max_sessions=1,
            mailbox_enabled=enabled,
            mailbox_database=self.store.path,
            mailbox_paclen=128,
            mailbox_info="KJ6YWD persistent packet mailbox",
        )

    def make_shell(self, *, enabled: bool = True, store=True):  # type: ignore[no-untyped-def]
        def submit(frame_no_fcs: bytes) -> ClassicTXSubmitResult:
            self.calls.append(bytes(frame_no_fcs))
            return ClassicTXSubmitResult(True, len(self.calls), "accepted")

        beacon = ThreadSafeProductBeaconCoordinator(
            source=LOCAL,
            paclen=128,
            tx_enabled=True,
            tx_submitter=submit,
        )
        return ProductMailboxCommandShell(
            source=LOCAL,
            paclen=128,
            tx_enabled=True,
            tx_submitter=submit,
            beacon=beacon,
            live_monitor_factory=FakeMonitor,
            diagnostics=None,
            monitor_policy=MonitorPolicyState(),
            mheard_db=None,
            mailbox_config=self.config(enabled=enabled),
            mailbox_store_getter=lambda: self.store if store else None,
        )

    def test_mbox_reuses_persistent_store_and_returns_to_command_mode(self) -> None:
        shell = self.make_shell()
        help_result = shell.execute("HELP")
        self.assertTrue(any(line.startswith("MBOX ") for line in help_result.lines))

        entered = shell.execute("MBOX")
        self.assertTrue(shell.mailbox_mode)
        self.assertFalse(shell.session_prompt_enabled)
        self.assertIn(
            "MBOX MODE; /CMD, COMMAND, CTRL-C, OR BYE RETURNS TO COMMAND MODE",
            entered.lines,
        )
        self.assertIn("YWD BBS:KJ6YWD-10", entered.lines)
        self.assertIn("Hello KJ6YWD - 0 new / 0 visible message(s)", entered.lines)
        self.assertIn("de KJ6YWD-10>", entered.lines)

        self.assertIn("Enter Title", "\n".join(shell.execute("SP KJ6YWD-1").lines))
        self.assertIn("Enter Message Text", "\n".join(shell.execute("LOCAL MBOX TEST").lines))
        self.assertEqual(shell.execute("survives local mode exit").lines, ())
        saved = shell.execute("/EX")
        self.assertIn("Message 1 saved for KJ6YWD", saved.lines)
        self.assertEqual(self.store.counts_for(LOCAL).visible, 1)
        self.assertEqual(self.store.counts_for(LOCAL).new, 1)
        self.assertEqual(self.calls, [])

        listed = shell.execute("LN")
        self.assertTrue(any("LOCAL MBOX TEST" in line for line in listed.lines))
        read = shell.execute("R 1")
        self.assertTrue(any("survives local mode exit" in line for line in read.lines))
        self.assertEqual(self.store.counts_for(LOCAL).new, 0)

        escaped = shell.execute("/CMD")
        self.assertEqual(escaped.lines, ("COMMAND MODE",))
        self.assertFalse(shell.mailbox_mode)
        self.assertTrue(shell.session_prompt_enabled)

        # Normal TNC command parsing is immediately restored.
        configured = shell.execute("UNPROTO JIM VIA YWDNOD")
        self.assertEqual(configured.lines, ("UNPROTO DEST=JIM VIA=YWDNOD",))

        reentered = shell.execute("MBOX")
        self.assertTrue(any("0 new / 1 visible message(s)" in line for line in reentered.lines))
        goodbye = shell.execute("BYE")
        self.assertIn("73 - disconnecting from YWD BBS", goodbye.lines)
        self.assertFalse(goodbye.close)
        self.assertFalse(shell.mailbox_mode)
        self.assertTrue(shell.session_prompt_enabled)
        self.assertEqual(self.calls, [])

    def test_command_and_ctrl_c_are_zero_tx_mbox_escapes(self) -> None:
        shell = self.make_shell()
        shell.execute("MBOX")
        command = shell.execute("COMMAND")
        self.assertEqual(command.lines, ("COMMAND MODE",))
        self.assertFalse(shell.mailbox_mode)

        shell.execute("MBOX")
        ctrl_c = shell.session_control_etx()
        self.assertIsNotNone(ctrl_c)
        assert ctrl_c is not None
        self.assertEqual(ctrl_c.lines, ("COMMAND MODE",))
        self.assertFalse(shell.mailbox_mode)
        self.assertTrue(shell.session_prompt_enabled)
        self.assertEqual(self.calls, [])

    def test_mbox_fails_closed_when_service_or_store_is_unavailable(self) -> None:
        disabled = self.make_shell(enabled=False)
        self.assertIn("ERROR MBOX DISABLED", disabled.execute("MBOX").lines[0])
        self.assertFalse(disabled.mailbox_mode)

        unavailable = self.make_shell(store=False)
        self.assertIn("ERROR MBOX UNAVAILABLE", unavailable.execute("MBOX").lines[0])
        self.assertFalse(unavailable.mailbox_mode)
        self.assertEqual(self.calls, [])

    def test_telnet_ctrl_c_discards_partial_mbox_line_and_restores_clean_cmd(self) -> None:
        shell = self.make_shell()
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
            client_sock.sendall(b"MBOX\r")
            entered = recv_until(b"de KJ6YWD-10>\r\n")
            self.assertIn(b"MBOX MODE", entered)
            self.assertNotIn(b"cmd:", entered)

            # No CR: the transport decoder owns this partial terminal line.
            client_sock.sendall(b"THIS MBOX TEXT MUST NOT LEAK\x03")
            escaped = recv_until(b"cmd:")
            self.assertIn(b"COMMAND MODE\r\ncmd:", escaped)
            self.assertFalse(shell.mailbox_mode)

            client_sock.sendall(b"UNPROTO JIM VIA YWDNOD\r")
            clean = recv_until(b"cmd:")
            self.assertIn(b"UNPROTO DEST=JIM VIA=YWDNOD\r\n", clean)
            self.assertNotIn(b"THIS MBOX TEXT MUST NOT LEAK", clean)
            self.assertNotIn(b"UNKNOWN", clean)
            self.assertEqual(self.calls, [])
        finally:
            try:
                client_sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client_sock.close()
            server_sock.close()
            thread.join(timeout=2.0)

        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main(verbosity=2)
