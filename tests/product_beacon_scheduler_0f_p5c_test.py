#!/usr/bin/env python3
"""Host lifecycle safety tests for 0F-P5c."""

from __future__ import annotations

import time
import unittest

from ywd1278.ax25 import Address
from ywd1278.console.classic_tx import ClassicTXSubmitResult
from ywd1278.service.beacon_scheduler import ProductBeaconScheduler
from ywd1278.service.classic_beacon import ProductBeaconCoordinator


class Clock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class Capture:
    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def __call__(self, frame: bytes) -> ClassicTXSubmitResult:
        self.frames.append(bytes(frame))
        return ClassicTXSubmitResult(True, len(self.frames), "accepted")


def coordinator(*, enabled: bool, capture: Capture) -> ProductBeaconCoordinator:
    return ProductBeaconCoordinator(
        source=Address.parse("KJ6YWD-10"), paclen=128,
        tx_enabled=enabled, tx_submitter=capture,
    )


def wait_until(predicate, timeout: float = 1.0) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class ProductBeaconSchedulerP5cTests(unittest.TestCase):
    def test_startup_off_never_admits_and_stop_is_clean(self) -> None:
        capture = Capture()
        beacon = coordinator(enabled=True, capture=capture)
        scheduler = ProductBeaconScheduler(beacon, poll_interval_seconds=0.01)
        scheduler.start()
        self.assertTrue(wait_until(lambda: scheduler.snapshot.ticks >= 2))
        scheduler.stop()
        self.assertFalse(scheduler.snapshot.running)
        self.assertEqual(capture.frames, [])
        self.assertFalse(beacon.snapshot.schedule.enabled)

    def test_double_start_is_rejected_without_duplicate_worker(self) -> None:
        capture = Capture()
        scheduler = ProductBeaconScheduler(
            coordinator(enabled=True, capture=capture), poll_interval_seconds=0.01
        )
        scheduler.start()
        with self.assertRaisesRegex(RuntimeError, "already running"):
            scheduler.start()
        self.assertEqual(scheduler.snapshot.starts, 1)
        scheduler.stop()

    def test_one_due_event_then_no_duplicate_at_same_time(self) -> None:
        clock = Clock(0.0)
        capture = Capture()
        beacon = coordinator(enabled=True, capture=capture)
        beacon.set_text("P5C HOST")
        beacon.arm(destination=Address.parse("BEACON"), interval_seconds=10, now=0.0)
        scheduler = ProductBeaconScheduler(
            beacon, poll_interval_seconds=0.01, clock=clock
        )
        scheduler.start()
        self.assertTrue(wait_until(lambda: scheduler.snapshot.ticks >= 1))
        self.assertEqual(capture.frames, [])
        clock.value = 10.0
        self.assertTrue(wait_until(lambda: len(capture.frames) == 1))
        time.sleep(0.04)
        self.assertEqual(len(capture.frames), 1)
        scheduler.stop()

    def test_stop_disarms_and_restart_cannot_transmit_without_rearm(self) -> None:
        clock = Clock(0.0)
        capture = Capture()
        beacon = coordinator(enabled=True, capture=capture)
        beacon.set_text("P5C HOST")
        beacon.arm(destination=Address.parse("BEACON"), interval_seconds=10, now=0.0)
        scheduler = ProductBeaconScheduler(beacon, poll_interval_seconds=0.01, clock=clock)
        scheduler.start()
        scheduler.stop()
        clock.value = 1000.0
        scheduler.start()
        self.assertTrue(wait_until(lambda: scheduler.snapshot.ticks >= 1))
        time.sleep(0.03)
        scheduler.stop()
        self.assertEqual(capture.frames, [])
        self.assertEqual(scheduler.snapshot.starts, 2)
        self.assertEqual(scheduler.snapshot.stops, 2)

    def test_tx_disabled_never_admits(self) -> None:
        clock = Clock(1000.0)
        capture = Capture()
        beacon = coordinator(enabled=False, capture=capture)
        beacon.set_text("BLOCKED")
        beacon.arm(destination=Address.parse("BEACON"), interval_seconds=10, now=0.0)
        scheduler = ProductBeaconScheduler(beacon, poll_interval_seconds=0.01, clock=clock)
        scheduler.start()
        self.assertTrue(wait_until(lambda: scheduler.snapshot.ticks >= 2))
        scheduler.stop()
        self.assertEqual(capture.frames, [])
        self.assertEqual(beacon.snapshot.admission_attempts, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
