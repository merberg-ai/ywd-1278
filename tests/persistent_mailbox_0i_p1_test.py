#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

from ywd1278.ax25 import Address
from ywd1278.node.persistent_mailbox import (
    BBS_MAILBOX_SCHEMA_VERSION,
    MailboxMessageType,
    PersistentMailboxAuthorizationError,
    PersistentMailboxDuplicateBidError,
    PersistentMailboxSchemaError,
    PersistentMailboxStore,
)


ALICE = Address.parse("KJ6YWD-1")
ALICE_MOBILE = Address.parse("KJ6YWD-15")
BOB = Address.parse("KE6CHO-5")
CAROL = Address.parse("W6UH-2")


class PersistentMailboxP1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="ywd-0i-p1-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "mailbox.sqlite3"

    def store(self) -> PersistentMailboxStore:
        return PersistentMailboxStore(self.path)

    def test_protected_schema_and_reopen(self) -> None:
        store = self.store()
        self.assertEqual(store.path, self.path)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(
                int(connection.execute("PRAGMA user_version").fetchone()[0]),
                BBS_MAILBOX_SCHEMA_VERSION,
            )
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        self.assertIn("messages", tables)
        self.assertIn("message_reads", tables)
        self.assertEqual(PersistentMailboxStore(self.path).counts_for(ALICE).visible, 0)

    def test_personal_mail_uses_base_callsign_across_ssids_and_persists_read_state(self) -> None:
        store = self.store()
        message = store.deposit_personal(
            sender=BOB,
            recipient=ALICE,
            subject="HELLO",
            body=b"old school packet mail",
            created_at_ns=10,
            bid="10_KE6CHO",
        )
        self.assertEqual(message.recipient, "KJ6YWD")
        listed = store.list_visible(ALICE_MOBILE)
        self.assertEqual(len(listed), 1)
        self.assertTrue(listed[0].unread)
        read = store.read_for(ALICE_MOBILE, message.message_id, read_at_ns=20)
        self.assertIsNotNone(read)
        self.assertEqual(read.body, b"old school packet mail")
        self.assertFalse(store.list_visible(ALICE)[0].unread)

        reopened = PersistentMailboxStore(self.path)
        self.assertFalse(reopened.list_visible(ALICE_MOBILE)[0].unread)
        self.assertEqual(reopened.list_visible(ALICE_MOBILE, new_only=True), ())

    def test_bulletin_read_state_is_independent_per_user(self) -> None:
        store = self.store()
        bulletin = store.deposit_bulletin(
            sender=ALICE,
            topic="LOCAL",
            subject="NET TONIGHT",
            body=b"Packet net at 1900 local.",
            created_at_ns=30,
            bid="LOCAL-30-KJ6YWD",
        )
        self.assertEqual(bulletin.message_type, MailboxMessageType.BULLETIN)
        self.assertEqual(bulletin.recipient, "LOCAL")
        self.assertTrue(store.list_visible(BOB)[0].unread)
        self.assertTrue(store.list_visible(CAROL)[0].unread)

        store.read_for(BOB, bulletin.message_id, read_at_ns=31)
        self.assertFalse(store.list_visible(BOB)[0].unread)
        self.assertTrue(store.list_visible(CAROL)[0].unread)
        self.assertEqual(store.counts_for(BOB).bulletin_new, 0)
        self.assertEqual(store.counts_for(CAROL).bulletin_new, 1)

    def test_new_listing_order_and_sent_listing_are_bounded_views(self) -> None:
        store = self.store()
        first = store.deposit_personal(
            sender=BOB, recipient=ALICE, subject="ONE", body=b"1", created_at_ns=1
        )
        second = store.deposit_personal(
            sender=BOB, recipient=ALICE, subject="TWO", body=b"2", created_at_ns=2
        )
        third = store.deposit_personal(
            sender=ALICE, recipient=BOB, subject="THREE", body=b"3", created_at_ns=3
        )
        store.read_for(ALICE, first.message_id, read_at_ns=4)

        self.assertEqual(
            [item.message_id for item in store.list_visible(ALICE, new_only=True)],
            [second.message_id],
        )
        self.assertEqual(
            [item.message_id for item in store.list_visible(ALICE, oldest_first=True)],
            [first.message_id, second.message_id],
        )
        self.assertEqual(
            [item.message_id for item in store.list_sent(ALICE)],
            [third.message_id],
        )

    def test_personal_message_may_be_killed_by_recipient_or_sender(self) -> None:
        store = self.store()
        to_alice = store.deposit_personal(
            sender=BOB, recipient=ALICE, subject="A", body=b"a", created_at_ns=1
        )
        to_bob = store.deposit_personal(
            sender=ALICE, recipient=BOB, subject="B", body=b"b", created_at_ns=2
        )
        self.assertTrue(store.kill_for(ALICE_MOBILE, to_alice.message_id, killed_at_ns=5))
        self.assertTrue(store.kill_for(ALICE, to_bob.message_id, killed_at_ns=6))
        self.assertEqual(store.list_visible(ALICE), ())
        self.assertEqual(store.list_sent(ALICE), ())
        self.assertFalse(store.kill_for(ALICE, to_bob.message_id, killed_at_ns=7))

    def test_bulletin_kill_is_sender_only(self) -> None:
        store = self.store()
        bulletin = store.deposit_bulletin(
            sender=ALICE,
            topic="ALL",
            subject="BULLETIN",
            body=b"hello everyone",
            created_at_ns=1,
        )
        with self.assertRaises(PersistentMailboxAuthorizationError):
            store.kill_for(BOB, bulletin.message_id, killed_at_ns=2)
        self.assertTrue(store.kill_for(ALICE_MOBILE, bulletin.message_id, killed_at_ns=3))
        self.assertEqual(store.list_visible(BOB), ())
        self.assertIsNone(store.read_for(BOB, bulletin.message_id, read_at_ns=4))

    def test_bid_is_case_normalized_and_unique(self) -> None:
        store = self.store()
        first = store.deposit_personal(
            sender=ALICE,
            recipient=BOB,
            subject="BID",
            body=b"one",
            created_at_ns=1,
            bid="abc-123",
        )
        self.assertEqual(first.bid, "ABC-123")
        with self.assertRaises(PersistentMailboxDuplicateBidError):
            store.deposit_bulletin(
                sender=BOB,
                topic="ALL",
                subject="DUP",
                body=b"two",
                created_at_ns=2,
                bid="ABC-123",
            )

    def test_counts_cover_personal_bulletin_and_sent(self) -> None:
        store = self.store()
        personal = store.deposit_personal(
            sender=BOB, recipient=ALICE, subject="P", body=b"p", created_at_ns=1
        )
        store.deposit_bulletin(
            sender=BOB, topic="ALL", subject="B", body=b"b", created_at_ns=2
        )
        store.deposit_personal(
            sender=ALICE, recipient=BOB, subject="S", body=b"s", created_at_ns=3
        )
        counts = store.counts_for(ALICE)
        self.assertEqual(
            (counts.visible, counts.new, counts.personal_new, counts.bulletin_new, counts.sent),
            (2, 2, 1, 1, 1),
        )
        store.read_for(ALICE, personal.message_id, read_at_ns=4)
        counts = store.counts_for(ALICE)
        self.assertEqual((counts.new, counts.personal_new, counts.bulletin_new), (1, 0, 1))

    def test_unversioned_nonempty_database_fails_closed(self) -> None:
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE surprise(x INTEGER)")
            connection.commit()
        with self.assertRaises(PersistentMailboxSchemaError):
            PersistentMailboxStore(self.path)

    def test_invalid_topic_body_limit_and_foreign_personal_read_fail_closed(self) -> None:
        store = self.store()
        with self.assertRaises(ValueError):
            store.deposit_bulletin(
                sender=ALICE,
                topic="bad topic!",
                subject="BAD",
                body=b"x",
                created_at_ns=1,
            )
        with self.assertRaises(ValueError):
            store.deposit_personal(
                sender=ALICE,
                recipient=BOB,
                subject="BAD",
                body=b"\x00",
                created_at_ns=1,
            )
        private = store.deposit_personal(
            sender=ALICE,
            recipient=BOB,
            subject="PRIVATE",
            body=b"for bob",
            created_at_ns=2,
        )
        self.assertIsNone(store.read_for(CAROL, private.message_id, read_at_ns=3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
