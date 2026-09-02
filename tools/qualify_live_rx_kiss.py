#!/usr/bin/env python3
"""0B-P12b live RF -> YWD_RX -> Bell-202 -> AX.25 -> TCP KISS proof.

This qualification assumes 0B-P12a has already left the exact packet firmware
installed. It never flashes, resets, or invokes a packet-transmit operation.
The real modem UART is owned only by ModemOwner and inbound TCP KISS DATA is
explicitly rejected by the RX-only backend.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import parse_frame  # noqa: E402
from ywd1278.kiss.framing import DATA, KISSStreamDecoder, encode  # noqa: E402
from ywd1278.kiss.server import RXOnlyBackend, start_server_thread, stop_server_thread  # noqa: E402
from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402
from ywd1278.service import RXOnlyPacketRuntime  # noqa: E402


def load_target(path: Path, target_id: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    matches = [item for item in data.get("targets", []) if item.get("id") == target_id]
    if len(matches) != 1:
        raise SystemExit(f"FAIL: target not found exactly once: {target_id}")
    target = matches[0]
    if target.get("status") != "0b-p12a-live-rx-qualified":
        raise SystemExit(f"FAIL: target is not at the qualified P12a boundary: {target.get('status')}")
    if target.get("flash_enabled") is not False:
        raise SystemExit("FAIL: normal product flashing must remain disabled")
    if target.get("option_bytes_permitted") is not False:
        raise SystemExit("FAIL: target permits option-byte writes")
    activation = target.get("packet_live_rx_activation") or {}
    if activation.get("enabled") is not False:
        raise SystemExit("FAIL: P12a activation write gate must be closed before P12b")
    qualification = target.get("packet_live_rx_qualification") or {}
    if qualification.get("phase") != "0B-P12a" or qualification.get("status") != "qualified":
        raise SystemExit("FAIL: target lacks physical P12a live-RX qualification")
    if qualification.get("fifo_dropped_bytes") != 0:
        raise SystemExit("FAIL: P12a evidence contains FIFO loss")
    if qualification.get("packet_firmware_left_installed") is not True:
        raise SystemExit("FAIL: P12a did not record the packet firmware as installed")
    if qualification.get("rf_transmitted") is not False:
        raise SystemExit("FAIL: P12a evidence contains RF transmission")
    return target


def uart_is_free(device: str) -> bool:
    if shutil.which("fuser") is None:
        return True
    result = subprocess.run(
        ["fuser", device],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode != 0


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 0B-P12b live RF to TCP KISS qualification")
    ap.add_argument("--targets", default=str(ROOT / "firmware" / "targets.json"))
    ap.add_argument("--target", required=True)
    ap.add_argument("--device", default="/dev/ttyAMA0")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--seconds", type=float, default=180.0)
    ap.add_argument("--min-frames", type=int, default=1)
    ap.add_argument("--expect-source", default="")
    args = ap.parse_args()

    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("FAIL: P12b qualification KISS listener must be loopback-only")
    if not 1 <= args.port <= 65535:
        raise SystemExit("FAIL: KISS port must be 1..65535")
    if not 5.0 <= args.seconds <= 600.0:
        raise SystemExit("FAIL: --seconds must be 5..600")
    if not 1 <= args.min_frames <= 20:
        raise SystemExit("FAIL: --min-frames must be 1..20")

    target = load_target(Path(args.targets), args.target)
    packet = target["packet_firmware_candidate"]
    expected_identity = packet["expected_identity"]
    frequency_hz = int(target["packet_live_rx_qualification"]["receive_frequency_hz"])

    if not uart_is_free(args.device):
        raise SystemExit(f"FAIL: modem UART already has an owner: {args.device}")

    print("=== YWD-1278 0B-P12b LIVE RF -> TCP KISS ===")
    print(f"Target               : {args.target}")
    print(f"Device               : {args.device}")
    print(f"Packet identity      : {expected_identity}")
    print(f"RX frequency         : {frequency_hz} Hz")
    print(f"KISS listen          : {args.host}:{args.port}")
    print(f"Wait interval        : {args.seconds:.1f} s")
    print(f"Required live frames : {args.min_frames}")
    print(f"Expected source      : {args.expect_source or '<any valid AX.25 source>'}")
    print("Firmware flash       : NO")
    print("GPIO/reset           : NO")
    print("Packet TX API        : ABSENT")
    print("Inbound KISS DATA    : REJECTED")

    backend = RXOnlyBackend(history_capacity=32, subscriber_queue_capacity=16)
    server = server_thread = None
    client = None
    runtime = None
    owner = ModemOwner(
        posix_serial_transport_factory(args.device),
        queue_capacity=8,
        submit_timeout=0.20,
        default_transaction_timeout=1.25,
    )
    messages = []
    diag_before = None
    diag_after = None

    try:
        server, server_thread = start_server_thread(backend, host=args.host, port=args.port)
        client = socket.create_connection((args.host, args.port), timeout=2.0)
        client.settimeout(0.25)

        # Exercise the safety boundary before any live packet arrives. The
        # RX-only backend counts this DATA request but cannot forward it to a
        # modem or TX broker because neither dependency exists here.
        client.sendall(encode(b"P12B CLIENT TX MUST REMAIN DISCONNECTED"))
        reject_deadline = time.monotonic() + 1.0
        while backend.snapshot.tx_rejected != 1 and time.monotonic() < reject_deadline:
            time.sleep(0.01)
        if backend.snapshot.tx_rejected != 1:
            raise RuntimeError("RX-only KISS backend did not reject inbound DATA exactly once")

        runtime = RXOnlyPacketRuntime(
            owner,
            backend,
            expected_identity=expected_identity,
            frequency_hz=frequency_hz,
            read_maximum=200,
            idle_sleep_seconds=0.001,
            status_interval_seconds=0.50,
        )
        runtime.start(timeout=2.0)

        diag_before = owner.rf_diagnostics(timeout=1.5)
        if diag_before.tx_active != 0:
            raise RuntimeError("RF diagnostics report TX active at P12b start")

        decoder = KISSStreamDecoder()
        deadline = time.monotonic() + args.seconds
        while len(messages) < args.min_frames and time.monotonic() < deadline:
            runtime.check_health()
            try:
                data = client.recv(4096)
            except socket.timeout:
                continue
            if not data:
                raise RuntimeError("TCP KISS client disconnected before qualification completed")
            for message in decoder.feed(data):
                if message.command != DATA or message.port != 0:
                    continue
                parsed = parse_frame(message.frame, has_fcs=False)
                source = str(parsed["source"])
                destination = str(parsed["destination"])
                frame_type = str(parsed["frame_type"])
                if args.expect_source and source.upper() != args.expect_source.upper():
                    print(
                        f"LIVE_KISS_IGNORED source={source} destination={destination} "
                        f"type={frame_type} bytes={len(message.frame)}"
                    )
                    continue
                messages.append((message, source, destination, frame_type))
                print(
                    f"LIVE_KISS[{len(messages)}] source={source} destination={destination} "
                    f"type={frame_type} bytes={len(message.frame)}"
                )
                print(f"LIVE_KISS_HEX[{len(messages)}]={message.frame.hex()}")
                if len(messages) >= args.min_frames:
                    break

        if len(messages) < args.min_frames:
            raise RuntimeError(
                f"timed out waiting for live qualifying KISS frames: got={len(messages)} "
                f"required={args.min_frames}"
            )

        diag_after = owner.rf_diagnostics(timeout=1.5)
        if diag_after.tx_active != 0:
            raise RuntimeError("RF diagnostics report TX active at P12b end")
        if diag_after.keyups != diag_before.keyups:
            raise RuntimeError(
                f"RF keyup counter changed during P12b: {diag_before.keyups}->{diag_after.keyups}"
            )
        if diag_after.generated_samples != diag_before.generated_samples:
            raise RuntimeError(
                "RF TX generated-sample counter changed during P12b: "
                f"{diag_before.generated_samples}->{diag_after.generated_samples}"
            )

    finally:
        runtime_error = None
        if runtime is not None:
            try:
                runtime.stop(timeout=3.0)
            except BaseException as exc:  # preserve cleanup while still surfacing it
                runtime_error = exc
        if client is not None:
            try:
                client.close()
            except OSError:
                pass
        if server is not None and server_thread is not None:
            stop_server_thread(server, server_thread)
        if runtime_error is not None:
            raise runtime_error

    snap = runtime.snapshot
    backend_snap = backend.snapshot
    owner_snap = owner.snapshot

    if snap.fifo_dropped_bytes != 0:
        raise RuntimeError(f"live runtime reported FIFO loss: {snap.fifo_dropped_bytes}")
    if backend_snap.subscriber_drops != 0:
        raise RuntimeError(f"KISS subscriber dropped events: {backend_snap.subscriber_drops}")
    if backend_snap.tx_rejected != 1:
        raise RuntimeError(f"unexpected inbound KISS DATA reject count: {backend_snap.tx_rejected}")
    if owner_snap.running:
        raise RuntimeError("modem owner still running after P12b shutdown")
    if not uart_is_free(args.device):
        raise RuntimeError("modem UART still owned after P12b shutdown")

    print(f"DECODED_FRAMES={snap.decoded_frames}")
    print(f"PACKED_BYTES={snap.packed_bytes}")
    print(f"YWD_RX_READ_TRANSACTIONS={snap.read_transactions}")
    print(f"YWD_RX_STATUS_CHECKS={snap.status_checks}")
    print(f"FIRMWARE_SAMPLES={snap.firmware_samples}")
    print(f"FIFO_DROPPED_BYTES={snap.fifo_dropped_bytes}")
    print(f"MODEM_OWNER_TRANSACTIONS={owner_snap.transactions}")
    print(f"KISS_TX_REJECTED={backend_snap.tx_rejected}")
    print(f"KISS_SUBSCRIBER_DROPS={backend_snap.subscriber_drops}")
    print(f"RF_KEYUPS={diag_before.keyups}->{diag_after.keyups}")
    print(f"RF_TX_GENERATED_SAMPLES={diag_before.generated_samples}->{diag_after.generated_samples}")
    print(f"LIVE_KISS_FRAMES={len(messages)}")
    print("YWD1278_0B_P12B_LIVE_RF_KISS=PASS")
    print("P12A_PACKET_FIRMWARE_IDENTITY_GATE=PASS")
    print("SINGLE_MODEM_OWNER=PASS")
    print("LIVE_YWD_RX_FIFO=PASS")
    print("LIVE_BELL202_DECODE=PASS")
    print("LIVE_AX25_EVENT=PASS")
    print("LIVE_TCP_KISS_PORT0=PASS")
    print("KISS_CLIENT_TX_PATH=REJECTED")
    print("MODEM_UART_RELEASED=YES")
    print("FLASH_WRITTEN=NO")
    print("GPIO_ACCESSED=NO")
    print("TX_COMMAND_PATH=ABSENT")
    print("RF_TRANSMITTED=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
