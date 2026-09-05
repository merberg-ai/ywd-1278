#!/usr/bin/env python3
"""Host-only 0F P1/P2 regression tests for classic UNPROTO/converse."""

from __future__ import annotations

import unittest

from ywd1278.ax25 import Address, parse_ui_frame
from ywd1278.console.classic import ClassicTNCCommandShell
from ywd1278.console.classic_tx import (
    COMMAND_MODE_ESCAPE,
    ClassicTXCommandShell,
    ClassicTXSubmitResult,
    make_classic_tx_shell,
)


class CaptureSubmitter:
    def __init__(self, *, admitted: bool = True, reason: str = "accepted") -> None:
        self.frames: list[bytes] = []
        self.admitted = admitted
        self.reason = reason

    def __call__(self, frame: bytes) -> ClassicTXSubmitResult:
        self.frames.append(bytes(frame))
        return ClassicTXSubmitResult(
            self.admitted,
            len(self.frames) if self.admitted else None,
            self.reason,
        )


class RaisingSubmitter:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, frame: bytes) -> ClassicTXSubmitResult:
        _ = frame
        self.calls += 1
        raise RuntimeError("synthetic downstream rejection")


def shell(*, enabled: bool = True, submitter=None, paclen: int = 128) -> ClassicTXCommandShell:  # type: ignore[no-untyped-def]
    return make_classic_tx_shell(
        source=Address.parse("KJ6YWD-10"),
        paclen=paclen,
        tx_enabled=enabled,
        tx_submitter=submitter,
    )


class ClassicTX0FTests(unittest.TestCase):
    def test_is_a_frozen_p5_subclass_and_preserves_non_0f_behavior(self) -> None:
        tx = shell(enabled=False)
        self.assertIsInstance(tx, ClassicTNCCommandShell)
        self.assertEqual(tx.execute("VER").lines, ("YWD-1278 0.1.0-alpha0",))
        self.assertIn("OWNER=0G", tx.execute("CONNECT KJ6YWD").lines[0])
        self.assertIn("LATER-TX-COMMAND", tx.execute("TX hello").lines[0])

    def test_unproto_query_set_direct_and_path(self) -> None:
        tx = shell(enabled=False)
        self.assertEqual(tx.execute("UNPROTO").lines, ("UNPROTO UNSET",))
        self.assertEqual(
            tx.execute("UNPROTO CQ").lines,
            ("UNPROTO DEST=CQ VIA=DIRECT",),
        )
        self.assertEqual(tx.tx_snapshot.destination, "CQ")
        self.assertEqual(tx.tx_snapshot.path, ())
        self.assertEqual(
            tx.execute("UNPROTO YWD127 VIA WIDE1-1,WIDE2-1").lines,
            ("UNPROTO DEST=YWD127 VIA=WIDE1-1,WIDE2-1",),
        )
        self.assertEqual(
            tx.execute("UNPROTO").lines,
            ("UNPROTO DEST=YWD127 VIA=WIDE1-1,WIDE2-1",),
        )
        self.assertEqual(tx.tx_snapshot.path, ("WIDE1-1", "WIDE2-1"))

    def test_unproto_validation_is_bounded_and_does_not_replace_last_good_state(self) -> None:
        tx = shell(enabled=False)
        tx.execute("UNPROTO CQ")
        bad = (
            "UNPROTO TOOLONG7",
            "UNPROTO CQ WIDE1-1",
            "UNPROTO CQ VIA",
            "UNPROTO CQ VIA WIDE1-1,WIDE2-1,D1,D2,D3,D4,D5,D6,D7",
            "UNPROTO CQ VIA BAD-99",
        )
        for line in bad:
            with self.subTest(line=line):
                self.assertTrue(tx.execute(line).lines[0].startswith("ERROR UNPROTO"))
                self.assertEqual(tx.tx_snapshot.destination, "CQ")
                self.assertEqual(tx.tx_snapshot.path, ())

    def test_converse_requires_destination_and_tx_authority_without_callback(self) -> None:
        capture = CaptureSubmitter()
        tx = shell(enabled=False, submitter=capture)
        self.assertEqual(
            tx.execute("CONVERSE").lines,
            ("ERROR CONVERSE requires UNPROTO destination",),
        )
        tx.execute("UNPROTO YWD127")
        self.assertEqual(
            tx.execute("CONVERSE").lines,
            ("ERROR CONVERSE TX DISABLED; radio.tx_enabled=false",),
        )
        self.assertFalse(tx.tx_snapshot.converse_mode)
        self.assertEqual(capture.frames, [])

    def test_one_converse_line_builds_one_exact_ui_body_and_no_fcs(self) -> None:
        capture = CaptureSubmitter()
        tx = shell(enabled=True, submitter=capture)
        tx.execute("UNPROTO YWD127 VIA WIDE1-1,WIDE2-1")
        entered = tx.execute("CONVERSE")
        self.assertIn("CONVERSE MODE DEST=YWD127 VIA=WIDE1-1,WIDE2-1", entered.lines)
        result = tx.execute("hello from 0F")
        self.assertEqual(len(capture.frames), 1)
        self.assertIn("TX QUEUED REQUEST=1", result.lines[0])
        parsed = parse_ui_frame(capture.frames[0], has_fcs=False)
        self.assertEqual(str(parsed["source"]), "KJ6YWD-10")
        self.assertEqual(str(parsed["destination"]), "YWD127")
        self.assertEqual(tuple(str(item) for item in parsed["path"]), ("WIDE1-1", "WIDE2-1"))
        self.assertEqual(parsed["info"], b"hello from 0F")
        self.assertEqual(parsed["pid"], 0xF0)
        self.assertEqual(tx.tx_snapshot.admitted_lines, 1)

    def test_command_escape_is_line_oriented_and_prevents_second_tx(self) -> None:
        capture = CaptureSubmitter()
        tx = shell(enabled=True, submitter=capture)
        tx.execute("UNPROTO YWD127")
        tx.execute("CONVERSE")
        tx.execute("one")
        self.assertEqual(tx.execute(COMMAND_MODE_ESCAPE).lines, ("COMMAND MODE",))
        self.assertFalse(tx.tx_snapshot.converse_mode)
        self.assertEqual(tx.execute("VER").lines, ("YWD-1278 0.1.0-alpha0",))
        self.assertEqual(len(capture.frames), 1)

    def test_empty_oversize_non_ascii_and_rejection_never_retry(self) -> None:
        capture = CaptureSubmitter(admitted=False, reason="queue full")
        tx = shell(enabled=True, submitter=capture, paclen=8)
        tx.execute("UNPROTO YWD127")
        tx.execute("CONVERSE")
        self.assertEqual(tx.execute("").lines, ("CONVERSE EMPTY LINE NOT SENT",))
        self.assertEqual(len(capture.frames), 0)

        oversize = tx.execute("123456789")
        self.assertIn("ERROR TX SUBMIT ValueError", oversize.lines[0])
        self.assertEqual(len(capture.frames), 0)

        non_ascii = tx.execute("caf\u00e9")
        self.assertIn("ERROR TX SUBMIT ValueError", non_ascii.lines[0])
        self.assertEqual(len(capture.frames), 0)

        rejected = tx.execute("12345678")
        self.assertEqual(rejected.lines, ("ERROR TX REJECTED queue full",))
        self.assertEqual(len(capture.frames), 1)
        self.assertEqual(tx.tx_snapshot.admitted_lines, 0)

    def test_submit_exception_is_single_attempt(self) -> None:
        raising = RaisingSubmitter()
        tx = shell(enabled=True, submitter=raising)
        tx.execute("UNPROTO YWD127")
        tx.execute("CONVERSE")
        result = tx.execute("one attempt")
        self.assertIn("ERROR TX SUBMIT RuntimeError", result.lines[0])
        self.assertEqual(raising.calls, 1)
        self.assertEqual(tx.tx_snapshot.admitted_lines, 0)

    def test_beacon_btext_id_remain_deferred_and_help_describes_scope(self) -> None:
        tx = shell(enabled=True, submitter=CaptureSubmitter())
        for command in ("BEACON EVERY 10", "BTEXT hello", "ID"):
            with self.subTest(command=command):
                self.assertIn("OWNER=0F-P5", tx.execute(command).lines[0])
        help_text = "\n".join(tx.execute("HELP").lines)
        self.assertIn("UNPROTO [DEST [VIA PATH]]", help_text)
        self.assertIn("CONVERSE", help_text)
        self.assertIn("COMMAND", help_text)
        self.assertIn("BEACON/BTEXT/ID remain deferred", help_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
