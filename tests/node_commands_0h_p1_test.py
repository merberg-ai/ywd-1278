#!/usr/bin/env python3
from __future__ import annotations

import unittest

from ywd1278.ax25 import Address
from ywd1278.node.commands import NodeCommandSession


class NodeCommandsP1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.node = NodeCommandSession(callsign=Address.parse("KJ6YWD-5"))

    def test_banner_and_safe_queries(self) -> None:
        self.assertEqual(self.node.banner()[0], b"YWD-1278 NODE YWDNOD:KJ6YWD-5\r")
        self.assertIn(b"INFO", b"".join(self.node.feed(b"HELP\r").responses))
        self.assertIn(b"KJ6YWD-5", b"".join(self.node.feed(b"INFO\r").responses))
        self.assertIn(b"YWD-1278", b"".join(self.node.feed(b"VERSION\r").responses))

    def test_fragmented_and_multiple_commands(self) -> None:
        self.assertEqual(self.node.feed(b"HE").responses, ())
        result = self.node.feed(b"LP\rINFO\n")
        self.assertIn(b"HELP", b"".join(result.responses))
        self.assertEqual(self.node.snapshot.commands, 2)

    def test_unknown_nonascii_control_and_overflow_fail_closed(self) -> None:
        self.assertFalse(self.node.feed(b"MAIL\r").accepted)
        self.assertIn(b"ASCII", self.node.feed(b"\xff\r").responses[0])
        self.assertIn(b"printable", self.node.feed(b"BAD\tX\r").responses[0])
        self.assertIn(b"overflow", self.node.feed(b"A" * 257).responses[0])
        self.assertEqual(self.node.snapshot.buffered_bytes, 0)

    def test_bye_closes_and_future_input_is_rejected(self) -> None:
        result = self.node.feed(b"BYE\rINFO\r")
        self.assertTrue(result.close_requested)
        self.assertEqual(result.responses, (b"BYE\r",))
        self.assertFalse(self.node.feed(b"INFO\r").accepted)

    def test_alias_and_type_validation(self) -> None:
        for alias in ("", "TOOLONG", "BAD-1", "é"):
            with self.assertRaises(ValueError):
                NodeCommandSession(callsign=Address.parse("KJ6YWD-5"), alias=alias)
        with self.assertRaises(TypeError):
            self.node.feed("INFO\r")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main(verbosity=2)
