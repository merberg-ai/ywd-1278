"""Read-only MHEARD database/list derived from the qualified 0D-P3 frame log.

0D-P4 deliberately does not subscribe to PacketEvent, create a worker thread,
or add an in-memory queue.  The authoritative persisted source remains the
0D-P3 SQLite ``frames`` table.  MHEARD is computed on demand through a SQLite
read-only URI with ``query_only`` enabled.

This keeps packet RX/TX scheduling completely outside the MHEARD boundary and
preserves the frozen 0D-P3 logger byte-for-byte.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

from ywd1278.ax25 import Address

from .sqlite_log import SQLITE_FRAME_LOG_SCHEMA_VERSION


class MHeardError(RuntimeError):
    """Base failure for the read-only MHEARD view."""


class MHeardSchemaError(MHeardError):
    """Raised when the source is not the exact qualified P3 schema."""


@dataclass(frozen=True)
class MHeardEntry:
    source: str
    callsign: str
    ssid: int
    first_heard_ns: int
    last_heard_ns: int
    heard_count: int
    last_destination: str
    last_path: tuple[str, ...]
    last_frame_class: str
    last_frame_type: str
    last_line: str


@dataclass(frozen=True)
class MHeardSummary:
    station_count: int
    frame_count: int
    latest_heard_ns: int | None


_REQUIRED_FRAME_COLUMNS = (
    "id",
    "observed_at_ns",
    "source",
    "destination",
    "path_json",
    "frame_class",
    "frame_type",
    "line",
)


class MHeardDatabase:
    """On-demand, read-only MHEARD queries over one P3 SQLite frame log."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        try:
            uri = self._path.resolve().as_uri() + "?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=2.0)
        except (sqlite3.Error, OSError, ValueError) as exc:
            raise MHeardError(f"unable to open frame log read-only: {exc}") from exc

        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            row = connection.execute("PRAGMA user_version").fetchone()
            version = int(row[0]) if row is not None else -1
            if version != SQLITE_FRAME_LOG_SCHEMA_VERSION:
                raise MHeardSchemaError(
                    f"unsupported frame-log schema version {version}; "
                    f"expected {SQLITE_FRAME_LOG_SCHEMA_VERSION}"
                )

            columns = {
                str(item[1]) for item in connection.execute("PRAGMA table_info(frames)")
            }
            missing = tuple(
                column for column in _REQUIRED_FRAME_COLUMNS if column not in columns
            )
            if missing:
                raise MHeardSchemaError(
                    "frame-log schema is missing required columns: "
                    + ", ".join(missing)
                )
            return connection
        except BaseException:
            connection.close()
            raise

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        return limit

    @staticmethod
    def _validate_since_ns(since_ns: int | None) -> int | None:
        if since_ns is None:
            return None
        if isinstance(since_ns, bool) or not isinstance(since_ns, int):
            raise TypeError("since_ns must be an integer or None")
        if since_ns < 0:
            raise ValueError("since_ns must be >= 0")
        return since_ns

    @staticmethod
    def _entry(row: sqlite3.Row) -> MHeardEntry:
        source = str(row["source"])
        try:
            address = Address.parse(source)
            raw_path = json.loads(str(row["path_json"]))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MHeardError(f"invalid persisted MHEARD source row: {exc}") from exc
        if not isinstance(raw_path, list) or not all(
            isinstance(item, str) for item in raw_path
        ):
            raise MHeardError("invalid persisted MHEARD path_json")

        return MHeardEntry(
            source=source,
            callsign=address.callsign,
            ssid=address.ssid,
            first_heard_ns=int(row["first_heard_ns"]),
            last_heard_ns=int(row["last_heard_ns"]),
            heard_count=int(row["heard_count"]),
            last_destination=str(row["destination"]),
            last_path=tuple(raw_path),
            last_frame_class=str(row["frame_class"]),
            last_frame_type=str(row["frame_type"]),
            last_line=str(row["line"]),
        )

    def list(
        self,
        *,
        limit: int = 50,
        since_ns: int | None = None,
    ) -> list[MHeardEntry]:
        """Return most-recently-heard source stations, newest first.

        Source callsign+SSID is the station identity.  When ``since_ns`` is
        supplied, counts and first/last timestamps are scoped to that window.
        Ties are resolved by the persisted frame id, giving deterministic
        selection of the latest route/line.
        """

        checked_limit = self._validate_limit(limit)
        checked_since = self._validate_since_ns(since_ns)
        where = "" if checked_since is None else "WHERE observed_at_ns >= ?"
        params: list[int] = [] if checked_since is None else [checked_since]
        params.append(checked_limit)

        sql = f"""
            WITH ranked AS (
                SELECT
                    id,
                    observed_at_ns,
                    source,
                    destination,
                    path_json,
                    frame_class,
                    frame_type,
                    line,
                    COUNT(*) OVER (PARTITION BY source) AS heard_count,
                    MIN(observed_at_ns) OVER (PARTITION BY source) AS first_heard_ns,
                    MAX(observed_at_ns) OVER (PARTITION BY source) AS last_heard_ns,
                    ROW_NUMBER() OVER (
                        PARTITION BY source
                        ORDER BY observed_at_ns DESC, id DESC
                    ) AS recency_rank
                FROM frames
                {where}
            )
            SELECT
                source,
                heard_count,
                first_heard_ns,
                last_heard_ns,
                destination,
                path_json,
                frame_class,
                frame_type,
                line
            FROM ranked
            WHERE recency_rank = 1
            ORDER BY last_heard_ns DESC, source ASC
            LIMIT ?
        """

        connection = self._connect()
        try:
            rows = connection.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise MHeardError(f"MHEARD query failed: {exc}") from exc
        finally:
            connection.close()
        return [self._entry(row) for row in rows]

    def get(self, source: str) -> MHeardEntry | None:
        """Return one exact callsign+SSID entry or ``None`` when unheard."""

        normalized = str(Address.parse(source))
        connection = self._connect()
        try:
            row = connection.execute(
                """
                WITH ranked AS (
                    SELECT
                        id,
                        observed_at_ns,
                        source,
                        destination,
                        path_json,
                        frame_class,
                        frame_type,
                        line,
                        COUNT(*) OVER (PARTITION BY source) AS heard_count,
                        MIN(observed_at_ns) OVER (PARTITION BY source) AS first_heard_ns,
                        MAX(observed_at_ns) OVER (PARTITION BY source) AS last_heard_ns,
                        ROW_NUMBER() OVER (
                            PARTITION BY source
                            ORDER BY observed_at_ns DESC, id DESC
                        ) AS recency_rank
                    FROM frames
                    WHERE source = ?
                )
                SELECT
                    source,
                    heard_count,
                    first_heard_ns,
                    last_heard_ns,
                    destination,
                    path_json,
                    frame_class,
                    frame_type,
                    line
                FROM ranked
                WHERE recency_rank = 1
                """,
                (normalized,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise MHeardError(f"MHEARD lookup failed: {exc}") from exc
        finally:
            connection.close()
        return None if row is None else self._entry(row)

    def summary(self, *, since_ns: int | None = None) -> MHeardSummary:
        """Return bounded metadata without materializing the station list."""

        checked_since = self._validate_since_ns(since_ns)
        where = "" if checked_since is None else "WHERE observed_at_ns >= ?"
        params: tuple[int, ...] = () if checked_since is None else (checked_since,)
        connection = self._connect()
        try:
            row = connection.execute(
                f"""
                SELECT
                    COUNT(DISTINCT source) AS station_count,
                    COUNT(*) AS frame_count,
                    MAX(observed_at_ns) AS latest_heard_ns
                FROM frames
                {where}
                """,
                params,
            ).fetchone()
        except sqlite3.Error as exc:
            raise MHeardError(f"MHEARD summary failed: {exc}") from exc
        finally:
            connection.close()
        assert row is not None
        latest = row["latest_heard_ns"]
        return MHeardSummary(
            station_count=int(row["station_count"]),
            frame_count=int(row["frame_count"]),
            latest_heard_ns=None if latest is None else int(latest),
        )
