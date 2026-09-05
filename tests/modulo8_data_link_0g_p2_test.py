#!/usr/bin/env python3
"""Host behavior tests for 0G-P2 I/S-frame sequencing."""

from __future__ import annotations

import unittest

from ywd1278.ax25 import Address, parse_frame
from ywd1278.link.data_link import Modulo8DataLink, build_i_frame, build_s_frame
from ywd1278.link.modulo8 import LinkState, build_unnumbered_frame


LOCAL = Address.parse("KJ6YWD-10")
REMOTE = Address.parse("KJ6YWD-5")


def u(name: str, *, command: bool) -> bytes:
    return build_unnumbered_frame(
        source=REMOTE, destination=LOCAL, frame_type=name,
        command=command, poll_final=True,
    )


def iframe(ns: int, nr: int, info: bytes = b"REMOTE", *, poll_final: bool = False) -> bytes:
    return build_i_frame(
        source=REMOTE, destination=LOCAL, ns=ns, nr=nr,
        info=info, command=True, poll_final=poll_final,
    )


def sframe(name: str, nr: int, *, command: bool = False, poll_final: bool = False) -> bytes:
    return build_s_frame(
        source=REMOTE, destination=LOCAL, frame_type=name, nr=nr,
        command=command, poll_final=poll_final,
    )


def connected(*, maxframe: int = 4, paclen: int = 128) -> Modulo8DataLink:
    link = Modulo8DataLink(local=LOCAL, remote=REMOTE, maxframe=maxframe, paclen=paclen)
    result = link.handle_frame(u("SABM", command=True))
    assert result.accepted and link.snapshot.state is LinkState.CONNECTED
    return link


class Modulo8DataLinkP2Tests(unittest.TestCase):
    def test_send_window_and_cumulative_rr_acknowledgement(self) -> None:
        link = connected(maxframe=3)
        for ns in range(3):
            result = link.send_information(f"FRAME-{ns}".encode())
            self.assertTrue(result.accepted)
            parsed = parse_frame(result.actions[0].frame_no_fcs, has_fcs=False)
            self.assertEqual((parsed["ns"], parsed["nr"]), (ns, 0))
        self.assertEqual((link.snapshot.vs, link.snapshot.va, link.snapshot.outstanding), (3, 0, 3))
        self.assertIn("MAXFRAME", link.send_information(b"BLOCKED").reason)
        self.assertTrue(link.handle_frame(sframe("RR", 2)).accepted)
        self.assertEqual((link.snapshot.va, link.snapshot.outstanding), (2, 1))
        self.assertTrue(link.send_information(b"FRAME-3").accepted)

    def test_sequence_numbers_wrap_without_window_ambiguity(self) -> None:
        link = connected(maxframe=7)
        for value in range(7):
            self.assertTrue(link.send_information(bytes((value,))).accepted)
        self.assertTrue(link.handle_frame(sframe("RR", 6)).accepted)
        self.assertTrue(link.send_information(b"SEVEN").accepted)
        self.assertEqual(link.snapshot.vs, 0)
        self.assertTrue(link.handle_frame(sframe("RR", 0)).accepted)
        self.assertEqual((link.snapshot.va, link.snapshot.outstanding), (0, 0))

    def test_ordered_receive_delivers_once_and_returns_rr(self) -> None:
        link = connected()
        result = link.handle_frame(iframe(0, 0, b"HELLO"))
        self.assertTrue(result.accepted)
        self.assertEqual(result.delivered, (b"HELLO",))
        self.assertEqual(link.snapshot.vr, 1)
        rr = parse_frame(result.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual((rr["frame_type"], rr["nr"]), ("RR", 1))
        duplicate = link.handle_frame(iframe(0, 0, b"HELLO"))
        self.assertEqual(duplicate.delivered, ())
        rej = parse_frame(duplicate.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual((rej["frame_type"], rej["nr"]), ("REJ", 1))
        self.assertEqual(link.snapshot.delivered_frames, 1)

    def test_rnr_blocks_new_information_until_rr(self) -> None:
        link = connected()
        self.assertTrue(link.handle_frame(sframe("RNR", 0)).accepted)
        self.assertTrue(link.snapshot.remote_busy)
        self.assertIn("remote receiver is busy", link.send_information(b"WAIT").reason)
        self.assertTrue(link.handle_frame(sframe("RR", 0)).accepted)
        self.assertFalse(link.snapshot.remote_busy)
        self.assertTrue(link.send_information(b"GO").accepted)

    def test_rej_cumulatively_acks_then_returns_inert_retransmission_set(self) -> None:
        link = connected()
        original: list[bytes] = []
        for value in range(3):
            result = link.send_information(f"F{value}".encode())
            original.append(result.actions[0].frame_no_fcs)
        rejected = link.handle_frame(sframe("REJ", 1))
        self.assertTrue(rejected.accepted)
        self.assertEqual((link.snapshot.va, link.snapshot.outstanding), (1, 2))
        self.assertEqual([item.frame_no_fcs for item in rejected.actions], original[1:])
        self.assertTrue(all(item.retransmission for item in rejected.actions))

    def test_invalid_ack_is_atomic_and_does_not_drop_outstanding_frames(self) -> None:
        link = connected()
        link.send_information(b"ONE")
        before = link.snapshot
        result = link.handle_frame(sframe("RR", 3))
        self.assertFalse(result.accepted)
        after = link.snapshot
        self.assertEqual((after.vs, after.va, after.outstanding), (before.vs, before.va, before.outstanding))

    def test_local_busy_returns_rnr_without_delivering_or_advancing_vr(self) -> None:
        link = connected()
        busy = link.set_local_busy(True)
        self.assertEqual(parse_frame(busy.actions[0].frame_no_fcs, has_fcs=False)["frame_type"], "RNR")
        result = link.handle_frame(iframe(0, 0, b"HELD"))
        self.assertEqual(result.delivered, ())
        self.assertEqual(link.snapshot.vr, 0)
        self.assertEqual(parse_frame(result.actions[0].frame_no_fcs, has_fcs=False)["frame_type"], "RNR")
        ready = link.set_local_busy(False)
        self.assertEqual(parse_frame(ready.actions[0].frame_no_fcs, has_fcs=False)["frame_type"], "RR")

    def test_disconnect_or_dm_discards_sequence_and_outstanding_state(self) -> None:
        for ending in ("DISC", "DM"):
            with self.subTest(ending=ending):
                link = connected()
                link.send_information(b"UNACKED")
                result = link.handle_frame(u(ending, command=ending == "DISC"))
                self.assertTrue(result.accepted)
                self.assertEqual(link.snapshot.state, LinkState.DISCONNECTED)
                self.assertEqual((link.snapshot.vs, link.snapshot.vr, link.snapshot.va), (0, 0, 0))
                self.assertEqual(link.snapshot.outstanding, 0)

    def test_fresh_sabm_while_connected_resets_all_data_state(self) -> None:
        link = connected()
        link.send_information(b"UNACKED")
        link.handle_frame(iframe(0, 0, b"DELIVERED"))
        result = link.handle_frame(u("SABM", command=True))
        self.assertTrue(result.accepted)
        self.assertEqual(link.snapshot.state, LinkState.CONNECTED)
        self.assertEqual((link.snapshot.vs, link.snapshot.vr, link.snapshot.va), (0, 0, 0))
        self.assertEqual(link.snapshot.outstanding, 0)

    def test_poll_commands_receive_matching_final_response(self) -> None:
        link = connected()
        received = link.handle_frame(iframe(0, 0, b"POLL", poll_final=True))
        rr = parse_frame(received.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual(rr["frame_type"], "RR")
        self.assertTrue(rr["poll_final"])

        polled = link.handle_frame(sframe("RR", 0, command=True, poll_final=True))
        response = parse_frame(polled.actions[0].frame_no_fcs, has_fcs=False)
        self.assertEqual(response["frame_type"], "RR")
        self.assertTrue(response["poll_final"])
        self.assertFalse(response["destination"].flag)
        self.assertTrue(response["source"].flag)

    def test_paclen_state_and_frame_validation_fail_closed(self) -> None:
        link = connected(paclen=5)
        self.assertFalse(link.send_information(b"").accepted)
        self.assertIn("PACLEN", link.send_information(b"123456").reason)
        self.assertFalse(link.handle_frame(iframe(0, 0, b"123456")).accepted)
        unrelated = build_s_frame(
            source=Address.parse("OTHER-1"), destination=LOCAL,
            frame_type="RR", nr=0, command=False,
        )
        self.assertFalse(link.handle_frame(unrelated).accepted)
        self.assertEqual(link.snapshot.vr, 0)

    def test_disconnected_data_and_invalid_configuration_are_rejected(self) -> None:
        link = Modulo8DataLink(local=LOCAL, remote=REMOTE)
        self.assertFalse(link.send_information(b"NO LINK").accepted)
        self.assertFalse(link.handle_frame(iframe(0, 0)).accepted)
        for kwargs in ({"maxframe": 0}, {"maxframe": 8}, {"paclen": 0}, {"paclen": 257}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    Modulo8DataLink(local=LOCAL, remote=REMOTE, **kwargs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
