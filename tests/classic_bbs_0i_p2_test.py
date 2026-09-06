#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ywd1278.ax25 import Address
from ywd1278.node.classic_bbs import ClassicBBSAction, ClassicBBSSession
from ywd1278.node.persistent_mailbox import PersistentMailboxStore


LOCAL = Address.parse("KJ6YWD-10")
ALICE = Address.parse("KJ6YWD-1")
ALICE_MOBILE = Address.parse("KJ6YWD-15")
BOB = Address.parse("KE6CHO-5")


def rendered(actions: tuple[ClassicBBSAction, ...]) -> str:
    return b"".join(action.data for action in actions).decode("ascii")


class TickClock:
    def __init__(self, start: int = 1_000_000_000) -> None:
        self.value = start

    def __call__(self) -> int:
        self.value += 1_000_000_000
        return self.value


class ClassicBBSP2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ywd-0i-p2-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "mailbox.sqlite3"
        self.store = PersistentMailboxStore(self.path)
        self.clock = TickClock()

    def session(self, peer: Address = ALICE, paclen: int = 128) -> ClassicBBSSession:
        return ClassicBBSSession(
            local=LOCAL,
            peer=peer,
            store=self.store,
            paclen=paclen,
            now_ns=self.clock,
        )

    def test_banner_is_classic_prompted_and_paclen_bounded(self) -> None:
        session = self.session(paclen=32)
        actions = session.banner()
        text = rendered(actions)
        self.assertIn("YWD BBS:KJ6YWD-10\r", text)
        self.assertIn("Hello KJ6YWD - 0 new / 0 visible message(s)\r", text)
        self.assertTrue(text.endswith("de KJ6YWD-10>\r"))
        self.assertTrue(all(1 <= len(action.data) <= 32 for action in actions))

    def test_help_info_and_unknown_command(self) -> None:
        session = self.session()
        help_result = session.feed(b"H\r")
        text = rendered(help_result.actions)
        self.assertTrue(help_result.accepted)
        self.assertIn("SP <call>", text)
        self.assertIn("SB <topic>", text)
        self.assertIn("LN [n]", text)
        self.assertTrue(text.endswith("de KJ6YWD-10>\r"))

        info = session.feed(b"INFO\r")
        self.assertIn("forwarding is disabled", rendered(info.actions))
        bad = session.feed(b"FOOBAR\r")
        self.assertFalse(bad.accepted)
        self.assertIn("? unknown BBS command", rendered(bad.actions))

    def test_personal_sp_list_read_and_cross_ssid_mailbox_identity(self) -> None:
        session = self.session(ALICE)
        self.assertIn("Enter Title", rendered(session.feed(b"SP KE6CHO-5\r").actions))
        self.assertIn("Enter Message Text", rendered(session.feed(b"HELLO BOB\r").actions))
        self.assertEqual(session.feed(b"Line one\r").actions, ())
        saved = session.feed(b"Line two\r/EX\r")
        self.assertTrue(saved.accepted)
        self.assertIn("Message 1 saved for KE6CHO", rendered(saved.actions))

        bob = self.session(BOB)
        listing = bob.feed(b"LN\r")
        text = rendered(listing.actions)
        self.assertIn("    1  PN", text)
        self.assertIn("HELLO BOB", text)

        read = bob.feed(b"R 1\r")
        text = rendered(read.actions)
        self.assertIn("From: KJ6YWD\r", text)
        self.assertIn("To: KE6CHO\r", text)
        self.assertIn("Type/Status: PR\r", text)
        self.assertIn("Line one\rLine two\r", text)
        self.assertIn("[End of Message #1 from KJ6YWD]", text)
        self.assertEqual(rendered(bob.feed(b"LN\r").actions), "No messages\rde KJ6YWD-10>\r")

        # A different KJ6YWD SSID owns the same mailbox and sent-message view.
        mobile = self.session(ALICE_MOBILE)
        mine = rendered(mobile.feed(b"LM\r").actions)
        self.assertIn("HELLO BOB", mine)

    def test_bulletin_is_visible_to_multiple_users_with_independent_new_state(self) -> None:
        alice = self.session(ALICE)
        alice.feed(b"SB LOCAL\r")
        alice.feed(b"PACKET NET\r")
        alice.feed(b"Tonight at 1900\r")
        saved = alice.feed(b"/EX\r")
        self.assertIn("Bulletin 1 saved for LOCAL", rendered(saved.actions))

        bob = self.session(BOB)
        self.assertIn("PACKET NET", rendered(bob.feed(b"LN\r").actions))
        bob.feed(b"R 1\r")
        self.assertEqual(rendered(bob.feed(b"LN\r").actions), "No messages\rde KJ6YWD-10>\r")

        # Alice's read state is independent, even though she authored it.
        fresh_alice = self.session(ALICE_MOBILE)
        self.assertIn("PACKET NET", rendered(fresh_alice.feed(b"LN\r").actions))

    def test_kill_enforces_store_ownership(self) -> None:
        message = self.store.deposit_personal(
            sender=BOB,
            recipient=ALICE,
            subject="PRIVATE",
            body=b"hello",
            created_at_ns=self.clock(),
        )
        alice = self.session(ALICE_MOBILE)
        killed = alice.feed(f"K {message.message_id}\r".encode("ascii"))
        self.assertTrue(killed.accepted)
        self.assertIn("Message 1 killed", rendered(killed.actions))
        self.assertIn("No messages", rendered(alice.feed(b"L\r").actions))

        bulletin = self.store.deposit_bulletin(
            sender=ALICE,
            topic="ALL",
            subject="SYSOP",
            body=b"notice",
            created_at_ns=self.clock(),
        )
        bob = self.session(BOB)
        denied = bob.feed(f"K {bulletin.message_id}\r".encode("ascii"))
        self.assertFalse(denied.accepted)
        self.assertIn("only the personal recipient or original sender", rendered(denied.actions))

    def test_lr_oldest_first_and_list_limit(self) -> None:
        for number in range(1, 4):
            self.store.deposit_personal(
                sender=BOB,
                recipient=ALICE,
                subject=f"MSG {number}",
                body=str(number).encode("ascii"),
                created_at_ns=self.clock(),
            )
        session = self.session()
        text = rendered(session.feed(b"LR 2\r").actions)
        positions = [text.index("MSG 1"), text.index("MSG 2")]
        self.assertLess(positions[0], positions[1])
        self.assertNotIn("MSG 3", text)
        rejected = session.feed(b"L 101\r")
        self.assertFalse(rejected.accepted)

    def test_fragmented_input_and_multiple_commands_in_one_information_payload(self) -> None:
        session = self.session()
        partial = session.feed(b"IN")
        self.assertTrue(partial.accepted)
        self.assertEqual(partial.actions, ())
        result = session.feed(b"FO\rLN\r")
        text = rendered(result.actions)
        self.assertIn("YWD-1278 persistent packet BBS", text)
        self.assertIn("No messages", text)
        self.assertEqual(session.snapshot.commands, 2)

    def test_abort_and_empty_body_do_not_deposit(self) -> None:
        session = self.session()
        session.feed(b"SP KE6CHO\r")
        aborted = session.feed(b"/ABORT\r")
        self.assertIn("Message aborted", rendered(aborted.actions))
        self.assertEqual(self.store.counts_for(BOB).visible, 0)

        session.feed(b"SP KE6CHO\r")
        session.feed(b"EMPTY TEST\r")
        empty = session.feed(b"/EX\r")
        self.assertFalse(empty.accepted)
        self.assertIn("message body is empty", rendered(empty.actions))
        self.assertTrue(session.snapshot.composing)
        session.feed(b"/ABORT\r")
        self.assertFalse(session.snapshot.composing)

    def test_bye_is_orderly_terminal_action(self) -> None:
        session = self.session()
        result = session.feed(b"BYE\r")
        self.assertTrue(result.accepted)
        self.assertTrue(result.close_requested)
        self.assertTrue(result.actions[-1].close)
        self.assertIn("73 - disconnecting", rendered(result.actions))
        later = session.feed(b"H\r")
        self.assertFalse(later.accepted)
        self.assertTrue(later.close_requested)

    def test_input_buffer_overflow_fails_closed_and_clears_composition(self) -> None:
        session = self.session()
        session.feed(b"SP KE6CHO\r")
        self.assertTrue(session.snapshot.composing)
        result = session.feed(b"X" * 513)
        self.assertFalse(result.accepted)
        self.assertIn("input buffer overflow", rendered(result.actions))
        self.assertFalse(session.snapshot.composing)
        self.assertEqual(session.snapshot.buffered_bytes, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
