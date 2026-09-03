#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame  # noqa: E402
from ywd1278.modem import protocol  # noqa: E402
from ywd1278.tx.access_queue import (  # noqa: E402
    AccessRequestState,
    BoundedChannelAccessQueue,
)
from ywd1278.tx.broker import TXBroker, TXReceipt  # noqa: E402
from ywd1278.tx.csma import CSMAState  # noqa: E402

P5_PACKED_SHA256 = "30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e"


def p5_reference_frame() -> bytes:
    return build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("APYWD1"),
        info=b"AX25-5B KISS TX TEST",
        include_fcs=True,
    )


class Bytes:
    def __init__(self, values: list[int]) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> int:
        if not self.values:
            raise AssertionError("random source exhausted")
        self.calls += 1
        return self.values.pop(0)


class FakeTXModemPort:
    """Broker-facing fake only; no ModemOwner, transport, UART, or RF exists."""

    def __init__(self, *, remaining_selectors: int = 0, fail_tx: bool = False) -> None:
        self.remaining_selectors = int(remaining_selectors)
        self.fail_tx = bool(fail_tx)
        self.status_calls: list[float | None] = []
        self.tx_calls: list[tuple[int, bytes, float | None]] = []

    def rf_status(self, *, timeout: float | None = None) -> protocol.RFStatus:
        self.status_calls.append(timeout)
        return protocol.RFStatus(
            flags=0x08,
            remaining_selectors=self.remaining_selectors,
            mode=0,
        )

    def transmit_selector_burst(
        self,
        selector_count: int,
        packed_selectors: bytes,
        *,
        timeout: float | None = None,
    ) -> None:
        self.tx_calls.append((int(selector_count), bytes(packed_selectors), timeout))
        if self.fail_tx:
            raise RuntimeError("synthetic fake-modem TX rejection")


def drive_ready(queue: BoundedChannelAccessQueue, *, start: float) -> object:
    queue.observe_rssi(now=start, raw_magnitude=106)
    queue.observe_rssi(now=start + 0.26, raw_magnitude=106)
    return queue.observe_rssi(
        now=start + 0.37,
        raw_magnitude=106,
        random_byte_source=Bytes([0]),
    )


# Happy path: P4a waits through P2/P1, then the real P13a TXBroker validates and
# serializes the frozen P5 reference frame before invoking only the fake modem.
owner = FakeTXModemPort()
broker = TXBroker(owner, transmit_enabled=True, queue_capacity=2)
broker.start()
try:
    queue = BoundedChannelAccessQueue(broker)
    reference = p5_reference_frame()
    queue.enqueue(reference, now=0.0)

    first = queue.observe_rssi(now=0.0, raw_magnitude=106)
    assert first.downstream_called is False
    assert owner.status_calls == []
    assert owner.tx_calls == []

    second = queue.observe_rssi(now=0.26, raw_magnitude=106)
    assert second.downstream_called is False
    assert second.access is not None and second.access.csma.state is CSMAState.WAIT_SLOT
    assert owner.status_calls == []
    assert owner.tx_calls == []

    result = queue.observe_rssi(
        now=0.37,
        raw_magnitude=106,
        random_byte_source=Bytes([0]),
    )
    assert result.request_state is AccessRequestState.DISPATCHED
    assert result.downstream_called is True
    assert isinstance(result.downstream_result, TXReceipt)
    receipt = result.downstream_result
    assert receipt.frame_bytes == 38
    assert receipt.selector_count == 691
    assert receipt.packed_selector_bytes == 87
    assert receipt.packed_selector_sha256 == P5_PACKED_SHA256
    assert len(owner.status_calls) == 1
    assert len(owner.tx_calls) == 1
    selector_count, packed, timeout = owner.tx_calls[0]
    assert selector_count == 691
    assert len(packed) == 87
    assert hashlib.sha256(packed).hexdigest() == P5_PACKED_SHA256
    assert timeout == 1.5
    assert broker.snapshot.submitted == 1
    assert broker.snapshot.accepted == 1
    assert broker.snapshot.failed == 0
    assert queue.snapshot.dispatched_requests == 1
finally:
    broker.stop()

# Broker busy preflight stays fail-closed behind the access queue. READY reaches
# the broker exactly once, but pending selectors prevent any selector burst.
busy_owner = FakeTXModemPort(remaining_selectors=17)
busy_broker = TXBroker(busy_owner, transmit_enabled=True)
busy_broker.start()
try:
    busy_queue = BoundedChannelAccessQueue(busy_broker)
    busy_queue.enqueue(p5_reference_frame(), now=10.0)
    result = drive_ready(busy_queue, start=10.0)
    assert result.request_state is AccessRequestState.DOWNSTREAM_FAILED
    assert result.downstream_called is True
    assert "TXBrokerBusy" in result.downstream_error
    assert len(busy_owner.status_calls) == 1
    assert busy_owner.tx_calls == []
    assert busy_broker.snapshot.busy_rejections == 1
    assert busy_broker.snapshot.failed == 1
    assert busy_queue.snapshot.downstream_failures == 1

    # Terminal request cannot be retried by later channel samples.
    busy_queue.observe_rssi(now=10.50, raw_magnitude=106, random_byte_source=Bytes([0]))
    assert len(busy_owner.status_calls) == 1
    assert busy_owner.tx_calls == []
finally:
    busy_broker.stop()

# A broker left at its product-safe default transmit-disabled state fails at the
# downstream boundary without touching even fake modem status.
disabled_owner = FakeTXModemPort()
disabled_broker = TXBroker(disabled_owner)
disabled_broker.start()
try:
    disabled_queue = BoundedChannelAccessQueue(disabled_broker)
    disabled_queue.enqueue(p5_reference_frame(), now=20.0)
    result = drive_ready(disabled_queue, start=20.0)
    assert result.request_state is AccessRequestState.DOWNSTREAM_FAILED
    assert "TXBrokerDisabled" in result.downstream_error
    assert disabled_owner.status_calls == []
    assert disabled_owner.tx_calls == []
    assert disabled_broker.snapshot.transmit_enabled is False
finally:
    disabled_broker.stop()

# P4a intentionally accepts an otherwise valid-FCS long frame; the real broker
# remains authoritative for Bell-202 selector-limit rejection. No fake modem
# status/TX call is reached when serialization exceeds MAX_SELECTORS.
overflow_owner = FakeTXModemPort()
overflow_broker = TXBroker(overflow_owner, transmit_enabled=True)
overflow_broker.start()
try:
    overflow_queue = BoundedChannelAccessQueue(overflow_broker)
    overflow = build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("APYWD1"),
        info=b"X" * 400,
        include_fcs=True,
    )
    overflow_queue.enqueue(overflow, now=30.0)
    result = drive_ready(overflow_queue, start=30.0)
    assert result.request_state is AccessRequestState.DOWNSTREAM_FAILED
    assert "TXBrokerFrameRejected" in result.downstream_error
    assert overflow_owner.status_calls == []
    assert overflow_owner.tx_calls == []
    assert overflow_broker.snapshot.invalid_rejections == 1
finally:
    overflow_broker.stop()

# A failure from the fake modem after the broker preflight is propagated through
# the broker and becomes one terminal P4a downstream failure with no auto retry.
fail_owner = FakeTXModemPort(fail_tx=True)
fail_broker = TXBroker(fail_owner, transmit_enabled=True)
fail_broker.start()
try:
    fail_queue = BoundedChannelAccessQueue(fail_broker)
    fail_queue.enqueue(p5_reference_frame(), now=40.0)
    result = drive_ready(fail_queue, start=40.0)
    assert result.request_state is AccessRequestState.DOWNSTREAM_FAILED
    assert "TXBrokerError" in result.downstream_error
    assert len(fail_owner.status_calls) == 1
    assert len(fail_owner.tx_calls) == 1
    assert fail_broker.snapshot.failed == 1
    assert fail_queue.snapshot.downstream_failures == 1
    fail_queue.observe_rssi(now=40.50, raw_magnitude=106, random_byte_source=Bytes([0]))
    assert len(fail_owner.status_calls) == 1
    assert len(fail_owner.tx_calls) == 1
finally:
    fail_broker.stop()

print("P4B_REAL_BROKER_FAKE_MODEM_INTEGRATION=PASS")
print("P5_SELECTOR_COUNT=691")
print(f"P5_PACKED_SHA256={P5_PACKED_SHA256}")
print("BROKER_BUSY_FAIL_CLOSED=PASS")
print("BROKER_DISABLED_FAIL_CLOSED=PASS")
print("BROKER_SELECTOR_LIMIT_AUTHORITATIVE=PASS")
print("DOWNSTREAM_FAILURE_RETRY=NO")
print("REAL_TX_BROKER_CLASS_USED=YES")
print("REAL_TX_MODEM_OWNER_USED=NO")
print("MODEM_TRANSPORT_USED=NO")
print("UART_OPENED=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("RF_TRANSMITTED=NO")
