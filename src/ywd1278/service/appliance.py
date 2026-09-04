"""Production packet-engine and observability composition for YWD-1278.

Stage B assembled the frozen packet engine.  Stage C preserves those qualified
engine components and composes the already-qualified 0D monitor/logging/MHEARD
and diagnostics facilities around the same PacketEvent backend.

The lifecycle remains intentionally narrow:

    one TXModemOwner
      -> active AX25R4 receive
      -> sustained Bell-202/AX.25 runtime
      -> bounded PacketEvent backend
           -> localhost KISS
           -> optional decoded monitor subscriptions
           -> optional bounded-subscriber SQLite logger -> read-only MHEARD
      -> bounded contextual DATA admission / CSMA
      -> persistent half-duplex RX_STOP/TX/RX_START
      -> contextual TXDELAY broker

Transmit authority remains construction-time and fail-closed.  The normal safe
configuration has ``tx_enabled = false``; in that mode KISS DATA is rejected at
ingress and never enters the access queue.  Product TX construction remains
limited to the already physically-qualified 145.050 MHz / power-200 profile.

This module does not flash firmware, manipulate GPIO/reset lines, write option
bytes, implement beacons, schedule retention, or compose the classic console.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import secrets
import threading
import time
import tomllib
from typing import Callable

from ywd1278.kiss.control import TNCControlBackend, TNCParameterSnapshot, TNCSessionState
from ywd1278.kiss.framing import DATA, KISSMessage
from ywd1278.kiss.server import ThreadingKISSServer, start_server_thread, stop_server_thread
from ywd1278.kiss.sustained import SustainedTNCBackend, ThreadSafeKISSDataAdmissionQueue
from ywd1278.modem._serial import posix_serial_transport_factory
from ywd1278.modem.owner import TransportFactory
from ywd1278.modem.rx_config import validate_rx_frequency_hz
from ywd1278.modem.tx_owner import TXModemOwner
from ywd1278.monitor.diagnostics import DiagnosticsSnapshot
from ywd1278.monitor.mheard import MHeardDatabase
from ywd1278.monitor.stream import MonitorSubscription
from ywd1278.service.observability import (
    ProductObservability,
    ProductObservabilityConfig,
    ProductObservabilityError,
)
from ywd1278.service.tnc_runtime import SustainedTNCRuntime
from ywd1278.tx.contextual import ContextualHalfDuplexSubmitter, ContextualTXDelayRouter
from ywd1278.tx.half_duplex import HalfDuplexParameters


PRODUCT_TARGET = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
PRODUCT_FIRMWARE_IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
    "ADF7021 FW based on CA6JAU GitID #7ff74ed"
)
QUALIFIED_TX_FREQUENCY_HZ = 145_050_000
QUALIFIED_TX_POWER = 200
KISS_LOOPBACK_HOST = "127.0.0.1"

MonotonicClock = Callable[[], float]
Sleeper = Callable[[float], None]
RandomByteSource = Callable[[], int]


class ProductConfigurationError(ValueError):
    pass


class ProductPacketEngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProductPacketEngineConfig:
    target: str
    device: str
    frequency_hz: int
    tx_power: int
    tx_enabled: bool
    txdelay: int
    persist: int
    slottime: int
    kiss_enabled: bool
    kiss_host: str
    kiss_port: int
    monitor_enabled: bool = False
    monitor_log_frames: bool = False
    database_path: Path | None = None


@dataclass(frozen=True)
class ProductPacketEngineSnapshot:
    running: bool
    firmware_identity: str
    tx_enabled: bool
    kiss_listener: tuple[str, int] | None
    owner_transactions: int
    tx_queue_depth: int
    decoded_rx_frames: int
    tx_dispatches: int
    failure: str


class ProductTNCBackend(SustainedTNCBackend):
    """P8 backend with a healthy no-TX product operating mode."""

    def __init__(self, *args, product_tx_enabled: bool, **kwargs) -> None:  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)
        self.product_tx_enabled = bool(product_tx_enabled)

    def reject_client_message(self, message: KISSMessage):  # type: ignore[no-untyped-def]
        if message.port == 0 and message.command == DATA and not self.product_tx_enabled:
            return TNCControlBackend.reject_client_message(self, message)
        return super().reject_client_message(message)


def _table(root: dict, name: str) -> dict:
    value = root.get(name)
    if not isinstance(value, dict):
        raise ProductConfigurationError(f"missing or invalid [{name}] table")
    return value


def _optional_table(root: dict, name: str) -> dict | None:
    value = root.get(name)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProductConfigurationError(f"invalid [{name}] table")
    return value


def _string(table: dict, key: str) -> str:
    value = table.get(key)
    if not isinstance(value, str):
        raise ProductConfigurationError(f"{key} must be a string")
    return value


def _boolean(table: dict, key: str) -> bool:
    value = table.get(key)
    if not isinstance(value, bool):
        raise ProductConfigurationError(f"{key} must be true or false")
    return value


def _integer(table: dict, key: str) -> int:
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProductConfigurationError(f"{key} must be an integer")
    return int(value)


def _frequency_hz(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProductConfigurationError("radio.frequency_mhz must be numeric")
    try:
        mhz = Decimal(str(value))
    except InvalidOperation as exc:
        raise ProductConfigurationError("radio.frequency_mhz is invalid") from exc
    hz_value = mhz * Decimal(1_000_000)
    if hz_value != hz_value.to_integral_value():
        raise ProductConfigurationError("radio.frequency_mhz must resolve to an integer Hz value")
    hz = int(hz_value)
    if hz == 0:
        raise ProductConfigurationError("radio.frequency_mhz is not configured")
    try:
        return validate_rx_frequency_hz(hz)
    except ValueError as exc:
        raise ProductConfigurationError(str(exc)) from exc


def _validate_product_config(config: ProductPacketEngineConfig) -> None:
    """Revalidate typed configuration at the capability-owning boundary."""

    if config.target != PRODUCT_TARGET:
        raise ProductConfigurationError(
            f"hardware.target must be the supported target {PRODUCT_TARGET!r}"
        )
    if not config.device.startswith("/dev/"):
        raise ProductConfigurationError("radio.device must be an absolute /dev path")
    try:
        validate_rx_frequency_hz(config.frequency_hz)
    except ValueError as exc:
        raise ProductConfigurationError(str(exc)) from exc
    if not 0 <= config.tx_power <= 255:
        raise ProductConfigurationError("radio.tx_power must be 0..255")
    if not 0 <= config.txdelay <= 255:
        raise ProductConfigurationError("packet TXDELAY units must be 0..255")
    if not 0 <= config.persist <= 255:
        raise ProductConfigurationError("packet.persist must be 0..255")
    if not 1 <= config.slottime <= 255:
        raise ProductConfigurationError("packet SLOTTIME units must be 1..255")
    if config.kiss_host != KISS_LOOPBACK_HOST:
        raise ProductConfigurationError("product KISS listener must remain on 127.0.0.1")
    if not 1 <= config.kiss_port <= 65535:
        raise ProductConfigurationError("kiss.port must be 1..65535")
    if config.tx_enabled and (
        config.frequency_hz != QUALIFIED_TX_FREQUENCY_HZ
        or config.tx_power != QUALIFIED_TX_POWER
    ):
        raise ProductConfigurationError(
            "product TX may only use the physically-qualified 145.050 MHz / power-200 profile"
        )
    try:
        ProductObservabilityConfig(
            enabled=config.monitor_enabled,
            log_frames=config.monitor_log_frames,
            database_path=config.database_path,
        )
    except ValueError as exc:
        raise ProductConfigurationError(str(exc)) from exc


def load_product_packet_engine_config(path: str | Path) -> ProductPacketEngineConfig:
    config_path = Path(path)
    try:
        with config_path.open("rb") as handle:
            root = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ProductConfigurationError(f"cannot load configuration {config_path}: {exc}") from exc

    hardware = _table(root, "hardware")
    radio = _table(root, "radio")
    packet = _table(root, "packet")
    kiss = _table(root, "kiss")
    firmware = _table(root, "firmware")
    beacon = _table(root, "beacon")
    monitor = _optional_table(root, "monitor")
    storage = _optional_table(root, "storage")

    target = _string(hardware, "target")
    device = _string(radio, "device").strip()
    frequency_hz = _frequency_hz(radio.get("frequency_mhz"))
    tx_power = _integer(radio, "tx_power")
    tx_enabled = _boolean(radio, "tx_enabled")

    baud = _integer(packet, "baud")
    if baud != 1200:
        raise ProductConfigurationError("packet.baud must remain 1200")
    txdelay_ms = _integer(packet, "txdelay_ms")
    if txdelay_ms < 0 or txdelay_ms % 10 or txdelay_ms > 2550:
        raise ProductConfigurationError("packet.txdelay_ms must be 0..2550 in 10 ms increments")
    persist = _integer(packet, "persist")
    slottime_ms = _integer(packet, "slottime_ms")
    if slottime_ms < 10 or slottime_ms % 10 or slottime_ms > 2550:
        raise ProductConfigurationError("packet.slottime_ms must be 10..2550 in 10 ms increments")

    kiss_enabled = _boolean(kiss, "enabled")
    kiss_host = _string(kiss, "listen")
    kiss_port = _integer(kiss, "port")

    if _string(firmware, "required_product") != "YWD-1278":
        raise ProductConfigurationError("firmware.required_product must be 'YWD-1278'")
    if _boolean(firmware, "allow_automatic_flash"):
        raise ProductConfigurationError("the product daemon does not permit automatic firmware flash")
    if _boolean(beacon, "enabled"):
        raise ProductConfigurationError("beacon.enabled requires future 0F qualification")

    monitor_enabled = False
    monitor_log_frames = False
    database_path: Path | None = None
    if monitor is not None:
        monitor_enabled = _boolean(monitor, "enabled")
        monitor_log_frames = _boolean(monitor, "log_frames")
        if monitor_log_frames:
            if storage is None:
                raise ProductConfigurationError(
                    "monitor.log_frames=true requires a [storage] table"
                )
            raw_database = _string(storage, "database").strip()
            database_path = Path(raw_database)
            if not database_path.is_absolute():
                raise ProductConfigurationError("storage.database must be an absolute path")

    config = ProductPacketEngineConfig(
        target=target,
        device=device,
        frequency_hz=frequency_hz,
        tx_power=tx_power,
        tx_enabled=tx_enabled,
        txdelay=txdelay_ms // 10,
        persist=persist,
        slottime=slottime_ms // 10,
        kiss_enabled=kiss_enabled,
        kiss_host=kiss_host,
        kiss_port=kiss_port,
        monitor_enabled=monitor_enabled,
        monitor_log_frames=monitor_log_frames,
        database_path=database_path,
    )
    _validate_product_config(config)
    return config


class ProductPacketEngine:
    """Lifecycle owner for one production packet-engine instance."""

    def __init__(
        self,
        config: ProductPacketEngineConfig,
        *,
        transport_factory: TransportFactory | None = None,
        monotonic: MonotonicClock = time.monotonic,
        sleep: Sleeper = time.sleep,
        random_byte_source: RandomByteSource | None = None,
    ) -> None:
        _validate_product_config(config)
        self.config = config
        self._transport_factory = transport_factory or posix_serial_transport_factory(config.device)
        self._monotonic = monotonic
        self._sleep = sleep
        self._random_byte_source = random_byte_source or (lambda: secrets.randbelow(256))

        self.owner: TXModemOwner | None = None
        self.router: ContextualTXDelayRouter | None = None
        self.lifecycle: ContextualHalfDuplexSubmitter | None = None
        self.admission: ThreadSafeKISSDataAdmissionQueue | None = None
        self.session: TNCSessionState | None = None
        self.backend: ProductTNCBackend | None = None
        self.runtime: SustainedTNCRuntime | None = None
        self.observability: ProductObservability | None = None
        self.kiss_server: ThreadingKISSServer | None = None
        self.kiss_thread: threading.Thread | None = None

        self._started = False
        self._stopped = False
        self._rx_started = False
        self._identity = ""

    @property
    def snapshot(self) -> ProductPacketEngineSnapshot:
        owner_transactions = 0
        tx_queue_depth = 0
        decoded_rx_frames = 0
        tx_dispatches = 0
        failure = ""
        running = False
        if self.owner is not None:
            owner_snapshot = self.owner.snapshot
            owner_transactions = owner_snapshot.transactions
            running = owner_snapshot.running
        if self.admission is not None:
            tx_queue_depth = self.admission.snapshot.queue_depth
        if self.runtime is not None:
            runtime_snapshot = self.runtime.runtime_counters
            decoded_rx_frames = runtime_snapshot.decoded_rx_frames
            tx_dispatches = runtime_snapshot.tx_dispatches
            failure = runtime_snapshot.failure
            running = running and runtime_snapshot.running
        if self.observability is not None and self.config.monitor_log_frames:
            running = running and self.observability.snapshot.logger_running
        listener = None
        if self.kiss_server is not None:
            host, port = self.kiss_server.server_address[:2]
            listener = (str(host), int(port))
            running = running and bool(self.kiss_thread and self.kiss_thread.is_alive())
        return ProductPacketEngineSnapshot(
            running=running,
            firmware_identity=self._identity,
            tx_enabled=self.config.tx_enabled,
            kiss_listener=listener,
            owner_transactions=owner_transactions,
            tx_queue_depth=tx_queue_depth,
            decoded_rx_frames=decoded_rx_frames,
            tx_dispatches=tx_dispatches,
            failure=failure,
        )

    @property
    def mheard_db(self) -> MHeardDatabase | None:
        if self.observability is None:
            return None
        return self.observability.mheard_db

    def open_monitor(self) -> MonitorSubscription:
        if self.observability is None:
            raise ProductPacketEngineError("product observability is not started")
        return self.observability.open_monitor()

    def diagnostics_snapshot(self) -> DiagnosticsSnapshot:
        if self.observability is None:
            if self.runtime is None or self.backend is None:
                raise ProductPacketEngineError("product packet engine is not started")
            from ywd1278.monitor.diagnostics import DiagnosticsStatus

            return DiagnosticsStatus(runtime=self.runtime, backend=self.backend).snapshot()
        return self.observability.diagnostics_snapshot()

    def start(self) -> None:
        if self._started:
            raise ProductPacketEngineError("product packet engine cannot be restarted")
        self._started = True

        owner = TXModemOwner(
            self._transport_factory,
            queue_capacity=16,
            submit_timeout=0.20,
            default_transaction_timeout=1.50,
        )
        self.owner = owner

        try:
            owner.start(timeout=2.0)
            version = owner.get_version(timeout=1.5)
            if version.identity != PRODUCT_FIRMWARE_IDENTITY:
                raise ProductPacketEngineError(
                    "packet firmware identity mismatch: "
                    f"expected={PRODUCT_FIRMWARE_IDENTITY!r} actual={version.identity!r}"
                )
            self._identity = version.identity

            rf_status = owner.rf_status(timeout=1.5)
            rf_diag = owner.rf_diagnostics(timeout=1.5)
            if rf_status.remaining_selectors != 0 or rf_diag.tx_active != 0:
                raise ProductPacketEngineError("modem RF path is not idle before appliance startup")

            if self.config.tx_enabled:
                owner.apply_tx_qualification_profile(timeout=1.5)
            else:
                owner.set_rx_frequency(self.config.frequency_hz, timeout=1.5)
            owner.arm_rx_modem_io(timeout=1.5)
            owner.rx_start(timeout=1.5)
            self._rx_started = True

            router = ContextualTXDelayRouter(
                owner,
                transmit_enabled=self.config.tx_enabled,
                broker_queue_capacity=1,
                broker_submit_timeout=0.05,
                default_transaction_timeout=1.5,
            )
            self.router = router
            lifecycle = ContextualHalfDuplexSubmitter(
                owner,
                router,
                monotonic=self._monotonic,
                sleep=self._sleep,
                parameters=HalfDuplexParameters(
                    transaction_timeout_seconds=1.5,
                    tx_idle_poll_seconds=0.05,
                    tx_idle_timeout_seconds=5.0,
                ),
            )
            self.lifecycle = lifecycle
            admission = ThreadSafeKISSDataAdmissionQueue(
                lifecycle,
                monotonic=self._monotonic,
                queue_capacity=4,
                request_timeout_seconds=30.0,
                downstream_timeout_seconds=1.5,
            )
            self.admission = admission
            session = TNCSessionState(
                TNCParameterSnapshot(
                    txdelay=self.config.txdelay,
                    persist=self.config.persist,
                    slottime=self.config.slottime,
                )
            )
            self.session = session
            backend = ProductTNCBackend(
                admission,
                monotonic=self._monotonic,
                session=session,
                history_capacity=256,
                subscriber_queue_capacity=64,
                product_tx_enabled=self.config.tx_enabled,
            )
            self.backend = backend
            runtime = SustainedTNCRuntime(
                owner,
                backend,
                admission,
                expected_identity=PRODUCT_FIRMWARE_IDENTITY,
                monotonic=self._monotonic,
                random_byte_source=self._random_byte_source,
                read_maximum=200,
                idle_sleep_seconds=0.005,
                status_interval_seconds=0.25,
            )
            self.runtime = runtime

            observability = ProductObservability(
                ProductObservabilityConfig(
                    enabled=self.config.monitor_enabled,
                    log_frames=self.config.monitor_log_frames,
                    database_path=self.config.database_path,
                ),
                backend=backend,
                runtime=runtime,
            )
            self.observability = observability
            # Register the bounded logger subscriber before the RX runtime can
            # publish its first decoded frame.
            observability.start()
            runtime.start(timeout=1.5)

            if self.config.kiss_enabled:
                server, thread = start_server_thread(
                    backend,
                    host=self.config.kiss_host,
                    port=self.config.kiss_port,
                )
                self.kiss_server = server
                self.kiss_thread = thread

            self.check_health()
        except BaseException:
            self._cleanup(suppress_errors=True)
            raise

    def check_health(self) -> None:
        if self.owner is None or self.runtime is None:
            raise ProductPacketEngineError("product packet engine is not started")
        if not self.owner.snapshot.running:
            raise ProductPacketEngineError("modem owner is not running")
        self.runtime.check_health()
        if self.observability is not None:
            try:
                self.observability.check_health()
            except ProductObservabilityError as exc:
                raise ProductPacketEngineError(str(exc)) from exc
        if self.kiss_server is not None:
            if self.kiss_thread is None or not self.kiss_thread.is_alive():
                raise ProductPacketEngineError("KISS listener thread is not running")

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        errors = self._cleanup(suppress_errors=False)
        if errors:
            raise ProductPacketEngineError("one or more packet-engine shutdown operations failed") from errors[0]

    def _cleanup(self, *, suppress_errors: bool) -> list[BaseException]:
        errors: list[BaseException] = []

        if self.kiss_server is not None and self.kiss_thread is not None:
            try:
                stop_server_thread(self.kiss_server, self.kiss_thread)
            except BaseException as exc:
                errors.append(exc)
            finally:
                self.kiss_server = None
                self.kiss_thread = None

        # Stop the producer before the persistent observer, so no new decoded
        # events can be published after logger shutdown begins.
        if self.runtime is not None:
            try:
                self.runtime.stop(timeout=3.0)
            except BaseException as exc:
                errors.append(exc)

        if self.observability is not None:
            try:
                self.observability.stop()
            except BaseException as exc:
                errors.append(exc)

        if self.router is not None:
            try:
                self.router.close()
            except BaseException as exc:
                errors.append(exc)

        if self.owner is not None:
            if self._rx_started:
                try:
                    self.owner.rx_stop(timeout=1.5)
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    self._rx_started = False
            try:
                self.owner.stop(timeout=2.0)
            except BaseException as exc:
                errors.append(exc)

        if suppress_errors:
            return []
        return errors
