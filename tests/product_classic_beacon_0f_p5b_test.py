#!/usr/bin/env python3
"""Host composition tests for 0F-P5b product beacon admission."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from ywd1278.ax25 import Address, parse_ui_frame
from ywd1278.kiss.framing import DATA
from ywd1278.kiss.tx_backend import KISSDataIngressResult
from ywd1278.kiss.tx_path import KISSDataRequestReceipt
from ywd1278.service.classic_beacon import ProductBeaconCoordinator
from ywd1278.service.classic_tx_console import make_product_backend_submitter


def receipt(request_id: int) -> KISSDataRequestReceipt:
    return KISSDataRequestReceipt(
        request_id=request_id,
        frame_bytes_no_fcs=20,
        frame_bytes_with_fcs=22,
        parameter_generation=1,
        txdelay=30,
        persist=63,
        slottime=10,
        enqueued_at=1.0,
        deadline_at=31.0,
    )


class Backend:
    def __init__(self, *, admitted: bool = True) -> None:
        self.messages = []
        self.admitted = admitted

    def reject_client_message(self, message):  # type: ignore[no-untyped-def]
        self.messages.append(message)
        if not self.admitted:
            return SimpleNamespace(reason="queue full")
        return KISSDataIngressResult(True, receipt(len(self.messages)), "accepted")


def coordinator(*, enabled: bool, backend: Backend) -> ProductBeaconCoordinator:
    return ProductBeaconCoordinator(
        source=Address.parse("KJ6YWD-10"),
        paclen=128,
        tx_enabled=enabled,
        tx_submitter=make_product_backend_submitter(lambda: backend),
    )


class ProductClassicBeaconP5bTests(unittest.TestCase):
    def test_startup_is_off_and_never_admits(self) -> None:
        backend = Backend()
        beacon = coordinator(enabled=True, backend=backend)
        self.assertFalse(beacon.snapshot.schedule.enabled)
        self.assertIsNone(beacon.tick(now=9999.0))
        self.assertEqual(backend.messages, [])

    def test_one_due_tick_uses_exact_existing_kiss_data_boundary_once(self) -> None:
        backend = Backend()
        beacon = coordinator(enabled=True, backend=backend)
        beacon.set_text("YWD-1278 P5B HOST")
        beacon.arm(
            destination=Address.parse("BEACON"),
            interval_seconds=10,
            now=100.0,
        )
        self.assertIsNone(beacon.tick(now=109.0))
        result = beacon.tick(now=110.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.admitted)
        self.assertEqual(len(backend.messages), 1)
        message = backend.messages[0]
        self.assertEqual(message.port, 0)
        self.assertEqual(message.command, DATA)
        parsed = parse_ui_frame(message.frame, has_fcs=False)
        self.assertEqual(str(parsed["source"]), "KJ6YWD-10")
        self.assertEqual(str(parsed["destination"]), "BEACON")
        self.assertEqual(parsed["info"], b"YWD-1278 P5B HOST")
        self.assertIsNone(beacon.tick(now=110.0))
        self.assertEqual(beacon.snapshot.admission_attempts, 1)
        self.assertEqual(beacon.snapshot.admissions_accepted, 1)

    def test_disabled_tx_does_not_consume_deadline_or_call_backend(self) -> None:
        backend = Backend()
        beacon = coordinator(enabled=False, backend=backend)
        beacon.set_text("disabled")
        beacon.arm(destination=Address.parse("BEACON"), interval_seconds=10, now=0.0)
        self.assertIsNone(beacon.tick(now=100.0))
        self.assertEqual(beacon.snapshot.schedule.emitted_events, 0)
        self.assertEqual(backend.messages, [])

    def test_rejection_and_exception_are_single_attempt_without_retry(self) -> None:
        backend = Backend(admitted=False)
        beacon = coordinator(enabled=True, backend=backend)
        beacon.set_text("one try")
        beacon.arm(destination=Address.parse("BEACON"), interval_seconds=10, now=0.0)
        result = beacon.tick(now=10.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.admitted)
        self.assertEqual(len(backend.messages), 1)
        self.assertIsNone(beacon.tick(now=10.0))

        calls = 0

        def raising(frame: bytes):  # type: ignore[no-untyped-def]
            nonlocal calls
            calls += 1
            raise RuntimeError("downstream failed")

        failed = ProductBeaconCoordinator(
            source=Address.parse("KJ6YWD-10"), paclen=128,
            tx_enabled=True, tx_submitter=raising,
        )
        failed.set_text("one try")
        failed.arm(destination=Address.parse("BEACON"), interval_seconds=10, now=0.0)
        result = failed.tick(now=10.0)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result.admitted)
        self.assertEqual(calls, 1)
        self.assertIsNone(failed.tick(now=10.0))

    def test_off_and_rearm_replace_state_without_duplicate_due_event(self) -> None:
        backend = Backend()
        beacon = coordinator(enabled=True, backend=backend)
        beacon.set_text("state")
        beacon.arm(destination=Address.parse("OLD"), interval_seconds=10, now=0.0)
        beacon.off()
        self.assertIsNone(beacon.tick(now=100.0))
        beacon.arm(destination=Address.parse("NEW"), interval_seconds=20, now=100.0)
        self.assertIsNone(beacon.tick(now=119.0))
        self.assertTrue(beacon.tick(now=120.0).admitted)  # type: ignore[union-attr]
        self.assertEqual(len(backend.messages), 1)
        parsed = parse_ui_frame(backend.messages[0].frame, has_fcs=False)
        self.assertEqual(str(parsed["destination"]), "NEW")


if __name__ == "__main__":
    unittest.main(verbosity=2)
