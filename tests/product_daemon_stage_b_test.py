#!/usr/bin/env python3
from __future__ import annotations

import math
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from p8_fake_modem import P8ThreadBoundTransport
from ywd1278.ax25 import Address, append_fcs, build_ui_frame
from ywd1278.daemon import run_daemon
from ywd1278.kiss.framing import DATA, KISSStreamDecoder, encode
from ywd1278.modem import protocol
from ywd1278.phy import SAMPLE_RATE, frame_to_selectors
from ywd1278.phy.bell202_rx import MARK_HZ, SPACE_HZ
from ywd1278.service.appliance import (
    PRODUCT_FIRMWARE_IDENTITY,
    PRODUCT_TARGET,
    ProductConfigurationError,
    ProductPacketEngine,
    load_product_packet_engine_config,
)


class StageBTransport(P8ThreadBoundTransport):
    """P8 fake endpoint plus the normal/fixed SET_FREQ setup used by Stage B."""

    def __init__(self) -> None:
        super().__init__()
        self.set_freq_payloads: list[bytes] = []

    def transact(self, request: bytes, *, timeout: float) -> bytes:
        frame = protocol.parse_frame(request)
        if frame.command == protocol.SET_FREQ:
            self._assert_owner()
            self.call_thread_ids.append(threading.get_ident())
            self.requests.append(bytes(request))
            self.set_freq_payloads.append(bytes(frame.payload))
            return protocol.ack_for(protocol.SET_FREQ)
        return super().transact(request, timeout=timeout)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def config_text(
    *,
    port: int,
    tx_enabled: bool,
    frequency_mhz: str = "145.050",
    tx_power: int = 200,
    persist: int = 255,
    kiss_enabled: bool = True,
    target: str = PRODUCT_TARGET,
    kiss_host: str = "127.0.0.1",
    automatic_flash: bool = False,
    beacon_enabled: bool = False,
) -> str:
    return f'''[hardware]
target = "{target}"

[radio]
device = "/dev/ttyAMA0"
frequency_mhz = {frequency_mhz}
tx_power = {tx_power}
tx_enabled = {str(tx_enabled).lower()}

[packet]
baud = 1200
txdelay_ms = 300
persist = {persist}
slottime_ms = 100

[kiss]
enabled = {str(kiss_enabled).lower()}
listen = "{kiss_host}"
port = {port}

[beacon]
enabled = {str(beacon_enabled).lower()}

[firmware]
required_product = "YWD-1278"
allow_automatic_flash = {str(automatic_flash).lower()}
'''


def write_config(directory: str, **kwargs) -> Path:  # type: ignore[no-untyped-def]
    path = Path(directory) / "config.toml"
    path.write_text(config_text(**kwargs), encoding="utf-8")
    return path


def wait_until(predicate, *, timeout: float = 5.0, detail: str = "condition") -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    raise TimeoutError(f"timed out waiting for {detail}")


def body(text: str) -> bytes:
    return build_ui_frame(
        source=Address.parse("KJ6YWD-10"),
        destination=Address.parse("YWDB"),
        path=[Address.parse("YWDNOD")],
        info=text.encode("ascii"),
        include_fcs=False,
    )


def synthesize(selectors: list[int], *, symbol_offset: float = 0.37) -> list[int]:
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


def pack_samples(samples: list[int]) -> bytes:
    out = bytearray((len(samples) + 7) // 8)
    for index, value in enumerate(samples):
        if value:
            out[index >> 3] |= 0x80 >> (index & 7)
    return bytes(out)


def rx_capture(frame_body: bytes) -> bytes:
    selectors = frame_to_selectors(append_fcs(frame_body), pre_flags=45, post_flags=6)
    return pack_samples(synthesize(selectors))


def recv_data(sock: socket.socket, *, timeout: float = 4.0):  # type: ignore[no-untyped-def]
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
        for message in decoder.feed(chunk):
            if message.port == 0 and message.command == DATA:
                return message
    raise TimeoutError("timed out waiting for KISS DATA")


class StageBProductDaemonTests(unittest.TestCase):
    def test_configuration_fails_closed(self) -> None:
        cases = [
            {"target": "", "message": "hardware.target"},
            {"frequency_mhz": "0.0", "message": "not configured"},
            {"tx_enabled": True, "frequency_mhz": "145.060", "message": "145.050"},
            {"tx_enabled": True, "tx_power": 199, "message": "power-200"},
            {"kiss_host": "0.0.0.0", "message": "127.0.0.1"},
            {"automatic_flash": True, "message": "automatic firmware flash"},
            {"beacon_enabled": True, "message": "future 0F"},
        ]
        for index, case in enumerate(cases):
            with self.subTest(index=index, case=case):
                with tempfile.TemporaryDirectory() as td:
                    kwargs = {
                        "port": free_port(),
                        "tx_enabled": False,
                    }
                    message = case.pop("message")
                    kwargs.update(case)
                    path = write_config(td, **kwargs)
                    with self.assertRaisesRegex(ProductConfigurationError, message):
                        load_product_packet_engine_config(path)

    def test_rx_only_mode_rejects_data_and_delivers_rx(self) -> None:
        created: list[StageBTransport] = []

        def factory() -> StageBTransport:
            transport = StageBTransport()
            created.append(transport)
            return transport

        with tempfile.TemporaryDirectory() as td:
            path = write_config(td, port=free_port(), tx_enabled=False, tx_power=64)
            config = load_product_packet_engine_config(path)
            engine = ProductPacketEngine(config, transport_factory=factory, random_byte_source=lambda: 0)
            engine.start()
            try:
                self.assertTrue(engine.snapshot.running)
                self.assertFalse(engine.snapshot.tx_enabled)
                self.assertEqual(engine.snapshot.firmware_identity, PRODUCT_FIRMWARE_IDENTITY)
                self.assertEqual(len(created[0].set_freq_payloads), 1)

                assert engine.kiss_server is not None
                host, port = engine.kiss_server.server_address[:2]
                with socket.create_connection((host, int(port)), timeout=1.0) as client:
                    outgoing = body("STAGE B TX MUST REJECT")
                    client.sendall(encode(outgoing, command=DATA))
                    assert engine.session is not None
                    assert engine.admission is not None
                    wait_until(
                        lambda: engine.session.counters.kiss_data_tx_rejected == 1,
                        detail="RX-only DATA rejection",
                    )
                    self.assertEqual(engine.admission.snapshot.queue_depth, 0)
                    self.assertEqual(created[0].tx_accept_count, 0)
                    engine.check_health()

                    inbound = body("STAGE B RX DELIVERY")
                    created[0].inject_rx_packed(rx_capture(inbound))
                    message = recv_data(client)
                    self.assertEqual(message.frame, inbound)
                    wait_until(
                        lambda: engine.snapshot.decoded_rx_frames >= 1,
                        detail="Stage-B decoded RX accounting",
                    )
                    engine.check_health()
            finally:
                engine.stop()

        self.assertEqual(created[0].tx_accept_count, 0)
        self.assertEqual(created[0].rx_start_count, 1)
        self.assertEqual(created[0].rx_stop_count, 1)
        self.assertEqual(created[0].close_thread_id, created[0].owner_thread_id)
        self.assertTrue(all(tid == created[0].owner_thread_id for tid in created[0].call_thread_ids))

    def test_tx_enabled_mode_traverses_full_frozen_graph_on_fake_transport(self) -> None:
        created: list[StageBTransport] = []

        def factory() -> StageBTransport:
            transport = StageBTransport()
            created.append(transport)
            return transport

        with tempfile.TemporaryDirectory() as td:
            path = write_config(td, port=free_port(), tx_enabled=True, persist=255)
            config = load_product_packet_engine_config(path)
            engine = ProductPacketEngine(config, transport_factory=factory, random_byte_source=lambda: 0)
            engine.start()
            try:
                self.assertTrue(engine.snapshot.running)
                self.assertTrue(engine.snapshot.tx_enabled)
                self.assertEqual(len(created[0].set_freq_payloads), 1)

                assert engine.kiss_server is not None
                host, port = engine.kiss_server.server_address[:2]
                outgoing = body("STAGE B FULL GRAPH")
                with socket.create_connection((host, int(port)), timeout=1.0) as client:
                    client.sendall(encode(outgoing, command=DATA))
                    wait_until(
                        lambda: created[0].tx_accept_count == 1,
                        timeout=6.0,
                        detail="Stage-B full-graph fake TX",
                    )
                wait_until(
                    lambda: engine.snapshot.tx_dispatches == 1,
                    detail="Stage-B dispatch accounting",
                )
                assert engine.admission is not None
                self.assertEqual(engine.admission.snapshot.queue_depth, 0)
                self.assertEqual(created[0].rx_stop_count, 1)
                self.assertEqual(created[0].rx_start_count, 2)
                self.assertEqual(created[0].tx_accept_count, 1)
                engine.check_health()
            finally:
                engine.stop()

        self.assertEqual(created[0].rx_stop_count, 2)
        self.assertEqual(created[0].close_thread_id, created[0].owner_thread_id)
        self.assertTrue(all(tid == created[0].owner_thread_id for tid in created[0].call_thread_ids))

    def test_run_daemon_uses_engine_lifecycle_and_releases_owner(self) -> None:
        created: list[StageBTransport] = []

        def factory() -> StageBTransport:
            transport = StageBTransport()
            created.append(transport)
            return transport

        with tempfile.TemporaryDirectory() as td:
            path = write_config(
                td,
                port=free_port(),
                tx_enabled=False,
                tx_power=64,
                kiss_enabled=False,
            )
            stop_event = threading.Event()
            result: list[int] = []
            error: list[BaseException] = []

            def target() -> None:
                try:
                    result.append(
                        run_daemon(
                            path,
                            stop_event=stop_event,
                            transport_factory=factory,
                            random_byte_source=lambda: 0,
                        )
                    )
                except BaseException as exc:
                    error.append(exc)

            thread = threading.Thread(target=target, name="stage-b-daemon-test")
            thread.start()
            wait_until(
                lambda: bool(created) and created[0].rx_active,
                detail="Stage-B daemon active RX",
            )
            stop_event.set()
            thread.join(timeout=5.0)
            self.assertFalse(thread.is_alive())
            self.assertEqual(error, [])
            self.assertEqual(result, [0])
            self.assertEqual(created[0].tx_accept_count, 0)
            self.assertEqual(created[0].rx_start_count, 1)
            self.assertEqual(created[0].rx_stop_count, 1)
            self.assertEqual(created[0].close_thread_id, created[0].owner_thread_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
