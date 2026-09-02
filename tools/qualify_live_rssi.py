#!/usr/bin/env python3
"""0C-P2 bounded live raw-RSSI telemetry qualification.

This tool assumes the exact staged AX25R4 firmware is already running. It owns
the modem UART through one base ModemOwner, configures the qualified passive
AX.25 receive path, continuously drains the raw RX FIFO, and samples the new
read-only YWD_RX/0x05 ADF7021 RSSI telemetry for a bounded interval.

It deliberately does not classify busy/clear, choose a carrier threshold, or
expose any transmit operation. RF diagnostics are checked before and after the
run to prove that the receive-only observation did not key RF or generate TX
waveform samples.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402

ACTIVE_RX_FLAGS = 0x0D
IDLE_RX_FLAGS = 0x04
ARMED_IDLE_RF_FLAGS = 0x08


def percentile(values: list[int], fraction: float) -> int:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires samples")
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 0C-P2 live raw RSSI receive-only probe")
    ap.add_argument("--device", default="/dev/ttyAMA0")
    ap.add_argument("--identity", required=True)
    ap.add_argument("--frequency-hz", type=int, default=145_050_000)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--poll-interval", type=float, default=0.05)
    args = ap.parse_args()

    if not 5.0 <= args.seconds <= 120.0:
        raise SystemExit("FAIL: --seconds must be 5..120")
    if not 0.02 <= args.poll_interval <= 1.0:
        raise SystemExit("FAIL: --poll-interval must be 0.02..1.0")
    if not 100_000_000 <= args.frequency_hz <= 1_000_000_000:
        raise SystemExit("FAIL: --frequency-hz outside guarded VHF/UHF range")

    print("=== YWD-1278 0C-P2 LIVE RAW RSSI RX-ONLY PROBE ===")
    print(f"Device               : {args.device}")
    print(f"RX frequency         : {args.frequency_hz} Hz")
    print(f"Observation interval : {args.seconds:.3f} s")
    print(f"RSSI poll interval   : {args.poll_interval:.3f} s")
    print("RSSI source          : YWD_RX/0x05 raw ADF7021 register-7 magnitude")
    print("Carrier threshold    : NOT SELECTED")
    print("Busy/clear decision  : NOT PERFORMED")
    print("UART ownership       : exactly one base ModemOwner thread")
    print("Packet transmit API  : ABSENT")
    print("RF transmit requested: NO")

    owner = ModemOwner(
        posix_serial_transport_factory(args.device),
        queue_capacity=4,
        submit_timeout=0.20,
        default_transaction_timeout=1.25,
    )

    rx_started = False
    rssis: list[int] = []
    packed_bytes = 0
    read_transactions = 0
    rssi_transactions = 0
    status_checks = 0
    initial_samples = 0
    final_samples = 0
    peak_available = 0
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
                f"firmware identity mismatch: expected={args.identity!r} actual={version.identity!r}"
            )
        print(f"Firmware identity    : {version.identity}")

        owner.set_rx_frequency(args.frequency_hz, timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)

        rf_before = owner.rf_status(timeout=1.5)
        if rf_before.flags != ARMED_IDLE_RF_FLAGS or rf_before.remaining_selectors != 0 or rf_before.mode != 0:
            raise RuntimeError(
                "modem IO did not arm idle: "
                f"flags=0x{rf_before.flags:02x} remaining={rf_before.remaining_selectors} mode={rf_before.mode}"
            )
        diag_before = owner.rf_diagnostics(timeout=1.5)
        before_keyups = diag_before.keyups
        before_generated = diag_before.generated_samples
        if diag_before.tx_active != 0:
            raise RuntimeError("RF diagnostics report TX active before RSSI observation")

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

        # Prove the new command is reachable immediately after RX START before
        # beginning the timed observation.
        first = owner.rx_rssi(timeout=1.5).raw_magnitude
        rssis.append(first)
        rssi_transactions += 1
        print(f"RSSI_SAMPLE[0001] elapsed=0.000 raw={first}")

        started = time.monotonic()
        deadline = started + args.seconds
        next_poll = started + args.poll_interval
        next_status = started + 0.50

        while True:
            now = time.monotonic()
            if now >= deadline:
                break

            # The raw slicer produces about 2400 packed bytes/s. Drain until a
            # short read so RSSI polling cannot starve the bounded 512-byte FIFO.
            while True:
                chunk = owner.rx_read(200, timeout=1.25)
                read_transactions += 1
                packed_bytes += len(chunk)
                if len(chunk) < 200:
                    break

            now = time.monotonic()
            if now >= next_poll:
                raw = owner.rx_rssi(timeout=1.25).raw_magnitude
                rssis.append(raw)
                rssi_transactions += 1
                elapsed = now - started
                print(f"RSSI_SAMPLE[{len(rssis):04d}] elapsed={elapsed:.3f} raw={raw}")
                while next_poll <= now:
                    next_poll += args.poll_interval

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
                while next_status <= now:
                    next_status += 0.50

            wait = min(next_poll, next_status, deadline) - time.monotonic()
            if wait > 0.001:
                time.sleep(min(wait, 0.005))

        owner.rx_stop(timeout=1.5)
        rx_started = False

        while True:
            chunk = owner.rx_read(200, timeout=1.25)
            read_transactions += 1
            packed_bytes += len(chunk)
            if not chunk:
                break

        stop_status = owner.rx_status(timeout=1.5)
        status_checks += 1
        final_samples = stop_status.samples
        dropped = stop_status.dropped_bytes
        peak_available = max(peak_available, stop_status.available_bytes)
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
        if len(rssis) < 2:
            raise RuntimeError("too few RSSI telemetry samples were collected")

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
            raise RuntimeError("RF diagnostics report TX active after RSSI observation")
        if after_keyups != before_keyups:
            raise RuntimeError(f"RF keyup counter changed during RX-only RSSI probe: {before_keyups}->{after_keyups}")
        if after_generated != before_generated:
            raise RuntimeError(
                "RF TX generated-sample counter changed during RX-only RSSI probe: "
                f"{before_generated}->{after_generated}"
            )

        snap = owner.snapshot
        if snap.owner_thread_id is None:
            raise RuntimeError("single modem owner thread ID was not established")

        rssi_min = min(rssis)
        rssi_max = max(rssis)
        rssi_median = statistics.median(rssis)
        rssi_p05 = percentile(rssis, 0.05)
        rssi_p95 = percentile(rssis, 0.95)
        distinct = len(set(rssis))

        print(f"RSSI samples         : {len(rssis)}")
        print(f"RSSI raw min         : {rssi_min}")
        print(f"RSSI raw p05         : {rssi_p05}")
        print(f"RSSI raw median      : {rssi_median}")
        print(f"RSSI raw p95         : {rssi_p95}")
        print(f"RSSI raw max         : {rssi_max}")
        print(f"RSSI distinct values : {distinct}")
        print(f"Packed bytes drained : {packed_bytes}")
        print(f"Read transactions    : {read_transactions}")
        print(f"RSSI transactions    : {rssi_transactions}")
        print(f"Status checks        : {status_checks}")
        print(f"Firmware samples     : {initial_samples}->{final_samples}")
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

    print("YWD1278_0C_P2_LIVE_RAW_RSSI=PASS")
    print(f"FIRMWARE_IDENTITY={args.identity}")
    print(f"RX_FREQUENCY_HZ={args.frequency_hz}")
    print(f"RSSI_SAMPLE_COUNT={len(rssis)}")
    print(f"RSSI_RAW_MIN={min(rssis)}")
    print(f"RSSI_RAW_MEDIAN={statistics.median(rssis)}")
    print(f"RSSI_RAW_MAX={max(rssis)}")
    print(f"RSSI_RAW_DISTINCT_VALUES={len(set(rssis))}")
    print(f"PACKED_BYTES_DRAINED={packed_bytes}")
    print(f"FIFO_DROPPED_BYTES={dropped}")
    print(f"RF_KEYUPS={before_keyups}->{after_keyups}")
    print(f"RF_TX_GENERATED_SAMPLES={before_generated}->{after_generated}")
    print("SINGLE_MODEM_OWNER=PASS")
    print("RSSI_SOURCE=ADF7021_REGISTER7_RAW_MAGNITUDE")
    print("CARRIER_THRESHOLD_SELECTED=NO")
    print("BUSY_CLEAR_DECISION=NO")
    print("TX_COMMAND_PATH=ABSENT")
    print("RF_TRANSMITTED=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
