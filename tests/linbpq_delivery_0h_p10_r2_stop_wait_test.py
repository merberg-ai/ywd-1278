#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import qualify_0h_p10_linbpq_delivery_r2 as r2  # noqa: E402
from ywd1278.ax25 import Address, parse_frame  # noqa: E402
from ywd1278.link.data_link import build_s_frame  # noqa: E402
from ywd1278.link.modulo8 import LinkState, build_unnumbered_frame  # noqa: E402
from ywd1278.link.timed_link import LinkTimerConfig  # noqa: E402


class P10R2StopAndWaitTests(unittest.TestCase):
    def make_link(self) -> r2.StopAndWaitTimedModulo8DataLink:
        return r2.StopAndWaitTimedModulo8DataLink(
            local=Address.parse("KJ6YWD-10"),
            remote=Address.parse("KJ6YWD-5"),
            maxframe=4,
            paclen=128,
            timers=LinkTimerConfig(
                t1_seconds=8.0,
                t2_seconds=1.0,
                t3_seconds=60.0,
                max_retries=2,
            ),
        )

    def connect_link(self, link: r2.StopAndWaitTimedModulo8DataLink) -> None:
        started = link.connect(now=0.0)
        self.assertTrue(started.accepted)
        ua = build_unnumbered_frame(
            source=Address.parse("KJ6YWD-5"),
            destination=Address.parse("KJ6YWD-10"),
            frame_type="UA",
            command=False,
            poll_final=True,
        )
        accepted = link.handle_frame(ua, now=0.1)
        self.assertTrue(accepted.accepted)
        self.assertIs(link.snapshot.link.state, LinkState.CONNECTED)

    def rr(self, nr: int) -> bytes:
        return build_s_frame(
            source=Address.parse("KJ6YWD-5"),
            destination=Address.parse("KJ6YWD-10"),
            frame_type="RR",
            nr=nr,
            command=False,
        )

    def test_forces_maxframe_one_even_when_p10_requests_four(self) -> None:
        link = self.make_link()
        self.assertEqual(link.requested_maxframe, 4)
        self.assertEqual(link.snapshot.link.maxframe, 1)

    def test_releases_exactly_one_queued_i_frame_per_ack(self) -> None:
        link = self.make_link()
        self.connect_link(link)

        first = link.send_information(b"BODY", now=1.0)
        second = link.send_information(b"\r", now=1.1)
        third = link.send_information(b"/EX\r", now=1.2)

        self.assertEqual(len(first.actions), 1)
        self.assertEqual(second.actions, ())
        self.assertEqual(third.actions, ())
        self.assertEqual(link.snapshot.link.outstanding, 1)
        self.assertEqual(link.queued_count, 2)

        ack1 = link.handle_frame(self.rr(1), now=2.0)
        self.assertTrue(ack1.accepted)
        self.assertEqual(link.queued_count, 1)
        self.assertEqual(link.snapshot.link.outstanding, 1)
        self.assertEqual(len(ack1.actions), 1)
        parsed1 = parse_frame(ack1.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual(parsed1["frame_type"], "I")
        self.assertEqual(parsed1["info"], b"\r")

        ack2 = link.handle_frame(self.rr(2), now=3.0)
        self.assertTrue(ack2.accepted)
        self.assertEqual(link.queued_count, 0)
        self.assertEqual(link.snapshot.link.outstanding, 1)
        self.assertEqual(len(ack2.actions), 1)
        parsed2 = parse_frame(ack2.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual(parsed2["frame_type"], "I")
        self.assertEqual(parsed2["info"], b"/EX\r")

        ack3 = link.handle_frame(self.rr(3), now=4.0)
        self.assertTrue(ack3.accepted)
        self.assertEqual(link.queued_count, 0)
        self.assertEqual(link.snapshot.link.outstanding, 0)
        self.assertEqual(ack3.actions, ())


if __name__ == "__main__":
    unittest.main(verbosity=2)
