#!/usr/bin/env python3
from __future__ import annotations

import math
import pathlib
import socket
import sys
import threading
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.kiss.framing import DATA, KISSStreamDecoder, encode  # noqa: E402
from ywd1278.kiss.server import RXOnlyBackend, start_server_thread, stop_server_thread  # noqa: E402
from ywd1278.modem import protocol  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402
from ywd1278.phy import SAMPLE_RATE, frame_to_selectors  # noqa: E402
from ywd1278.phy.bell202_rx import MARK_HZ, SPACE_HZ  # noqa: E402
from ywd1278.service import RXOnlyPacketRuntime, RXRuntimeError  # noqa: E402

IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 "
    "14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
)

PHYSICAL_SABM = bytes.fromhex(
    "a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 3f 4a 88"
)
PHYSICAL_I_N = bytes.fromhex(
    "a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 20 f0 6e 0d 00 28"
)
PHYSICAL_I_MH = bytes.fromhex(
    "a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 82 f0 6d 68 0d 70 23"
)
FRAMES = (PHYSICAL_SABM, PHYSICAL_I_N, PHYSICAL_I_MH)


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


def synthetic_capture() -> bytes:
    selectors: list[int] = []
    for frame in FRAMES:
        selectors.extend(frame_to_selectors(frame, pre_flags=20, post_flags=6))
    return pack(synthesize(selectors))


class FakeRX3Transport:
    def __init__(self, packed: bytes, *, initial_dropped: int = 0) -> None:
        self._thread_id = threading.get_ident()
        self._packed = packed
        self._offset = 0
        self._active = False
        self._initial_dropped = initial_dropped
        self.closed = False
        self.commands: list[tuple[int, bytes]] = []

    def _check_thread(self) -> None:
        if threading.get_ident() != self._thread_id:
            raise RuntimeError("fake transport escaped owner thread")

    def transact(self, request: bytes, *, timeout: float) -> bytes:
        self._check_thread()
        if timeout <= 0.0:
            raise ValueError("timeout must be positive")
        frame = protocol.parse_frame(request)
        self.commands.append((frame.command, frame.payload))

        if frame.command == protocol.GET_VERSION:
            return protocol.build_frame(
                protocol.GET_VERSION,
                bytes((1,)) + IDENTITY.encode("ascii") + b"\0",
            )

        if frame.command != protocol.YWD_RX or not frame.payload:
            raise RuntimeError("unexpected fake modem command")

        subcommand = frame.payload[0]
        if subcommand == protocol.RX_START:
            self._active = True
            return protocol.ack_for(protocol.YWD_RX)
        if subcommand == protocol.RX_STOP:
            self._active = False
            return protocol.ack_for(protocol.YWD_RX)
        if subcommand == protocol.RX_READ:
            maximum = frame.payload[1]
            end = min(len(self._packed), self._offset + maximum)
            chunk = self._packed[self._offset:end]
            self._offset = end
            return protocol.build_frame(
                protocol.YWD_RX,
                bytes((protocol.RX_READ, len(chunk))) + chunk,
            )
        if subcommand == protocol.RX_STATUS:
            available = len(self._packed) - self._offset
            samples = self._offset * 8
            dropped = self._initial_dropped
            flags = 0x0D if self._active else 0x04
            payload = bytes(
                (
                    protocol.RX_STATUS,
                    protocol.RX_PROTOCOL_REVISION,
                    flags,
                    available & 0xFF,
                    (available >> 8) & 0xFF,
                    samples & 0xFF,
                    (samples >> 8) & 0xFF,
                    (samples >> 16) & 0xFF,
                    (samples >> 24) & 0xFF,
                    dropped & 0xFF,
                    (dropped >> 8) & 0xFF,
                )
            )
            return protocol.build_frame(protocol.YWD_RX, payload)
        raise RuntimeError(f"unexpected fake RX subcommand 0x{subcommand:02x}")

    def close(self) -> None:
        self._check_thread()
        self.closed = True


def recv_messages(sock: socket.socket, count: int, timeout: float = 5.0):
    decoder = KISSStreamDecoder()
    messages = []
    deadline = time.monotonic() + timeout
    sock.settimeout(0.05)
    while len(messages) < count and time.monotonic() < deadline:
        try:
            data = sock.recv(4096)
        except socket.timeout:
            continue
        if not data:
            break
        messages.extend(decoder.feed(data))
    return messages


class RXProductRuntimeTests(unittest.TestCase):
    def test_fake_rx3_to_real_tcp_kiss_pipeline(self) -> None:
        packed = synthetic_capture()
        holder: dict[str, FakeRX3Transport] = {}

        def factory() -> FakeRX3Transport:
            transport = FakeRX3Transport(packed)
            holder["transport"] = transport
            return transport

        owner = ModemOwner(factory, queue_capacity=4)
        backend = RXOnlyBackend(history_capacity=16, subscriber_queue_capacity=8)
        runtime = RXOnlyPacketRuntime(
            owner,
            backend,
            expected_identity=IDENTITY,
            read_maximum=120,
            idle_sleep_seconds=0.0005,
            status_interval_seconds=0.02,
        )
        server, server_thread = start_server_thread(backend, host="127.0.0.1", port=0)
        host, port = server.server_address[:2]

        try:
            runtime.start()
            with socket.create_connection((host, port), timeout=1.0) as client:
                messages = recv_messages(client, len(FRAMES))
                self.assertEqual(len(messages), len(FRAMES))
                self.assertEqual(
                    [message.frame for message in messages],
                    [frame[:-2] for frame in FRAMES],
                )
                self.assertTrue(all(message.port == 0 for message in messages))
                self.assertTrue(all(message.command == DATA for message in messages))

                client.sendall(encode(b"P9 TX MUST REMAIN DISCONNECTED"))
                deadline = time.monotonic() + 1.0
                while backend.snapshot.tx_rejected != 1 and time.monotonic() < deadline:
                    time.sleep(0.005)
                self.assertEqual(backend.snapshot.tx_rejected, 1)

            runtime.stop()
        finally:
            try:
                runtime.stop()
            except (RXRuntimeError, RuntimeError):
                pass
            stop_server_thread(server, server_thread)

        snap = runtime.snapshot
        self.assertEqual(snap.identity, IDENTITY)
        self.assertEqual(snap.decoded_frames, 3)
        self.assertEqual(snap.packed_bytes, len(packed))
        self.assertEqual(snap.fifo_dropped_bytes, 0)
        self.assertEqual(snap.failure, "")
        self.assertEqual(backend.snapshot.subscriber_drops, 0)
        self.assertTrue(holder["transport"].closed)

    def test_fifo_drop_fails_closed_during_start_gate(self) -> None:
        packed = synthetic_capture()
        owner = ModemOwner(lambda: FakeRX3Transport(packed, initial_dropped=1))
        backend = RXOnlyBackend()
        runtime = RXOnlyPacketRuntime(owner, backend, expected_identity=IDENTITY)

        with self.assertRaises(RXRuntimeError):
            runtime.start()
        self.assertFalse(owner.snapshot.running)
        self.assertEqual(backend.snapshot.stored_events, 0)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RXProductRuntimeTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    print("YWD1278_RX_PRODUCT_RUNTIME=PASS")
    print("SINGLE_MODEM_OWNER=PASS")
    print("YWD_RX_FIFO_TO_BELL202=PASS")
    print("AX25_EVENT_TO_TCP_KISS=PASS")
    print("PHYSICAL_FRAME_VECTORS=3")
    print("KISS_CLIENT_TX_PATH=REJECTED")
    print("FIFO_DROP_FAIL_CLOSED=PASS")
    print("RAW_UART_CLIENT_ACCESS=ABSENT")
    print("RF_TRANSMITTED=NO")
