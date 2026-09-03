#!/usr/bin/env python3
from __future__ import annotations

import hashlib
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
from ywd1278.tx.csma import CSMAState  # noqa: E402

P5_PACKED_SHA256 = "30718ba5a4368e82bab69e6343f95c7e226cd08426844ed328ad8c52fbfd750e"


def p5_reference_frame() -> bytes:
    return build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("APYWD1"),
        info=b"AX25-5B KISS TX TEST",
        include_fcs=True,
    )


def idle_rf_status_response() -> bytes:
    return protocol.build_frame(
        protocol.YWD_RF,
        bytes((protocol.RF_GET_STATUS, 1, 0x08, 0, 0, 0)),
    )


class ThreadBoundTransport:
    """Fake wire endpoint created and used only inside TXModemOwner's thread."""

    def __init__(self) -> None:
        self.owner_thread_id = threading.get_ident()
        self.call_thread_ids: list[int] = []
        self.requests: list[bytes] = []
        self.timeouts: list[float] = []
        self.close_thread_id: int | None = None

    def _assert_owner(self) -> None:
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("fake modem transport escaped the single owner thread")

    def transact(self, request: bytes, *, timeout: float) -> bytes:
        self._assert_owner()
        self.call_thread_ids.append(threading.get_ident())
        self.requests.append(bytes(request))
        self.timeouts.append(float(timeout))
        frame = protocol.parse_frame(request)
        if frame.command != protocol.YWD_RF:
            raise AssertionError(f"unexpected modem command: {request.hex()}")
        if frame.payload == bytes((protocol.RF_GET_STATUS,)):
            return idle_rf_status_response()
        if frame.payload and frame.payload[0] == protocol.RF_TX_TONES:
            return protocol.ack_for(protocol.YWD_RF)
        raise AssertionError(f"unexpected YWD_RF payload: {frame.payload.hex()}")

    def close(self) -> None:
        self._assert_owner()
        self.close_thread_id = threading.get_ident()


class Bytes:
    def __init__(self, values: list[int]) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> int:
        if not self.values:
            raise AssertionError("random source exhausted")
        self.calls += 1
        return self.values.pop(0)


created: list[ThreadBoundTransport] = []


def factory() -> ThreadBoundTransport:
    transport = ThreadBoundTransport()
    created.append(transport)
    return transport


owner = TXModemOwner(factory, queue_capacity=4)
owner.start(timeout=2.0)
broker = TXBroker(owner, transmit_enabled=True, queue_capacity=2)
broker.start()
try:
    queue = BoundedChannelAccessQueue(broker)
    reference = p5_reference_frame()
    queue.enqueue(reference, now=0.0)

    # P2/P1 gating happens completely before the concrete broker/owner graph is
    # touched. The transport exists because the owner is running, but there are
    # no modem transactions before READY.
    obs = queue.observe_rssi(now=0.00, raw_magnitude=106)
    assert obs.downstream_called is False
    assert created and created[0].requests == []

    obs = queue.observe_rssi(now=0.26, raw_magnitude=106)
    assert obs.downstream_called is False
    assert obs.access is not None and obs.access.csma.state is CSMAState.WAIT_SLOT
    assert created[0].requests == []

    rng = Bytes([0])
    obs = queue.observe_rssi(now=0.37, raw_magnitude=106, random_byte_source=rng)
    assert obs.request_state is AccessRequestState.DISPATCHED
    assert obs.downstream_called is True
    assert obs.access is not None and obs.access.csma.state is CSMAState.READY
    assert isinstance(obs.downstream_result, TXReceipt)
    receipt = obs.downstream_result
    assert receipt.frame_bytes == 38
    assert receipt.selector_count == 691
    assert receipt.packed_selector_bytes == 87
    assert receipt.packed_selector_sha256 == P5_PACKED_SHA256
    assert rng.calls == 1

    transport = created[0]
    assert len(transport.requests) == 2
    assert transport.requests[0] == protocol.rf_status_request()
    status_frame = protocol.parse_frame(transport.requests[0], expected_command=protocol.YWD_RF)
    assert status_frame.payload == bytes((protocol.RF_GET_STATUS,))

    tx_request = transport.requests[1]
    tx_frame = protocol.parse_frame(tx_request, expected_command=protocol.YWD_RF)
    assert tx_frame.payload[0] == protocol.RF_TX_TONES
    selector_count = tx_frame.payload[1] | (tx_frame.payload[2] << 8)
    packed = tx_frame.payload[3:]
    assert selector_count == 691
    assert len(packed) == 87
    assert hashlib.sha256(packed).hexdigest() == P5_PACKED_SHA256

    # Both wire transactions occur on exactly the owner thread, not the caller
    # or broker worker thread. The owner accounts for exactly those two calls.
    assert set(transport.call_thread_ids) == {transport.owner_thread_id}
    assert transport.owner_thread_id == owner.snapshot.owner_thread_id
    assert transport.owner_thread_id != threading.get_ident()
    assert owner.snapshot.transactions == 2
    assert transport.timeouts == [1.5, 1.5]

    assert broker.snapshot.submitted == 1
    assert broker.snapshot.accepted == 1
    assert broker.snapshot.failed == 0
    assert queue.snapshot.dispatched_requests == 1

    # Once removed from P4a, later observations cannot emit another wire TX.
    queue.observe_rssi(now=0.50, raw_magnitude=48, random_byte_source=Bytes([0]))
    assert len(transport.requests) == 2
    assert owner.snapshot.transactions == 2
finally:
    broker.stop(timeout=2.0)
    owner.stop(timeout=2.0)

transport = created[0]
assert transport.close_thread_id == transport.owner_thread_id
assert not owner.snapshot.running

print("P4C_FULL_SOFTWARE_GRAPH_FAKE_TRANSPORT=PASS")
print("ACCESS_QUEUE=REAL")
print("TX_BROKER=REAL")
print("TX_MODEM_OWNER=REAL")
print("MODEM_TRANSPORT=FAKE_THREAD_BOUND")
print("MODEM_TRANSACTIONS=2")
print("WIRE_REQUEST_1=YWD_RF_GET_STATUS")
print("WIRE_REQUEST_2=YWD_RF_TX_TONES")
print("P5_SELECTOR_COUNT=691")
print(f"P5_PACKED_SHA256={P5_PACKED_SHA256}")
print("SINGLE_MODEM_OWNER_THREAD=PASS")
print("DUPLICATE_DISPATCH=NO")
print("POSIX_SERIAL_TRANSPORT=NO")
print("UART_OPENED=NO")
print("KISS_TX_CONNECTED=NO")
print("PRODUCT_TX_ENABLED=NO")
print("RF_TRANSMITTED=NO")
