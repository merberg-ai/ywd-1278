#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import qualify_0h_p10_linbpq_delivery as p10  # noqa: E402
from ywd1278.node.linbpq_dialogue import LinBPQState  # noqa: E402


class LinBPQDeliveryP10PreRFTests(unittest.TestCase):
    def test_fixed_one_message_work(self) -> None:
        work = p10.make_work()
        self.assertEqual(str(work.sender), "KJ6YWD-10")
        self.assertEqual(str(work.destination), "KJ6YWD-15")
        self.assertEqual(str(work.next_hop), "KJ6YWD-1")
        self.assertEqual(work.subject, "P10 TEST")
        self.assertEqual(
            b"".join(work.body_chunks),
            b"YWD-1278 0H-P10 LINBPQ DELIVERY 1/1",
        )
        self.assertEqual(work.trace, (p10.LOCAL,))
        self.assertEqual(len(work.body_chunks), 1)
        self.assertLessEqual(len(work.body_chunks[0]), 128)

    def test_observed_banner_shape_drives_exact_p10_actions(self) -> None:
        dialogue = p10.build_dialogue()
        banner = dialogue.feed(
            b"YWDNOD:KJ6YWD-5} Connected to BBS\r"
            b"[BPQ-6.0.25.30-IHJM$]\r"
            b"YWDBBS:KJ6YWD-1}\r"
            b"de KJ6YWD>"
        )
        actions = [(x.kind, x.data) for x in banner.actions]
        self.assertEqual(actions, [("SP", b"SP KJ6YWD-15\r")])

        title = dialogue.feed(b"Enter Title (only):\r")
        self.assertEqual(
            [(x.kind, x.data) for x in title.actions],
            [("TITLE", b"P10 TEST\r")],
        )

        body = dialogue.feed(b"Enter Message Text, end with /EX\r")
        self.assertEqual(
            [(x.kind, x.data) for x in body.actions],
            [
                ("BODY", b"YWD-1278 0H-P10 LINBPQ DELIVERY 1/1"),
                ("BODY_END", b"\r"),
                ("END", b"/EX\r"),
            ],
        )

        accepted = dialogue.feed(b"Message 42 Saved\rde KJ6YWD>")
        self.assertTrue(accepted.accepted)
        self.assertIs(dialogue.snapshot.state, LinBPQState.COMPLETE)
        self.assertEqual(dialogue.snapshot.actions_prepared, 5)

    def test_physical_entry_is_one_bounded_command(self) -> None:
        self.assertEqual(p10.BBS_ENTRY, b"BBS\r")
        self.assertLessEqual(len(p10.BBS_ENTRY), 128)
        self.assertEqual(
            p10.EXPECTED_DIALOGUE_ACTIONS,
            ("SP", "TITLE", "BODY", "BODY_END", "END"),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
