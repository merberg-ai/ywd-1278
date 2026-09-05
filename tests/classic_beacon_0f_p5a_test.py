#!/usr/bin/env python3
"""Host-only tests for 0F-P5a BTEXT/beacon behavior."""

from __future__ import annotations

import unittest

from ywd1278.ax25 import Address, parse_ui_frame
from ywd1278.console.classic_beacon import ClassicBeaconCommandShell
from ywd1278.console.classic_tx import ClassicTXSubmitResult


class Clock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class CaptureSubmitter:
    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def __call__(self, frame: bytes) -> ClassicTXSubmitResult:
        self.frames.append(bytes(frame))
        return ClassicTXSubmitResult(True, len(self.frames), "accepted")


def shell(*, enabled: bool, clock: Clock, submitter: CaptureSubmitter) -> ClassicBeaconCommandShell:
    return ClassicBeaconCommandShell(
        source=Address.parse("KJ6YWD-10"),
        paclen=32,
        tx_enabled=enabled,
        tx_submitter=submitter,
        clock=clock,
    )


class ClassicBeaconP5aTests(unittest.TestCase):
    def test_boot_default_is_off_and_polling_has_no_side_effect(self) -> None:
        clock = Clock()
        capture = CaptureSubmitter()
        tnc = shell(enabled=True, clock=clock, submitter=capture)
        self.assertEqual(tnc.execute("BEACON").lines, ("BEACON OFF",))
        self.assertFalse(tnc.beacon_snapshot.enabled)
        self.assertIsNone(tnc.take_due_beacon(now=100000.0))
        self.assertEqual(capture.frames, [])

    def test_btext_is_ascii_printable_paclen_bounded_and_atomic(self) -> None:
        clock = Clock()
        tnc = shell(enabled=False, clock=clock, submitter=CaptureSubmitter())
        self.assertEqual(tnc.execute("BTEXT").lines, ("BTEXT UNSET",))
        self.assertEqual(tnc.execute("BTEXT hello packet world").lines, ("BTEXT SET BYTES=18",))
        self.assertEqual(tnc.btext, "hello packet world")
        self.assertIn("must be ASCII", tnc.execute("BTEXT café").lines[0])
        self.assertIn("exceeds PACLEN", tnc.execute("BTEXT " + "x" * 33).lines[0])
        self.assertEqual(tnc.btext, "hello packet world")

    def test_arm_requires_payload_and_destination_and_valid_bounded_interval(self) -> None:
        clock = Clock()
        tnc = shell(enabled=False, clock=clock, submitter=CaptureSubmitter())
        self.assertIn("requires BTEXT", tnc.execute("BEACON EVERY 10").lines[0])
        tnc.execute("BTEXT hello")
        self.assertIn("requires UNPROTO", tnc.execute("BEACON EVERY 10").lines[0])
        tnc.execute("UNPROTO BEACON")
        for value in ("nope", "9", "86401"):
            with self.subTest(value=value):
                self.assertTrue(tnc.execute(f"BEACON EVERY {value}").lines[0].startswith("ERROR BEACON"))
                self.assertFalse(tnc.beacon_snapshot.enabled)
        result = tnc.execute("BEACON EVERY 10")
        self.assertIn("NEXT=110.000000 TX-BLOCKED", result.lines[0])
        self.assertTrue(tnc.beacon_snapshot.enabled)

    def test_tx_disabled_never_consumes_due_event_or_calls_submitter(self) -> None:
        clock = Clock()
        capture = CaptureSubmitter()
        tnc = shell(enabled=False, clock=clock, submitter=capture)
        tnc.execute("BTEXT disabled")
        tnc.execute("UNPROTO BEACON")
        tnc.execute("BEACON EVERY 10")
        self.assertIsNone(tnc.take_due_beacon(now=999.0))
        self.assertEqual(tnc.beacon_snapshot.emitted_events, 0)
        self.assertEqual(capture.frames, [])

    def test_due_poll_is_at_most_one_and_discards_missed_periods(self) -> None:
        clock = Clock()
        capture = CaptureSubmitter()
        tnc = shell(enabled=True, clock=clock, submitter=capture)
        tnc.execute("BTEXT YWD-1278 P5a")
        tnc.execute("UNPROTO BEACON")
        tnc.execute("BEACON EVERY 10")
        self.assertIsNone(tnc.take_due_beacon(now=109.999))
        event = tnc.take_due_beacon(now=1000.0)
        self.assertIsNotNone(event)
        assert event is not None
        parsed = parse_ui_frame(event.frame_no_fcs, has_fcs=False)
        self.assertEqual(str(parsed["source"]), "KJ6YWD-10")
        self.assertEqual(str(parsed["destination"]), "BEACON")
        self.assertEqual(parsed["info"], b"YWD-1278 P5a")
        self.assertEqual(tnc.beacon_snapshot.next_due_at, 1010.0)
        self.assertIsNone(tnc.take_due_beacon(now=1000.0))
        self.assertEqual(tnc.beacon_snapshot.emitted_events, 1)
        # P5a returns an inert value and never invokes even an injected submitter.
        self.assertEqual(capture.frames, [])

    def test_off_cancels_cleanly_and_rearm_has_new_generation(self) -> None:
        clock = Clock()
        tnc = shell(enabled=True, clock=clock, submitter=CaptureSubmitter())
        tnc.execute("BTEXT hello")
        tnc.execute("UNPROTO BEACON")
        tnc.execute("BEACON EVERY 10")
        first_generation = tnc.beacon_snapshot.generation
        self.assertEqual(tnc.execute("BEACON OFF").lines, ("BEACON OFF",))
        self.assertFalse(tnc.beacon_snapshot.enabled)
        self.assertIsNone(tnc.take_due_beacon(now=999.0))
        clock.now = 200.0
        tnc.execute("BEACON EVERY 20")
        self.assertGreater(tnc.beacon_snapshot.generation, first_generation)
        self.assertEqual(tnc.beacon_snapshot.next_due_at, 220.0)

    def test_reissuing_every_replaces_schedule_without_duplicates(self) -> None:
        clock = Clock()
        tnc = shell(enabled=True, clock=clock, submitter=CaptureSubmitter())
        tnc.execute("BTEXT hello")
        tnc.execute("UNPROTO BEACON")
        tnc.execute("BEACON EVERY 10")
        clock.now = 105.0
        tnc.execute("BEACON EVERY 30")
        self.assertIsNone(tnc.take_due_beacon(now=110.0))
        self.assertIsNotNone(tnc.take_due_beacon(now=135.0))
        self.assertIsNone(tnc.take_due_beacon(now=135.0))

    def test_id_is_explicitly_non_transmitting_in_p5a(self) -> None:
        clock = Clock()
        capture = CaptureSubmitter()
        tnc = shell(enabled=True, clock=clock, submitter=capture)
        self.assertEqual(tnc.execute("ID").lines, ("ID TX DEFERRED; OWNER=0F-P5e",))
        self.assertEqual(capture.frames, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
