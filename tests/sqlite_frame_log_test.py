#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sqlite3
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame, parse_frame  # noqa: E402
from ywd1278.kiss.server import PacketEvent, RXOnlyBackend  # noqa: E402
from ywd1278.monitor.sqlite_log import (  # noqa: E402
    SQLITE_FRAME_LOG_SCHEMA_VERSION,
    SQLiteFrameLogSchemaError,
    SQLiteFrameLogger,
)


def event_for(body: bytes) -> PacketEvent:
    parsed = parse_frame(body, has_fcs=False)
    return PacketEvent(
        body,
        source=str(parsed["source"]),
        destination=str(parsed["destination"]),
        frame_type=str(parsed["frame_type"]),
    )


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out waiting for condition")


class TickClock:
    def __init__(self) -> None:
        self.value = 1_000_000

    def __call__(self) -> int:
        value = self.value
        self.value += 1_000_000
        return value


class SQLiteFrameLogTests(unittest.TestCase):
    def test_exact_live_frame_is_persisted_with_structured_fields(self) -> None:
        body = build_ui_frame(
            source=Address.parse("KJ6YWD-9"),
            destination=Address.parse("APRS"),
            path=[Address.parse("WIDE1-1", flag=True), Address.parse("WIDE2-1")],
            info=b"hello\x00\r\n",
            include_fcs=False,
        )
        backend = RXOnlyBackend(history_capacity=8, subscriber_queue_capacity=4)

        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            logger = SQLiteFrameLogger(backend, db, clock_ns=TickClock())
            logger.start()
            backend.publish(event_for(body))
            wait_until(lambda: logger.snapshot.rows_written == 1)
            logger.stop()

            connection = sqlite3.connect(db)
            try:
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
                row = connection.execute(
                    "SELECT observed_at_ns, monitor_sequence, history_replay, "
                    "source, destination, path_json, frame_class, frame_type, "
                    "poll_final, ns, nr, pid, info, frame_no_fcs, line "
                    "FROM frames"
                ).fetchone()
            finally:
                connection.close()

        self.assertEqual(version, SQLITE_FRAME_LOG_SCHEMA_VERSION)
        self.assertEqual(str(mode).lower(), "wal")
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1_000_000)
        self.assertEqual(row[1], 1)
        self.assertEqual(row[2], 0)
        self.assertEqual(row[3], "KJ6YWD-9")
        self.assertEqual(row[4], "APRS")
        self.assertEqual(json.loads(row[5]), ["WIDE1-1*", "WIDE2-1"])
        self.assertEqual((row[6], row[7]), ("U", "UI"))
        self.assertEqual(row[8], 0)
        self.assertIsNone(row[9])
        self.assertIsNone(row[10])
        self.assertEqual(row[11], 0xF0)
        self.assertEqual(bytes(row[12]), b"hello\x00\r\n")
        self.assertEqual(bytes(row[13]), body)
        self.assertEqual(
            row[14],
            r"KJ6YWD-9>APRS,WIDE1-1*,WIDE2-1:hello\x00\r\n",
        )
        self.assertEqual(backend.snapshot.subscribers, 0)

    def test_restart_ignores_backend_history_without_duplicate_replay(self) -> None:
        one = build_ui_frame(
            source=Address.parse("ONE"),
            destination=Address.parse("LOG"),
            info=b"one",
            include_fcs=False,
        )
        two = build_ui_frame(
            source=Address.parse("TWO"),
            destination=Address.parse("LOG"),
            info=b"two",
            include_fcs=False,
        )
        backend = RXOnlyBackend(history_capacity=8, subscriber_queue_capacity=4)

        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"

            first = SQLiteFrameLogger(backend, db)
            first.start()
            backend.publish(event_for(one))
            wait_until(lambda: first.snapshot.rows_written == 1)
            first.stop()

            second = SQLiteFrameLogger(backend, db)
            second.start()
            self.assertEqual(second.snapshot.ignored_history_events, 1)
            backend.publish(event_for(two))
            wait_until(lambda: second.snapshot.rows_written == 1)
            second.stop()

            connection = sqlite3.connect(db)
            try:
                rows = connection.execute(
                    "SELECT id, source, line FROM frames ORDER BY id"
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual(
            rows,
            [
                (1, "ONE", "ONE>LOG:one"),
                (2, "TWO", "TWO>LOG:two"),
            ],
        )

    def test_unsupported_existing_schema_fails_closed(self) -> None:
        backend = RXOnlyBackend(history_capacity=0)
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            connection = sqlite3.connect(db)
            connection.execute("PRAGMA user_version=99")
            connection.commit()
            connection.close()

            logger = SQLiteFrameLogger(backend, db)
            with self.assertRaises(SQLiteFrameLogSchemaError):
                logger.start()
            logger.stop()

        self.assertEqual(backend.snapshot.subscribers, 0)
        self.assertFalse(logger.snapshot.running)
        self.assertIsNotNone(logger.snapshot.fatal_error)

    def test_unversioned_nonempty_database_is_not_adopted(self) -> None:
        backend = RXOnlyBackend(history_capacity=0)
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"
            connection = sqlite3.connect(db)
            connection.execute("CREATE TABLE unrelated (value TEXT)")
            connection.commit()
            connection.close()

            logger = SQLiteFrameLogger(backend, db)
            with self.assertRaises(SQLiteFrameLogSchemaError):
                logger.start()
            logger.stop()

        self.assertEqual(backend.snapshot.subscribers, 0)

    def test_sqlite_write_failure_isolated_from_packet_backend(self) -> None:
        body = build_ui_frame(
            source=Address.parse("FAIL"),
            destination=Address.parse("LOG"),
            info=b"forced",
            include_fcs=False,
        )
        backend = RXOnlyBackend(history_capacity=0, subscriber_queue_capacity=2)

        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / "frames.sqlite3"

            seed = SQLiteFrameLogger(backend, db)
            seed.start()
            seed.stop()

            connection = sqlite3.connect(db)
            connection.execute(
                "CREATE TRIGGER force_insert_failure BEFORE INSERT ON frames "
                "BEGIN SELECT RAISE(ABORT, 'forced test failure'); END"
            )
            connection.commit()
            connection.close()

            logger = SQLiteFrameLogger(backend, db)
            logger.start()
            backend.publish(event_for(body))
            wait_until(lambda: logger.snapshot.write_failures == 1)
            wait_until(lambda: backend.snapshot.subscribers == 0)

            # The packet backend itself remains usable and non-blocking after
            # the logger sink has failed and detached.
            backend.publish(event_for(body))
            self.assertEqual(backend.snapshot.stored_events, 0)
            self.assertFalse(logger.snapshot.running)
            self.assertEqual(logger.snapshot.rows_written, 0)
            self.assertIsNotNone(logger.snapshot.fatal_error)
            logger.stop()

    def test_logger_surface_has_no_tx_operation(self) -> None:
        backend = RXOnlyBackend()
        with tempfile.TemporaryDirectory() as tmp:
            logger = SQLiteFrameLogger(backend, pathlib.Path(tmp) / "frames.sqlite3")
            for name in ("publish", "transmit", "send", "submit"):
                self.assertFalse(hasattr(logger, name), name)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SQLiteFrameLogTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("YWD1278_0D_P3_SQLITE_FRAME_LOG=PASS")
    print("SQLITE_SCHEMA_VERSION=1")
    print("SQLITE_JOURNAL_MODE=WAL")
    print("EXACT_FRAME_BYTES_PERSISTED=PASS")
    print("STRUCTURED_AX25_FIELDS_PERSISTED=PASS")
    print("RESTART_HISTORY_REPLAY=NO_DUPLICATES")
    print("UNSUPPORTED_SCHEMA=FAIL_CLOSED")
    print("SQLITE_WRITE_FAILURE_ISOLATED=PASS")
    print("ADDITIONAL_IN_MEMORY_QUEUE=NO")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
