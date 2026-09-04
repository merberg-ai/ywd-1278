"""Explicit bounded retention controls for the qualified 0D-P3 SQLite log.

0D-P5 is deliberately maintenance-only.  It does not subscribe to packet
traffic, create a worker thread, schedule itself, touch the modem, or expose a
transmit path.  Retention is disabled unless a typed policy contains at least
one bound, and destructive work happens only through an explicit ``apply``
call.

Each apply operation deletes at most ``max_delete_per_run`` oldest eligible
rows in one short SQLite transaction.  If another writer owns the database,
the operation fails closed rather than looping or blocking packet processing.
The P3 schema remains unchanged; P4 MHEARD naturally reflects the retained
``frames`` table.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from .sqlite_log import SQLITE_FRAME_LOG_SCHEMA_VERSION


RETENTION_DEFAULT_MAX_DELETE_PER_RUN = 1000
RETENTION_ABSOLUTE_MAX_DELETE_PER_RUN = 10000


class RetentionError(RuntimeError):
    """Base failure for SQLite retention maintenance."""


class RetentionSchemaError(RetentionError):
    """Raised when the target is not the exact qualified frame-log schema."""


class RetentionBusyError(RetentionError):
    """Raised when bounded maintenance cannot acquire the SQLite write lock."""


@dataclass(frozen=True)
class RetentionPolicy:
    """Typed retention limits; no limits means retention is disabled."""

    max_age_ns: int | None = None
    max_rows: int | None = None

    def __post_init__(self) -> None:
        if self.max_age_ns is not None:
            if isinstance(self.max_age_ns, bool) or not isinstance(self.max_age_ns, int):
                raise TypeError("max_age_ns must be an integer or None")
            if self.max_age_ns <= 0:
                raise ValueError("max_age_ns must be > 0")
        if self.max_rows is not None:
            if isinstance(self.max_rows, bool) or not isinstance(self.max_rows, int):
                raise TypeError("max_rows must be an integer or None")
            if self.max_rows <= 0:
                raise ValueError("max_rows must be > 0")

    @property
    def enabled(self) -> bool:
        return self.max_age_ns is not None or self.max_rows is not None


@dataclass(frozen=True)
class RetentionPlan:
    enabled: bool
    total_rows: int
    eligible_rows: int
    next_batch_rows: int
    cutoff_ns: int | None
    max_rows: int | None
    max_delete_per_run: int


@dataclass(frozen=True)
class RetentionResult:
    enabled: bool
    deleted_rows: int
    remaining_rows: int
    remaining_eligible_rows: int
    more_eligible: bool


_REQUIRED_COLUMNS = {
    "id",
    "observed_at_ns",
    "source",
    "destination",
    "path_json",
    "frame_class",
    "frame_type",
    "line",
}


class SQLiteRetentionController:
    """Explicit bounded maintenance for one qualified P3 frame-log database."""

    def __init__(
        self,
        path: str | Path,
        *,
        max_delete_per_run: int = RETENTION_DEFAULT_MAX_DELETE_PER_RUN,
        sqlite_timeout: float = 0.25,
    ) -> None:
        if isinstance(max_delete_per_run, bool) or not isinstance(max_delete_per_run, int):
            raise TypeError("max_delete_per_run must be an integer")
        if not 1 <= max_delete_per_run <= RETENTION_ABSOLUTE_MAX_DELETE_PER_RUN:
            raise ValueError(
                "max_delete_per_run must be between 1 and "
                f"{RETENTION_ABSOLUTE_MAX_DELETE_PER_RUN}"
            )
        if sqlite_timeout <= 0.0:
            raise ValueError("sqlite_timeout must be > 0")
        self._path = Path(path)
        self._max_delete_per_run = max_delete_per_run
        self._sqlite_timeout = float(sqlite_timeout)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def max_delete_per_run(self) -> int:
        return self._max_delete_per_run

    @staticmethod
    def _validate_now_ns(now_ns: int) -> int:
        if isinstance(now_ns, bool) or not isinstance(now_ns, int):
            raise TypeError("now_ns must be an integer")
        if now_ns < 0:
            raise ValueError("now_ns must be >= 0")
        return now_ns

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        row = connection.execute("PRAGMA user_version").fetchone()
        version = int(row[0]) if row is not None else -1
        if version != SQLITE_FRAME_LOG_SCHEMA_VERSION:
            raise RetentionSchemaError(
                f"unsupported frame-log schema version {version}; "
                f"expected {SQLITE_FRAME_LOG_SCHEMA_VERSION}"
            )
        columns = {
            str(item[1]) for item in connection.execute("PRAGMA table_info(frames)")
        }
        missing = tuple(sorted(_REQUIRED_COLUMNS - columns))
        if missing:
            raise RetentionSchemaError(
                "frame-log schema is missing required columns: " + ", ".join(missing)
            )

    def _connect_read_only(self) -> sqlite3.Connection:
        try:
            uri = self._path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=self._sqlite_timeout)
            connection.execute("PRAGMA query_only=ON")
            self._validate_schema(connection)
            return connection
        except (sqlite3.Error, OSError, ValueError) as exc:
            raise RetentionError(f"unable to open frame log read-only: {exc}") from exc

    def _connect_write(self) -> sqlite3.Connection:
        try:
            uri = self._path.resolve().as_uri() + "?mode=rw"
            connection = sqlite3.connect(uri, uri=True, timeout=self._sqlite_timeout)
            self._validate_schema(connection)
            return connection
        except RetentionSchemaError:
            raise
        except (sqlite3.Error, OSError, ValueError) as exc:
            raise RetentionError(f"unable to open frame log for retention: {exc}") from exc

    @staticmethod
    def _cutoff(policy: RetentionPolicy, now_ns: int) -> int | None:
        if policy.max_age_ns is None:
            return None
        return max(0, now_ns - policy.max_age_ns)

    @staticmethod
    def _eligible_sql(*, count_only: bool) -> str:
        select = "COUNT(*)" if count_only else "id"
        order_limit = "" if count_only else "ORDER BY observed_at_ns ASC, id ASC LIMIT ?"
        return f"""
            WITH ranked AS (
                SELECT
                    id,
                    observed_at_ns,
                    ROW_NUMBER() OVER (
                        ORDER BY observed_at_ns DESC, id DESC
                    ) AS recency_rank
                FROM frames
            ), eligible AS (
                SELECT id, observed_at_ns
                FROM ranked
                WHERE (? IS NOT NULL AND observed_at_ns < ?)
                   OR (? IS NOT NULL AND recency_rank > ?)
            )
            SELECT {select}
            FROM eligible
            {order_limit}
        """

    @staticmethod
    def _policy_params(policy: RetentionPolicy, cutoff_ns: int | None) -> tuple[int | None, ...]:
        return (cutoff_ns, cutoff_ns, policy.max_rows, policy.max_rows)

    def _eligible_count(
        self,
        connection: sqlite3.Connection,
        policy: RetentionPolicy,
        cutoff_ns: int | None,
    ) -> int:
        if not policy.enabled:
            return 0
        row = connection.execute(
            self._eligible_sql(count_only=True),
            self._policy_params(policy, cutoff_ns),
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def plan(self, policy: RetentionPolicy, *, now_ns: int) -> RetentionPlan:
        checked_now = self._validate_now_ns(now_ns)
        cutoff = self._cutoff(policy, checked_now)
        connection = self._connect_read_only()
        try:
            total = int(connection.execute("SELECT COUNT(*) FROM frames").fetchone()[0])
            eligible = self._eligible_count(connection, policy, cutoff)
        except sqlite3.Error as exc:
            raise RetentionError(f"retention plan query failed: {exc}") from exc
        finally:
            connection.close()
        return RetentionPlan(
            enabled=policy.enabled,
            total_rows=total,
            eligible_rows=eligible,
            next_batch_rows=min(eligible, self._max_delete_per_run),
            cutoff_ns=cutoff,
            max_rows=policy.max_rows,
            max_delete_per_run=self._max_delete_per_run,
        )

    def apply(self, policy: RetentionPolicy, *, now_ns: int) -> RetentionResult:
        """Apply one explicit bounded retention batch.

        Disabled policy is a read-only no-op.  Enabled policy acquires one
        immediate write transaction and never retries automatically.
        """

        checked_now = self._validate_now_ns(now_ns)
        cutoff = self._cutoff(policy, checked_now)
        if not policy.enabled:
            plan = self.plan(policy, now_ns=checked_now)
            return RetentionResult(False, 0, plan.total_rows, 0, False)

        connection = self._connect_write()
        try:
            try:
                connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                raise RetentionBusyError(
                    f"retention write lock unavailable: {exc}"
                ) from exc

            ids = [
                int(row[0])
                for row in connection.execute(
                    self._eligible_sql(count_only=False),
                    (*self._policy_params(policy, cutoff), self._max_delete_per_run),
                ).fetchall()
            ]
            if ids:
                placeholders = ",".join("?" for _ in ids)
                connection.execute(
                    f"DELETE FROM frames WHERE id IN ({placeholders})",
                    ids,
                )
            connection.commit()
            remaining = int(connection.execute("SELECT COUNT(*) FROM frames").fetchone()[0])
            remaining_eligible = self._eligible_count(connection, policy, cutoff)
        except RetentionBusyError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise RetentionError(f"retention transaction failed: {exc}") from exc
        finally:
            connection.close()

        return RetentionResult(
            enabled=True,
            deleted_rows=len(ids),
            remaining_rows=remaining,
            remaining_eligible_rows=remaining_eligible,
            more_eligible=remaining_eligible > 0,
        )
