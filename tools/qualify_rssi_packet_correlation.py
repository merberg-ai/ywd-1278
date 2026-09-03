#!/usr/bin/env python3
"""0C-P2 receive-only packet-correlated RSSI characterization.

The exact AX25R4 firmware must already be installed. This tool uses one base
ModemOwner to drain live slicer data, decode FCS-valid AX.25 with the already
qualified streaming Bell-202 receiver, and poll the read-only ADF7021 RSSI
telemetry. It then asks one narrow physical question: are RSSI values measured
inside real decoded packet intervals materially lower than the independent
outside-frame RSSI population?

Only after that direct polarity proof does the tool describe a well-separated
guard gap above the packet signal reference. No carrier threshold or hysteresis
is selected here. No TX-capable owner, broker, KISS server, GPIO, or firmware
writer is imported or reachable.
"""

from __future__ import annotations

import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402
from ywd1278.phy.bell202_rx import SAMPLE_RATE, StreamingBell202Decoder  # noqa: E402
from ywd1278.tx.rssi_analysis import (  # noqa: E402
    correlate_rssi_window,
    guard_gap_above_signal,
    rssi_values_outside_windows,
)

DEVICE = "/dev/ttyAMA0"
FREQUENCY_HZ = 145_050_000
IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 "
    "14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
)
MAX_SECONDS = 120.0
MIN_SECONDS = 15.0
TARGET_VALID_FRAMES = 2
RSSI_POLL_SECONDS = 0.05
STATUS_SECONDS = 0.50
READ_BYTES = 100
FRAME_CORRELATION_PADDING_SAMPLES = 0
OUTSIDE_FRAME_GUARD_SAMPLES = int(round(0.20 * SAMPLE_RATE))
MIN_OUTSIDE_SAMPLES = 20
MIN_POLARITY_MARGIN = 12
MIN_SEPARATING_GAP = 12

ACTIVE_RX_FLAGS = 0x0D
IDLE_RX_FLAGS = 0x04
ARMED_IDLE_RF_FLAGS = 0x08


def main() -> int:
    print("=== YWD-1278 0C-P2 PACKET-CORRELATED RSSI CHARACTERIZATION ===")
    print(f"Device                    : {DEVICE}")
    print(f"RX frequency              : {FREQUENCY_HZ} Hz")
    print(f"Maximum observation       : {MAX_SECONDS:.1f} s")
    print(f"Minimum observation       : {MIN_SECONDS:.1f} s")
    print(f"Target valid AX.25 frames : {TARGET_VALID_FRAMES}")
    print(f"RSSI poll interval        : {RSSI_POLL_SECONDS:.3f} s")
    print("RSSI source               : ADF7021 register-7 raw magnitude")
    print("Expected polarity         : NOT ASSUMED; frame/outside-frame data must prove it")
    print(f"Required polarity margin  : {MIN_POLARITY_MARGIN} raw counts")
    print("Carrier threshold         : NOT SELECTED")
    print("Hysteresis                : NOT SELECTED")
    print("KISS/product TX           : DISCONNECTED")
    print("Packet transmit API       : ABSENT")

    owner = ModemOwner(
        posix_serial_transport_factory(DEVICE),
        queue_capacity=4,
        submit_timeout=0.20,
        default_transaction_timeout=1.25,
    )
    decoder = StreamingBell202Decoder()
    rssi_samples: list[tuple[int, int]] = []
    frames = []
    packed_bytes = 0
    read_transactions = 0
    rssi_transactions = 0
    status_checks = 0
    peak_available = 0
    dropped = 0
    initial_samples = 0
    final_samples = 0
    rx_started = False
    before_keyups = 0
    after_keyups = 0
    before_generated = 0
    after_generated = 0

    owner.start(timeout=2.0)
    try:
        version = owner.get_version(timeout=1.5)
        if version.identity != IDENTITY:
            raise RuntimeError(
                f"firmware identity mismatch: expected={IDENTITY!r} actual={version.identity!r}"
            )
        print(f"Firmware identity         : {version.identity}")

        owner.set_rx_frequency(FREQUENCY_HZ, timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)
        rf_before = owner.rf_status(timeout=1.5)
        if rf_before.flags != ARMED_IDLE_RF_FLAGS or rf_before.remaining_selectors != 0 or rf_before.mode != 0:
            raise RuntimeError(
                "RF engine did not arm idle: "
                f"flags=0x{rf_before.flags:02x} remaining={rf_before.remaining_selectors} mode={rf_before.mode}"
            )
        diag_before = owner.rf_diagnostics(timeout=1.5)
        before_keyups = diag_before.keyups
        before_generated = diag_before.generated_samples
        if diag_before.tx_active != 0:
            raise RuntimeError("RF diagnostics report TX active before characterization")

        owner.rx_start(timeout=1.5)
        rx_started = True
        start_status = owner.rx_status(timeout=1.5)
        status_checks += 1
        if start_status.flags != ACTIVE_RX_FLAGS:
            raise RuntimeError(f"RX start flags mismatch: 0x{start_status.flags:02x}")
        if start_status.dropped_bytes != 0:
            raise RuntimeError("RX FIFO already reports dropped bytes")
        initial_samples = start_status.samples
        peak_available = start_status.available_bytes

        first = owner.rx_rssi(timeout=1.5).raw_magnitude
        rssi_samples.append((decoder.stats.samples, first))
        rssi_transactions += 1
        print(f"RSSI_SAMPLE[0001] capture_sample={decoder.stats.samples} raw={first}")

        started = time.monotonic()
        deadline = started + MAX_SECONDS
        next_poll = started + RSSI_POLL_SECONDS
        next_status = started + STATUS_SECONDS

        while True:
            now = time.monotonic()
            elapsed = now - started
            if now >= deadline:
                break
            if elapsed >= MIN_SECONDS and len(frames) >= TARGET_VALID_FRAMES:
                break

            while True:
                chunk = owner.rx_read(READ_BYTES, timeout=1.25)
                read_transactions += 1
                packed_bytes += len(chunk)
                if chunk:
                    fresh = decoder.feed(chunk)
                    for item in fresh:
                        frames.append(item)
                        print(
                            f"VALID_AX25[{len(frames)}] "
                            f"sample_start={item.sample_start} sample_end={item.sample_end} "
                            f"bytes={len(item.frame)} hex={item.frame.hex()}"
                        )
                if len(chunk) < READ_BYTES:
                    break

            now = time.monotonic()
            if now >= next_poll:
                raw = owner.rx_rssi(timeout=1.25).raw_magnitude
                position = decoder.stats.samples
                rssi_samples.append((position, raw))
                rssi_transactions += 1
                print(f"RSSI_SAMPLE[{len(rssi_samples):04d}] capture_sample={position} raw={raw}")
                while next_poll <= now:
                    next_poll += RSSI_POLL_SECONDS

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
                    next_status += STATUS_SECONDS

            wait = min(next_poll, next_status, deadline) - time.monotonic()
            if wait > 0.001:
                time.sleep(min(wait, 0.005))

        owner.rx_stop(timeout=1.5)
        rx_started = False

        while True:
            chunk = owner.rx_read(READ_BYTES, timeout=1.25)
            read_transactions += 1
            packed_bytes += len(chunk)
            if chunk:
                fresh = decoder.feed(chunk)
                for item in fresh:
                    frames.append(item)
                    print(
                        f"VALID_AX25[{len(frames)}] "
                        f"sample_start={item.sample_start} sample_end={item.sample_end} "
                        f"bytes={len(item.frame)} hex={item.frame.hex()}"
                    )
            if not chunk:
                break

        stop_status = owner.rx_status(timeout=1.5)
        status_checks += 1
        final_samples = stop_status.samples
        dropped = stop_status.dropped_bytes
        peak_available = max(peak_available, stop_status.available_bytes)
        if stop_status.flags != IDLE_RX_FLAGS:
            raise RuntimeError(f"RX stop flags mismatch: 0x{stop_status.flags:02x}")
        if stop_status.available_bytes != 0:
            raise RuntimeError(f"RX FIFO not empty after stop/drain: {stop_status.available_bytes}")
        if dropped != 0:
            raise RuntimeError(f"RX FIFO dropped {dropped} packed bytes")
        if final_samples <= initial_samples:
            raise RuntimeError("firmware sample counter did not advance")

        rf_after = owner.rf_status(timeout=1.5)
        if rf_after.flags != ARMED_IDLE_RF_FLAGS or rf_after.remaining_selectors != 0 or rf_after.mode != 0:
            raise RuntimeError("RF engine did not remain armed-idle")
        diag_after = owner.rf_diagnostics(timeout=1.5)
        after_keyups = diag_after.keyups
        after_generated = diag_after.generated_samples
        if diag_after.tx_active != 0:
            raise RuntimeError("RF diagnostics report TX active after characterization")
        if after_keyups != before_keyups:
            raise RuntimeError(f"RF keyups changed: {before_keyups}->{after_keyups}")
        if after_generated != before_generated:
            raise RuntimeError(f"RF TX generated samples changed: {before_generated}->{after_generated}")

        if not frames:
            print("CHARACTERIZATION_INCOMPLETE=NO_FCS_VALID_AX25_FRAME_OBSERVED")
            print("SAFE_TO_REPEAT_LATER=YES")
            return 2

        correlations = []
        for index, item in enumerate(frames, 1):
            try:
                corr = correlate_rssi_window(
                    rssi_samples,
                    sample_start=item.sample_start,
                    sample_end=item.sample_end,
                    padding_samples=FRAME_CORRELATION_PADDING_SAMPLES,
                )
            except ValueError:
                continue
            correlations.append(corr)
            print(
                f"FRAME_RSSI[{index}] count={corr.count} min={corr.raw_min} "
                f"median={corr.raw_median} max={corr.raw_max}"
            )

        if not correlations:
            raise RuntimeError("decoded frames had no overlapping RSSI telemetry samples")

        frame_windows = [(corr.sample_start, corr.sample_end) for corr in correlations]
        outside_raws = rssi_values_outside_windows(
            rssi_samples,
            frame_windows,
            padding_samples=OUTSIDE_FRAME_GUARD_SAMPLES,
        )
        if len(outside_raws) < MIN_OUTSIDE_SAMPLES:
            raise RuntimeError(
                f"only {len(outside_raws)} RSSI samples remain outside decoded-frame windows; "
                f"need at least {MIN_OUTSIDE_SAMPLES}"
            )

        packet_worst_median = max(corr.raw_median for corr in correlations)
        outside_median = statistics.median(outside_raws)
        polarity_margin = outside_median - packet_worst_median
        print(f"Outside-frame samples     : {len(outside_raws)}")
        print(f"Packet worst median RSSI  : {packet_worst_median}")
        print(f"Outside-frame median RSSI : {outside_median}")
        print(f"Observed polarity margin  : {polarity_margin}")
        if polarity_margin < MIN_POLARITY_MARGIN:
            raise RuntimeError(
                "decoded packet RSSI is not independently lower than the outside-frame "
                f"population by the required {MIN_POLARITY_MARGIN} raw counts"
            )

        # Polarity is now established independently. Only after that proof do
        # we describe the highest large guard gap above the packet signal
        # reference. The midpoint remains evidence, not an enabled threshold.
        signal_reference_max = math.ceil(packet_worst_median)
        raws = [raw for _, raw in rssi_samples]
        separation = guard_gap_above_signal(
            raws,
            signal_reference_max=signal_reference_max,
            min_gap=MIN_SEPARATING_GAP,
            min_low_count=5,
            min_high_count=20,
        )

        snap = owner.snapshot
        if snap.owner_thread_id is None:
            raise RuntimeError("single modem owner thread ID was not established")

        print(f"RSSI samples              : {len(rssi_samples)}")
        print(f"Valid AX.25 frames        : {len(frames)}")
        print(f"Correlated frame windows  : {len(correlations)}")
        print(f"Packet signal reference   : <= {signal_reference_max}")
        print(f"Observed signal/guard side: {separation.low_min}..{separation.low_max} median={separation.low_median}")
        print(f"Observed upper population : {separation.high_min}..{separation.high_max} median={separation.high_median}")
        print(f"Observed guard gap        : {separation.low_max}..{separation.high_min} width={separation.gap}")
        print(f"Descriptive midpoint      : {separation.midpoint}")
        print(f"Packed bytes drained      : {packed_bytes}")
        print(f"Read transactions         : {read_transactions}")
        print(f"RSSI transactions         : {rssi_transactions}")
        print(f"Status checks             : {status_checks}")
        print(f"Peak FIFO available       : {peak_available}")
        print(f"FIFO dropped bytes        : {dropped}")
        print(f"RF keyups                 : {before_keyups}->{after_keyups}")
        print(f"RF TX generated samples   : {before_generated}->{after_generated}")
        print(f"Owner transactions        : {snap.transactions}")

    finally:
        if rx_started:
            try:
                owner.rx_stop(timeout=1.0)
            except BaseException:
                pass
        owner.stop(timeout=2.0)

    print("YWD1278_0C_P2_PACKET_CORRELATED_RSSI=PASS")
    print(f"FIRMWARE_IDENTITY={IDENTITY}")
    print(f"RX_FREQUENCY_HZ={FREQUENCY_HZ}")
    print(f"VALID_AX25_FRAMES={len(frames)}")
    print(f"CORRELATED_FRAME_WINDOWS={len(correlations)}")
    print("RSSI_POLARITY=LOWER_RAW_IS_STRONGER_RF")
    print(f"PACKET_WORST_MEDIAN={packet_worst_median}")
    print(f"OUTSIDE_FRAME_MEDIAN={outside_median}")
    print(f"POLARITY_MARGIN={polarity_margin}")
    print(f"PACKET_SIGNAL_REFERENCE_MAX={signal_reference_max}")
    print(f"OBSERVED_BUSY_SIDE_MAX={separation.low_max}")
    print(f"OBSERVED_UPPER_SIDE_MIN={separation.high_min}")
    print(f"OBSERVED_GUARD_GAP={separation.gap}")
    print(f"DESCRIPTIVE_MIDPOINT={separation.midpoint}")
    print(f"FIFO_DROPPED_BYTES={dropped}")
    print(f"RF_KEYUPS={before_keyups}->{after_keyups}")
    print(f"RF_TX_GENERATED_SAMPLES={before_generated}->{after_generated}")
    print("SINGLE_MODEM_OWNER=PASS")
    print("POLARITY_PROOF_INDEPENDENT_OF_GUARD_GAP=PASS")
    print("CARRIER_THRESHOLD_SELECTED=NO")
    print("HYSTERESIS_SELECTED=NO")
    print("BUSY_CLEAR_DECISION=NO")
    print("CSMA_INTEGRATION=NO")
    print("TX_COMMAND_PATH=ABSENT")
    print("KISS_TX_CONNECTED=NO")
    print("PRODUCT_TX_ENABLED=NO")
    print("RF_TRANSMITTED=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
