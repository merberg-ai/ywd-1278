#!/usr/bin/env python3
"""Host behavior tests for exclusive 0G-P5 connected-session ownership."""

from __future__ import annotations

import unittest

from ywd1278.ax25 import Address, parse_frame
from ywd1278.link.modulo8 import LinkState, build_unnumbered_frame
from ywd1278.link.session_manager import ConnectedSessionManager
from ywd1278.link.timed_link import LinkTimerConfig


LOCAL = Address.parse("KJ6YWD-10")
REMOTE = Address.parse("KJ6YWD-5")
TIMERS = LinkTimerConfig(t1_seconds=3.0, t2_seconds=1.0, t3_seconds=10.0, max_retries=1)


def remote_u(name: str, *, command: bool = False) -> bytes:
    return build_unnumbered_frame(
        source=REMOTE, destination=LOCAL, frame_type=name, command=command, poll_final=True
    )


def manager(*, maximum: int = 3) -> ConnectedSessionManager:
    value = ConnectedSessionManager(local=LOCAL, max_sessions=maximum, timers=TIMERS)
    assert value.open_session("telnet-1").accepted
    assert value.open_session("pty-1").accepted
    return value


class ConnectedSessionsP5Tests(unittest.TestCase):
    def test_registration_is_unique_bounded_and_ordered(self) -> None:
        value = manager(maximum=2)
        self.assertEqual(value.snapshot.session_ids, ("telnet-1", "pty-1"))
        self.assertFalse(value.open_session("telnet-1").accepted)
        self.assertFalse(value.open_session("third").accepted)
        for bad in ("", "has space", "bad/route", "x" * 33):
            self.assertFalse(ConnectedSessionManager(local=LOCAL).open_session(bad).accepted)

    def test_first_connect_claims_exclusive_owner_and_contention_is_atomic(self) -> None:
        value = manager()
        first = value.execute_line("telnet-1", "CONNECT KJ6YWD-5", now=0.0)
        self.assertTrue(first.accepted)
        blocked = value.execute_line("pty-1", "CONNECT N0CALL", now=0.0)
        self.assertFalse(blocked.accepted)
        self.assertIn("owned by session telnet-1", blocked.reason)
        self.assertEqual(value.snapshot.owner_session_id, "telnet-1")
        self.assertEqual(value.session_snapshot("pty-1").link_state, LinkState.DISCONNECTED)
        self.assertEqual(value.snapshot.contention_rejections, 1)

    def test_bad_connect_releases_provisional_lease(self) -> None:
        value = manager()
        bad = value.execute_line("telnet-1", "CONNECT BAD!", now=0.0)
        self.assertFalse(bad.accepted)
        self.assertIsNone(value.snapshot.owner_session_id)
        self.assertTrue(value.execute_line("pty-1", "CONNECT KJ6YWD-5", now=0.0).accepted)

    def test_only_owner_receives_frames_and_timer_actions(self) -> None:
        value = manager()
        connect = value.execute_line("pty-1", "CONNECT KJ6YWD-5", now=0.0)
        retry = value.poll(now=3.0)
        self.assertEqual(retry.session_id, "pty-1")
        self.assertEqual(retry.terminal.link.actions[0].frame_no_fcs, connect.terminal.link.actions[0].frame_no_fcs)
        accepted = value.handle_frame(remote_u("UA"), now=3.1)
        self.assertEqual(accepted.session_id, "pty-1")
        self.assertEqual(value.session_snapshot("pty-1").link_state, LinkState.CONNECTED)

    def test_remote_release_returns_lease_for_other_session(self) -> None:
        value = manager()
        value.execute_line("telnet-1", "CONNECT KJ6YWD-5", now=0.0)
        value.handle_frame(remote_u("UA"), now=0.1)
        released = value.handle_frame(remote_u("DISC", command=True), now=1.0)
        self.assertEqual(parse_frame(released.terminal.link.actions[0].frame_no_fcs, has_fcs=False)["frame_type"], "UA")
        self.assertIsNone(value.snapshot.owner_session_id)
        self.assertTrue(value.execute_line("pty-1", "CONNECT KJ6YWD-5", now=1.1).accepted)

    def test_idle_session_close_never_disturbs_owner(self) -> None:
        value = manager()
        value.execute_line("telnet-1", "CONNECT KJ6YWD-5", now=0.0)
        closed = value.close_session("pty-1", now=0.1)
        self.assertTrue(closed.accepted)
        self.assertEqual(value.snapshot.owner_session_id, "telnet-1")
        self.assertEqual(value.snapshot.session_ids, ("telnet-1",))

    def test_owner_close_waits_for_orderly_release_before_deletion(self) -> None:
        value = manager()
        value.execute_line("telnet-1", "CONNECT KJ6YWD-5", now=0.0)
        value.handle_frame(remote_u("UA"), now=0.1)
        closing = value.close_session("telnet-1", now=1.0)
        self.assertEqual(value.snapshot.pending_close_session_id, "telnet-1")
        self.assertEqual(parse_frame(closing.terminal.link.actions[0].frame_no_fcs, has_fcs=False)["frame_type"], "DISC")
        self.assertFalse(value.execute_line("telnet-1", "CSTATUS", now=1.1).accepted)
        value.handle_frame(remote_u("UA"), now=1.2)
        self.assertEqual(value.snapshot.session_ids, ("pty-1",))
        self.assertIsNone(value.snapshot.owner_session_id)

    def test_pending_connect_close_cancels_immediately_without_disc(self) -> None:
        value = manager()
        value.execute_line("telnet-1", "CONNECT KJ6YWD-5", now=0.0)
        closed = value.close_session("telnet-1", now=0.1)
        self.assertTrue(closed.accepted)
        self.assertEqual(closed.terminal.link.actions, ())
        self.assertNotIn("telnet-1", value.snapshot.session_ids)
        self.assertIsNone(value.snapshot.owner_session_id)

    def test_timeout_releases_failed_connection_lease(self) -> None:
        value = manager()
        value.execute_line("telnet-1", "CONNECT KJ6YWD-5", now=0.0)
        value.poll(now=3.0)
        failed = value.poll(now=6.0)
        self.assertIn("LINK FAILURE", failed.terminal.lines[0])
        self.assertIsNone(value.snapshot.owner_session_id)

    def test_no_owner_frame_and_poll_are_inert(self) -> None:
        value = manager()
        self.assertFalse(value.handle_frame(remote_u("SABM", command=True), now=0.0).accepted)
        self.assertTrue(value.poll(now=0.0).accepted)


if __name__ == "__main__":
    unittest.main(verbosity=2)
