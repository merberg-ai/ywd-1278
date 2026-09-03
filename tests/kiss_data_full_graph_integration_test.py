#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import socket
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p7_fake_modem import ACTIVE_FLAGS, FakeClock, ThreadBoundHalfDuplexTransport  # noqa: E402
from ywd1278.ax25 import Address, append_fcs, build_ui_frame  # noqa: E402
from ywd1278.kiss.control import TNCSessionState  # noqa: E402
from ywd1278.kiss.framing import DATA, PERSIST, SLOTTIME, TXDELAY, encode  # noqa: E402
from ywd1278.kiss.server import start_server_thread, stop_server_thread  # noqa: E402
from ywd1278.kiss.tx_backend import TNCTransmitBackend  # noqa: E402
from ywd1278.kiss.tx_path import KISSDataAdmissionQueue, KISSDataRequestState  # noqa: E402
from ywd1278.modem import protocol  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.phy import frame_to_selectors  # noqa: E402
from ywd1278.tx.broker import P5_INITIAL_TONE, P5_POST_FLAGS, TXReceipt  # noqa: E402
from ywd1278.tx.contextual import ContextualHalfDuplexSubmitter, ContextualTXDelayRouter  # noqa: E402
from ywd1278.tx.half_duplex import HalfDuplexParameters  # noqa: E402
from ywd1278.tx.txdelay import resolve_txdelay  # noqa: E402


def wait_until(predicate, *, timeout: float = 1.5) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise TimeoutError("timed out waiting for localhost KISS state")


def build_body() -> bytes:
    return build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("YWD7"),
        path=[Address.parse("YWDNOD")],
        info=b"YWD-1278 P7 HOST KISS DATA",
        include_fcs=False,
    )


created: list[ThreadBoundHalfDuplexTransport] = []


def factory() -> ThreadBoundHalfDuplexTransport:
    transport = ThreadBoundHalfDuplexTransport()
    created.append(transport)
    return transport


clock = FakeClock()
owner = TXModemOwner(factory, queue_capacity=8)
owner.start(timeout=2.0)
router = ContextualTXDelayRouter(owner, transmit_enabled=True, broker_queue_capacity=1)
server = None
server_thread = None
try:
    owner.arm_rx_modem_io(timeout=1.5)
    owner.rx_start(timeout=1.5)
    assert owner.rx_status(timeout=1.5).flags & ACTIVE_FLAGS == ACTIVE_FLAGS

    lifecycle = ContextualHalfDuplexSubmitter(
        owner,
        router,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        parameters=HalfDuplexParameters(
            transaction_timeout_seconds=1.5,
            tx_idle_poll_seconds=0.05,
            tx_idle_timeout_seconds=1.0,
        ),
    )
    admission = KISSDataAdmissionQueue(lifecycle, queue_capacity=4)
    session = TNCSessionState()
    backend = TNCTransmitBackend(
        admission,
        monotonic=clock.monotonic,
        session=session,
        history_capacity=0,
    )
    server, server_thread = start_server_thread(backend, port=0)
    host, port = server.server_address[:2]

    payload = build_body()
    with socket.create_connection((host, port), timeout=1.0) as client:
        client.sendall(encode(bytes([50]), command=TXDELAY))
        client.sendall(encode(bytes([200]), command=PERSIST))
        client.sendall(encode(bytes([20]), command=SLOTTIME))
        wait_until(lambda: session.snapshot.generation == 3)

        client.sendall(encode(payload, command=DATA))
        wait_until(lambda: backend.ingress_counters.data_admitted == 1)

        client.sendall(encode(bytes([30]), command=TXDELAY))
        client.sendall(encode(bytes([0]), command=PERSIST))
        client.sendall(encode(bytes([10]), command=SLOTTIME))
        wait_until(lambda: session.snapshot.generation == 6)

    stop_server_thread(server, server_thread)
    server = None
    server_thread = None

    assert backend.ingress_counters.data_messages_received == 1
    assert backend.ingress_counters.data_admitted == 1
    assert admission.snapshot.queue_depth == 1
    assert (session.snapshot.txdelay, session.snapshot.persist, session.snapshot.slottime) == (30, 0, 10)

    assert admission.observe_rssi(now=0.00, raw_magnitude=106).downstream_called is False
    clear = admission.observe_rssi(now=0.26, raw_magnitude=106)
    assert clear.access is not None
    assert abs(clear.access.csma.next_slot_at - 0.46) < 1e-9

    def premature_randomness() -> int:
        raise AssertionError("captured 200 ms slot consumed randomness too early")

    assert admission.observe_rssi(
        now=0.37,
        raw_magnitude=106,
        random_byte_source=premature_randomness,
    ).downstream_called is False

    clock.now = 0.47
    dispatched = admission.observe_rssi(
        now=0.47,
        raw_magnitude=106,
        random_byte_source=lambda: 100,
    )
    assert dispatched.request_state is KISSDataRequestState.DISPATCHED
    assert dispatched.parameter_generation == 3
    assert isinstance(dispatched.downstream_result, TXReceipt)

    expected_with_fcs = append_fcs(payload)
    expected_selectors = frame_to_selectors(
        expected_with_fcs,
        pre_flags=resolve_txdelay(50).pre_flags,
        post_flags=P5_POST_FLAGS,
        initial_tone=P5_INITIAL_TONE,
    )

    transport = created[0]
    assert transport.tx_accept_count == 1
    assert transport.tx_selector_counts == [len(expected_selectors)]
    assert transport.generated_samples == len(expected_selectors) * 16
    assert transport.rx_stop_count == 1
    assert transport.rx_start_count == 2
    assert transport.rx_active is True
    assert set(transport.call_thread_ids) == {transport.owner_thread_id}
    assert transport.owner_thread_id == owner.snapshot.owner_thread_id
    assert transport.owner_thread_id != threading.get_ident()

    half = lifecycle.half_duplex_snapshot
    assert half.cycles_started == 1
    assert half.cycles_completed == 1
    assert half.downstream_accepted == 1
    assert half.failed_latched is False

    route = router.snapshot
    assert route.broker_profiles == (50,)
    assert route.contextual_submissions == 1
    assert route.contextual_failures == 0
    assert admission.snapshot.dispatched_requests == 1

    parsed = [protocol.parse_frame(request) for request in transport.requests]
    tx_indices = [
        i for i, item in enumerate(parsed)
        if item.command == protocol.YWD_RF
        and item.payload
        and item.payload[0] == protocol.RF_TX_TONES
    ]
    assert len(tx_indices) == 1
    tx_index = tx_indices[0]
    assert any(
        item.command == protocol.YWD_RX and item.payload == bytes((protocol.RX_STOP,))
        for item in parsed[:tx_index]
    )
    assert any(
        item.command == protocol.YWD_RX and item.payload == bytes((protocol.RX_START,))
        for item in parsed[tx_index + 1:]
    )
finally:
    if server is not None and server_thread is not None:
        stop_server_thread(server, server_thread)
    router.close()
    owner.stop(timeout=2.0)

transport = created[0]
assert transport.close_thread_id == transport.owner_thread_id

print("P7_FULL_KISS_TO_FAKE_MODEM_GRAPH=PASS")
print("KISS_TCP_CLIENT=REAL_LOCALHOST")
print("KISS_DATA_PARAMETER_GENERATION=3")
print("LIVE_PARAMETER_GENERATION_AFTER_ADMISSION=6")
print("CAPTURED_TXDELAY_UNITS=50")
print("CAPTURED_TXDELAY_PRE_FLAGS=75")
print("CAPTURED_PERSIST=200")
print("CAPTURED_SLOTTIME=20")
print("HALF_DUPLEX_RX_STOP_TX_RX_START=PASS")
print("TX_MODEM_OWNER=REAL")
print("TXDELAY_BROKER=REAL")
print("MODEM_TRANSPORT=FAKE_THREAD_BOUND")
print("POSIX_SERIAL_TRANSPORT=NO")
print("UART_OPENED=NO")
print("RF_TRANSMITTED=NO")
