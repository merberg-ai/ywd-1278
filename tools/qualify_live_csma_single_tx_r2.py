#!/usr/bin/env python3
"""0C-P4d-R2 guarded live CSMA single-TX physical qualification.

R2 corrects the first P4d physical attempt by explicitly starting passive AX.25
RX before RSSI polling, draining the RX FIFO while sampling, and performing the
firmware-required half-duplex handoff RX_STOP -> TXBroker.submit_frame only
when the already-qualified P2/P1 channel-access path reaches READY.

This remains a one-purpose qualification harness, not a transmitter UI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(TOOLS))

import qualify_live_csma_single_tx as r1  # noqa: E402

from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.tx.access_queue import AccessRequestState, BoundedChannelAccessQueue  # noqa: E402
from ywd1278.tx.broker import TXBroker, TXReceipt  # noqa: E402
from ywd1278.tx.channel_busy import ChannelBusyState  # noqa: E402
from ywd1278.tx.csma import CSMAState  # noqa: E402

STAGING_R2 = ROOT / "firmware" / "qualification" / "0c-p4d-r2-live-csma-single-tx.json"
CONFIRMATION_TOKEN = "P4D-R2-145050-P200-CSMA-VERIFY-1"
INTERACTIVE_CONFIRMATION = "TRANSMIT-P4D-R2-CSMA-VERIFY-ONE"
RSSI_POLL_SECONDS = 0.050
STATUS_INTERVAL_SECONDS = 0.250
RX_READ_MAXIMUM = 200
ACTIVE_RX_REQUIRED_MASK = 0x0D  # active + RF ready + STATE_AX25
TX_FLAG = 0x02


def load_r2_stage() -> dict:
    stage = json.loads(STAGING_R2.read_text(encoding="utf-8"))
    required = {
        "schema": 1,
        "phase": "0C-P4d-R2",
        "status": "staged",
        "supersedes": "0C-P4d-R1",
        "base_checkpoint": "checkpoint/0c-p4c-real-owner-fake-transport-qualified",
        "base_checkpoint_sha": "e137b98b86b70b6835990c35f192741f0cb496e8",
        "r1_staged_checkpoint": "checkpoint/0c-p4d-live-csma-single-tx-staged-green",
        "r1_staged_checkpoint_sha": "d2ff131b989ad4fe81baa8a86067383e98e66c73",
        "target_id": r1.TARGET_ID,
        "device": r1.DEVICE,
        "frequency_hz": 145050000,
        "rf_power": 200,
        "expected_identity": (
            "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
            "ADF7021 FW based on CA6JAU GitID #7ff74ed"
        ),
        "source": "KJ6YWD-10",
        "destination": "YWD4D",
        "information_text": "YWD-1278 P4D CSMA VERIFY 1/1",
        "frame_bytes": 46,
        "selector_count": 753,
        "packed_selector_bytes": 95,
        "packed_selector_sha256": "ab9fca393ff79f287c9cd04c9a5f7dcea9a2530b9b4799b636246277a8ef46ca",
        "expected_generated_samples": 12048,
        "maximum_transmit_submissions": 1,
        "automatic_tx_retry": False,
        "requires_live_busy_before_tx": True,
        "rx_start_required_before_rssi": True,
        "rx_active_status_required": True,
        "rx_fifo_drain_while_sampling": True,
        "fifo_dropped_bytes_required": 0,
        "half_duplex_handoff": "RX_STOP_AFTER_READY_BEFORE_BROKER_SUBMIT",
        "rx_must_be_inactive_before_tx_tones": True,
        "external_decode_required": True,
        "kiss_tx_connected": False,
        "product_tx_enabled": False,
        "flash_permitted": False,
        "gpio_reset_permitted": False,
        "option_bytes_permitted": False,
        "confirmation_token": CONFIRMATION_TOKEN,
        "interactive_phrase": INTERACTIVE_CONFIRMATION,
    }
    for key, expected in required.items():
        if stage.get(key) != expected:
            raise SystemExit(
                f"FAIL: P4d-R2 staging mismatch for {key}: "
                f"expected={expected!r} actual={stage.get(key)!r}"
            )
    return stage


def require_active_rx(status) -> None:
    if status.dropped_bytes != 0:
        raise RuntimeError(f"RX FIFO dropped {status.dropped_bytes} packed bytes")
    if status.flags & TX_FLAG:
        raise RuntimeError(f"RX status unexpectedly reports TX active: flags=0x{status.flags:02X}")
    if status.flags & ACTIVE_RX_REQUIRED_MASK != ACTIVE_RX_REQUIRED_MASK:
        raise RuntimeError(
            "passive AX.25 RX is not fully active: "
            f"flags=0x{status.flags:02X} expected-mask=0x{ACTIVE_RX_REQUIRED_MASK:02X}"
        )


class RXStopThenBrokerSubmitter:
    """Qualification-only half-duplex READY -> RX_STOP -> broker handoff."""

    def __init__(self, owner: TXModemOwner, broker: TXBroker) -> None:
        self.owner = owner
        self.broker = broker
        self.calls = 0
        self.rx_stop_completed = False
        self.inactive_status_flags: int | None = None
        self.inactive_available_bytes: int | None = None
        self.inactive_dropped_bytes: int | None = None

    def submit_frame(self, frame_with_fcs: bytes, *, timeout: float | None = None):
        self.calls += 1
        if self.calls != 1:
            raise RuntimeError("P4d-R2 half-duplex submitter called more than once")
        before = self.owner.rx_status(timeout=1.25)
        require_active_rx(before)

        # Firmware intentionally rejects TX_TONES while passive RX capture is
        # active. Stop RX only after qualified channel access has reached READY.
        self.owner.rx_stop(timeout=1.25)
        after = self.owner.rx_status(timeout=1.25)
        if after.flags & 0x01:
            raise RuntimeError("RX capture remained active after P4d-R2 RX_STOP")
        if after.flags & TX_FLAG:
            raise RuntimeError("RX status reported TX active during RX_STOP handoff")
        if after.dropped_bytes != 0:
            raise RuntimeError(
                f"RX FIFO recorded drops at half-duplex handoff: {after.dropped_bytes}"
            )
        rf = self.owner.rf_status(timeout=1.25)
        if rf.remaining_selectors != 0:
            raise RuntimeError("modem has pending selectors before P4d-R2 broker submit")

        self.rx_stop_completed = True
        self.inactive_status_flags = after.flags
        self.inactive_available_bytes = after.available_bytes
        self.inactive_dropped_bytes = after.dropped_bytes
        return self.broker.submit_frame(frame_with_fcs, timeout=timeout)


def print_plan(r2: dict, r1_stage: dict) -> None:
    print("=== YWD-1278 0C-P4d-R2 GUARDED LIVE CSMA SINGLE TX ===")
    print(f"Target                 : {r1.TARGET_ID}")
    print(f"Device                 : {r1.DEVICE}")
    print(f"AX25R4 identity        : {r2['expected_identity']}")
    print(f"TX/RX frequency        : {r2['frequency_hz']} Hz")
    print(f"RF power byte          : {r2['rf_power']}/255 (frozen P13b-qualified level)")
    print("Detector               : busy<=83 clear>=90 hold=250ms")
    print("P1                     : PERSIST=63 SLOTTIME=100ms max-wait=30s")
    print("Qualification RNG      : 255 until first LIVE BUSY; then 255,0")
    print("RX before RSSI         : RX_START + active RX3 status REQUIRED")
    print("RX FIFO                : drained every 50ms; drops must remain zero")
    print("READY handoff          : RX_STOP -> verify inactive -> TXBroker.submit_frame")
    print("Live BUSY before TX    : REQUIRED")
    print("Maximum TX submissions : 1")
    print("Automatic TX retry     : NO")
    print("KISS/product TX        : DISCONNECTED")
    print("Flash/GPIO/options     : FORBIDDEN")
    print("Independent decode     : REQUIRED before qualification promotion")
    print(
        f"Fixed packet            : {r2['source']}>{r2['destination']}:"
        f"{r2['information_text']}"
    )
    print(f"Frame bytes/selectors  : {r2['frame_bytes']} / {r2['selector_count']}")
    print(f"Packed selector bytes  : {r2['packed_selector_bytes']}")
    print(f"Expected TX samples    : {r2['expected_generated_samples']}")
    print(
        "ACTION after LIVE_WINDOW=OPEN: create or allow one independent packet/RF burst "
        "on 145.050 MHz so the qualified detector observes BUSY."
    )
    if r1_stage["packed_selector_sha256"] != r2["packed_selector_sha256"]:
        raise RuntimeError("R2 vector does not match frozen R1 staged vector")


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 P4d-R2 guarded live-CSMA single-TX qualification")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()

    r1.load_target()
    r1_stage = r1.load_stage()
    r2 = load_r2_stage()
    frame = r1.build_vector(r1_stage)
    print_plan(r2, r1_stage)
    print(f"FRAME_HEX={frame.hex()}")
    print(
        f"EXPECTED_EXTERNAL_DECODE={r2['source']}>{r2['destination']}:"
        f"{r2['information_text']}"
    )

    if not args.transmit:
        print("P4D_R2_DRY_RUN=PASS")
        print("TX_MODEM_OWNER_CONSTRUCTED=NO")
        print("HARDWARE_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if args.confirm != CONFIRMATION_TOKEN:
        raise SystemExit(
            "FAIL: physical TX requires exact confirmation token "
            f"--confirm {CONFIRMATION_TOKEN}"
        )
    if not r1.uart_is_free():
        raise SystemExit(f"FAIL: modem UART already has an owner: {r1.DEVICE}")
    typed = input(f"Type exactly {INTERACTIVE_CONFIRMATION} to arm this one-shot test: ").strip()
    if typed != INTERACTIVE_CONFIRMATION:
        raise SystemExit("FAIL: interactive P4d-R2 confirmation did not match; no UART opened")

    owner = TXModemOwner(
        posix_serial_transport_factory(r1.DEVICE),
        queue_capacity=8,
        submit_timeout=0.20,
        default_transaction_timeout=1.50,
    )
    broker: TXBroker | None = None
    handoff: RXStopThenBrokerSubmitter | None = None
    access_queue: BoundedChannelAccessQueue | None = None
    owner_started = False
    rx_started = False

    samples = 0
    packed_bytes = 0
    status_checks = 0
    pre_busy_trials = 0
    post_busy_trials = 0
    seen_busy = False
    busy_forced_wait_clear = False
    recent_after_busy = False
    clear_after_busy = False
    post_busy_full_slot = False
    post_busy_defer = False
    dispatched = False
    transmit_submissions = 0
    busy_elapsed: float | None = None
    clear_elapsed: float | None = None
    defer_elapsed: float | None = None
    dispatch_elapsed: float | None = None
    receipt: TXReceipt | None = None
    last_state: tuple[ChannelBusyState, CSMAState] | None = None

    before_keyups = 0
    before_generated = 0
    final_keyups = 0
    final_generated = 0
    final_fifo_drops = 0

    def qualification_random_byte() -> int:
        nonlocal pre_busy_trials, post_busy_trials
        if not seen_busy:
            pre_busy_trials += 1
            return 255
        post_busy_trials += 1
        if post_busy_trials == 1:
            return 255
        if post_busy_trials == 2:
            return 0
        raise RuntimeError("P4d-R2 attempted more than two post-busy persistence trials")

    try:
        owner.start(timeout=2.0)
        owner_started = True
        version = owner.get_version(timeout=1.5)
        if version.identity != r2["expected_identity"]:
            raise RuntimeError(
                "running firmware identity is not exact qualified AX25R4 image: "
                f"{version.identity!r}"
            )

        status_initial = owner.rf_status(timeout=1.5)
        diag_initial = owner.rf_diagnostics(timeout=1.5)
        if status_initial.remaining_selectors != 0 or diag_initial.tx_active != 0:
            raise RuntimeError("modem is not idle before P4d-R2 setup")

        owner.apply_tx_qualification_profile(timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)
        armed = owner.rf_status(timeout=1.5)
        if armed.remaining_selectors != 0:
            raise RuntimeError("modem has pending TX selectors while arming P4d-R2")

        # R1 omitted this operation. AX25R4 RSSI must not be polled before it.
        owner.rx_start(timeout=1.5)
        rx_started = True
        active = owner.rx_status(timeout=1.5)
        status_checks += 1
        require_active_rx(active)
        if active.available_bytes:
            first = owner.rx_read(RX_READ_MAXIMUM, timeout=1.25)
            packed_bytes += len(first)
        active = owner.rx_status(timeout=1.5)
        status_checks += 1
        require_active_rx(active)

        diag_armed = owner.rf_diagnostics(timeout=1.5)
        if diag_armed.tx_active != 0:
            raise RuntimeError("TX became active during P4d-R2 RX setup")
        if diag_armed.keyups != diag_initial.keyups:
            raise RuntimeError("RF keyup diagnostic changed during P4d-R2 setup")
        if diag_armed.generated_samples != diag_initial.generated_samples:
            raise RuntimeError("generated-sample diagnostic changed during P4d-R2 setup")
        before_keyups = diag_armed.keyups
        before_generated = diag_armed.generated_samples

        broker = TXBroker(
            owner,
            transmit_enabled=True,
            queue_capacity=1,
            submit_timeout=0.05,
            default_transaction_timeout=1.5,
            thread_name="ywd1278-0c-p4d-r2-single-tx",
        )
        broker.start()
        handoff = RXStopThenBrokerSubmitter(owner, broker)
        access_queue = BoundedChannelAccessQueue(
            handoff,
            queue_capacity=1,
            request_timeout_seconds=30.0,
            downstream_timeout_seconds=1.5,
        )

        started_at = time.monotonic()
        queued = access_queue.enqueue(frame, now=started_at)
        deadline = queued.deadline_at
        next_sample = started_at
        next_status = started_at
        print("LIVE_WINDOW=OPEN")

        while not dispatched:
            now = time.monotonic()
            if now >= deadline:
                break
            if now < next_sample:
                time.sleep(min(next_sample - now, 0.005))
                continue

            # 19.2 ksps packed RX produces about 120 bytes per 50 ms. One
            # bounded 200-byte drain per cycle keeps ahead without monopolizing
            # the owner queue.
            chunk = owner.rx_read(RX_READ_MAXIMUM, timeout=1.25)
            packed_bytes += len(chunk)

            if now >= next_status:
                live_status = owner.rx_status(timeout=1.25)
                status_checks += 1
                require_active_rx(live_status)
                next_status = now + STATUS_INTERVAL_SECONDS

            rssi = owner.rx_rssi(timeout=1.25)
            obs = access_queue.observe_rssi(
                now=now,
                raw_magnitude=rssi.raw_magnitude,
                random_byte_source=qualification_random_byte,
            )
            samples += 1
            elapsed = now - started_at

            if obs.access is not None:
                state = (obs.access.detector.state, obs.access.csma.state)
                if state != last_state or obs.access.random_byte is not None or obs.downstream_called:
                    random_text = "-" if obs.access.random_byte is None else str(obs.access.random_byte)
                    print(
                        f"ACCESS[{samples:04d}] elapsed={elapsed:.3f} "
                        f"raw={obs.access.detector.raw_magnitude} "
                        f"detector={obs.access.detector.state.value} "
                        f"csma={obs.access.csma.state.value} random={random_text} "
                        f"trials={obs.access.csma.persistence_trials} "
                        f"busy_obs={obs.access.csma.busy_observations} "
                        f"request={obs.request_state.value if obs.request_state else '-'}"
                    )
                    last_state = state

                if obs.access.detector.state is ChannelBusyState.BUSY:
                    if not seen_busy:
                        busy_elapsed = elapsed
                    seen_busy = True
                    if obs.access.csma.state is CSMAState.WAIT_CLEAR and obs.access.csma.next_slot_at is None:
                        busy_forced_wait_clear = True
                if seen_busy and obs.access.detector.state is ChannelBusyState.RECENT_RX:
                    if obs.access.csma.state is CSMAState.WAIT_CLEAR:
                        recent_after_busy = True
                if seen_busy and obs.access.detector.state is ChannelBusyState.CLEAR:
                    if clear_elapsed is None:
                        clear_elapsed = elapsed
                    clear_after_busy = True
                    if obs.access.csma.state is CSMAState.WAIT_SLOT and obs.access.random_byte is None:
                        post_busy_full_slot = True
                if seen_busy and obs.access.random_byte == 255 and obs.access.csma.state is CSMAState.WAIT_SLOT:
                    post_busy_defer = True
                    defer_elapsed = elapsed

            if obs.downstream_called:
                transmit_submissions += 1
                if not seen_busy:
                    raise RuntimeError("P4d-R2 downstream TX was reached before required live BUSY")
                if obs.request_state is not AccessRequestState.DISPATCHED:
                    raise RuntimeError(
                        f"P4d-R2 downstream call did not dispatch: {obs.request_state} {obs.downstream_error}"
                    )
                if not isinstance(obs.downstream_result, TXReceipt):
                    raise RuntimeError("P4d-R2 broker returned unexpected receipt type")
                receipt = obs.downstream_result
                dispatch_elapsed = elapsed
                dispatched = True
                rx_started = False  # handoff performed RX_STOP before broker submit
                break

            if obs.request_state in {AccessRequestState.TIMED_OUT, AccessRequestState.DOWNSTREAM_FAILED}:
                raise RuntimeError(
                    f"P4d-R2 request terminated before successful dispatch: "
                    f"{obs.request_state.value} {obs.downstream_error}"
                )

            next_sample += RSSI_POLL_SECONDS
            while next_sample <= now:
                next_sample += RSSI_POLL_SECONDS

        if not seen_busy:
            raise RuntimeError("P4d-R2 observed no live BUSY event; no TX was permitted")
        if not dispatched or receipt is None:
            raise RuntimeError("P4d-R2 did not dispatch the one-shot frame within the bounded window")
        if transmit_submissions != 1:
            raise RuntimeError(
                f"P4d-R2 expected exactly one TX submission; observed {transmit_submissions}"
            )
        if handoff is None or handoff.calls != 1 or not handoff.rx_stop_completed:
            raise RuntimeError("P4d-R2 did not perform exactly one RX_STOP -> broker handoff")
        if not busy_forced_wait_clear:
            raise RuntimeError("live BUSY did not force P1 WAIT_CLEAR")
        if not recent_after_busy:
            raise RuntimeError("post-busy RECENT_RX was not observed as busy-for-access")
        if not clear_after_busy or not post_busy_full_slot:
            raise RuntimeError("P4d-R2 did not observe fresh full-slot gating after detector CLEAR")
        if not post_busy_defer:
            raise RuntimeError("first post-busy persistence byte 255 did not defer")
        if post_busy_trials != 2:
            raise RuntimeError(f"expected exactly two post-busy trials; observed {post_busy_trials}")

        if receipt.frame_bytes != r2["frame_bytes"]:
            raise RuntimeError("P4d-R2 broker receipt frame byte count changed")
        if receipt.selector_count != r2["selector_count"]:
            raise RuntimeError("P4d-R2 broker receipt selector count changed")
        if receipt.packed_selector_bytes != r2["packed_selector_bytes"]:
            raise RuntimeError("P4d-R2 broker receipt packed selector byte count changed")
        if receipt.packed_selector_sha256 != r2["packed_selector_sha256"]:
            raise RuntimeError("P4d-R2 broker receipt packed selector SHA256 changed")

        post_status, post_diag = r1.wait_for_idle(owner, receipt.nominal_duration_seconds)
        if post_status.remaining_selectors != 0 or post_diag.tx_active != 0:
            raise RuntimeError("P4d-R2 burst did not return to modem idle")
        if post_diag.keyups != 1:
            raise RuntimeError(
                f"expected P4d-R2 completed-burst keyups=1; actual={post_diag.keyups}"
            )
        if post_diag.generated_samples != r2["expected_generated_samples"]:
            raise RuntimeError(
                "unexpected P4d-R2 generated samples: "
                f"expected={r2['expected_generated_samples']} actual={post_diag.generated_samples}"
            )
        final_keyups = post_diag.keyups
        final_generated = post_diag.generated_samples

        # No second request exists. Do not restart RX just to prove that fact;
        # queue/broker counters are sufficient and avoid another RF-state transition.
        if access_queue.snapshot.queue_depth != 0:
            raise RuntimeError("P4d-R2 queue retained a request after one-shot dispatch")
        if access_queue.snapshot.dispatched_requests != 1:
            raise RuntimeError("P4d-R2 access queue did not record exactly one dispatch")
        if broker.snapshot.submitted != 1 or broker.snapshot.accepted != 1:
            raise RuntimeError("P4d-R2 broker did not record exactly one accepted submission")

        inactive = owner.rx_status(timeout=1.25)
        status_checks += 1
        if inactive.flags & 0x01:
            raise RuntimeError("RX unexpectedly active after completed P4d-R2 TX")
        if inactive.dropped_bytes != 0:
            raise RuntimeError(
                f"RX FIFO drops changed by end of P4d-R2: {inactive.dropped_bytes}"
            )
        final_fifo_drops = inactive.dropped_bytes

        broker.stop(timeout=2.0)
        broker = None
        owner.stop(timeout=2.0)
        owner_started = False
        if owner.snapshot.running:
            raise RuntimeError("TXModemOwner still running after P4d-R2 stop")
        if owner.snapshot.owner_thread_id is None:
            raise RuntimeError("single modem owner thread ID was never established")

        print("YWD1278_0C_P4D_R2_LIVE_CSMA_SINGLE_TX_EXECUTION=PASS")
        print(f"RSSI_SAMPLES={samples}")
        print(f"PACKED_RX_BYTES_DRAINED={packed_bytes}")
        print(f"RX_STATUS_CHECKS={status_checks}")
        print(f"FIFO_DROPPED_BYTES={final_fifo_drops}")
        print(f"PRE_BUSY_DEFER_TRIALS={pre_busy_trials}")
        print(f"POST_BUSY_PERSIST_TRIALS={post_busy_trials}")
        print(f"BUSY_ELAPSED={busy_elapsed:.3f}" if busy_elapsed is not None else "BUSY_ELAPSED=-")
        print(f"CLEAR_ELAPSED={clear_elapsed:.3f}" if clear_elapsed is not None else "CLEAR_ELAPSED=-")
        print(f"DEFER_ELAPSED={defer_elapsed:.3f}" if defer_elapsed is not None else "DEFER_ELAPSED=-")
        print(f"DISPATCH_ELAPSED={dispatch_elapsed:.3f}" if dispatch_elapsed is not None else "DISPATCH_ELAPSED=-")
        print("RX_START_BEFORE_RSSI=PASS")
        print("LIVE_BUSY_OBSERVED=YES")
        print("BUSY_FORCED_CSMA_WAIT_CLEAR=YES")
        print("RECENT_RX_BUSY_FOR_ACCESS=YES")
        print("POST_BUSY_CLEAR_OBSERVED=YES")
        print("POST_BUSY_FULL_100MS_SLOT=YES")
        print("POST_BUSY_PERSIST_255_DEFER=YES")
        print("POST_BUSY_PERSIST_0_DISPATCH=YES")
        print("RX_STOP_AFTER_READY_BEFORE_BROKER=PASS")
        print("RX_INACTIVE_BEFORE_TX_TONES=PASS")
        print("TRANSMIT_SUBMISSIONS=1")
        print(f"TX_FRAME_BYTES={receipt.frame_bytes}")
        print(f"TX_SELECTOR_COUNT={receipt.selector_count}")
        print(f"TX_PACKED_SELECTOR_BYTES={receipt.packed_selector_bytes}")
        print(f"TX_PACKED_SELECTOR_SHA256={receipt.packed_selector_sha256}")
        print(f"RF_KEYUPS_BEFORE={before_keyups}")
        print(f"RF_GENERATED_SAMPLES_BEFORE={before_generated}")
        print(f"RF_KEYUPS_COMPLETED_BURST_ABSOLUTE={final_keyups}")
        print(f"RF_GENERATED_SAMPLES_COMPLETED_BURST_ABSOLUTE={final_generated}")
        print("DIAGNOSTIC_COUNTERS_RESET_ON_ACCEPT=PASS")
        print("DUPLICATE_DISPATCH=NO")
        print("SINGLE_MODEM_OWNER=PASS")
        print("UART_RELEASED=YES")
        print("KISS_TX_CONNECTED=NO")
        print("PRODUCT_TX_ENABLED=NO")
        print("AUTOMATIC_TX_RETRY=NO")
        print("FLASH_WRITTEN=NO")
        print("GPIO_ACCESSED=NO")
        print("OPTION_BYTES_WRITTEN=NO")
        print("RF_TRANSMITTED=YES_EXACTLY_ONE_BURST")
        print("EXTERNAL_DECODE_REQUIRED=YES")
        print("QUALIFICATION_COMPLETE=NO_PENDING_EXTERNAL_DECODE")
        return 0
    finally:
        if broker is not None:
            try:
                broker.stop(timeout=2.0)
            except BaseException:
                pass
        if owner_started:
            if rx_started:
                try:
                    owner.rx_stop(timeout=1.0)
                except BaseException:
                    pass
            try:
                owner.stop(timeout=2.0)
            except BaseException:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
