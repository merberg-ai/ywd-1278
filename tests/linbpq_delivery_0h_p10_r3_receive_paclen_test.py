#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import qualify_0h_p10_linbpq_delivery as p10  # noqa: E402
import qualify_0h_p10_linbpq_delivery_r2 as r2  # noqa: E402
import qualify_0h_p10_linbpq_delivery_r3 as r3  # noqa: E402
from ywd1278.ax25 import Address  # noqa: E402
from ywd1278.link.data_link import build_i_frame  # noqa: E402
from ywd1278.link.modulo8 import LinkState, build_unnumbered_frame  # noqa: E402
from ywd1278.link.timed_link import LinkTimerConfig  # noqa: E402


LOCAL = Address.parse("KJ6YWD-10")
REMOTE = Address.parse("KJ6YWD-5")
TIMERS = LinkTimerConfig(
    t1_seconds=8.0,
    t2_seconds=1.0,
    t3_seconds=60.0,
    max_retries=2,
)


class P10R3ReceivePaclenTests(unittest.TestCase):
    def connect(self, link) -> None:  # type: ignore[no-untyped-def]
        started = link.connect(now=0.0)
        self.assertTrue(started.accepted)
        ua = build_unnumbered_frame(
            source=REMOTE,
            destination=LOCAL,
            frame_type="UA",
            command=False,
            poll_final=True,
        )
        accepted = link.handle_frame(ua, now=0.1)
        self.assertTrue(accepted.accepted)
        self.assertIs(link.snapshot.link.state, LinkState.CONNECTED)

    def incoming_i(self, payload: bytes) -> bytes:
        return build_i_frame(
            source=REMOTE,
            destination=LOCAL,
            ns=0,
            nr=0,
            info=payload,
            command=True,
        )

    def test_r3_keeps_stop_and_wait_and_raises_effective_paclen_to_256(self) -> None:
        link = r3.LinBPQReceive256StopAndWait(
            local=LOCAL,
            remote=REMOTE,
            maxframe=4,
            paclen=128,
            timers=TIMERS,
        )
        self.assertEqual(link.requested_maxframe, 4)
        self.assertEqual(link.snapshot.link.maxframe, 1)
        self.assertEqual(link.requested_paclen, 128)
        self.assertEqual(link.effective_paclen, 256)

    def test_196_byte_linbpq_style_i_frame_is_rejected_by_r2_but_delivered_by_r3(self) -> None:
        payload = b"X" * 196
        frame = self.incoming_i(payload)

        old = r2.StopAndWaitTimedModulo8DataLink(
            local=LOCAL,
            remote=REMOTE,
            maxframe=4,
            paclen=128,
            timers=TIMERS,
        )
        self.connect(old)
        rejected = old.handle_frame(frame, now=1.0)
        self.assertFalse(rejected.accepted)
        self.assertIn("PACLEN 128", rejected.reason)
        self.assertEqual(rejected.delivered, ())

        new = r3.LinBPQReceive256StopAndWait(
            local=LOCAL,
            remote=REMOTE,
            maxframe=4,
            paclen=128,
            timers=TIMERS,
        )
        self.connect(new)
        accepted = new.handle_frame(frame, now=1.0)
        self.assertTrue(accepted.accepted)
        self.assertEqual(accepted.delivered, (payload,))
        self.assertEqual(new.snapshot.link.vr, 1)

    def test_257_byte_inbound_i_frame_still_fails_closed(self) -> None:
        link = r3.LinBPQReceive256StopAndWait(
            local=LOCAL,
            remote=REMOTE,
            maxframe=4,
            paclen=128,
            timers=TIMERS,
        )
        self.connect(link)
        result = link.handle_frame(self.incoming_i(b"X" * 257), now=1.0)
        self.assertFalse(result.accepted)
        self.assertIn("PACLEN 256", result.reason)
        self.assertEqual(result.delivered, ())

    def test_p10_outbound_information_guard_remains_128(self) -> None:
        link = r3.LinBPQReceive256StopAndWait(
            local=LOCAL,
            remote=REMOTE,
            maxframe=4,
            paclen=128,
            timers=TIMERS,
        )
        self.connect(link)
        with self.assertRaisesRegex(RuntimeError, "1..128"):
            p10._submit_information(object(), link, b"X" * 129, now=1.0)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main(verbosity=2)
