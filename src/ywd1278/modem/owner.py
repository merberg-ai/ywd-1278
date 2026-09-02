"""Bounded single-owner modem command runtime.

0B-P7b-1 deliberately exposes only read/control operations needed by the
receive path.  Clients cannot submit arbitrary modem frames and there is no
TX_TONES method in this layer.  The transport object is created inside the
owner thread, so device ownership begins and ends in exactly one thread.
"""

from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
from typing import Callable, Protocol, TypeVar, cast

from . import protocol


class ModemTransport(Protocol):
    """Minimal transport contract consumed only by :class:`ModemOwner`."""

    def transact(self, request: bytes, *, timeout: float) -> bytes: ...

    def close(self) -> None: ...


TransportFactory = Callable[[], ModemTransport]
T = TypeVar("T")


class ModemOwnerError(RuntimeError):
    pass


class ModemOwnerNotRunning(ModemOwnerError):
    pass


class ModemOwnerQueueFull(ModemOwnerError):
    pass


@dataclass(frozen=True)
class OwnerSnapshot:
    running: bool
    owner_thread_id: int | None
    queue_depth: int
    queue_capacity: int
    transactions: int


@dataclass
class _Call:
    operation: str
    argument: int | None
    timeout: float
    done: threading.Event
    result: object | None = None
    error: BaseException | None = None


_STOP = object()


class ModemOwner:
    """Exactly-one-thread modem transaction owner with a bounded request queue.

    Public callers receive typed methods only.  They cannot pass a raw modem
    frame through this object.  In P7b-1 the reachable command set is:

    * GET_VERSION
    * YWD_RX START / READ / STATUS / STOP
    * YWD_RF GET_DIAG (read-only diagnostic)

    There is intentionally no RF TX/ABORT/EXIT API here.  TX sequencing will be
    added later behind its own bounded broker and qualification gate.
    """

    def __init__(
        self,
        transport_factory: TransportFactory,
        *,
        queue_capacity: int = 8,
        submit_timeout: float = 0.25,
        default_transaction_timeout: float = 1.0,
        thread_name: str = "ywd1278-modem-owner",
    ) -> None:
        if queue_capacity < 1:
            raise ValueError("queue_capacity must be at least 1")
        if submit_timeout <= 0.0:
            raise ValueError("submit_timeout must be positive")
        if default_transaction_timeout <= 0.0:
            raise ValueError("default_transaction_timeout must be positive")

        self._transport_factory = transport_factory
        self._queue: queue.Queue[_Call | object] = queue.Queue(maxsize=queue_capacity)
        self._submit_timeout = submit_timeout
        self._default_transaction_timeout = default_transaction_timeout
        self._thread_name = thread_name

        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._start_error: BaseException | None = None
        self._owner_thread_id: int | None = None
        self._transactions = 0
        self._accepting = False

    def start(self, *, timeout: float = 2.0) -> None:
        if timeout <= 0.0:
            raise ValueError("timeout must be positive")
        with self._lock:
            if self._thread is not None:
                if self._thread.is_alive() and self._accepting:
                    return
                raise ModemOwnerError("modem owner cannot be restarted")
            self._ready.clear()
            self._stopped.clear()
            self._start_error = None
            self._thread = threading.Thread(
                target=self._run,
                name=self._thread_name,
                daemon=True,
            )
            self._thread.start()

        if not self._ready.wait(timeout):
            raise ModemOwnerError("timed out waiting for modem owner startup")
        if self._start_error is not None:
            raise ModemOwnerError("modem transport startup failed") from self._start_error

    def stop(self, *, timeout: float = 2.0) -> None:
        if timeout <= 0.0:
            raise ValueError("timeout must be positive")
        with self._lock:
            thread = self._thread
            if thread is None:
                return
            if not thread.is_alive():
                return
            self._accepting = False

        # Once acceptance is closed, existing queued calls are allowed to drain
        # ahead of the sentinel.  No new client call can enter the queue.
        try:
            self._queue.put(_STOP, timeout=timeout)
        except queue.Full as exc:
            raise ModemOwnerError("timed out queueing modem-owner stop") from exc
        thread.join(timeout)
        if thread.is_alive():
            raise ModemOwnerError("timed out waiting for modem owner shutdown")

    def __enter__(self) -> "ModemOwner":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.stop()

    @property
    def snapshot(self) -> OwnerSnapshot:
        with self._lock:
            thread = self._thread
            running = bool(thread and thread.is_alive() and self._accepting)
            owner_thread_id = self._owner_thread_id
            transactions = self._transactions
        return OwnerSnapshot(
            running=running,
            owner_thread_id=owner_thread_id,
            queue_depth=self._queue.qsize(),
            queue_capacity=self._queue.maxsize,
            transactions=transactions,
        )

    def get_version(self, *, timeout: float | None = None) -> protocol.VersionResponse:
        return cast(protocol.VersionResponse, self._call("get_version", None, timeout))

    def rx_start(self, *, timeout: float | None = None) -> None:
        self._call("rx_start", None, timeout)

    def rx_read(
        self,
        maximum: int = protocol.MAX_RX_READ_BYTES,
        *,
        timeout: float | None = None,
    ) -> bytes:
        return cast(bytes, self._call("rx_read", maximum, timeout))

    def rx_status(self, *, timeout: float | None = None) -> protocol.RX3Status:
        return cast(protocol.RX3Status, self._call("rx_status", None, timeout))

    def rx_stop(self, *, timeout: float | None = None) -> None:
        self._call("rx_stop", None, timeout)

    def rf_diagnostics(self, *, timeout: float | None = None) -> protocol.RFDiagnostics:
        return cast(protocol.RFDiagnostics, self._call("rf_diag", None, timeout))

    def _call(self, operation: str, argument: int | None, timeout: float | None) -> object | None:
        transaction_timeout = (
            self._default_transaction_timeout if timeout is None else timeout
        )
        if transaction_timeout <= 0.0:
            raise ValueError("transaction timeout must be positive")

        with self._lock:
            thread = self._thread
            accepting = self._accepting
        if thread is None or not thread.is_alive() or not accepting:
            raise ModemOwnerNotRunning("modem owner is not accepting requests")

        call = _Call(
            operation=operation,
            argument=argument,
            timeout=transaction_timeout,
            done=threading.Event(),
        )
        try:
            self._queue.put(call, timeout=self._submit_timeout)
        except queue.Full as exc:
            raise ModemOwnerQueueFull(
                f"modem owner request queue is full (capacity={self._queue.maxsize})"
            ) from exc

        # The owner transaction timeout applies to device I/O; allow a bounded
        # extra interval for time spent waiting behind earlier queue entries.
        wait_timeout = transaction_timeout + self._submit_timeout + 1.0
        if not call.done.wait(wait_timeout):
            raise ModemOwnerError(
                f"timed out waiting for modem owner operation {operation!r}"
            )
        if call.error is not None:
            raise ModemOwnerError(f"modem owner operation {operation!r} failed") from call.error
        return call.result

    def _run(self) -> None:
        transport: ModemTransport | None = None
        try:
            self._owner_thread_id = threading.get_ident()
            transport = self._transport_factory()
            with self._lock:
                self._accepting = True
            self._ready.set()

            while True:
                item = self._queue.get()
                try:
                    if item is _STOP:
                        return
                    call = cast(_Call, item)
                    try:
                        call.result = self._dispatch(transport, call)
                    except BaseException as exc:  # propagate exact cause to caller
                        call.error = exc
                    finally:
                        call.done.set()
                finally:
                    self._queue.task_done()
        except BaseException as exc:
            self._start_error = exc
            self._ready.set()
        finally:
            with self._lock:
                self._accepting = False
            if transport is not None:
                try:
                    transport.close()
                finally:
                    pass
            self._stopped.set()

    def _dispatch(self, transport: ModemTransport, call: _Call) -> object | None:
        if threading.get_ident() != self._owner_thread_id:
            raise RuntimeError("modem transport dispatch escaped the owner thread")

        if call.operation == "get_version":
            response = self._transact(transport, protocol.get_version_request(), call.timeout)
            return protocol.parse_version_response(response)
        if call.operation == "rx_start":
            response = self._transact(transport, protocol.rx_start_request(), call.timeout)
            protocol.parse_ack(response, expected_command=protocol.YWD_RX)
            return None
        if call.operation == "rx_read":
            maximum = cast(int, call.argument)
            request = protocol.rx_read_request(maximum)
            response = self._transact(transport, request, call.timeout)
            return protocol.parse_rx_read(response)
        if call.operation == "rx_status":
            response = self._transact(transport, protocol.rx_status_request(), call.timeout)
            return protocol.parse_rx3_status(response)
        if call.operation == "rx_stop":
            response = self._transact(transport, protocol.rx_stop_request(), call.timeout)
            protocol.parse_ack(response, expected_command=protocol.YWD_RX)
            return None
        if call.operation == "rf_diag":
            response = self._transact(transport, protocol.rf_diag_request(), call.timeout)
            return protocol.parse_rf_diagnostics(response)
        raise RuntimeError(f"unsupported owner operation: {call.operation}")

    def _transact(self, transport: ModemTransport, request: bytes, timeout: float) -> bytes:
        response = transport.transact(request, timeout=timeout)
        with self._lock:
            self._transactions += 1
        return response
