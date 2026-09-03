#!/usr/bin/env python3
"""0C-P3 live RSSI -> busy detector -> P1 CSMA shadow qualification.

This bounded receive-only tool assumes the exact physically qualified AX25R4
firmware is already running. It starts the existing RXOnlyPacketRuntime, shares
that runtime's single base ModemOwner through LiveChannelAccessSampler, and
observes P2 detector / P1 CSMA state transitions while real 145.050 MHz packet
traffic is received.

The qualification uses explicit deterministic persistence bytes: 255 before a
live busy event so shadow access cannot become READY, then 255 for the first
post-busy persistence trial and 0 for the second. READY is observational only.
There is no TXModemOwner, TXBroker, KISS TX connection, flash, GPIO, or RF TX
operation in this tool.
"""

from __future__ import annotations

from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.kiss.server import RXOnlyBackend  # noqa: E402
from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.owner import ModemOwner  # noqa: E402
from ywd1278.service.live_channel_access import LiveChannelAccessSampler  # noqa: E402
from ywd1278.service.rx_runtime import RXOnlyPacketRuntime  # noqa: E402
from ywd1278.tx.channel_busy import ChannelBusyState  # noqa: E402
from ywd1278.tx.csma import CSMAState  # noqa: E402


TARGET_ID = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
DEVICE = "/dev/ttyAMA0"
FREQUENCY_HZ = 145_050_000
EXPECTED_IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
    "ADF7021 FW based on CA6JAU GitID #7ff74ed"
)
MAXIMUM_DURATION_SECONDS = 20.0
RSSI_POLL_SECONDS = 0.050


def main() -> int:
    print("=== YWD-1278 0C-P3 LIVE SHADOW CHANNEL ACCESS ===")
    print(f"Target               : {TARGET_ID}")
    print(f"Device               : {DEVICE}")
    print(f"RX frequency         : {FREQUENCY_HZ} Hz")
    print(f"Maximum window       : {MAXIMUM_DURATION_SECONDS:.1f} s")
    print(f"RSSI poll interval   : {RSSI_POLL_SECONDS:.3f} s")
    print("Detector             : busy<=83 clear>=90 hold=250ms")
    print("P1                   : PERSIST=63 SLOTTIME=100ms max-wait=30s")
    print("Qualification RNG    : explicit 255... then post-busy 255,0")
    print("Transmit path        : ABSENT")
    print("ACTION: send or allow at least one real AX.25 packet on 145.050 MHz during the window.")

    owner = ModemOwner(
        posix_serial_transport_factory(DEVICE),
        queue_capacity=8,
        submit_timeout=0.20,
        default_transaction_timeout=1.25,
    )
    backend = RXOnlyBackend(history_capacity=64, subscriber_queue_capacity=8)
    runtime = RXOnlyPacketRuntime(
        owner,
        backend,
        expected_identity=EXPECTED_IDENTITY,
        frequency_hz=FREQUENCY_HZ,
        read_maximum=200,
        idle_sleep_seconds=0.002,
        status_interval_seconds=0.50,
        thread_name="ywd1278-0c-p3-rx-runtime",
    )

    runtime_started = False
    samples = 0
    pre_busy_trials = 0
    post_busy_trials = 0
    seen_busy = False
    busy_forced_wait_clear = False
    recent_after_busy = False
    clear_after_busy = False
    post_busy_full_slot = False
    post_busy_defer = False
    shadow_ready = False
    decoded_after_busy = False
    last_state: tuple[ChannelBusyState, CSMAState] | None = None
    before_keyups = 0
    after_keyups = 0
    before_generated = 0
    after_generated = 0

    started_at = 0.0

    def qualification_random_byte() -> int:
        nonlocal pre_busy_trials, post_busy_trials
        if not seen_busy:
            pre_busy_trials += 1
            return 255
        post_busy_trials += 1
        if post_busy_trials == 1:
            return 255
        return 0

    try:
        runtime.start(timeout=2.0)
        runtime_started = True
        if runtime.snapshot.identity != EXPECTED_IDENTITY:
            raise RuntimeError("RX runtime did not verify the exact AX25R4 identity")

        started_at = time.monotonic()
        sampler = LiveChannelAccessSampler(owner, started_at=started_at)
        sampler.preflight(timeout=1.25)

        diag_before = owner.rf_diagnostics(timeout=1.25)
        before_keyups = diag_before.keyups
        before_generated = diag_before.generated_samples
        if diag_before.tx_active != 0:
            raise RuntimeError("RF diagnostics report TX active before shadow observation")

        deadline = started_at + MAXIMUM_DURATION_SECONDS
        next_sample = started_at
        print("LIVE_WINDOW=OPEN")

        while True:
            now = time.monotonic()
            if now >= deadline:
                break
            if now < next_sample:
                time.sleep(min(next_sample - now, 0.005))
                continue

            obs = sampler.sample(
                now=now,
                random_byte_source=qualification_random_byte,
                timeout=1.25,
            )
            samples += 1
            elapsed = now - started_at

            state = (obs.detector.state, obs.csma.state)
            if state != last_state or obs.random_byte is not None:
                random_text = "-" if obs.random_byte is None else str(obs.random_byte)
                print(
                    f"ACCESS[{samples:04d}] elapsed={elapsed:.3f} raw={obs.detector.raw_magnitude} "
                    f"detector={obs.detector.state.value} csma={obs.csma.state.value} "
                    f"random={random_text} trials={obs.csma.persistence_trials} "
                    f"busy_obs={obs.csma.busy_observations}"
                )
                last_state = state

            if obs.detector.state is ChannelBusyState.BUSY:
                seen_busy = True
                if obs.csma.state is CSMAState.WAIT_CLEAR and obs.csma.next_slot_at is None:
                    busy_forced_wait_clear = True

            if seen_busy and obs.detector.state is ChannelBusyState.RECENT_RX:
                if obs.csma.state is CSMAState.WAIT_CLEAR:
                    recent_after_busy = True

            if seen_busy and obs.detector.state is ChannelBusyState.CLEAR:
                clear_after_busy = True
                if obs.csma.state is CSMAState.WAIT_SLOT and obs.random_byte is None:
                    post_busy_full_slot = True

            if seen_busy and obs.random_byte == 255 and obs.csma.state is CSMAState.WAIT_SLOT:
                post_busy_defer = True

            if seen_busy and obs.random_byte == 0 and obs.csma.state is CSMAState.READY:
                shadow_ready = True

            runtime.check_health()
            snap = runtime.snapshot
            if seen_busy and snap.decoded_frames >= 1:
                decoded_after_busy = True
            if snap.fifo_dropped_bytes != 0:
                raise RuntimeError(f"RX FIFO dropped {snap.fifo_dropped_bytes} packed bytes")

            if shadow_ready and decoded_after_busy:
                break

            next_sample += RSSI_POLL_SECONDS
            while next_sample <= now:
                next_sample += RSSI_POLL_SECONDS

        diag_after = owner.rf_diagnostics(timeout=1.25)
        after_keyups = diag_after.keyups
        after_generated = diag_after.generated_samples
        if diag_after.tx_active != 0:
            raise RuntimeError("RF diagnostics report TX active after shadow observation")
        if after_keyups != before_keyups:
            raise RuntimeError(
                f"RF keyup counter changed during shadow observation: {before_keyups}->{after_keyups}"
            )
        if after_generated != before_generated:
            raise RuntimeError(
                "RF generated-sample counter changed during shadow observation: "
                f"{before_generated}->{after_generated}"
            )

        final_live = runtime.snapshot
        if final_live.decoded_frames < 1:
            raise RuntimeError("no FCS-valid AX.25 frame was decoded during the live window")
        if final_live.fifo_dropped_bytes != 0:
            raise RuntimeError(f"RX FIFO dropped {final_live.fifo_dropped_bytes} packed bytes")
        if not seen_busy:
            raise RuntimeError("qualified P2 detector never observed BUSY during the live window")
        if not busy_forced_wait_clear:
            raise RuntimeError("live BUSY did not force P1 back to WAIT_CLEAR")
        if not recent_after_busy:
            raise RuntimeError("post-busy RECENT_RX hold was not observed as busy-for-access")
        if not clear_after_busy:
            raise RuntimeError("detector never returned CLEAR after the live busy event")
        if not post_busy_full_slot:
            raise RuntimeError("P1 did not start a new full slot after detector CLEAR")
        if not post_busy_defer:
            raise RuntimeError("first post-busy deterministic PERSIST=255 deferral was not observed")
        if not shadow_ready:
            raise RuntimeError("second post-busy deterministic PERSIST=0 trial did not reach READY")
        if post_busy_trials != 2:
            raise RuntimeError(
                f"expected exactly two post-busy persistence trials, observed {post_busy_trials}"
            )

        history, stream = backend.open_stream()
        try:
            if not history:
                raise RuntimeError("RX backend history is empty despite decoded-frame count")
            for index, event in enumerate(history, start=1):
                print(
                    f"DECODED[{index}] source={event.source} destination={event.destination} "
                    f"type={event.frame_type} bytes_no_fcs={len(event.frame_no_fcs)}"
                )
        finally:
            backend.close_stream(stream)

        runtime.stop(timeout=3.0)
        runtime_started = False
        stopped = runtime.snapshot
        owner_snap = owner.snapshot
        if stopped.failure:
            raise RuntimeError(f"RX runtime stopped with failure: {stopped.failure}")
        if owner_snap.running:
            raise RuntimeError("ModemOwner still reports running after RX runtime stop")
        if owner_snap.owner_thread_id is None:
            raise RuntimeError("single modem owner thread ID was never established")

        print("YWD1278_0C_P3_LIVE_SHADOW_CHANNEL_ACCESS=PASS")
        print(f"RSSI_SAMPLES={samples}")
        print(f"DECODED_AX25_FRAMES={stopped.decoded_frames}")
        print(f"PACKED_BYTES={stopped.packed_bytes}")
        print(f"FIFO_DROPPED_BYTES={stopped.fifo_dropped_bytes}")
        print(f"PRE_BUSY_DEFER_TRIALS={pre_busy_trials}")
        print(f"POST_BUSY_PERSIST_TRIALS={post_busy_trials}")
        print("LIVE_BUSY_OBSERVED=YES")
        print("BUSY_FORCED_CSMA_WAIT_CLEAR=YES")
        print("RECENT_RX_BUSY_FOR_ACCESS=YES")
        print("POST_BUSY_CLEAR_OBSERVED=YES")
        print("POST_BUSY_FULL_100MS_SLOT=YES")
        print("POST_BUSY_PERSIST_255_DEFER=YES")
        print("POST_BUSY_PERSIST_0_READY=YES")
        print("SHADOW_READY_ONLY=YES")
        print(f"RF_KEYUPS={before_keyups}->{after_keyups}")
        print(f"RF_TX_GENERATED_SAMPLES={before_generated}->{after_generated}")
        print("SINGLE_MODEM_OWNER=PASS")
        print("KISS_TX_CONNECTED=NO")
        print("TX_BROKER_CONNECTED=NO")
        print("PRODUCT_TX_ENABLED=NO")
        print("RF_TRANSMITTED=NO")
        print("FLASH_WRITTEN=NO")
        print("GPIO_ACCESSED=NO")
        print("OPTION_BYTES_WRITTEN=NO")
        return 0
    finally:
        if runtime_started:
            try:
                runtime.stop(timeout=3.0)
            except BaseException:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
