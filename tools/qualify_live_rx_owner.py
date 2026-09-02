#!/usr/bin/env python3
"""0B-P12a receive-only live YWD_RX owner/FIFO lifecycle qualification.

This tool assumes the exact P10/P11-qualified packet firmware is already
running. It opens the modem UART only through the single ModemOwner, reproduces
the frozen receive setup, continuously drains YWD_RX for a bounded interval,
and cleanly stops/drains the FIFO.

There is no packet transmit API in ModemOwner and this tool never constructs or
sends YWD_RF/TX_TONES, RF_ABORT, or RF_EXIT.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402

ACTIVE_RX_FLAGS = 0x0D
IDLE_RX_FLAGS = 0x04
ARMED_IDLE_RF_FLAGS = 0x08


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 0B-P12a live RX-only owner qualification")
    ap.add_argument("--device", default="/dev/ttyAMA0")
    ap.add_argument("--identity", required=True, help="exact P11-qualified packet GET_VERSION identity")
    ap.add_argument("--frequency-hz", type=int, default=144_390_000)
    ap.add_argument("--seconds", type=float, default=3.0)
    args = ap.parse_args()

    if not 1.0 <= args.seconds <= 15.0:
        raise SystemExit("FAIL: --seconds must be 1..15")

    print("=== YWD-1278 0B-P12a LIVE RX OWNER/FIFO ===")
    print(f"Device               : {args.device}")
    print(f"RX frequency         : {args.frequency_hz} Hz")
    print(f"Capture interval     : {args.seconds:.3f} s")
    print("UART ownership       : exactly one ModemOwner thread")
    print("RF receive setup     : SET_FREQ + fixed idle SET_CONFIG")
    print("Packet transmit API  : ABSENT")
    print("RF transmit requested: NO")

    owner = ModemOwner(
        posix_serial_transport_factory(args.device),
        queue_capacity=4,
        submit_timeout=0.20,
        default_transaction_timeout=1.25,
    )

    rx_started = False
    packed_bytes = 0
    read_transactions = 0
    status_checks = 0
    initial_samples = 0
    peak_available = 0
    final_samples = 0
    dropped = 0
    before_keyups = 0
    after_keyups = 0
    before_generated = 0
    after_generated = 0

    owner.start(timeout=2.0)
    try:
        version = owner.get_version(timeout=1.5)
        if version.identity != args.identity:
            raise RuntimeError(
                f"packet identity mismatch: expected={args.identity!r} actual={version.identity!r}"
            )
        print(f"Packet identity       : {version.identity}")

        owner.set_rx_frequency(args.frequency_hz, timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)

        rf = owner.rf_status(timeout=1.5)
        if rf.flags != ARMED_IDLE_RF_FLAGS or rf.remaining_selectors != 0 or rf.mode != 0:
            raise RuntimeError(
                "modem IO did not arm idle: "
                f"flags=0x{rf.flags:02x} remaining={rf.remaining_selectors} mode={rf.mode}"
            )

        diag_before = owner.rf_diagnostics(timeout=1.5)
        before_keyups = diag_before.keyups
        before_generated = diag_before.generated_samples
        if diag_before.tx_active != 0:
            raise RuntimeError("RF diagnostic reports TX active before receive capture")
        if before_keyups != 0 or before_generated != 0:
            raise RuntimeError(
                "fresh packet firmware RF diagnostics are not TX-cold before receive capture: "
                f"keyups={before_keyups} generated_samples={before_generated}"
            )

        owner.rx_start(timeout=1.5)
        rx_started = True
        start_status = owner.rx_status(timeout=1.5)
        status_checks += 1
        if start_status.flags != ACTIVE_RX_FLAGS:
            raise RuntimeError(
                f"RX start flags mismatch: expected=0x{ACTIVE_RX_FLAGS:02x} actual=0x{start_status.flags:02x}"
            )
        if start_status.dropped_bytes != 0:
            raise RuntimeError(f"RX FIFO already reports {start_status.dropped_bytes} dropped bytes")
        initial_samples = start_status.samples
        peak_available = start_status.available_bytes

        started = time.monotonic()
        deadline = started + args.seconds
        next_status = started + 0.50
        while time.monotonic() < deadline:
            chunk = owner.rx_read(200, timeout=1.25)
            read_transactions += 1
            packed_bytes += len(chunk)
            now = time.monotonic()
            if now >= next_status:
                status = owner.rx_status(timeout=1.25)
                status_checks += 1
                peak_available = max(peak_available, status.available_bytes)
                dropped = status.dropped_bytes
                final_samples = status.samples
                if status.flags != ACTIVE_RX_FLAGS:
                    raise RuntimeError(f"RX active flags changed to 0x{status.flags:02x}")
                if dropped != 0:
                    raise RuntimeError(f"RX FIFO dropped {dropped} packed bytes")
                next_status = now + 0.50
            if not chunk:
                time.sleep(0.001)

        owner.rx_stop(timeout=1.5)
        rx_started = False

        while True:
            chunk = owner.rx_read(200, timeout=1.25)
            read_transactions += 1
            if not chunk:
                break
            packed_bytes += len(chunk)

        stop_status = owner.rx_status(timeout=1.5)
        status_checks += 1
        final_samples = stop_status.samples
        dropped = stop_status.dropped_bytes
        if stop_status.flags != IDLE_RX_FLAGS:
            raise RuntimeError(
                f"RX stop flags mismatch: expected=0x{IDLE_RX_FLAGS:02x} actual=0x{stop_status.flags:02x}"
            )
        if stop_status.available_bytes != 0:
            raise RuntimeError(f"RX FIFO not empty after stop/drain: {stop_status.available_bytes}")
        if dropped != 0:
            raise RuntimeError(f"RX FIFO dropped {dropped} packed bytes")
        if final_samples <= initial_samples:
            raise RuntimeError(
                f"firmware sample counter did not advance: start={initial_samples} final={final_samples}"
            )

        rf_after = owner.rf_status(timeout=1.5)
        if rf_after.flags != ARMED_IDLE_RF_FLAGS or rf_after.remaining_selectors != 0 or rf_after.mode != 0:
            raise RuntimeError(
                "RF engine did not remain armed-idle after RX stop: "
                f"flags=0x{rf_after.flags:02x} remaining={rf_after.remaining_selectors} mode={rf_after.mode}"
            )

        diag_after = owner.rf_diagnostics(timeout=1.5)
        after_keyups = diag_after.keyups
        after_generated = diag_after.generated_samples
        if diag_after.tx_active != 0:
            raise RuntimeError("RF diagnostic reports TX active after receive capture")
        if after_keyups != before_keyups:
            raise RuntimeError(f"RF keyup counter changed during RX-only qualification: {before_keyups}->{after_keyups}")
        if after_generated != before_generated:
            raise RuntimeError(
                "RF TX generated-sample counter changed during RX-only qualification: "
                f"{before_generated}->{after_generated}"
            )

        snap = owner.snapshot
        if snap.owner_thread_id is None:
            raise RuntimeError("single modem owner thread ID was not established")

        print(f"Packed bytes drained : {packed_bytes}")
        print(f"Read transactions    : {read_transactions}")
        print(f"Status checks        : {status_checks}")
        print(f"Initial samples      : {initial_samples}")
        print(f"Final samples        : {final_samples}")
        print(f"Peak FIFO available  : {peak_available}")
        print(f"FIFO dropped bytes   : {dropped}")
        print(f"RF keyups            : {before_keyups}->{after_keyups}")
        print(f"RF TX samples        : {before_generated}->{after_generated}")
        print(f"Owner transactions   : {snap.transactions}")

    finally:
        if rx_started:
            try:
                owner.rx_stop(timeout=1.0)
            except BaseException:
                pass
        owner.stop(timeout=2.0)

    print("YWD1278_P12A_LIVE_RX_OWNER=PASS")
    print(f"PACKET_IDENTITY={args.identity}")
    print(f"RX_FREQUENCY_HZ={args.frequency_hz}")
    print("SINGLE_MODEM_OWNER=PASS")
    print("RX_ACTIVE_FLAGS=0x0D")
    print("RX_IDLE_FLAGS=0x04")
    print("FIRMWARE_SAMPLES_ADVANCED=YES")
    print(f"PACKED_BYTES_DRAINED={packed_bytes}")
    print(f"FIFO_DROPPED_BYTES={dropped}")
    print(f"RF_KEYUPS={after_keyups}")
    print("RF_TX_ACTIVE=0")
    print("TX_COMMAND_PATH=ABSENT")
    print("RF_RECEIVE_CONFIGURED=YES")
    print("RF_TRANSMITTED=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
