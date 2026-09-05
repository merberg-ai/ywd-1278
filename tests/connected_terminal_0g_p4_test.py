#!/usr/bin/env python3
"""Host behavior tests for the inert 0G-P4 connected terminal."""

from __future__ import annotations

import unittest

from ywd1278.ax25 import Address, parse_frame
from ywd1278.link.data_link import build_i_frame, build_s_frame
from ywd1278.link.modulo8 import LinkState, build_unnumbered_frame
from ywd1278.link.terminal_session import ConnectedTerminalSession, TerminalMode
from ywd1278.link.timed_link import LinkTimerConfig


LOCAL = Address.parse("KJ6YWD-10")
REMOTE = Address.parse("KJ6YWD-5")
TIMERS = LinkTimerConfig(t1_seconds=3.0, t2_seconds=1.0, t3_seconds=10.0, max_retries=2)


def remote_u(name: str, *, command: bool = False) -> bytes:
    return build_unnumbered_frame(
        source=REMOTE, destination=LOCAL, frame_type=name, command=command, poll_final=True
    )


def established(*, paclen: int = 128, maxframe: int = 4) -> ConnectedTerminalSession:
    session = ConnectedTerminalSession(
        local=LOCAL, paclen=paclen, maxframe=maxframe, timers=TIMERS
    )
    request = session.execute_line("CONNECT KJ6YWD-5", now=0.0)
    assert request.accepted and request.link is not None
    accepted = session.handle_frame(remote_u("UA"), now=0.1)
    assert accepted.accepted
    return session


class ConnectedTerminalP4Tests(unittest.TestCase):
    def test_connect_ua_enters_connected_text_mode(self) -> None:
        session = ConnectedTerminalSession(local=LOCAL, timers=TIMERS)
        request = session.execute_line("CONNECT KJ6YWD-5", now=0.0)
        self.assertEqual(parse_frame(request.link.actions[0].frame_no_fcs, has_fcs=False)["frame_type"], "SABM")
        self.assertEqual(session.snapshot.link_state, LinkState.AWAITING_CONNECTION)
        accepted = session.handle_frame(remote_u("UA"), now=0.1)
        self.assertEqual(accepted.lines, ("CONNECTED TO KJ6YWD-5",))
        self.assertEqual(session.snapshot.mode, TerminalMode.CONNECTED)

    def test_connected_line_prepares_exactly_one_inert_i_frame(self) -> None:
        session = established()
        sent = session.execute_line("hello packet", now=1.0)
        self.assertTrue(sent.accepted)
        self.assertEqual(len(sent.link.actions), 1)
        parsed = parse_frame(sent.link.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual((parsed["frame_type"], parsed["info"]), ("I", b"hello packet"))
        self.assertEqual(session.snapshot.submitted_lines, 1)

    def test_command_escape_preserves_link_and_converse_returns(self) -> None:
        session = established()
        escaped = session.execute_line(" command ", now=1.0)
        self.assertEqual(escaped.lines, ("COMMAND MODE",))
        self.assertEqual(session.snapshot.link_state, LinkState.CONNECTED)
        status = session.execute_line("CSTATUS", now=1.1)
        self.assertIn("STATE=CONNECTED MODE=COMMAND", status.lines[0])
        resumed = session.execute_line("CONVERSE", now=1.2)
        self.assertTrue(resumed.accepted)
        self.assertEqual(session.snapshot.mode, TerminalMode.CONNECTED)

    def test_incoming_information_is_delivered_once_and_controls_are_escaped(self) -> None:
        session = established()
        incoming = build_i_frame(
            source=REMOTE, destination=LOCAL, ns=0, nr=0,
            info=b"A\r\n\x1bB", command=True,
        )
        received = session.handle_frame(incoming, now=1.0)
        self.assertEqual(received.lines, (r"A\x0d\x0a\x1bB",))
        self.assertEqual(received.link.delivered, (b"A\r\n\x1bB",))
        self.assertEqual(session.snapshot.delivered_lines, 1)

    def test_paclen_ascii_empty_and_window_fail_closed(self) -> None:
        session = established(paclen=4, maxframe=1)
        for line in ("", "ABCDE", "NOPE\t", "café"):
            with self.subTest(line=line):
                self.assertFalse(session.execute_line(line, now=1.0).accepted)
        self.assertTrue(session.execute_line("GOOD", now=1.0).accepted)
        blocked = session.execute_line("NEXT", now=1.1)
        self.assertFalse(blocked.accepted)
        self.assertIn("MAXFRAME", blocked.reason)

    def test_rr_ack_reopens_window(self) -> None:
        session = established(maxframe=1)
        session.execute_line("ONE", now=1.0)
        rr = build_s_frame(source=REMOTE, destination=LOCAL, frame_type="RR", nr=1)
        self.assertTrue(session.handle_frame(rr, now=1.1).accepted)
        self.assertTrue(session.execute_line("TWO", now=1.2).accepted)

    def test_orderly_local_and_remote_disconnect_return_command_mode(self) -> None:
        session = established()
        session.execute_line("COMMAND", now=1.0)
        release = session.execute_line("DISCONNECT", now=1.1)
        self.assertEqual(parse_frame(release.link.actions[0].frame_no_fcs, has_fcs=False)["frame_type"], "DISC")
        done = session.handle_frame(remote_u("UA"), now=1.2)
        self.assertEqual(done.lines, ("DISCONNECTED FROM KJ6YWD-5",))
        self.assertEqual(session.snapshot.link_state, LinkState.DISCONNECTED)

        other = established()
        remote = other.handle_frame(remote_u("DISC", command=True), now=1.0)
        self.assertEqual(parse_frame(remote.link.actions[0].frame_no_fcs, has_fcs=False)["frame_type"], "UA")
        self.assertEqual(other.snapshot.mode, TerminalMode.COMMAND)

    def test_disconnect_cancels_pending_connect_without_fake_disc(self) -> None:
        session = ConnectedTerminalSession(local=LOCAL, timers=TIMERS)
        session.execute_line("CONNECT KJ6YWD-5", now=0.0)
        cancelled = session.execute_line("DISCONNECT", now=0.1)
        self.assertTrue(cancelled.accepted)
        self.assertEqual(cancelled.link.actions, ())
        self.assertEqual(cancelled.lines, ("DISCONNECTED FROM KJ6YWD-5",))
        self.assertEqual(session.snapshot.link_state, LinkState.DISCONNECTED)

    def test_t1_failure_returns_command_mode_and_inert_disc(self) -> None:
        session = established()
        session.execute_line("NO ACK", now=1.0)
        session.poll(now=4.0)
        session.poll(now=7.0)
        failed = session.poll(now=10.0)
        self.assertIn("LINK FAILURE", failed.lines[0])
        self.assertEqual(session.snapshot.mode, TerminalMode.COMMAND)
        self.assertEqual(parse_frame(failed.link.actions[0].frame_no_fcs, has_fcs=False)["frame_type"], "DISC")
        self.assertEqual(session.poll(now=10.1).lines, ())

    def test_invalid_commands_and_destinations_do_not_create_link(self) -> None:
        session = ConnectedTerminalSession(local=LOCAL, timers=TIMERS)
        for line in ("CONNECT", "CONNECT BAD!", "CONNECT KJ6YWD-10", "CONVERSE", "DISCONNECT", "RECONNECT KJ6YWD"):
            with self.subTest(line=line):
                self.assertFalse(session.execute_line(line, now=0.0).accepted)
                self.assertEqual(session.snapshot.link_state, LinkState.DISCONNECTED)

    def test_timers_remain_caller_driven_and_actions_remain_visible(self) -> None:
        session = ConnectedTerminalSession(local=LOCAL, timers=TIMERS)
        first = session.execute_line("CONNECT KJ6YWD-5", now=0.0)
        retry = session.poll(now=3.0)
        self.assertEqual(retry.link.actions[0].frame_no_fcs, first.link.actions[0].frame_no_fcs)
        self.assertTrue(retry.link.actions[0].retransmission)


if __name__ == "__main__":
    unittest.main(verbosity=2)
