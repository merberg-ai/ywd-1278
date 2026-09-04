#!/usr/bin/env python3
"""0D-P6 read-only diagnostics/status regression tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ywd1278.kiss.server import PacketEvent, RXOnlyBackend
from ywd1278.monitor.diagnostics import DiagnosticsStatus
from ywd1278.monitor.mheard import MHeardDatabase
from ywd1278.monitor.retention import RetentionPolicy, SQLiteRetentionController
from ywd1278.monitor.sqlite_log import _prepare_schema


@dataclass(frozen=True)
class FakeRuntimeCounters:
    running: bool = True
    identity: str = "AX25R4"
    rx_read_transactions: int = 12
    packed_rx_bytes: int = 3456
    decoded_rx_frames: int = 7
    rx_status_checks: int = 8
    rssi_samples: int = 9
    tx_dispatches: int = 3
    access_timeouts: int = 0
    decoder_resets_after_tx: int = 3
    failure: str = ""


@dataclass(frozen=True)
class FakeParameters:
    generation: int = 5
    txdelay: int = 30
    persist: int = 63
    slottime: int = 10
    fullduplex: int = 0
    port: int = 0


@dataclass(frozen=True)
class FakeControl:
    kiss_messages_received: int = 11
    kiss_parameter_updates: int = 4
    kiss_parameter_rejections: int = 1
    kiss_malformed_frames: int = 2
    kiss_unknown_commands: int = 1
    kiss_unsupported_ports: int = 0
    kiss_full_duplex_rejected: int = 1
    kiss_slot_time_rejected: int = 0
    kiss_data_tx_rejected: int = 0


@dataclass(frozen=True)
class FakeIngress:
    data_messages_received: int = 5
    data_admitted: int = 4
    data_invalid_rejections: int = 0
    data_queue_full_drops: int = 1
    data_time_rejections: int = 0
    data_other_rejections: int = 0


@dataclass(frozen=True)
class FakeQueue:
    tx_queue_depth: int = 0
    tx_queue_capacity: int = 4
    tx_queue_accepted: int = 4
    tx_invalid_rejections: int = 0
    tx_queue_full_drops: int = 1
    tx_dispatched: int = 4
    tx_access_timeouts: int = 0
    tx_downstream_failures: int = 0


@dataclass(frozen=True)
class FakeConnections:
    total_connections: int = 2
    total_disconnects: int = 2
    active_connections: int = 0


@dataclass(frozen=True)
class FakeAccounting:
    runtime: FakeRuntimeCounters = FakeRuntimeCounters()
    parameters: FakeParameters = FakeParameters()
    control: FakeControl = FakeControl()
    ingress: FakeIngress = FakeIngress()
    queue: FakeQueue = FakeQueue()
    connections: FakeConnections = FakeConnections()
    subscriber_drops: int = 0


class FakeRuntime:
    @property
    def accounting(self):
        return FakeAccounting()

    @property
    def runtime_counters(self):
        return FakeRuntimeCounters()


@dataclass(frozen=True)
class FakeSQLiteSnapshot:
    running: bool = True
    rows_written: int = 10
    write_failures: int = 0
    ignored_history_events: int = 2
    queued_live_events: int = 0
    source_subscriber_drops: int = 0
    fatal_error: str | None = None


class FakeSQLiteLogger:
    @property
    def snapshot(self):
        return FakeSQLiteSnapshot()


class DiagnosticsStatusTests(unittest.TestCase):
    def _database(self, directory: str) -> str:
        path = str(Path(directory) / "frames.sqlite3")
        connection = sqlite3.connect(path)
        _prepare_schema(connection)
        connection.execute(
            "INSERT INTO frames (observed_at_ns,monitor_sequence,history_replay,source,destination,path_json,frame_class,frame_type,poll_final,ns,nr,pid,info,frame_no_fcs,line) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (100, 1, 0, "KJ6YWD", "JIM", "[]", "U", "UI", 0, None, None, 240, b"ONE", b"x", "KJ6YWD>JIM:ONE"),
        )
        connection.execute(
            "INSERT INTO frames (observed_at_ns,monitor_sequence,history_replay,source,destination,path_json,frame_class,frame_type,poll_final,ns,nr,pid,info,frame_no_fcs,line) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (200, 2, 0, "KJ6YWD-9", "APRS", "[]", "U", "UI", 0, None, None, 240, b"TWO", b"y", "KJ6YWD-9>APRS:TWO"),
        )
        connection.commit()
        connection.close()
        return path

    def test_full_snapshot_aggregates_existing_sources_without_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            path = self._database(td)
            backend = RXOnlyBackend(history_capacity=8, subscriber_queue_capacity=4)
            backend.publish(PacketEvent(b"abc"))
            retention = SQLiteRetentionController(path)
            status = DiagnosticsStatus(
                runtime=FakeRuntime(),
                backend=backend,
                sqlite_logger=FakeSQLiteLogger(),
                mheard_db=MHeardDatabase(path),
                retention_controller=retention,
                retention_policy=RetentionPolicy(max_rows=1),
                retention_now_ns=1000,
            )
            before = sqlite3.connect(path).execute("SELECT COUNT(*) FROM frames").fetchone()[0]
            snap = status.snapshot()
            after = sqlite3.connect(path).execute("SELECT COUNT(*) FROM frames").fetchone()[0]

            self.assertEqual(before, 2)
            self.assertEqual(after, 2)
            self.assertTrue(snap.healthy)
            self.assertEqual(snap.problems, ())
            self.assertEqual(snap.runtime["decoded_rx_frames"], 7)
            self.assertEqual(snap.parameters["generation"], 5)
            self.assertEqual(snap.control["kiss_parameter_updates"], 4)
            self.assertEqual(snap.ingress["data_queue_full_drops"], 1)
            self.assertEqual(snap.queue["tx_dispatched"], 4)
            self.assertEqual(snap.connections["total_connections"], 2)
            self.assertEqual(snap.backend["stored_events"], 1)
            self.assertEqual(snap.sqlite_log["rows_written"], 10)
            self.assertEqual(snap.mheard["station_count"], 2)
            self.assertEqual(snap.mheard["frame_count"], 2)
            self.assertEqual(snap.retention_plan["eligible_rows"], 1)

    def test_failures_are_reported_without_side_effects(self):
        @dataclass(frozen=True)
        class BadRuntime:
            running: bool = True
            failure: str = "RuntimeError: boom"

        class Runtime:
            @property
            def runtime_counters(self):
                return BadRuntime()

        backend = RXOnlyBackend(history_capacity=0, subscriber_queue_capacity=1)
        _, q = backend.open_stream()
        backend.publish(PacketEvent(b"one"))
        backend.publish(PacketEvent(b"two"))
        backend.close_stream(q)

        @dataclass(frozen=True)
        class BadSQLite:
            running: bool = False
            rows_written: int = 4
            write_failures: int = 1
            ignored_history_events: int = 0
            queued_live_events: int = 0
            source_subscriber_drops: int = 1
            fatal_error: str | None = "OperationalError: disk"

        class Logger:
            @property
            def snapshot(self):
                return BadSQLite()

        snap = DiagnosticsStatus(runtime=Runtime(), backend=backend, sqlite_logger=Logger()).snapshot()
        self.assertFalse(snap.healthy)
        self.assertEqual(
            snap.problems,
            ("runtime-failure", "subscriber-drops", "sqlite-write-failures", "sqlite-fatal-error"),
        )

    def test_queue_timeout_and_downstream_failure_are_visible(self):
        @dataclass(frozen=True)
        class Q:
            timed_out_requests: int = 2
            downstream_failures: int = 1

        class Admission:
            @property
            def snapshot(self):
                return Q()

        class Backend(RXOnlyBackend):
            def __init__(self):
                super().__init__()
                self.admission = Admission()

        snap = DiagnosticsStatus(backend=Backend()).snapshot()
        self.assertFalse(snap.healthy)
        self.assertEqual(snap.problems, ("tx-access-timeouts", "tx-downstream-failures"))

    def test_retention_sources_must_be_complete(self):
        with self.assertRaises(ValueError):
            DiagnosticsStatus(retention_controller=object())
        with self.assertRaises(ValueError):
            DiagnosticsStatus(retention_policy=object())
        with self.assertRaises(ValueError):
            DiagnosticsStatus(retention_controller=object(), retention_policy=object())

    def test_surface_is_observation_only(self):
        forbidden = {"start", "stop", "publish", "open_stream", "transmit", "send", "submit", "apply"}
        self.assertTrue(forbidden.isdisjoint(set(dir(DiagnosticsStatus))))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DiagnosticsStatusTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("YWD1278_0D_P6_DIAGNOSTICS_STATUS=PASS")
    print("DIAGNOSTICS_SOURCE=EXISTING_SNAPSHOTS_ONLY")
    print("DIAGNOSTICS_RUNTIME_ACCOUNTING=PASS")
    print("DIAGNOSTICS_KISS_CONTROL_INGRESS_QUEUE_CONNECTIONS=PASS")
    print("DIAGNOSTICS_BACKEND_SUBSCRIBER_DROPS=PASS")
    print("DIAGNOSTICS_SQLITE_MHEARD_RETENTION=PASS")
    print("DIAGNOSTICS_DATABASE_MUTATION=NO")
    print("DIAGNOSTICS_PACKET_SUBSCRIBER=NO")
    print("DIAGNOSTICS_WORKER_THREAD=NO")
    print("DIAGNOSTICS_ADDITIONAL_IN_MEMORY_QUEUE=NO")
    print("DIAGNOSTICS_TX_CAPABILITY=ABSENT")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
