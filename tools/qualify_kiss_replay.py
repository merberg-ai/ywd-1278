#!/usr/bin/env python3
"""Qualify the RX-only TCP KISS boundary using a saved physical capture.

No modem/UART module is imported.  The saved packed slicer capture is decoded
through the already-qualified P6 decoder, published through the product KISS
backend, received through a real localhost TCP connection, and compared byte
for byte.  One inbound KISS DATA request is then sent and must be counted as
rejected; there is no TX callback or modem reference in this path.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import parse_frame  # noqa: E402
from ywd1278.kiss.framing import DATA, KISSStreamDecoder, encode  # noqa: E402
from ywd1278.kiss.server import PacketEvent, RXOnlyBackend, start_server_thread, stop_server_thread  # noqa: E402
from ywd1278.phy.bell202_rx import StreamingBell202Decoder  # noqa: E402


def decode_capture(path: Path, *, chunk_bytes: int = 120) -> list[PacketEvent]:
    decoder = StreamingBell202Decoder()
    packed = path.read_bytes()
    for offset in range(0, len(packed), chunk_bytes):
        decoder.feed(packed[offset : offset + chunk_bytes])
    decoder.finish()

    events: list[PacketEvent] = []
    for item in decoder.occurrences:
        parsed = parse_frame(item.frame, has_fcs=True)
        events.append(
            PacketEvent(
                frame_no_fcs=item.frame[:-2],
                source=str(parsed["source"]),
                destination=str(parsed["destination"]),
                frame_type=str(parsed["frame_type"]),
            )
        )
    return events


def recv_messages(sock: socket.socket, expected: int, *, timeout: float = 2.0):
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
    ap = argparse.ArgumentParser(description="Qualify YWD-1278 RX-only TCP KISS using saved physical RX")
    ap.add_argument("capture", type=Path)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8001)
    args = ap.parse_args()

    if not args.capture.is_file():
        ap.error(f"capture not found: {args.capture}")
    if not 1 <= args.port <= 65535:
        ap.error("--port must be 1..65535")

    events = decode_capture(args.capture)
    if not events:
        print("YWD1278_KISS_REPLAY=FAIL reason=no-decoded-events")
        return 2

    print("=== YWD-1278 0B-P8 RX-ONLY TCP KISS REPLAY ===")
    print(f"Capture          : {args.capture}")
    print(f"Decoded events   : {len(events)}")
    print(f"KISS listen      : {args.host}:{args.port}")
    print("KISS TX backend  : ABSENT")
    print("Modem UART       : NOT ACCESSED")
    print("RF transmit      : IMPOSSIBLE IN THIS PATH")

    for index, event in enumerate(events, 1):
        print(
            f"EVENT[{index}] {event.source}>{event.destination} "
            f"type={event.frame_type} ax25_no_fcs_bytes={len(event.frame_no_fcs)}"
        )

    backend = RXOnlyBackend(events, history_capacity=max(8, len(events)), subscriber_queue_capacity=16)
    server = None
    thread = None
    try:
        server, thread = start_server_thread(backend, host=args.host, port=args.port)
        host, port = server.server_address[:2]
        with socket.create_connection((host, port), timeout=1.0) as client:
            messages = recv_messages(client, len(events))
            if len(messages) != len(events):
                raise RuntimeError(f"expected {len(events)} KISS messages, received {len(messages)}")

            for index, (message, event) in enumerate(zip(messages, events), 1):
                if message.port != 0 or message.command != DATA:
                    raise RuntimeError(
                        f"KISS[{index}] wrong type: port={message.port} command={message.command}"
                    )
                if message.frame != event.frame_no_fcs:
                    raise RuntimeError(f"KISS[{index}] AX.25 payload mismatch")
                print(f"KISS_RX[{index}]=PASS bytes={len(message.frame)}")

            # Prove that an ordinary KISS client can send DATA but this stage
            # terminates it at the RX-only backend rather than handing it toward RF.
            client.sendall(encode(b"YWD-1278 P8 TX MUST BE REJECTED"))
            deadline = time.monotonic() + 1.0
            while backend.snapshot.tx_rejected < 1 and time.monotonic() < deadline:
                time.sleep(0.01)
            if backend.snapshot.tx_rejected != 1:
                raise RuntimeError("client KISS DATA was not accounted as rejected")
    except BaseException as exc:
        print(f"YWD1278_KISS_REPLAY=FAIL reason={exc}")
        return 2
    finally:
        if server is not None and thread is not None:
            stop_server_thread(server, thread)

    snap = backend.snapshot
    print(f"KISS_TX_REJECTED={snap.tx_rejected}")
    print(f"KISS_SUBSCRIBER_DROPS={snap.subscriber_drops}")
    print(f"YWD1278_KISS_REPLAY=PASS frames={len(events)}")
    print("KISS_TCP_SERVER=PASS")
    print("KISS_STANDARD_DATA_PORT0=PASS")
    print("KISS_CLIENT_TX_PATH=REJECTED")
    print("MODEM_UART_OPENED=NO")
    print("RF_CONFIGURED=NO")
    print("RF_TRANSMITTED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
