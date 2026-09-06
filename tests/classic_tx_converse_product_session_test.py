#!/usr/bin/env python3
"""Host qualification for product classic converse session composition."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from ywd1278.ax25 import Address, build_ui_frame, parse_frame
from ywd1278.console.classic_tx import ClassicTXSubmitResult
from ywd1278.console.telnet import TelnetLineDecoder
from ywd1278.kiss.server import PacketEvent, RXOnlyBackend
from ywd1278.monitor.policy import MonitorPolicyState
from ywd1278.service.product_beacon_console import ThreadSafeProductBeaconCoordinator
from ywd1278.service.product_converse_console import (
    ProductConverseCommandShell,
    open_live_only_monitor,
)


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


class ProductConverseHostTests(unittest.TestCase):
    def make_shell(self, monitor: FakeMonitor | None = None):
        calls: list[bytes] = []
        source = Address.parse("KJ6YWD-10")

        def submit(frame_no_fcs: bytes) -> ClassicTXSubmitResult:
            calls.append(bytes(frame_no_fcs))
            return ClassicTXSubmitResult(True, len(calls), "accepted")

        beacon = ThreadSafeProductBeaconCoordinator(
            source=source,
            paclen=128,
            tx_enabled=True,
            tx_submitter=submit,
        )
        selected = FakeMonitor() if monitor is None else monitor
        shell = ProductConverseCommandShell(
            source=source,
            paclen=128,
            tx_enabled=True,
            tx_submitter=submit,
            beacon=beacon,
            live_monitor_factory=lambda: selected,
            diagnostics=None,
            monitor_policy=MonitorPolicyState(),
            mheard_db=None,
        )
        return shell, selected, calls

    def test_one_line_is_one_ui_admission_and_printable_escape_closes(self) -> None:
        shell, monitor, calls = self.make_shell()
        self.assertIn("UNPROTO DEST=YWD127", shell.execute("UNPROTO YWD127").lines[0])
        entered = shell.execute("CONVERSE")
        self.assertTrue(shell.tx_snapshot.converse_mode)
        self.assertTrue(any("/CMD" in line for line in entered.lines))

        queued = shell.execute("hello packet")
        self.assertEqual(len(calls), 1)
        self.assertIn("TX QUEUED REQUEST=1", queued.lines[0])
        parsed = parse_frame(calls[0], has_fcs=False)
        self.assertEqual(str(parsed["source"]), "KJ6YWD-10")
        self.assertEqual(str(parsed["destination"]), "YWD127")
        self.assertEqual(parsed["frame_type"], "UI")
        self.assertEqual(parsed["pid"], 0xF0)
        self.assertEqual(parsed["info"], b"hello packet")

        escaped = shell.execute("/CMD")
        self.assertEqual(escaped.lines, ("COMMAND MODE",))
        self.assertFalse(shell.tx_snapshot.converse_mode)
        self.assertEqual(len(calls), 1)
        self.assertEqual(monitor.closed, 1)

    def test_live_output_is_only_active_in_converse_and_session_close_is_idempotent(self) -> None:
        shell, monitor, _calls = self.make_shell()
        monitor.lines.append("OLD>HISTORY:must-not-be-visible-before-converse")
        self.assertEqual(shell.session_drain_output(), ())

        shell.execute("UNPROTO YWD127")
        shell.execute("CONVERSE")
        monitor.lines.clear()
        monitor.lines.append("KJ6YWD-5>KJ6YWD-10:LIVE")
        self.assertEqual(
            shell.session_drain_output(),
            ("RX KJ6YWD-5>KJ6YWD-10:LIVE",),
        )
        shell.session_close()
        shell.session_close()
        self.assertEqual(monitor.closed, 1)

    def test_ctrl_c_is_product_converse_only_and_generic_telnet_stays_strict(self) -> None:
        generic = TelnetLineDecoder().feed(b"\x03")
        self.assertIsNotNone(generic.fatal_error)

        shell, monitor, calls = self.make_shell()
        self.assertIsNone(shell.session_control_etx())
        shell.execute("UNPROTO YWD127")
        shell.execute("CONVERSE")
        result = shell.session_control_etx()
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.lines, ("COMMAND MODE",))
        self.assertFalse(shell.tx_snapshot.converse_mode)
        self.assertEqual(calls, [])
        self.assertEqual(monitor.closed, 1)

    def test_live_subscription_discards_history_without_draining_new_live_queue(self) -> None:
        old_frame = build_ui_frame(
            source=Address.parse("KJ6YWD-5"),
            destination=Address.parse("KJ6YWD-10"),
            info=b"OLD",
            include_fcs=False,
        )
        live_frame = build_ui_frame(
            source=Address.parse("KJ6YWD-5"),
            destination=Address.parse("KJ6YWD-10"),
            info=b"LIVE",
            include_fcs=False,
        )
        backend = RXOnlyBackend([PacketEvent(old_frame)])
        subscription = open_live_only_monitor(backend, clock_ns=lambda: 123)
        self.assertEqual(subscription.read_available(), [])
        self.assertEqual(backend.snapshot.subscribers, 1)

        backend.publish(PacketEvent(live_frame))
        records = subscription.read_available()
        self.assertEqual(len(records), 1)
        self.assertFalse(records[0].history_replay)
        self.assertEqual(records[0].line, "KJ6YWD-5>KJ6YWD-10:LIVE")
        subscription.close()
        self.assertEqual(backend.snapshot.subscribers, 0)

    def test_failed_live_subscription_fails_closed_before_any_tx(self) -> None:
        calls: list[bytes] = []
        source = Address.parse("KJ6YWD-10")

        def submit(frame_no_fcs: bytes) -> ClassicTXSubmitResult:
            calls.append(bytes(frame_no_fcs))
            return ClassicTXSubmitResult(True, 1, "accepted")

        beacon = ThreadSafeProductBeaconCoordinator(
            source=source,
            paclen=128,
            tx_enabled=True,
            tx_submitter=submit,
        )

        def fail_monitor():
            raise RuntimeError("subscriber unavailable")

        shell = ProductConverseCommandShell(
            source=source,
            paclen=128,
            tx_enabled=True,
            tx_submitter=submit,
            beacon=beacon,
            live_monitor_factory=fail_monitor,
            diagnostics=None,
            monitor_policy=MonitorPolicyState(),
            mheard_db=None,
        )
        shell.execute("UNPROTO YWD127")
        result = shell.execute("CONVERSE")
        self.assertFalse(shell.tx_snapshot.converse_mode)
        self.assertEqual(calls, [])
        self.assertIn("ERROR CONVERSE RX UNAVAILABLE", result.lines[0])
        self.assertIn("COMMAND MODE", result.lines[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
