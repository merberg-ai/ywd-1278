#!/usr/bin/env python3
"""Host behavior tests for the 0G-P1 modulo-8 link state machine."""

from __future__ import annotations

import unittest

from ywd1278.ax25 import Address, parse_frame
from ywd1278.link.modulo8 import (
    LinkState,
    Modulo8Link,
    build_unnumbered_frame,
    sequence_distance,
    sequence_next,
)


LOCAL = Address.parse("KJ6YWD-10")
REMOTE = Address.parse("KJ6YWD-5")


def incoming(name: str, *, command: bool, poll_final: bool = True) -> bytes:
    return build_unnumbered_frame(
        source=REMOTE, destination=LOCAL, frame_type=name,
        command=command, poll_final=poll_final,
    )


class Modulo8LinkP1Tests(unittest.TestCase):
    def test_modulo8_sequence_arithmetic_wraps_exactly(self) -> None:
        self.assertEqual([sequence_next(value) for value in range(8)], [1, 2, 3, 4, 5, 6, 7, 0])
        self.assertEqual(sequence_distance(6, 1), 3)
        self.assertEqual(sequence_distance(1, 6), 5)
        for invalid in (-1, 8, True, 1.0):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    sequence_next(invalid)  # type: ignore[arg-type]

    def test_local_connect_and_ua_establish_link(self) -> None:
        link = Modulo8Link(local=LOCAL, remote=REMOTE)
        request = link.connect()
        self.assertTrue(request.accepted)
        self.assertEqual(request.before, LinkState.DISCONNECTED)
        self.assertEqual(request.after, LinkState.AWAITING_CONNECTION)
        self.assertEqual(len(request.actions), 1)
        parsed = parse_frame(request.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual(parsed["frame_type"], "SABM")
        self.assertTrue(parsed["poll_final"])
        self.assertTrue(parsed["destination"].flag)
        self.assertFalse(parsed["source"].flag)

        accepted = link.handle_frame(incoming("UA", command=False))
        self.assertTrue(accepted.accepted)
        self.assertEqual(accepted.after, LinkState.CONNECTED)
        self.assertEqual((link.snapshot.vs, link.snapshot.vr, link.snapshot.va), (0, 0, 0))

    def test_local_disconnect_and_ua_release_link(self) -> None:
        link = Modulo8Link(local=LOCAL, remote=REMOTE)
        link.handle_frame(incoming("SABM", command=True))
        release = link.disconnect()
        self.assertEqual(release.after, LinkState.AWAITING_RELEASE)
        parsed = parse_frame(release.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual(parsed["frame_type"], "DISC")
        self.assertTrue(parsed["poll_final"])
        done = link.handle_frame(incoming("UA", command=False))
        self.assertEqual(done.after, LinkState.DISCONNECTED)

    def test_remote_sabm_connects_and_returns_matching_ua_final(self) -> None:
        link = Modulo8Link(local=LOCAL, remote=REMOTE)
        result = link.handle_frame(incoming("SABM", command=True, poll_final=True))
        self.assertTrue(result.accepted)
        self.assertEqual(result.after, LinkState.CONNECTED)
        self.assertEqual(len(result.actions), 1)
        response = parse_frame(result.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual(response["frame_type"], "UA")
        self.assertTrue(response["poll_final"])
        self.assertFalse(response["destination"].flag)
        self.assertTrue(response["source"].flag)

    def test_remote_disc_returns_ua_or_dm_and_disconnects(self) -> None:
        connected = Modulo8Link(local=LOCAL, remote=REMOTE)
        connected.handle_frame(incoming("SABM", command=True))
        result = connected.handle_frame(incoming("DISC", command=True))
        self.assertEqual(result.after, LinkState.DISCONNECTED)
        self.assertEqual(result.actions[0].frame_type, "UA")

        disconnected = Modulo8Link(local=LOCAL, remote=REMOTE)
        result = disconnected.handle_frame(incoming("DISC", command=True))
        self.assertEqual(result.after, LinkState.DISCONNECTED)
        self.assertEqual(result.actions[0].frame_type, "DM")

    def test_dm_terminates_pending_or_established_link_without_reply(self) -> None:
        for setup in ("pending", "connected", "release"):
            with self.subTest(setup=setup):
                link = Modulo8Link(local=LOCAL, remote=REMOTE)
                if setup == "pending":
                    link.connect()
                else:
                    link.handle_frame(incoming("SABM", command=True))
                    if setup == "release":
                        link.disconnect()
                result = link.handle_frame(incoming("DM", command=False))
                self.assertTrue(result.accepted)
                self.assertEqual(result.after, LinkState.DISCONNECTED)
                self.assertEqual(result.actions, ())

    def test_collision_remote_sabm_wins_and_local_cancel_is_inert(self) -> None:
        link = Modulo8Link(local=LOCAL, remote=REMOTE)
        link.connect()
        collision = link.handle_frame(incoming("SABM", command=True))
        self.assertEqual(collision.after, LinkState.CONNECTED)
        self.assertEqual(collision.actions[0].frame_type, "UA")

        pending = Modulo8Link(local=LOCAL, remote=REMOTE)
        pending.connect()
        cancelled = pending.disconnect()
        self.assertEqual(cancelled.after, LinkState.DISCONNECTED)
        self.assertEqual(cancelled.actions, ())

    def test_invalid_or_unrelated_frames_leave_state_unchanged(self) -> None:
        link = Modulo8Link(local=LOCAL, remote=REMOTE)
        cases = (
            b"bad",
            build_unnumbered_frame(
                source=Address.parse("OTHER-1"), destination=LOCAL,
                frame_type="SABM", command=True, poll_final=True,
            ),
            build_unnumbered_frame(
                source=REMOTE, destination=Address.parse("OTHER-2"),
                frame_type="SABM", command=True, poll_final=True,
            ),
            incoming("SABM", command=False),
            incoming("UA", command=True),
        )
        for frame in cases:
            with self.subTest(frame=frame):
                result = link.handle_frame(frame)
                self.assertFalse(result.accepted)
                self.assertEqual(result.before, LinkState.DISCONNECTED)
                self.assertEqual(result.after, LinkState.DISCONNECTED)
        self.assertEqual(link.snapshot.received_frames, 0)

    def test_control_frame_information_is_rejected_without_state_change(self) -> None:
        link = Modulo8Link(local=LOCAL, remote=REMOTE)
        frame = incoming("SABM", command=True) + b"unexpected"
        result = link.handle_frame(frame)
        self.assertFalse(result.accepted)
        self.assertIn("must not contain information", result.reason)
        self.assertEqual(link.snapshot.state, LinkState.DISCONNECTED)

    def test_ua_without_final_or_in_wrong_state_is_ignored(self) -> None:
        link = Modulo8Link(local=LOCAL, remote=REMOTE)
        link.connect()
        result = link.handle_frame(incoming("UA", command=False, poll_final=False))
        self.assertFalse(result.accepted)
        self.assertEqual(result.after, LinkState.AWAITING_CONNECTION)
        self.assertFalse(link.connect().accepted)

    def test_generated_control_frame_can_include_valid_fcs(self) -> None:
        frame = build_unnumbered_frame(
            source=LOCAL, destination=REMOTE, frame_type="SABM",
            command=True, poll_final=True, include_fcs=True,
        )
        parsed = parse_frame(frame, has_fcs=True)
        self.assertEqual(parsed["frame_type"], "SABM")


if __name__ == "__main__":
    unittest.main(verbosity=2)
