#!/usr/bin/env python3
"""Host behavior tests for caller-driven 0G-P3 T1/T2/T3 policy."""

from __future__ import annotations

import unittest

from ywd1278.ax25 import Address, parse_frame
from ywd1278.link.data_link import build_i_frame, build_s_frame
from ywd1278.link.modulo8 import LinkState, build_unnumbered_frame
from ywd1278.link.timed_link import LinkTimerConfig, TimedModulo8DataLink


LOCAL = Address.parse("KJ6YWD-10")
REMOTE = Address.parse("KJ6YWD-5")
TIMERS = LinkTimerConfig(t1_seconds=3.0, t2_seconds=1.0, t3_seconds=10.0, max_retries=2)


def u(name: str, *, command: bool, poll_final: bool = True) -> bytes:
    return build_unnumbered_frame(
        source=REMOTE, destination=LOCAL, frame_type=name,
        command=command, poll_final=poll_final,
    )


def iframe(ns: int, nr: int, info: bytes, *, poll_final: bool = False) -> bytes:
    return build_i_frame(
        source=REMOTE, destination=LOCAL, ns=ns, nr=nr, info=info,
        command=True, poll_final=poll_final,
    )


def sframe(name: str, nr: int, *, command: bool = False, poll_final: bool = False) -> bytes:
    return build_s_frame(
        source=REMOTE, destination=LOCAL, frame_type=name, nr=nr,
        command=command, poll_final=poll_final,
    )


def connected() -> TimedModulo8DataLink:
    link = TimedModulo8DataLink(local=LOCAL, remote=REMOTE, timers=TIMERS)
    self_connect = link.connect(now=0.0)
    assert self_connect.accepted
    established = link.handle_frame(u("UA", command=False), now=0.1)
    assert established.accepted and link.snapshot.link.state is LinkState.CONNECTED
    return link


class TimedLinkP3Tests(unittest.TestCase):
    def test_t1_retries_sabm_exactly_n2_then_cancels_pending_connect(self) -> None:
        link = TimedModulo8DataLink(local=LOCAL, remote=REMOTE, timers=TIMERS)
        first = link.connect(now=0.0)
        sabm = first.actions[0].frame_no_fcs
        self.assertEqual(link.snapshot.t1_deadline, 3.0)
        self.assertEqual(link.poll(now=2.999).actions, ())
        retry1 = link.poll(now=3.0)
        self.assertEqual(retry1.actions[0].frame_no_fcs, sabm)
        self.assertTrue(retry1.actions[0].retransmission)
        retry2 = link.poll(now=6.0)
        self.assertEqual(retry2.actions[0].frame_no_fcs, sabm)
        exhausted = link.poll(now=9.0)
        self.assertEqual(exhausted.actions, ())
        self.assertTrue(link.snapshot.retry_exhausted)
        self.assertEqual(link.snapshot.link.state, LinkState.DISCONNECTED)
        self.assertIsNone(link.snapshot.t1_deadline)

    def test_t1_retransmits_outstanding_data_and_ack_cancels_it(self) -> None:
        link = connected()
        sent = link.send_information(b"ONE", now=1.0)
        original = sent.actions[0].frame_no_fcs
        retry = link.poll(now=4.0)
        self.assertEqual(retry.actions[0].frame_no_fcs, original)
        self.assertTrue(retry.actions[0].retransmission)
        acknowledged = link.handle_frame(sframe("RR", 1), now=4.1)
        self.assertTrue(acknowledged.accepted)
        self.assertEqual(link.snapshot.link.outstanding, 0)
        self.assertIsNone(link.snapshot.t1_deadline)

    def test_t1_exhaustion_fails_closed_with_one_inert_disc(self) -> None:
        link = connected()
        link.send_information(b"NO ACK", now=1.0)
        link.poll(now=4.0)
        link.poll(now=7.0)
        exhausted = link.poll(now=10.0)
        self.assertTrue(link.snapshot.retry_exhausted)
        self.assertEqual(link.snapshot.link.state, LinkState.AWAITING_RELEASE)
        self.assertEqual(len(exhausted.actions), 1)
        self.assertEqual(parse_frame(exhausted.actions[0].frame_no_fcs, has_fcs=False)["frame_type"], "DISC")
        self.assertIsNone(link.snapshot.t1_deadline)

    def test_release_disc_is_retried_only_to_n2_then_stops(self) -> None:
        link = connected()
        release = link.disconnect(now=1.0)
        disc = release.actions[0].frame_no_fcs
        self.assertEqual(link.poll(now=4.0).actions[0].frame_no_fcs, disc)
        self.assertEqual(link.poll(now=7.0).actions[0].frame_no_fcs, disc)
        exhausted = link.poll(now=10.0)
        self.assertEqual(exhausted.actions, ())
        self.assertTrue(link.snapshot.retry_exhausted)
        self.assertEqual(link.snapshot.link.state, LinkState.AWAITING_RELEASE)
        self.assertIsNone(link.snapshot.t1_deadline)

    def test_dm_cancels_every_timer_and_fails_link_disconnected(self) -> None:
        link = connected()
        link.handle_frame(iframe(0, 0, b"IN"), now=1.0)
        link.send_information(b"OUT", now=1.1)
        result = link.handle_frame(u("DM", command=False), now=1.2)
        self.assertTrue(result.accepted)
        snapshot = link.snapshot
        self.assertEqual(snapshot.link.state, LinkState.DISCONNECTED)
        self.assertIsNone(snapshot.t1_deadline)
        self.assertIsNone(snapshot.t2_deadline)
        self.assertIsNone(snapshot.t3_deadline)

    def test_t2_delays_plain_rr_and_emits_it_once(self) -> None:
        link = connected()
        received = link.handle_frame(iframe(0, 0, b"HELLO"), now=1.0)
        self.assertEqual(received.delivered, (b"HELLO",))
        self.assertEqual(received.actions, ())
        self.assertEqual(link.snapshot.t2_deadline, 2.0)
        self.assertEqual(link.poll(now=1.999).actions, ())
        due = link.poll(now=2.0)
        self.assertEqual(len(due.actions), 1)
        rr = parse_frame(due.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual((rr["frame_type"], rr["nr"]), ("RR", 1))
        self.assertEqual(link.poll(now=2.1).actions, ())

    def test_poll_requires_immediate_final_and_never_arms_t2(self) -> None:
        link = connected()
        received = link.handle_frame(iframe(0, 0, b"POLL", poll_final=True), now=1.0)
        self.assertEqual(len(received.actions), 1)
        response = parse_frame(received.actions[0].frame_no_fcs, has_fcs=False)
        self.assertTrue(response["poll_final"])
        self.assertFalse(link.snapshot.pending_delayed_ack)

    def test_outbound_i_piggybacks_and_cancels_pending_t2_ack(self) -> None:
        link = connected()
        link.handle_frame(iframe(0, 0, b"IN"), now=1.0)
        self.assertTrue(link.snapshot.pending_delayed_ack)
        sent = link.send_information(b"OUT", now=1.5)
        parsed = parse_frame(sent.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual(parsed["nr"], 1)
        self.assertFalse(link.snapshot.pending_delayed_ack)
        self.assertEqual(link.poll(now=2.0).actions, ())

    def test_t3_idle_enquiry_uses_rr_poll_and_final_response_cancels_t1(self) -> None:
        link = connected()
        self.assertEqual(link.snapshot.t3_deadline, 10.1)
        enquiry = link.poll(now=10.1)
        parsed = parse_frame(enquiry.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual(parsed["frame_type"], "RR")
        self.assertTrue(parsed["poll_final"])
        self.assertTrue(parsed["destination"].flag)
        self.assertTrue(link.snapshot.probe_waiting)
        response = link.handle_frame(
            sframe("RR", 0, command=False, poll_final=True), now=10.2
        )
        self.assertTrue(response.accepted)
        self.assertFalse(link.snapshot.probe_waiting)
        self.assertIsNone(link.snapshot.t1_deadline)
        self.assertEqual(link.snapshot.t3_deadline, 20.2)

    def test_t3_does_not_fire_while_t1_supervises_outstanding_data(self) -> None:
        link = connected()
        link.send_information(b"WAIT", now=1.0)
        polled = link.poll(now=11.0)
        self.assertNotIn("T3", polled.reason)
        self.assertTrue(all(parse_frame(a.frame_no_fcs, has_fcs=False)["frame_type"] == "I" for a in polled.actions))

    def test_rej_actions_stay_inert_and_are_supervised_by_t1(self) -> None:
        link = connected()
        first = link.send_information(b"A", now=1.0).actions[0].frame_no_fcs
        second = link.send_information(b"B", now=1.1).actions[0].frame_no_fcs
        rejected = link.handle_frame(sframe("REJ", 0), now=1.2)
        self.assertEqual([a.frame_no_fcs for a in rejected.actions], [first, second])
        self.assertTrue(all(a.retransmission for a in rejected.actions))
        self.assertEqual(link.snapshot.t1_deadline, 4.2)

    def test_configuration_and_time_validation_fail_closed(self) -> None:
        for kwargs in (
            {"t1_seconds": 0.01}, {"t2_seconds": 3.0},
            {"t3_seconds": 3.0}, {"max_retries": 16},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises((TypeError, ValueError)):
                    LinkTimerConfig(**kwargs)
        link = connected()
        with self.assertRaisesRegex(ValueError, "monotonic"):
            link.poll(now=0.0)
        with self.assertRaises(ValueError):
            link.poll(now=float("nan"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
