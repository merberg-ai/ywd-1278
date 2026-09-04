"""Read-only 0D-P6 diagnostics/status aggregation.

P6 intentionally does not create a sampler, scheduler, worker thread, packet
subscriber, queue, modem owner, UART handle, or transmit surface. It merely
reads already-qualified snapshot/counter properties supplied by the running
components and returns one immutable operator-facing status structure.

Every source is optional so diagnostics can describe a partially assembled
host graph without inventing state. SQLite/MHEARD/retention summaries are
queried on demand only when explicit database helpers are supplied by the
caller.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DiagnosticsSnapshot:
    runtime: dict[str, Any] | None
    backend: dict[str, Any] | None
    parameters: dict[str, Any] | None
    control: dict[str, Any] | None
    ingress: dict[str, Any] | None
    queue: dict[str, Any] | None
    connections: dict[str, Any] | None
    sqlite_log: dict[str, Any] | None
    mheard: dict[str, Any] | None
    retention_plan: dict[str, Any] | None
    healthy: bool
    problems: tuple[str, ...]


def _mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    raise TypeError(
        f"diagnostic source must be dataclass/dict/None, got {type(value).__name__}"
    )


def _read(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    return getattr(obj, name, None)


class DiagnosticsStatus:
    """One-shot observer over already-qualified runtime/status properties."""

    def __init__(
        self,
        *,
        runtime: Any = None,
        backend: Any = None,
        sqlite_logger: Any = None,
        mheard_db: Any = None,
        retention_controller: Any = None,
        retention_policy: Any = None,
        retention_now_ns: int | None = None,
    ) -> None:
        if (retention_controller is None) != (retention_policy is None):
            raise ValueError(
                "retention_controller and retention_policy must be supplied together"
            )
        if retention_controller is not None and retention_now_ns is None:
            raise ValueError(
                "retention_now_ns is required when retention diagnostics are enabled"
            )
        self._runtime = runtime
        self._backend = backend
        self._sqlite_logger = sqlite_logger
        self._mheard_db = mheard_db
        self._retention_controller = retention_controller
        self._retention_policy = retention_policy
        self._retention_now_ns = retention_now_ns

    def snapshot(self) -> DiagnosticsSnapshot:
        runtime_accounting = _read(self._runtime, "accounting")
        runtime_counters = _read(self._runtime, "runtime_counters")

        runtime_map = None
        parameters = control = ingress = queue = connections = None
        if runtime_accounting is not None:
            runtime_map = _mapping(runtime_accounting.runtime)
            parameters = _mapping(runtime_accounting.parameters)
            control = _mapping(runtime_accounting.control)
            ingress = _mapping(runtime_accounting.ingress)
            queue = _mapping(runtime_accounting.queue)
            connections = _mapping(runtime_accounting.connections)
        elif runtime_counters is not None:
            runtime_map = _mapping(runtime_counters)

        backend_map = _mapping(_read(self._backend, "snapshot"))
        if parameters is None:
            parameters = _mapping(_read(self._backend, "control_snapshot"))
        if control is None:
            control = _mapping(_read(self._backend, "control_counters"))
        if ingress is None:
            ingress = _mapping(_read(self._backend, "ingress_counters"))
        if queue is None and self._backend is not None:
            admission = getattr(self._backend, "admission", None)
            if admission is not None:
                queue = _mapping(_read(admission, "snapshot"))
        if connections is None:
            connections = _mapping(_read(self._backend, "connection_counters"))

        sqlite_map = _mapping(_read(self._sqlite_logger, "snapshot"))

        mheard_map = None
        if self._mheard_db is not None:
            mheard_map = _mapping(self._mheard_db.summary())

        retention_map = None
        if self._retention_controller is not None:
            retention_map = _mapping(
                self._retention_controller.plan(
                    self._retention_policy,
                    now_ns=int(self._retention_now_ns),
                )
            )

        problems: list[str] = []
        if runtime_map is not None and runtime_map.get("failure"):
            problems.append("runtime-failure")
        if backend_map is not None and int(backend_map.get("subscriber_drops", 0)) > 0:
            problems.append("subscriber-drops")
        if queue is not None:
            if int(
                queue.get("timed_out_requests", queue.get("tx_access_timeouts", 0))
            ) > 0:
                problems.append("tx-access-timeouts")
            if int(
                queue.get(
                    "downstream_failures", queue.get("tx_downstream_failures", 0)
                )
            ) > 0:
                problems.append("tx-downstream-failures")
        if sqlite_map is not None:
            if int(sqlite_map.get("write_failures", 0)) > 0:
                problems.append("sqlite-write-failures")
            if sqlite_map.get("fatal_error"):
                problems.append("sqlite-fatal-error")

        return DiagnosticsSnapshot(
            runtime=runtime_map,
            backend=backend_map,
            parameters=parameters,
            control=control,
            ingress=ingress,
            queue=queue,
            connections=connections,
            sqlite_log=sqlite_map,
            mheard=mheard_map,
            retention_plan=retention_map,
            healthy=not problems,
            problems=tuple(problems),
        )
