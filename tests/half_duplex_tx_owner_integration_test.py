#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame  # noqa: E402
from ywd1278.modem import protocol  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.tx.access_queue import AccessRequestState, BoundedChannelAccessQueue  # noqa: E402
from ywd1278.tx.broker import TXBroker, TXReceipt  # noqa: E402
from ywd1278.tx.half_duplex import HalfDuplexParameters, PersistentHalfDuplexSubmitter  # noqa: E402


ACTIVE_FLAGS = 0x0D
IDLE_FLAGS = 0x04


def rx_status_response(*, active: bool, samples: int = 0, dropped: int = 0) -> bytes:
    flags = ACTIVE_FLAGS if active else IDLE_FLAGS
    payload = bytes(
        (
            protocol.RX_STATUS,
            protocol.RX_PROTOCOL_REVISION,
            flags,
            0,
            0,
            samples & 0xFF,
            (samples >> 8) & 0xFF,
            (samples >> 16) & 0xFF,
            (samples >> 24) & 0xFF,
            dropped & 0xFF,
            (dropped >> 8) & 0xFF,
        )
    )
    return protocol.build_frame(protocol.YWD_RX, payload)


def rf_status_response(*, remaining: int) -> bytes:
    return protocol.build_frame(
        protocol.YWD_RF,
        bytes(
            (
                protocol.RF_GET_STATUS,
                1,
                0x08 if remaining else 0x04,
                remaining & 0xFF,
                (remaining >> 8) & 0xFF,
                3 if remaining else 0,
            )
        ),
    )


def rf_diag_response(*, active: bool, generated_samples: int) -> bytes:
    return protocol.build_frame(
        protocol.YWD_RF,
        bytes(
            (
                protocol.RF_GET_DIAG,
                0,
                0,
                1 if generated_samples else 0,
                generated_samples & 0xFF,
                (generated_samples >> 8) & 0xFF,
                1 if active else 0,
            )
        ),
    )


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(float(seconds))
        self.now += float(seconds)


class ThreadBoundHalfDuplexTransport:
    """Stateful fake MMDVM wire endpoint for repeated RX/TX/RX cycles."""

    def __init__(self) -> None:
        self.owner_thread_id = threading.get_ident()
        self.call_thread_ids: list[int] = []
        self.requests: list[bytes] = []
        self.close_thread_id: int | None = None
        self.rf_ready = False
        self.rx_active = False
        self.rx_start_count = 0
        self.rx_stop_count = 0
        self.tx_accept_count = 0
        self.tx_selector_counts: list[int] = []
        self.busy_pairs_remaining = 0
        self.last_status_busy = False
        self.generated_samples = 0
        self.samples = 0

    def _assert_owner(self) -> None:
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("fake half-duplex transport escaped the modem owner thread")

    def transact(self, request: bytes, *, timeout: float) -> bytes:
        self._assert_owner()
        self.call_thread_ids.append(threading.get_ident())
        self.requests.append(bytes(request))
        frame = protocol.parse_frame(request)

        if frame.command == protocol.SET_CONFIG:
            self.rf_ready = True
            return protocol.ack_for(protocol.SET_CONFIG)

        if frame.command == protocol.YWD_RX:
            sub = frame.payload[0]
            if sub == protocol.RX_START:
                if not self.rf_ready or self.rx_active or self.busy_pairs_remaining:
                    return protocol.nak_for(protocol.YWD_RX, 5)
                self.rx_active = True
                self.rx_start_count += 1
                return protocol.ack_for(protocol.YWD_RX)
            if sub == protocol.RX_STOP:
                if not self.rx_active:
                    return protocol.nak_for(protocol.YWD_RX, 5)
                self.rx_active = False
                self.rx_stop_count += 1
                return protocol.ack_for(protocol.YWD_RX)
            if sub == protocol.RX_STATUS:
                self.samples += 100
                return rx_status_response(active=self.rx_active, samples=self.samples)
            raise AssertionError(f"unexpected fake YWD_RX request: {request.hex()}")

        if frame.command == protocol.YWD_RF:
            sub = frame.payload[0]
            if sub == protocol.RF_GET_STATUS:
                busy = self.busy_pairs_remaining > 0
                self.last_status_busy = busy
                remaining = self.tx_selector_counts[-1] if busy and self.tx_selector_counts else 0
                return rf_status_response(remaining=remaining)
            if sub == protocol.RF_GET_DIAG:
                busy = self.last_status_busy
                if busy and self.busy_pairs_remaining > 0:
                    self.busy_pairs_remaining -= 1
                return rf_diag_response(active=busy, generated_samples=self.generated_samples)
            if sub == protocol.RF_TX_TONES:
                if self.rx_active:
                    return protocol.nak_for(protocol.YWD_RF, 5)
                selector_count = frame.payload[1] | (frame.payload[2] << 8)
                self.tx_accept_count += 1
                self.tx_selector_counts.append(selector_count)
                self.generated_samples = selector_count * 16
                self.busy_pairs_remaining = 2
                return protocol.ack_for(protocol.YWD_RF)
            raise AssertionError(f"unexpected fake YWD_RF request: {request.hex()}")

        raise AssertionError(f"unexpected fake modem command: {request.hex()}")

    def close(self) -> None:
        self._assert_owner()
        self.close_thread_id = threading.get_ident()


def build_cycle_frame(index: int) -> bytes:
    return build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("YWD4E"),
        info=f"YWD-1278 P4E HOST CYCLE {index}/3".encode("ascii"),
        include_fcs=True,
    )


created: list[ThreadBoundHalfDuplexTransport] = []


def factory() -> ThreadBoundHalfDuplexTransport:
    transport = ThreadBoundHalfDuplexTransport()
    created.append(transport)
    return transport


clock = FakeClock()
owner = TXModemOwner(factory, queue_capacity=8)
owner.start(timeout=2.0)
broker = TXBroker(owner, transmit_enabled=True, queue_capacity=2)
broker.start()
try:
    owner.arm_rx_modem_io(timeout=1.5)
    owner.rx_start(timeout=1.5)
    initial = owner.rx_status(timeout=1.5)
    assert initial.flags & ACTIVE_FLAGS == ACTIVE_FLAGS

    lifecycle = PersistentHalfDuplexSubmitter(
        owner,
        broker,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        parameters=HalfDuplexParameters(
            transaction_timeout_seconds=1.5,
            tx_idle_poll_seconds=0.05,
            tx_idle_timeout_seconds=1.0,
        ),
    )
    queue = BoundedChannelAccessQueue(lifecycle, queue_capacity=4)

    # Cycle 1: startup clear qualification -> full slot -> READY.
    queue.enqueue(build_cycle_frame(1), now=0.00)
    assert queue.observe_rssi(now=0.00, raw_magnitude=106).downstream_called is False
    assert queue.observe_rssi(now=0.26, raw_magnitude=106).downstream_called is False
    first = queue.observe_rssi(now=0.37, raw_magnitude=106, random_byte_source=lambda: 0)
    assert first.request_state is AccessRequestState.DISPATCHED
    assert isinstance(first.downstream_result, TXReceipt)
    assert created[0].rx_active is True

    # Cycle 2: an actual BUSY observation resets access before the same
    # qualified clear/recent-RX/slot path can dispatch another distinct frame.
    queue.enqueue(build_cycle_frame(2), now=0.50)
    assert queue.observe_rssi(now=0.50, raw_magnitude=48).downstream_called is False
    assert queue.observe_rssi(now=0.60, raw_magnitude=106).downstream_called is False
    assert queue.observe_rssi(now=0.86, raw_magnitude=106).downstream_called is False
    second = queue.observe_rssi(now=0.97, raw_magnitude=106, random_byte_source=lambda: 0)
    assert second.request_state is AccessRequestState.DISPATCHED
    assert isinstance(second.downstream_result, TXReceipt)
    assert created[0].rx_active is True

    # Cycle 3 proves the lifecycle is reusable again after two complete
    # RX_STOP/TX/RX_START handoffs.
    queue.enqueue(build_cycle_frame(3), now=1.20)
    assert queue.observe_rssi(now=1.20, raw_magnitude=108).downstream_called is False
    assert queue.observe_rssi(now=1.46, raw_magnitude=108).downstream_called is False
    third = queue.observe_rssi(now=1.57, raw_magnitude=108, random_byte_source=lambda: 0)
    assert third.request_state is AccessRequestState.DISPATCHED
    assert isinstance(third.downstream_result, TXReceipt)
    assert created[0].rx_active is True

    transport = created[0]
    assert transport.rx_start_count == 4  # initial start + restart after each TX
    assert transport.rx_stop_count == 3
    assert transport.tx_accept_count == 3
    assert len(transport.tx_selector_counts) == 3
    assert all(count > 0 for count in transport.tx_selector_counts)
    assert set(transport.call_thread_ids) == {transport.owner_thread_id}
    assert transport.owner_thread_id == owner.snapshot.owner_thread_id
    assert transport.owner_thread_id != threading.get_ident()

    snapshot = lifecycle.snapshot
    assert snapshot.cycles_started == 3
    assert snapshot.cycles_completed == 3
    assert snapshot.downstream_accepted == 3
    assert snapshot.pre_transmit_failures == 0
    assert snapshot.downstream_failures == 0
    assert snapshot.post_transmit_failures == 0
    assert snapshot.rx_stop_operations == 3
    assert snapshot.rx_restart_operations == 3
    assert snapshot.failed_latched is False
    assert queue.snapshot.dispatched_requests == 3
    assert broker.snapshot.submitted == 3
    assert broker.snapshot.accepted == 3
    assert broker.snapshot.failed == 0
finally:
    broker.stop(timeout=2.0)
    owner.stop(timeout=2.0)

transport = created[0]
assert transport.close_thread_id == transport.owner_thread_id

# Wire-level ordering: every TX_TONES must be bracketed by RX_STOP before it and
# a later RX_START before the next TX_TONES.
parsed = [protocol.parse_frame(request) for request in transport.requests]
tx_indices = [
    index
    for index, frame in enumerate(parsed)
    if frame.command == protocol.YWD_RF and frame.payload and frame.payload[0] == protocol.RF_TX_TONES
]
assert len(tx_indices) == 3
for ordinal, tx_index in enumerate(tx_indices):
    before = parsed[:tx_index]
    assert any(
        frame.command == protocol.YWD_RX and frame.payload == bytes((protocol.RX_STOP,))
        for frame in before
    )
    boundary = tx_indices[ordinal + 1] if ordinal + 1 < len(tx_indices) else len(parsed)
    after = parsed[tx_index + 1 : boundary]
    assert any(
        frame.command == protocol.YWD_RX and frame.payload == bytes((protocol.RX_START,))
        for frame in after
    )

print("P4E_REAL_GRAPH_REPEATED_HALF_DUPLEX=PASS")
print("ACCESS_QUEUE=REAL")
print("TX_BROKER=REAL")
print("TX_MODEM_OWNER=REAL")
print("MODEM_TRANSPORT=FAKE_THREAD_BOUND")
print("COMPLETE_RX_TX_RX_CYCLES=3")
print("RX_START_COUNT=4")
print("RX_STOP_COUNT=3")
print("TX_TONES_ACCEPTED=3")
print("RX_ACTIVE_AFTER_EACH_CYCLE=YES")
print("SINGLE_MODEM_OWNER_THREAD=PASS")
print("KISS_TX_CONNECTED=NO")
print("POSIX_SERIAL_TRANSPORT=NO")
print("UART_OPENED=NO")
print("RF_TRANSMITTED=NO")
