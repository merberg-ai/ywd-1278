"""0I-P4b product-backend service wrapper for the frozen persistent BBS runtime.

The service subscribes to the already-qualified product PacketEvent backend and
returns every connected-mode response through that same backend's port-0 KISS
DATA admission method.  It therefore creates no second decoder, CSMA policy,
transmit queue, modem owner, UART path, or RF implementation.

P4b is host-qualified with an injected backend.  The exact real product backend
composition is qualified separately before physical service activation.
"""
from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
import threading
import time
from typing import Any, Callable

from ywd1278.ax25 import Address, parse_frame
from ywd1278.kiss.framing import DATA, KISSMessage
from ywd1278.kiss.server import PacketEvent
from ywd1278.node.persistent_bbs_runtime import PersistentBBSRuntime
from ywd1278.node.persistent_mailbox import PersistentMailboxStore
from ywd1278.service.node_mailbox_config import ProductNodeMailboxConfig


BackendGetter = Callable[[], Any]
MonotonicClock = Callable[[], float]
WallClockNS = Callable[[], int]


class ProductPersistentBBSServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProductPersistentBBSServiceSnapshot:
    running: bool
    local: str
    database: str
    history_discarded: int
    live_events_seen: int
    relevant_frames: int
    runtime_rejections: int
    tx_actions_prepared: int
    tx_actions_admitted: int
    tx_admission_failures: int
    failure: str
    active_peer: str | None


class ProductPersistentBBSService:
    """One worker joining live PacketEvents to the frozen P4a BBS runtime."""

    def __init__(
        self,
        config: ProductNodeMailboxConfig,
        *,
        backend_getter: BackendGetter,
        tx_enabled: bool,
        monotonic: MonotonicClock = time.monotonic,
        time_ns: WallClockNS = time.time_ns,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        if not isinstance(config, ProductNodeMailboxConfig):
            raise TypeError("config must be ProductNodeMailboxConfig")
        if not config.node_enabled or not config.mailbox_enabled or config.local is None:
            raise ProductPersistentBBSServiceError(
                "persistent BBS service requires enabled node/mailbox configuration"
            )
        if not isinstance(tx_enabled, bool):
            raise TypeError("tx_enabled must be bool")
        if not tx_enabled:
            raise ProductPersistentBBSServiceError(
                "persistent connected BBS requires radio.tx_enabled=true"
            )
        if not callable(backend_getter):
            raise TypeError("backend_getter must be callable")
        if not callable(monotonic) or not callable(time_ns):
            raise TypeError("clocks must be callable")
        if isinstance(poll_interval_seconds, bool) or not isinstance(
            poll_interval_seconds, (int, float)
        ) or not 0.01 <= float(poll_interval_seconds) <= 0.5:
            raise ValueError("poll_interval_seconds must be 0.01..0.5")

        self.config = config
        self._backend_getter = backend_getter
        self._monotonic = monotonic
        self._time_ns = time_ns
        self._poll_interval = float(poll_interval_seconds)
        self._store: PersistentMailboxStore | None = None
        self._runtime: PersistentBBSRuntime | None = None
        self._backend: Any = None
        self._live_queue: Queue[PacketEvent] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._started = False
        self._stopped = False
        self._history_discarded = 0
        self._live_events_seen = 0
        self._relevant_frames = 0
        self._runtime_rejections = 0
        self._tx_actions_prepared = 0
        self._tx_actions_admitted = 0
        self._tx_admission_failures = 0
        self._failure = ""
        self._lock = threading.Lock()

    @property
    def snapshot(self) -> ProductPersistentBBSServiceSnapshot:
        with self._lock:
            thread = self._thread
            runtime = self._runtime
            active_peer = None if runtime is None else runtime.snapshot.active_peer
            return ProductPersistentBBSServiceSnapshot(
                running=bool(
                    self._started
                    and not self._stopped
                    and thread is not None
                    and thread.is_alive()
                    and not self._failure
                ),
                local=str(self.config.local),
                database=str(self.config.mailbox_database),
                history_discarded=self._history_discarded,
                live_events_seen=self._live_events_seen,
                relevant_frames=self._relevant_frames,
                runtime_rejections=self._runtime_rejections,
                tx_actions_prepared=self._tx_actions_prepared,
                tx_actions_admitted=self._tx_actions_admitted,
                tx_admission_failures=self._tx_admission_failures,
                failure=self._failure,
                active_peer=active_peer,
            )

    @property
    def store(self) -> PersistentMailboxStore | None:
        return self._store

    def start(self) -> None:
        if self._started:
            raise ProductPersistentBBSServiceError("persistent BBS service cannot be restarted")
        self._started = True
        backend = self._backend_getter()
        if backend is None:
            raise ProductPersistentBBSServiceError("product backend is unavailable")
        for name in ("open_stream", "close_stream", "reject_client_message"):
            if not callable(getattr(backend, name, None)):
                raise ProductPersistentBBSServiceError(
                    f"product backend does not provide required {name} method"
                )

        store = PersistentMailboxStore(self.config.mailbox_database)
        runtime = PersistentBBSRuntime(
            local=self.config.local,
            alias=self.config.alias,
            store=store,
            mailbox_paclen=self.config.mailbox_paclen,
            now_ns=self._time_ns,
            info=self.config.mailbox_info,
        )
        history, live_queue = backend.open_stream()
        if not isinstance(live_queue, Queue):
            backend.close_stream(live_queue)
            raise ProductPersistentBBSServiceError("product backend returned invalid live queue")

        self._backend = backend
        self._store = store
        self._runtime = runtime
        self._live_queue = live_queue
        self._history_discarded = len(history)
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ywd1278-persistent-bbs",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if not self._started or self._stopped:
            return
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
            if thread.is_alive():
                raise ProductPersistentBBSServiceError(
                    "persistent BBS worker did not stop"
                )
        if self._backend is not None and self._live_queue is not None:
            self._backend.close_stream(self._live_queue)
        self._stopped = True

    def check_health(self) -> None:
        snapshot = self.snapshot
        if snapshot.failure:
            raise ProductPersistentBBSServiceError(snapshot.failure)
        if self._started and not self._stopped and not snapshot.running:
            raise ProductPersistentBBSServiceError("persistent BBS worker is not running")

    def _run(self) -> None:
        try:
            assert self._runtime is not None
            assert self._live_queue is not None
            while not self._stop.is_set():
                event: PacketEvent | None = None
                try:
                    event = self._live_queue.get(timeout=self._poll_interval)
                except Empty:
                    pass
                if event is not None:
                    with self._lock:
                        self._live_events_seen += 1
                    if self._is_relevant(event):
                        with self._lock:
                            self._relevant_frames += 1
                        handled = self._runtime.handle_frame(
                            event.frame_no_fcs,
                            now=float(self._monotonic()),
                        )
                        if not handled.accepted:
                            with self._lock:
                                self._runtime_rejections += 1
                        self._submit_actions(handled.actions)
                polled = self._runtime.poll(now=float(self._monotonic()))
                if not polled.accepted:
                    with self._lock:
                        self._runtime_rejections += 1
                self._submit_actions(polled.actions)
        except BaseException as exc:
            with self._lock:
                self._failure = f"{type(exc).__name__}: {exc}"
            self._stop.set()

    def _is_relevant(self, event: PacketEvent) -> bool:
        try:
            parsed = parse_frame(event.frame_no_fcs, has_fcs=False)
        except (TypeError, ValueError):
            return False
        destination = parsed["destination"]
        if not isinstance(destination, Address):
            return False
        local = self.config.local
        assert local is not None
        if (destination.callsign, destination.ssid) != (local.callsign, local.ssid):
            return False
        if parsed["path"]:
            return False
        return parsed["frame_class"] in {"I", "S", "U"}

    def _submit_actions(self, actions) -> None:  # type: ignore[no-untyped-def]
        for action in actions:
            with self._lock:
                self._tx_actions_prepared += 1
            result = self._backend.reject_client_message(
                KISSMessage(port=0, command=DATA, frame=bytes(action.frame_no_fcs))
            )
            admitted = bool(getattr(result, "admitted", False))
            if not admitted:
                reason = str(getattr(result, "reason", "product DATA admission rejected"))
                with self._lock:
                    self._tx_admission_failures += 1
                raise ProductPersistentBBSServiceError(
                    f"persistent BBS TX action was not admitted: {reason}"
                )
            with self._lock:
                self._tx_actions_admitted += 1


__all__ = [
    "ProductPersistentBBSServiceError",
    "ProductPersistentBBSServiceSnapshot",
    "ProductPersistentBBSService",
]
