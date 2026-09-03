"""Bounded-subscriber SQLite frame logging for 0D-P3.

The logger deliberately does not add an in-memory queue.  It atomically opens
one existing bounded PacketEvent subscriber on RXOnlyBackend, discards the
history snapshot, and reuses the frozen 0D-P1 MonitorSubscription decoder for
live records only.  SQLite work is owned by one dedicated logger thread.

Disk slowness or failure therefore cannot block the modem/RX/TX scheduler and
cannot create an unbounded RAM backlog.  The authoritative source queue remains
the already-qualified bounded backend queue and its drop counter.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from queue import Empty
import sqlite3
import threading
import time
from typing import Callable

from ywd1278.kiss.server import RXOnlyBackend

from .stream import MonitorRecord, MonitorSubscription


SQLITE_FRAME_LOG_SCHEMA_VERSION = 1


class SQLiteFrameLogError(RuntimeError):
    """Base failure for the isolated SQLite monitor sink."""


class SQLiteFrameLogSchemaError(SQLiteFrameLogError):
    """Raised when an existing database is not the exact supported schema."""


@dataclass(frozen=True)
class SQLiteFrameLogSnapshot:
    running: bool
    rows_written: int
    write_failures: int
    ignored_history_events: int
    queued_live_events: int
    source_subscriber_drops: int
    fatal_error: str | None


_COLUMNS = (
    "id",
    "observed_at_ns",
    "monitor_sequence",
    "history_replay",
    "source",
    "destination",
    "path_json",
    "frame_class",
    "frame_type",
    "poll_final",
    "ns",
    "nr",
    "pid",
    "info",
    "frame_no_fcs",
    "line",
)


def _prepare_schema(connection: sqlite3.Connection) -> None:
    row = connection.execute("PRAGMA user_version").fetchone()
    version = int(row[0]) if row is not None else -1

    if version == 0:
        existing = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        if existing:
            raise SQLiteFrameLogSchemaError(
                "refusing unversioned non-empty SQLite database"
            )

        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.executescript(
            """
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                observed_at_ns INTEGER NOT NULL,
                monitor_sequence INTEGER NOT NULL,
                history_replay INTEGER NOT NULL CHECK (history_replay IN (0, 1)),
                source TEXT NOT NULL,
                destination TEXT NOT NULL,
                path_json TEXT NOT NULL,
                frame_class TEXT NOT NULL,
                frame_type TEXT NOT NULL,
                poll_final INTEGER NOT NULL CHECK (poll_final IN (0, 1)),
                ns INTEGER,
                nr INTEGER,
                pid INTEGER,
                info BLOB NOT NULL,
                frame_no_fcs BLOB NOT NULL,
                line TEXT NOT NULL
            );
            CREATE INDEX frames_observed_at_idx
                ON frames(observed_at_ns, id);
            """
        )
        connection.execute(
            f"PRAGMA user_version={SQLITE_FRAME_LOG_SCHEMA_VERSION}"
        )
        connection.commit()
    elif version != SQLITE_FRAME_LOG_SCHEMA_VERSION:
        raise SQLiteFrameLogSchemaError(
            f"unsupported SQLite frame-log schema version {version}; "
            f"expected {SQLITE_FRAME_LOG_SCHEMA_VERSION}"
        )

    actual = tuple(
        str(item[1]) for item in connection.execute("PRAGMA table_info(frames)")
    )
    if actual != _COLUMNS:
        raise SQLiteFrameLogSchemaError(
            f"frames table columns do not match schema v{SQLITE_FRAME_LOG_SCHEMA_VERSION}"
        )

    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")


def _insert_record(connection: sqlite3.Connection, record: MonitorRecord) -> None:
    if record.history_replay:
        raise SQLiteFrameLogError("history replay must never be persisted by 0D-P3")
    connection.execute(
        """
        INSERT INTO frames (
            observed_at_ns, monitor_sequence, history_replay,
            source, destination, path_json,
            frame_class, frame_type, poll_final,
            ns, nr, pid, info, frame_no_fcs, line
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(record.observed_at_ns),
            int(record.sequence),
            0,
            record.source,
            record.destination,
            json.dumps(record.path, separators=(",", ":")),
            record.frame_class,
            record.frame_type,
            1 if record.poll_final else 0,
            record.ns,
            record.nr,
            record.pid,
            sqlite3.Binary(record.info),
            sqlite3.Binary(record.frame_no_fcs),
            record.line,
        ),
    )
    connection.commit()


class SQLiteFrameLogger:
    """One-thread, live-only SQLite sink over an existing bounded subscriber."""

    def __init__(
        self,
        backend: RXOnlyBackend,
        path: str | Path,
        *,
        clock_ns: Callable[[], int] = time.time_ns,
        poll_interval: float = 0.05,
        sqlite_timeout: float = 5.0,
        startup_timeout: float = 5.0,
    ) -> None:
        if poll_interval <= 0.0:
            raise ValueError("poll_interval must be > 0")
        if sqlite_timeout <= 0.0:
            raise ValueError("sqlite_timeout must be > 0")
        if startup_timeout <= 0.0:
            raise ValueError("startup_timeout must be > 0")

        self._backend = backend
        self._path = Path(path)
        self._clock_ns = clock_ns
        self._poll_interval = float(poll_interval)
        self._sqlite_timeout = float(sqlite_timeout)
        self._startup_timeout = float(startup_timeout)

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._startup_ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._subscription: MonitorSubscription | None = None
        self._running = False
        self._rows_written = 0
        self._write_failures = 0
        self._ignored_history_events = 0
        self._fatal_error: str | None = None
        self._startup_error: BaseException | None = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def snapshot(self) -> SQLiteFrameLogSnapshot:
        with self._lock:
            subscription = self._subscription
            running = self._running
            rows_written = self._rows_written
            write_failures = self._write_failures
            ignored_history_events = self._ignored_history_events
            fatal_error = self._fatal_error
        if subscription is None:
            queued = 0
            drops = self._backend.snapshot.subscriber_drops
        else:
            upstream = subscription.snapshot
            queued = upstream.queued_live_events
            drops = upstream.source_subscriber_drops
        return SQLiteFrameLogSnapshot(
            running=running,
            rows_written=rows_written,
            write_failures=write_failures,
            ignored_history_events=ignored_history_events,
            queued_live_events=queued,
            source_subscriber_drops=drops,
            fatal_error=fatal_error,
        )

    def start(self) -> None:
        """Register the bounded live source, then start SQLite ownership.

        The backend history snapshot is intentionally ignored.  Registration
        and history capture happen under the backend's existing lock, so events
        published after registration enter the live bounded queue exactly once.
        """

        with self._lock:
            if self._thread is not None:
                raise RuntimeError("SQLiteFrameLogger instances are single-start")

            history, live_queue = self._backend.open_stream()
            self._ignored_history_events = len(history)
            self._subscription = MonitorSubscription(
                self._backend,
                [],
                live_queue,
                clock_ns=self._clock_ns,
            )
            self._stop_event.clear()
            self._startup_ready.clear()
            self._startup_error = None
            self._fatal_error = None
            thread = threading.Thread(
                target=self._worker,
                name="ywd1278-sqlite-frame-log",
                daemon=True,
            )
            self._thread = thread
            thread.start()

        if not self._startup_ready.wait(self._startup_timeout):
            self._stop_event.set()
            thread.join(timeout=self._startup_timeout)
            raise SQLiteFrameLogError("SQLite frame-log startup timed out")

        with self._lock:
            startup_error = self._startup_error
        if startup_error is not None:
            thread.join(timeout=self._startup_timeout)
            if isinstance(startup_error, SQLiteFrameLogError):
                raise startup_error
            raise SQLiteFrameLogError(str(startup_error)) from startup_error

    def _worker(self) -> None:
        connection: sqlite3.Connection | None = None
        with self._lock:
            subscription = self._subscription
        assert subscription is not None

        try:
            connection = sqlite3.connect(
                str(self._path),
                timeout=self._sqlite_timeout,
            )
            _prepare_schema(connection)
            with self._lock:
                self._running = True
            self._startup_ready.set()

            while not self._stop_event.is_set():
                try:
                    record = subscription.get(timeout=self._poll_interval)
                except Empty:
                    continue

                try:
                    _insert_record(connection, record)
                except (sqlite3.Error, SQLiteFrameLogError) as exc:
                    with self._lock:
                        self._write_failures += 1
                        self._fatal_error = f"{type(exc).__name__}: {exc}"
                    break
                else:
                    with self._lock:
                        self._rows_written += 1

        except (sqlite3.Error, OSError, SQLiteFrameLogError) as exc:
            with self._lock:
                if not self._startup_ready.is_set():
                    self._startup_error = exc
                self._fatal_error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                self._running = False
            self._startup_ready.set()
            if connection is not None:
                connection.close()
            subscription.close()

    def stop(self, *, timeout: float = 2.0) -> None:
        if timeout <= 0.0:
            raise ValueError("timeout must be > 0")
        with self._lock:
            thread = self._thread
        if thread is None:
            return
        self._stop_event.set()
        thread.join(timeout=timeout)
        if thread.is_alive():
            raise RuntimeError("SQLite frame-log thread did not stop")

    def __enter__(self) -> "SQLiteFrameLogger":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
