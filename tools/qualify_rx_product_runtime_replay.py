#!/usr/bin/env python3
"""Qualify the assembled RX-only product runtime with a saved physical capture.

The capture impersonates a revision-3 YWD_RX FIFO through an injected fake
transport.  The real ModemOwner, RXOnlyPacketRuntime, Bell-202 decoder, event
backend and localhost TCP KISS server are used.  No serial device is opened and
no RF/TX API is present in this path.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.kiss.framing import DATA, KISSStreamDecoder, encode  # noqa: E402
from ywd1278.kiss.server import RXOnlyBackend, start_server_thread, stop_server_thread  # noqa: E402
from ywd1278.modem import protocol  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402
from ywd1278.service import RXOnlyPacketRuntime  # noqa: E402

IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R3-v0.1.0-alpha0 "
    "14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
)

PHYSICAL_FRAMES = (
    bytes.fromhex("a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 3f 4a 88"),
    bytes.fromhex("a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 20 f0 6e 0d 00 28"),
    bytes.fromhex("a4 88 8e 40 40 40 e0 96 94 6c b2 ae 88 63 82 f0 6d 68 0d 70 23"),
)


class CaptureRX3Transport:
    """Thread-bound fake revision-3 modem backed by one packed slicer capture."""

    def __init__(self, packed: bytes) -> None:
        self._thread_id = threading.get_ident()
        self._packed = packed
        self._offset = 0
        self._active = False
        self.closed = False
        self.commands = 0

    def _check_thread(self) -> None:
        if threading.get_ident() != self._thread_id:
            raise RuntimeError("capture transport escaped the modem-owner thread")

    def transact(self, request: bytes, *, timeout: float) -> bytes:
        self._check_thread()
        if timeout <= 0.0:
            raise ValueError("timeout must be positive")
        frame = protocol.parse_frame(request)
        self.commands += 1

        if frame.command == protocol.GET_VERSION:
            return protocol.build_frame(
                protocol.GET_VERSION,
                bytes((1,)) + IDENTITY.encode("ascii") + b"\0",
            )
        if frame.command != protocol.YWD_RX or not frame.payload:
            raise RuntimeError("qualification transport received a non-RX command")

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
                    0,
                    0,
                )
            )
            return protocol.build_frame(protocol.YWD_RX, payload)
        raise RuntimeError(f"unexpected YWD_RX subcommand 0x{subcommand:02x}")

    def close(self) -> None:
        self._check_thread()
        self.closed = True


def recv_messages(sock: socket.socket, expected: int, *, timeout: float = 15.0):
    decoder = KISSStreamDecoder()
    messages = []
    deadline = time.monotonic() + timeout
    sock.settimeout(0.05)
    while len(messages) < expected and time.monotonic() < deadline:
        try:
            data = sock.recv(4096)
        except socket.timeout:
            continue
        if not data:
            break
        messages.extend(decoder.feed(data))
    return messages


def main() -> int:
    ap = argparse.ArgumentParser(description="Qualify assembled YWD-1278 RX runtime using saved physical RX")
    ap.add_argument("capture", type=Path)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8001)
    args = ap.parse_args()

    if not args.capture.is_file():
        ap.error(f"capture not found: {args.capture}")
    if not 1 <= args.port <= 65535:
        ap.error("--port must be 1..65535")

    packed = args.capture.read_bytes()
    holder: dict[str, CaptureRX3Transport] = {}

    def factory() -> CaptureRX3Transport:
        transport = CaptureRX3Transport(packed)
        holder["transport"] = transport
        return transport

    owner = ModemOwner(factory, queue_capacity=8)
    backend = RXOnlyBackend(history_capacity=16, subscriber_queue_capacity=16)
    runtime = RXOnlyPacketRuntime(
        owner,
        backend,
        expected_identity=IDENTITY,
        read_maximum=200,
        idle_sleep_seconds=0.0005,
        status_interval_seconds=0.25,
    )

    print("=== YWD-1278 0B-P9 RX-ONLY PRODUCT RUNTIME REPLAY ===")
    print(f"Capture             : {args.capture}")
    print(f"Packed bytes        : {len(packed)}")
    print(f"KISS listen         : {args.host}:{args.port}")
    print(f"Required identity   : {IDENTITY}")
    print("Transport           : injected capture-backed YWD_RX revision-3 fake")
    print("Real modem UART     : NOT OPENED")
    print("TX API              : ABSENT")
    print("RF transmit         : IMPOSSIBLE IN THIS PATH")

    server = None
    server_thread = None
    client = None
    try:
        server, server_thread = start_server_thread(backend, host=args.host, port=args.port)
        host, port = server.server_address[:2]
        runtime.start()
        client = socket.create_connection((host, port), timeout=1.0)
        messages = recv_messages(client, len(PHYSICAL_FRAMES))
        if len(messages) != len(PHYSICAL_FRAMES):
            raise RuntimeError(
                f"expected {len(PHYSICAL_FRAMES)} KISS frames, received {len(messages)}"
            )

        for index, (message, expected) in enumerate(zip(messages, PHYSICAL_FRAMES), 1):
            if message.port != 0 or message.command != DATA:
                raise RuntimeError(
                    f"KISS[{index}] wrong type port={message.port} command={message.command}"
                )
            if message.frame != expected[:-2]:
                raise RuntimeError(f"KISS[{index}] does not match frozen physical frame")
            print(f"KISS_RX[{index}]=PASS bytes={len(message.frame)}")

        client.sendall(encode(b"P9 TX MUST REMAIN DISCONNECTED"))
        deadline = time.monotonic() + 1.0
        while backend.snapshot.tx_rejected != 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        if backend.snapshot.tx_rejected != 1:
            raise RuntimeError("inbound KISS DATA was not rejected exactly once")

        runtime.stop(timeout=5.0)
        runtime.check_health()
    except BaseException as exc:
        print(f"YWD1278_RX_PRODUCT_REPLAY=FAIL reason={exc}")
        try:
            runtime.stop(timeout=3.0)
        except BaseException:
            pass
        return 2
    finally:
        if client is not None:
            try:
                client.close()
            except OSError:
                pass
        if server is not None and server_thread is not None:
            stop_server_thread(server, server_thread)

    snap = runtime.snapshot
    owner_snap = owner.snapshot
    backend_snap = backend.snapshot
    transport = holder["transport"]

    if snap.decoded_frames != 3:
        print(f"YWD1278_RX_PRODUCT_REPLAY=FAIL reason=decoded-frames-{snap.decoded_frames}")
        return 2
    if snap.packed_bytes != len(packed):
        print(
            "YWD1278_RX_PRODUCT_REPLAY=FAIL "
            f"reason=packed-byte-mismatch-{snap.packed_bytes}-vs-{len(packed)}"
        )
        return 2
    if snap.fifo_dropped_bytes != 0 or backend_snap.subscriber_drops != 0:
        print("YWD1278_RX_PRODUCT_REPLAY=FAIL reason=drop-counter-nonzero")
        return 2
    if not transport.closed or owner_snap.running:
        print("YWD1278_RX_PRODUCT_REPLAY=FAIL reason=owner-transport-not-released")
        return 2

    print(f"PACKED_BYTES_CONSUMED={snap.packed_bytes}")
    print(f"YWD_RX_READ_TRANSACTIONS={snap.read_transactions}")
    print(f"YWD_RX_STATUS_CHECKS={snap.status_checks}")
    print(f"DECODED_FRAMES={snap.decoded_frames}")
    print(f"MODEM_OWNER_TRANSACTIONS={owner_snap.transactions}")
    print(f"KISS_TX_REJECTED={backend_snap.tx_rejected}")
    print(f"KISS_SUBSCRIBER_DROPS={backend_snap.subscriber_drops}")
    print("YWD1278_RX_PRODUCT_REPLAY=PASS frames=3")
    print("SINGLE_MODEM_OWNER=PASS")
    print("YWD_RX_FIFO_TO_BELL202=PASS")
    print("AX25_EVENT_TO_TCP_KISS=PASS")
    print("PACKET_FIRMWARE_IDENTITY_GATE=PASS")
    print("FIFO_DROPPED_BYTES=0")
    print("MODEM_UART_OPENED=NO")
    print("RF_CONFIGURED=NO")
    print("RF_TRANSMITTED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
