#!/usr/bin/env python3
from __future__ import annotations
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from ywd1278.ax25 import Address
from ywd1278.node.mailbox import MailboxQuotaError, MailboxSchemaError, MailboxStore

A = Address.parse("KJ6YWD-10")
B = Address.parse("KJ6YWD-5")
C = Address.parse("KJ6YWD-1")

class MailboxStorageP2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "mailbox.sqlite3"
        self.store = MailboxStore(self.path)
    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_create_mode_deposit_list_and_owner_read(self) -> None:
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        first = self.store.deposit(sender=A, recipient=B, subject="Hello", body=b"Line 1\rLine 2", created_at_ns=10)
        self.store.deposit(sender=C, recipient=B, subject="Second", body=b"Body", created_at_ns=20)
        listing = self.store.list_for(B)
        self.assertEqual([x.subject for x in listing], ["Second", "Hello"])
        self.assertEqual(self.store.read_for(B, first.message_id), first)
        self.assertIsNone(self.store.read_for(C, first.message_id))

    def test_content_and_identifier_validation(self) -> None:
        cases = ({"subject": "", "body": b"x"}, {"subject": "x" * 65, "body": b"x"}, {"subject": "café", "body": b"x"}, {"subject": "ok", "body": b""}, {"subject": "ok", "body": b"\x00"})
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.store.deposit(sender=A, recipient=B, created_at_ns=1, **item)
        with self.assertRaises(ValueError):
            self.store.read_for(B, 0)

    def test_parameterized_content_cannot_escape_recipient(self) -> None:
        message = self.store.deposit(sender=A, recipient=B, subject="'; DROP TABLE messages;--", body=b"safe", created_at_ns=1)
        self.assertEqual(self.store.read_for(B, message.message_id).subject, "'; DROP TABLE messages;--")
        self.assertEqual(len(self.store.list_for(B)), 1)

    def test_quotas_are_checked_inside_write_transaction(self) -> None:
        with patch("ywd1278.node.mailbox.MAX_MESSAGES_PER_RECIPIENT", 1):
            self.store.deposit(sender=A, recipient=B, subject="one", body=b"one", created_at_ns=1)
            with self.assertRaises(MailboxQuotaError):
                self.store.deposit(sender=A, recipient=B, subject="two", body=b"two", created_at_ns=2)
        self.assertEqual(len(self.store.list_for(B)), 1)

    def test_path_and_schema_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            MailboxStore("relative.sqlite3")
        target = Path(self.temp.name) / "target"
        target.touch()
        link = Path(self.temp.name) / "link"
        link.symlink_to(target)
        with self.assertRaises(Exception):
            MailboxStore(link)
        bad = Path(self.temp.name) / "bad.sqlite3"
        with sqlite3.connect(bad) as db:
            db.execute("CREATE TABLE surprise(x)")
        with self.assertRaises(MailboxSchemaError):
            MailboxStore(bad)

    def test_replaced_database_identity_fails_closed(self) -> None:
        replacement = Path(self.temp.name) / "replacement.sqlite3"
        self.path.rename(replacement)
        self.path.symlink_to(replacement)
        with self.assertRaisesRegex(Exception, "identity changed"):
            self.store.list_for(B)

if __name__ == "__main__": unittest.main(verbosity=2)
