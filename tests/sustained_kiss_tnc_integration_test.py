#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path
import socket
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p8_fake_modem import IDENTITY, P8ThreadBoundTransport  # noqa: E402
from ywd1278.ax25 import Address, append_fcs, build_ui_frame  # noqa: E402
from ywd1278.kiss.control import TNCSessionState  # noqa: E402
from ywd1278.kiss.framing import DATA, KISSStreamDecoder, TXDELAY, encode  # noqa: E402
from ywd1278.kiss.server import start_server_thread, stop_server_thread  # noqa: E402
from ywd1278.kiss.sustained import SustainedTNCBackend, ThreadSafeKISSDataAdmissionQueue  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.phy import SAMPLE_RATE, frame_to_selectors  # noqa: E402
from ywd1278.phy.bell202_rx import MARK_HZ, SPACE_HZ  # noqa: E402
from ywd1278.service.tnc_runtime import SustainedTNCRuntime  # noqa: E402
from ywd1278.tx.broker import P5_INITIAL_TONE, P5_POST_FLAGS  # noqa: E402
from ywd1278.tx.contextual import ContextualHalfDuplexSubmitter, ContextualTXDelayRouter  # noqa: E402
from ywd1278.tx.half_duplex import HalfDuplexParameters  # noqa: E402
from ywd1278.tx.txdelay import resolve_txdelay  # noqa: E402


def wait_until(predicate, *, timeout: float = 6.0, detail: str = "condition") -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise TimeoutError(f"timed out waiting for {detail}")


def outgoing_body(index: int) -> bytes:
    return build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("YWD8"),
        path=[Address.parse("YWDNOD")],
        info=f"YWD-1278 P8 HOST {index}/4".encode("ascii"),
        include_fcs=False,
    )


def recovery_body() -> bytes:
    return build_ui_frame(
        source=Address.parse("KJ6YWD-5"),
        destination=Address.parse("YWD8RX"),
        info=b"P8 sustained RX recovery",
        include_fcs=False,
    )


def synthesize(selectors: list[int], *, symbol_offset: float = 7.0) -> list[int]:
    period = SAMPLE_RATE / 1200.0
    total = int(math.ceil(symbol_offset + len(selectors) * period)) + 8
    samples: list[int] = []
    phase = 0.37
    for n in range(total):
        relative = n - symbol_offset
        if relative < 0.0:
            samples.append(n & 1)
            continue
        index = int(relative // period)
        selector = selectors[-1] if index >= len(selectors) else selectors[index]
        frequency = SPACE_HZ if selector else MARK_HZ
        samples.append(1 if math.sin(phase) >= 0.0 else 0)
        phase += 2.0 * math.pi * frequency / SAMPLE_RATE
        if phase > 2.0 * math.pi:
            phase -= 2.0 * math.pi
    return samples


def pack(samples: list[int]) -> bytes:
    out = bytearray((len(samples) + 7) // 8)
    for index, value in enumerate(samples):
        if value:
            out[index >> 3] |= 0x80 >> (index & 7)
    return bytes(out)


def recovery_capture() -> bytes:
    selectors = frame_to_selectors(append_fcs(recovery_body()), pre_flags=45, post_flags=6)
    return pack(synthesize(selectors))


def recv_one(sock: socket.socket, *, timeout: float = 3.0):  # type: ignore[no-untyped-def]
    decoder = KISSStreamDecoder()
    deadline = time.monotonic() + timeout
    sock.settimeout(0.05)
    while time.monotonic() < deadline:
        try:
            chunk = sock.recv(4096)
        except socket.timeout:
            continue
        if not chunk:
            break
        messages = decoder.feed(chunk)
        if messages:
            return messages[0]
    raise TimeoutError("timed out waiting for KISS history frame")


created: list[P8ThreadBoundTransport] = []


def factory() -> P8ThreadBoundTransport:
    transport = P8ThreadBoundTransport()
    created.append(transport)
    return transport


owner = TXModemOwner(factory, queue_capacity=16)
owner.start(timeout=2.0)
router = ContextualTXDelayRouter(
    owner,
    transmit_enabled=True,
    broker_queue_capacity=1,
)
server = None
server_thread = None
runtime = None
try:
    owner.arm_rx_modem_io(timeout=1.5)
    owner.rx_start(timeout=1.5)

    lifecycle = ContextualHalfDuplexSubmitter(
        owner,
        router,
        monotonic=time.monotonic,
        sleep=time.sleep,
        parameters=HalfDuplexParameters(
            transaction_timeout_seconds=1.5,
            tx_idle_poll_seconds=0.01,
            tx_idle_timeout_seconds=1.0,
        ),
    )
    admission = ThreadSafeKISSDataAdmissionQueue(
        lifecycle,
        queue_capacity=3,
        request_timeout_seconds=8.0,
        downstream_timeout_seconds=1.5,
    )
    session = TNCSessionState()
    backend = SustainedTNCBackend(
        admission,
        monotonic=time.monotonic,
        session=session,
        history_capacity=8,
        subscriber_queue_capacity=8,
    )
    server, server_thread = start_server_thread(backend, host="127.0.0.1", port=0)
    host, port = server.server_address[:2]

    bodies = [outgoing_body(i) for i in range(1, 5)]
    txdelays = [20, 30, 40, 50]

    # Client 1 fills the bounded queue with three immutable generations, then
    # proves the fourth DATA frame is dropped rather than expanding the queue.
    with socket.create_connection((host, port), timeout=1.0) as client1:
        for units, body in zip(txdelays[:3], bodies[:3]):
            client1.sendall(encode(bytes((units,)), command=TXDELAY))
            wait_until(
                lambda units=units: session.snapshot.txdelay == units,
                detail=f"TXDELAY={units}",
            )
            client1.sendall(encode(body, command=DATA))
            expected = txdelays.index(units) + 1
            wait_until(
                lambda expected=expected: backend.ingress_counters.data_admitted == expected,
                detail=f"DATA admission {expected}",
            )

        client1.sendall(encode(bytes((50,)), command=TXDELAY))
        wait_until(lambda: session.snapshot.txdelay == 50, detail="full-queue TXDELAY update")
        client1.sendall(encode(bodies[3], command=DATA))
        wait_until(
            lambda: backend.ingress_counters.data_queue_full_drops == 1,
            detail="bounded queue-full drop",
        )

    wait_until(
        lambda: backend.connection_counters.total_disconnects == 1,
        detail="client1 disconnect accounting",
    )
    assert admission.snapshot.queue_depth == 3
    assert backend.ingress_counters.data_messages_received == 4
    assert backend.ingress_counters.data_admitted == 3
    assert backend.ingress_counters.data_queue_full_drops == 1

    runtime = SustainedTNCRuntime(
        owner,
        backend,
        admission,
        expected_identity=IDENTITY,
        monotonic=time.monotonic,
        random_byte_source=lambda: 0,
        read_maximum=200,
        idle_sleep_seconds=0.002,
        status_interval_seconds=0.05,
    )
    runtime.start(timeout=1.5)

    wait_until(lambda: created[0].tx_accept_count >= 1, detail="first sustained TX")

    # Inject one complete FCS-valid Bell-202 capture after the first TX.  The
    # runtime must decode it after its mandatory post-TX decoder reset and keep
    # it in KISS history while no client is connected.
    created[0].inject_rx_packed(recovery_capture())
    wait_until(
        lambda: runtime.runtime_counters.decoded_rx_frames >= 1,
        detail="post-TX sustained RX decode",
    )

    # Client 2 reconnects, receives the stored RX history frame, then retries
    # the previously-full fourth DATA frame.  Its fresh generation must use the
    # already-updated TXDELAY=50 state.
    with socket.create_connection((host, port), timeout=1.0) as client2:
        history = recv_one(client2)
        assert history.port == 0 and history.command == DATA
        assert history.frame == recovery_body()
        client2.sendall(encode(bodies[3], command=DATA))
        wait_until(
            lambda: backend.ingress_counters.data_admitted == 4,
            detail="client2 DATA admission after queue space",
        )

    wait_until(
        lambda: backend.connection_counters.total_disconnects == 2,
        detail="client2 disconnect accounting",
    )
    wait_until(lambda: created[0].tx_accept_count == 4, timeout=8.0, detail="four sustained TX cycles")
    wait_until(lambda: admission.snapshot.queue_depth == 0, detail="P8 queue drain")
    wait_until(lambda: runtime.runtime_counters.tx_dispatches == 4, detail="runtime dispatch accounting")

    runtime.check_health()
    accounting = runtime.accounting
    assert accounting.runtime.failure == ""
    assert accounting.runtime.tx_dispatches == 4
    assert accounting.runtime.decoder_resets_after_tx == 4
    assert accounting.runtime.decoded_rx_frames >= 1
    assert accounting.runtime.rssi_samples > 0
    assert accounting.queue.tx_queue_capacity == 3
    assert accounting.queue.tx_queue_accepted == 4
    assert accounting.queue.tx_queue_full_drops == 1
    assert accounting.queue.tx_dispatched == 4
    assert accounting.queue.tx_access_timeouts == 0
    assert accounting.queue.tx_downstream_failures == 0
    assert accounting.ingress.data_messages_received == 5
    assert accounting.ingress.data_admitted == 4
    assert accounting.ingress.data_queue_full_drops == 1
    assert accounting.connections.total_connections == 2
    assert accounting.connections.total_disconnects == 2
    assert accounting.connections.active_connections == 0
    assert accounting.subscriber_drops == 0

    transport = created[0]
    assert transport.tx_accept_count == 4
    assert transport.rx_stop_count == 4
    assert transport.rx_start_count == 5
    assert transport.rx_active is True
    assert set(transport.call_thread_ids) == {transport.owner_thread_id}
    assert transport.owner_thread_id == owner.snapshot.owner_thread_id
    assert transport.owner_thread_id != threading.get_ident()

    route = router.snapshot
    assert route.broker_profiles == (20, 30, 40, 50)
    assert route.contextual_submissions == 4
    assert route.contextual_failures == 0

    expected_counts = []
    for body, units in zip(bodies, txdelays):
        expected = frame_to_selectors(
            append_fcs(body),
            pre_flags=resolve_txdelay(units).pre_flags,
            post_flags=P5_POST_FLAGS,
            initial_tone=P5_INITIAL_TONE,
        )
        expected_counts.append(len(expected))
    assert transport.tx_selector_counts == expected_counts

    half = lifecycle.half_duplex_snapshot
    assert half.cycles_started == 4
    assert half.cycles_completed == 4
    assert half.downstream_accepted == 4
    assert half.rx_restart_operations == 4
    assert half.failed_latched is False
finally:
    if runtime is not None:
        try:
            runtime.stop(timeout=3.0)
        except BaseException:
            pass
    if server is not None and server_thread is not None:
        stop_server_thread(server, server_thread)
    try:
        if owner.snapshot.running:
            try:
                owner.rx_stop(timeout=1.5)
            except BaseException:
                pass
    finally:
        router.close()
        owner.stop(timeout=2.0)

transport = created[0]
assert transport.close_thread_id == transport.owner_thread_id

print("P8_SUSTAINED_KISS_TNC_HOST_INTEGRATION=PASS")
print("KISS_TCP_CLIENTS=2_RECONNECT_PROVED")
print("KISS_DATA_MESSAGES_RECEIVED=5")
print("KISS_DATA_ADMITTED=4")
print("KISS_QUEUE_FULL_DROPS=1")
print("SUSTAINED_TX_CYCLES=4")
print("RX_STARTS=5")
print("RX_STOPS=4")
print("POST_TX_BELL202_DECODER_RESETS=4")
print("POST_TX_FCS_VALID_RX=PASS")
print("CAPTURED_TXDELAY_PROFILES=20,30,40,50")
print("AX25_PATH=VIA_YWDNOD")
print("SINGLE_MODEM_OWNER=PASS")
print("MODEM_TRANSPORT=FAKE_THREAD_BOUND")
print("POSIX_SERIAL_TRANSPORT=NO")
print("UART_OPENED=NO")
print("RF_TRANSMITTED=NO")
