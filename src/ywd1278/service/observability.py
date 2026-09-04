"""Production composition of the frozen 0D observability components.

Stage C deliberately adds no packet decoder, modem owner, transport, transmit
surface, scheduler, or destructive maintenance loop.  It receives the already
assembled product backend/runtime from Stage B and composes only the qualified
0D read/observe facilities around them:

* decoded monitor subscriptions over the existing bounded PacketEvent backend;
* one bounded-subscriber SQLite frame logger when configured;
* read-only MHEARD queries over that logger's qualified schema; and
* one-shot diagnostics aggregation over already-existing snapshots/counters.

Retention remains explicit maintenance and is not scheduled or applied here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ywd1278.kiss.server import RXOnlyBackend
from ywd1278.monitor.diagnostics import DiagnosticsSnapshot, DiagnosticsStatus
from ywd1278.monitor.mheard import MHeardDatabase
from ywd1278.monitor.sqlite_log import SQLiteFrameLogger
from ywd1278.monitor.stream import DecodedMonitorStream, MonitorSubscription


@dataclass(frozen=True)
class ProductObservabilityConfig:
    enabled: bool
    log_frames: bool
    database_path: Path | None

    def __post_init__(self) -> None:
        if self.log_frames and not self.enabled:
            raise ValueError("frame logging requires monitor.enabled=true")
        if self.log_frames and self.database_path is None:
            raise ValueError("frame logging requires a database path")
        if self.database_path is not None and not self.database_path.is_absolute():
            raise ValueError("monitor database path must be absolute")


@dataclass(frozen=True)
class ProductObservabilitySnapshot:
    enabled: bool
    logging_enabled: bool
    logger_running: bool
    rows_written: int
    write_failures: int
    source_subscriber_drops: int
    fatal_error: str | None


class ProductObservabilityError(RuntimeError):
    pass


class ProductObservability:
    """Lifecycle owner for the product's observation-only 0D composition."""

    def __init__(
        self,
        config: ProductObservabilityConfig,
        *,
        backend: RXOnlyBackend,
        runtime: Any,
    ) -> None:
        self.config = config
        self.backend = backend
        self.runtime = runtime
        self.monitor_stream: DecodedMonitorStream | None = None
        self.sqlite_logger: SQLiteFrameLogger | None = None
        self.mheard_db: MHeardDatabase | None = None
        self._started = False
        self._stopped = False

    @property
    def snapshot(self) -> ProductObservabilitySnapshot:
        logger = self.sqlite_logger
        if logger is None:
            return ProductObservabilitySnapshot(
                enabled=self.config.enabled,
                logging_enabled=False,
                logger_running=False,
                rows_written=0,
                write_failures=0,
                source_subscriber_drops=self.backend.snapshot.subscriber_drops,
                fatal_error=None,
            )
        snap = logger.snapshot
        return ProductObservabilitySnapshot(
            enabled=self.config.enabled,
            logging_enabled=True,
            logger_running=snap.running,
            rows_written=snap.rows_written,
            write_failures=snap.write_failures,
            source_subscriber_drops=snap.source_subscriber_drops,
            fatal_error=snap.fatal_error,
        )

    def start(self) -> None:
        if self._started:
            raise ProductObservabilityError("product observability is single-start")
        self._started = True
        if not self.config.enabled:
            return

        self.monitor_stream = DecodedMonitorStream(self.backend)
        if not self.config.log_frames:
            return

        assert self.config.database_path is not None
        logger = SQLiteFrameLogger(self.backend, self.config.database_path)
        self.sqlite_logger = logger
        try:
            logger.start()
        except BaseException:
            self.sqlite_logger = None
            raise
        self.mheard_db = MHeardDatabase(self.config.database_path)

    def open_monitor(self) -> MonitorSubscription:
        if not self.config.enabled or self.monitor_stream is None:
            raise ProductObservabilityError("decoded monitor stream is disabled")
        return self.monitor_stream.open()

    def diagnostics_snapshot(self) -> DiagnosticsSnapshot:
        status = DiagnosticsStatus(
            runtime=self.runtime,
            backend=self.backend,
            sqlite_logger=self.sqlite_logger,
            mheard_db=self.mheard_db,
        )
        return status.snapshot()

    def check_health(self) -> None:
        """Enforce only configured component liveness, not observer warnings.

        0D diagnostics intentionally reports subscriber drops and other operator
        problems.  Those observations must not themselves halt packet service.
        A configured SQLite logger that dies, however, means a requested product
        component is no longer running and is therefore a Stage-C health error.
        """

        if not self.config.log_frames:
            return
        logger = self.sqlite_logger
        if logger is None:
            raise ProductObservabilityError("configured SQLite frame logger is absent")
        snap = logger.snapshot
        if not snap.running:
            detail = snap.fatal_error or "logger thread is not running"
            raise ProductObservabilityError(f"SQLite frame logger unhealthy: {detail}")
        if snap.write_failures or snap.fatal_error:
            raise ProductObservabilityError(
                f"SQLite frame logger unhealthy: {snap.fatal_error or 'write failure'}"
            )

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self.sqlite_logger is not None:
            self.sqlite_logger.stop(timeout=2.0)
