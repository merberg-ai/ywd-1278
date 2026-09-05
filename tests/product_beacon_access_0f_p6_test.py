#!/usr/bin/env python3
"""Host behavior tests for 0F-P6 beacon jitter and CSMA gating."""

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
from ywd1278.service.beacon_access_policy import JitteredThreadSafeProductBeaconCoordinator


class Capture:
    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def __call__(self, frame: bytes) -> ClassicTXSubmitResult:
        self.frames.append(bytes(frame))
        return ClassicTXSubmitResult(True, len(self.frames), "accepted")


class Clock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class MutableByte:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value


def coordinator(capture: Capture, byte: MutableByte) -> JitteredThreadSafeProductBeaconCoordinator:
    return JitteredThreadSafeProductBeaconCoordinator(
        source=Address.parse("KJ6YWD-10"), paclen=128, tx_enabled=True,
        tx_submitter=capture, jitter_byte_source=byte,
    )


class ProductBeaconAccessP6Tests(unittest.TestCase):
    def test_maximum_jitter_delays_but_never_advances_due_event(self) -> None:
        capture = Capture()
        beacon = coordinator(capture, MutableByte(255))
        beacon.set_text("P6 JITTER")
        beacon.arm(destination=Address.parse("BEACON"), interval_seconds=10, now=0.0)
        jitter = beacon.jitter_snapshot
        self.assertEqual(jitter.base_due_at, 10.0)
        self.assertEqual(jitter.jitter_seconds, 1.0)
        self.assertEqual(jitter.eligible_at, 11.0)
        self.assertIsNone(beacon.tick(now=10.999))
        self.assertEqual(capture.frames, [])
        self.assertTrue(beacon.tick(now=11.0).admitted)  # type: ignore[union-attr]
        self.assertEqual(len(capture.frames), 1)

    def test_zero_jitter_preserves_exact_p5_due_time_and_no_catchup(self) -> None:
        capture = Capture()
        beacon = coordinator(capture, MutableByte(0))
        beacon.set_text("P6 ZERO")
        beacon.arm(destination=Address.parse("BEACON"), interval_seconds=10, now=0.0)
        self.assertIsNone(beacon.tick(now=9.999))
        self.assertTrue(beacon.tick(now=100.0).admitted)  # type: ignore[union-attr]
        self.assertIsNone(beacon.tick(now=100.0))
        self.assertEqual(len(capture.frames), 1)
        self.assertEqual(beacon.jitter_snapshot.base_due_at, 110.0)

    def test_bad_random_source_disarms_instead_of_leaving_schedule_live(self) -> None:
        capture = Capture()
        beacon = coordinator(capture, MutableByte(256))
        beacon.set_text("P6 BAD")
        with self.assertRaisesRegex(ValueError, "0..255"):
            beacon.arm(destination=Address.parse("BEACON"), interval_seconds=10, now=0.0)
        self.assertFalse(beacon.snapshot.schedule.enabled)
        self.assertEqual(capture.frames, [])

    def test_due_beacon_enters_existing_queue_but_cannot_bypass_csma(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            port = free_port()
            path = write_0f_config(td, tx_enabled=True, tx_power=200, console_port=port)
            text = Path(path).read_text(encoding="utf-8").replace("persist = 255", "persist = 0")
            Path(path).write_text(text, encoding="utf-8")
            created: list[StageBTransport] = []
            clock = Clock(0.0)
            random = MutableByte(255)

            def factory() -> StageBTransport:
                transport = StageBTransport()
                created.append(transport)
                return transport

            stop = threading.Event()
            errors: list[BaseException] = []

            def target() -> None:
                try:
                    run_daemon(
                        path, stop_event=stop, transport_factory=factory,
                        random_byte_source=random, beacon_clock=clock,
                        beacon_jitter_byte_source=random,
                        beacon_poll_interval_seconds=0.01,
                    )
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=target, name="p6-beacon-csma")
            thread.start()
            wait_until(lambda: bool(created) and created[0].rx_active, detail="P6 RX")
            client: socket.socket | None = None
            try:
                client = connect_when_ready("127.0.0.1", port)
                read_socket_until(client, b"cmd:")
                for command, marker in (
                    (b"BTEXT P6 CSMA GATE\r", b"BTEXT SET"),
                    (b"UNPROTO BEACON\r", b"UNPROTO DEST=BEACON"),
                    (b"BEACON EVERY 10\r", b"TX-ELIGIBLE"),
                ):
                    client.sendall(command)
                    self.assertIn(marker, read_socket_until(client, b"cmd:"))
                clock.value = 11.0
                time.sleep(0.35)
                self.assertEqual(created[0].tx_accept_count, 0)
                random.value = 0
                wait_until(
                    lambda: created[0].tx_accept_count == 1 and created[0].rx_active,
                    timeout=6.0, detail="P6 CSMA-controlled dispatch and RX recovery",
                )
                self.assertEqual(created[0].tx_accept_count, 1)
            finally:
                if client is not None:
                    client.close()
                stop.set()
                thread.join(timeout=8.0)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(created[0].tx_accept_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
