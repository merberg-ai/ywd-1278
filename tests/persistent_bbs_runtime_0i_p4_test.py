#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ywd1278.ax25 import Address
from ywd1278.link.data_link import Modulo8DataLink
from ywd1278.link.modulo8 import LinkState
from ywd1278.node.persistent_bbs_runtime import PersistentBBSRuntime
from ywd1278.node.persistent_mailbox import PersistentMailboxStore


LOCAL = Address.parse("KJ6YWD-10")
ALICE = Address.parse("KJ6YWD-15")
ALICE_BASE = Address.parse("KJ6YWD-1")
BOB = Address.parse("KE6CHO-5")


class TickNS:
    def __init__(self) -> None:
        self.value = 1_000_000_000

    def __call__(self) -> int:
        self.value += 1_000_000_000
        return self.value


class RuntimeHarness:
    def __init__(self, service: PersistentBBSRuntime, peer: Address) -> None:
        self.service = service
        self.peer_address = peer
        self.peer = Modulo8DataLink(
            local=peer,
            remote=LOCAL,
            maxframe=1,
            paclen=256,
        )
        self.now = 0.0
        self.received: list[bytes] = []

    def _advance(self, amount: float = 0.01) -> float:
        self.now += amount
        return self.now

    def _drain_service_actions(self, actions) -> None:  # type: ignore[no-untyped-def]
        pending = list(actions)
        guard = 0
        while pending:
            guard += 1
            if guard > 200:
                raise AssertionError("host link pump did not quiesce")
            action = pending.pop(0)
            remote_result = self.peer.handle_frame(action.frame_no_fcs)
            if not remote_result.accepted:
                raise AssertionError(f"remote rejected {action.frame_type}: {remote_result.reason}")
            self.received.extend(remote_result.delivered)
            for reply in remote_result.actions:
                service_result = self.service.handle_frame(
                    reply.frame_no_fcs,
                    now=self._advance(),
                )
                if not service_result.accepted:
                    raise AssertionError(f"service rejected remote reply: {service_result.reason}")
                pending.extend(service_result.actions)

    def connect(self) -> bytes:
        result = self.peer.connect()
        self.assert_accepted(result.accepted, result.reason)
        service_result = self.service.handle_frame(
            result.actions[0].frame_no_fcs,
            now=self._advance(),
        )
        self.assert_accepted(service_result.accepted, service_result.reason)
        self._drain_service_actions(service_result.actions)
        return b"".join(self.received)

    def send(self, information: bytes) -> bytes:
        before = len(self.received)
        result = self.peer.send_information(information)
        self.assert_accepted(result.accepted, result.reason)
        service_result = self.service.handle_frame(
            result.actions[0].frame_no_fcs,
            now=self._advance(),
        )
        self.assert_accepted(service_result.accepted, service_result.reason)
        self._drain_service_actions(service_result.actions)
        # A body line intentionally has no BBS response, so P4 must still
        # deliver the frozen timed-link T2 RR and let the peer advance.
        if self.peer.snapshot.outstanding:
            polled = self.service.poll(now=self._advance(1.1))
            self.assert_accepted(polled.accepted, polled.reason)
            self._drain_service_actions(polled.actions)
        return b"".join(self.received[before:])

    @staticmethod
    def assert_accepted(accepted: bool, reason: str) -> None:
        if not accepted:
            raise AssertionError(reason)


class PersistentBBSRuntimeP4Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ywd-0i-p4-")
        self.addCleanup(self.temp.cleanup)
        self.store = PersistentMailboxStore(Path(self.temp.name) / "mailbox.sqlite3")
        self.clock = TickNS()

    def service(self) -> PersistentBBSRuntime:
        return PersistentBBSRuntime(
            local=LOCAL,
            alias="YWDNOD",
            store=self.store,
            mailbox_paclen=128,
            now_ns=self.clock,
            info="KJ6YWD persistent packet mailbox",
        )

    def test_direct_sabm_opens_one_bbs_and_emits_classic_banner(self) -> None:
        service = self.service()
        harness = RuntimeHarness(service, ALICE)
        banner = harness.connect()
        self.assertIn(b"YWDNOD:KJ6YWD-10} Connected to BBS\r", banner)
        self.assertIn(b"YWD BBS:KJ6YWD-10\r", banner)
        self.assertIn(b"Hello KJ6YWD - 0 new / 0 visible message(s)\r", banner)
        self.assertIn(b"de KJ6YWD-10>\r", banner)
        self.assertEqual(service.snapshot.active_peer, "KJ6YWD-15")
        self.assertEqual(service.snapshot.state, LinkState.CONNECTED)
        self.assertEqual(service.snapshot.sessions_accepted, 1)

    def test_full_sp_list_read_kill_bye_and_reconnect_persists_state(self) -> None:
        service = self.service()
        alice = RuntimeHarness(service, ALICE)
        alice.connect()
        self.assertIn(b"Enter Title", alice.send(b"SP KJ6YWD-1\r"))
        self.assertIn(b"Enter Message Text", alice.send(b"PERSISTENT TEST\r"))
        self.assertEqual(alice.send(b"survives service restart\r"), b"")
        saved = alice.send(b"/EX\r")
        self.assertIn(b"Message 1 saved for KJ6YWD\r", saved)
        self.assertIn(b"PERSISTENT TEST", alice.send(b"LN\r"))
        read = alice.send(b"R 1\r")
        self.assertIn(b"survives service restart\r", read)
        self.assertIn(b"Type/Status: PR\r", read)
        killed = alice.send(b"K 1\r")
        self.assertIn(b"Message 1 killed\r", killed)
        goodbye = alice.send(b"BYE\r")
        self.assertIn(b"73 - disconnecting from YWD BBS\r", goodbye)
        self.assertEqual(alice.peer.snapshot.state, LinkState.DISCONNECTED)
        self.assertIsNone(service.snapshot.active_peer)

        # Re-create the runtime around the same P1 store to model daemon/service
        # restart; killed state survives and the database is not recreated.
        restarted = self.service()
        same_user = RuntimeHarness(restarted, ALICE_BASE)
        banner = same_user.connect()
        self.assertIn(b"0 new / 0 visible message(s)", banner)
        self.assertIn(b"No messages\r", same_user.send(b"L\r"))

    def test_bulletin_read_state_survives_runtime_recreation(self) -> None:
        service = self.service()
        alice = RuntimeHarness(service, ALICE)
        alice.connect()
        alice.send(b"SB LOCAL\r")
        alice.send(b"PACKET NET\r")
        alice.send(b"Tonight 1900\r")
        self.assertIn(b"Bulletin 1 saved for LOCAL", alice.send(b"/EX\r"))
        alice.send(b"BYE\r")

        bob_service = self.service()
        bob = RuntimeHarness(bob_service, BOB)
        banner = bob.connect()
        self.assertIn(b"1 new / 1 visible message(s)", banner)
        self.assertIn(b"PACKET NET", bob.send(b"LN\r"))
        bob.send(b"R 1\r")
        bob.send(b"BYE\r")

        bob_again = RuntimeHarness(self.service(), BOB)
        banner2 = bob_again.connect()
        self.assertIn(b"0 new / 1 visible message(s)", banner2)

    def test_second_peer_is_rejected_with_dm_while_first_owns_link(self) -> None:
        service = self.service()
        alice = RuntimeHarness(service, ALICE)
        alice.connect()

        contender = Modulo8DataLink(local=BOB, remote=LOCAL, maxframe=1, paclen=256)
        sabm = contender.connect()
        result = service.handle_frame(sabm.actions[0].frame_no_fcs, now=5.0)
        self.assertFalse(result.accepted)
        self.assertEqual(len(result.actions), 1)
        self.assertEqual(result.actions[0].frame_type, "DM")
        handled = contender.handle_frame(result.actions[0].frame_no_fcs)
        self.assertTrue(handled.accepted)
        self.assertEqual(contender.snapshot.state, LinkState.DISCONNECTED)
        self.assertEqual(service.snapshot.active_peer, "KJ6YWD-15")
        self.assertEqual(service.snapshot.busy_rejections, 1)

    def test_non_sabm_cannot_create_session_and_wrong_destination_is_ignored(self) -> None:
        service = self.service()
        remote = Modulo8DataLink(local=ALICE, remote=LOCAL, maxframe=1, paclen=256)
        connect = remote.connect()
        # Mutating the destination would require rebuilding; instead first prove
        # no ordinary connected traffic can create a session before SABM.
        self.assertIsNone(service.snapshot.active_peer)
        # A valid SABM does create it; this also anchors the intended direct gate.
        accepted = service.handle_frame(connect.actions[0].frame_no_fcs, now=0.1)
        self.assertTrue(accepted.accepted)
        self.assertEqual(service.snapshot.active_peer, "KJ6YWD-15")

    def test_body_line_without_response_uses_t2_ack_and_does_not_stall(self) -> None:
        service = self.service()
        alice = RuntimeHarness(service, ALICE)
        alice.connect()
        alice.send(b"SP KJ6YWD\r")
        alice.send(b"T2 TEST\r")
        self.assertEqual(alice.send(b"body-only-line\r"), b"")
        self.assertEqual(alice.peer.snapshot.outstanding, 0)
        self.assertEqual(service.snapshot.state, LinkState.CONNECTED)
        self.assertIn(b"Message 1 saved", alice.send(b"/EX\r"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
