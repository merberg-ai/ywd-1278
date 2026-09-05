#!/usr/bin/env python3
"""Host tests for shared classic beacon command composition."""

from __future__ import annotations

from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from product_classic_console_stage_d_test import connect_when_ready, read_socket_until
from product_classic_tx_daemon_0f_test import write_0f_config
from product_daemon_stage_b_test import StageBTransport, free_port, wait_until
from ywd1278.ax25 import Address
from ywd1278.console.classic_tx import ClassicTXSubmitResult
from ywd1278.daemon import run_daemon
from ywd1278.monitor.diagnostics import DiagnosticsStatus
from ywd1278.service.classic_tx_console import (
    ProductClassicTXConfig,
)
from ywd1278.service.classic_console import ProductClassicConsoleConfig
from ywd1278.service.product_beacon_console import (
    ProductClassicBeaconConsole,
    ThreadSafeProductBeaconCoordinator,
)


class Clock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def shared_console(clock: Clock):  # type: ignore[no-untyped-def]
    submitter = lambda frame: ClassicTXSubmitResult(True, 1, "accepted")
    beacon = ThreadSafeProductBeaconCoordinator(
        source=Address.parse("KJ6YWD-10"), paclen=128,
        tx_enabled=False, tx_submitter=submitter,
    )
    console = ProductClassicBeaconConsole(
        ProductClassicConsoleConfig(enabled=False),
        tx_config=ProductClassicTXConfig(source=Address.parse("KJ6YWD-10"), paclen=128),
        tx_enabled=False,
        tx_submitter=submitter,
        beacon=beacon,
        diagnostics_snapshot=DiagnosticsStatus().snapshot,
        mheard_db=None,
    )
    first = console._shell_factory()
    second = console._shell_factory()
    first._clock = clock
    second._clock = clock
    return beacon, first, second


class ProductBeaconConsoleP5c2Tests(unittest.TestCase):
    def test_sessions_share_btext_and_schedule_but_not_unproto_state(self) -> None:
        beacon, first, second = shared_console(Clock())
        self.assertEqual(first.execute("BTEXT shared node").lines, ("BTEXT SET BYTES=11",))
        self.assertEqual(second.execute("BTEXT").lines, ("BTEXT shared node",))
        first.execute("UNPROTO BEACON VIA WIDE1-1")
        armed = first.execute("BEACON EVERY 10")
        self.assertIn("NEXT=110.000000 TX-BLOCKED", armed.lines[0])
        self.assertIn("DEST=BEACON VIA=WIDE1-1", second.execute("BEACON").lines[0])
        self.assertIsNone(second.tx_snapshot.destination)
        self.assertTrue(beacon.snapshot.schedule.enabled)

    def test_any_session_can_cancel_shared_schedule(self) -> None:
        beacon, first, second = shared_console(Clock())
        first.execute("BTEXT shared")
        first.execute("UNPROTO BEACON")
        first.execute("BEACON EVERY 10")
        self.assertEqual(second.execute("BEACON OFF").lines, ("BEACON OFF",))
        self.assertFalse(beacon.snapshot.schedule.enabled)
        self.assertEqual(first.execute("BEACON").lines, ("BEACON OFF",))

    def test_invalid_command_never_replaces_last_good_shared_state(self) -> None:
        _, first, second = shared_console(Clock())
        first.execute("BTEXT good")
        first.execute("UNPROTO BEACON")
        first.execute("BEACON EVERY 10")
        self.assertTrue(first.execute("BTEXT café").lines[0].startswith("ERROR BTEXT"))
        self.assertTrue(first.execute("BEACON EVERY 9").lines[0].startswith("ERROR BEACON"))
        self.assertEqual(second.execute("BTEXT").lines, ("BTEXT good",))
        self.assertIn("BEACON EVERY 10", second.execute("BEACON").lines[0])

    def test_tx_disabled_full_daemon_exposes_commands_but_never_admits(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            port = free_port()
            path = write_0f_config(td, tx_enabled=False, tx_power=64, console_port=port)
            created: list[StageBTransport] = []

            def factory() -> StageBTransport:
                transport = StageBTransport()
                created.append(transport)
                return transport

            stop = threading.Event()
            errors: list[BaseException] = []
            result: list[int] = []

            def target() -> None:
                try:
                    result.append(run_daemon(path, stop_event=stop, transport_factory=factory))
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=target, name="p5c2-daemon")
            thread.start()
            wait_until(lambda: bool(created) and created[0].rx_active, detail="P5c2 daemon RX")
            client: socket.socket | None = None
            try:
                client = connect_when_ready("127.0.0.1", port)
                read_socket_until(client, b"cmd:")
                for command, marker in (
                    (b"BTEXT HOST SAFE\r", b"BTEXT SET BYTES=9"),
                    (b"UNPROTO BEACON\r", b"UNPROTO DEST=BEACON"),
                    (b"BEACON EVERY 10\r", b"TX-BLOCKED"),
                ):
                    client.sendall(command)
                    self.assertIn(marker, read_socket_until(client, b"cmd:"))
                time.sleep(0.15)
                self.assertEqual(created[0].tx_accept_count, 0)
                client.close()
                client = connect_when_ready("127.0.0.1", port)
                read_socket_until(client, b"cmd:")
                client.sendall(b"BEACON\r")
                self.assertIn(b"BEACON EVERY 10 DEST=BEACON", read_socket_until(client, b"cmd:"))
            finally:
                if client is not None:
                    client.close()
                stop.set()
                thread.join(timeout=8.0)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(result, [0])
            self.assertEqual(created[0].tx_accept_count, 0)

    def test_tx_enabled_full_daemon_command_schedules_exactly_one_fake_hat_tx(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            port = free_port()
            path = write_0f_config(td, tx_enabled=True, tx_power=200, console_port=port)
            created: list[StageBTransport] = []
            clock = Clock(0.0)

            def factory() -> StageBTransport:
                transport = StageBTransport()
                created.append(transport)
                return transport

            stop = threading.Event()
            errors: list[BaseException] = []

            def target() -> None:
                try:
                    run_daemon(
                        path,
                        stop_event=stop,
                        transport_factory=factory,
                        random_byte_source=lambda: 0,
                        beacon_clock=clock,
                        beacon_poll_interval_seconds=0.01,
                    )
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=target, name="p5c2-enabled-daemon")
            thread.start()
            wait_until(lambda: bool(created) and created[0].rx_active, detail="P5c2 enabled RX")
            client: socket.socket | None = None
            try:
                client = connect_when_ready("127.0.0.1", port)
                read_socket_until(client, b"cmd:")
                for command, marker in (
                    (b"BTEXT P5C2 HOST ONE\r", b"BTEXT SET BYTES=13"),
                    (b"UNPROTO BEACON\r", b"UNPROTO DEST=BEACON"),
                    (b"BEACON EVERY 10\r", b"TX-ELIGIBLE"),
                ):
                    client.sendall(command)
                    self.assertIn(marker, read_socket_until(client, b"cmd:"))
                self.assertEqual(created[0].tx_accept_count, 0)
                clock.value = 10.0
                wait_until(
                    lambda: created[0].tx_accept_count == 1 and created[0].rx_active,
                    timeout=6.0,
                    detail="one scheduled fake-HAT TX and RX recovery",
                )
                client.sendall(b"BEACON OFF\r")
                self.assertIn(b"BEACON OFF", read_socket_until(client, b"cmd:"))
                clock.value = 1000.0
                time.sleep(0.1)
                self.assertEqual(created[0].tx_accept_count, 1)
            finally:
                if client is not None:
                    client.close()
                stop.set()
                thread.join(timeout=8.0)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(created[0].tx_accept_count, 1)
            self.assertEqual(created[0].rx_start_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
