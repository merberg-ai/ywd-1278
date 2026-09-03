#!/usr/bin/env python3
"""0C-P4d guarded live channel-access-controlled single RF TX qualification.

This is a one-purpose physical qualification harness, not a transmitter UI.
It composes the already-qualified P4a/P4b/P4c software graph with the real
POSIX modem transport and the already-qualified AX25R4 RSSI source.

Safety properties are deliberately rigid:

* exact target, /dev/ttyAMA0, AX25R4 identity, 145.050 MHz and RF power 200;
* one fixed FCS-bearing AX.25 frame and one maximum TX submission;
* no transmit is possible until a real live BUSY observation has occurred;
* persistence is forced to 255 before that BUSY event, then 255 and 0 after it;
* no automatic retry after any broker/downstream failure;
* no KISS/product TX, flash, GPIO/reset, or option-byte path;
* independent over-air decode is required before P4d may be called qualified.

Without --transmit the tool exits before TXModemOwner construction and therefore
cannot open the UART or access RF hardware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.ax25 import Address, build_ui_frame, verify_fcs  # noqa: E402
from ywd1278.modem._serial import posix_serial_transport_factory  # noqa: E402
from ywd1278.modem.tx_config import P13B_TX_FREQUENCY_HZ, P13B_TX_POWER  # noqa: E402
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.phy import MARK, frame_to_selectors, pack_selectors  # noqa: E402
from ywd1278.tx.access_queue import AccessRequestState, BoundedChannelAccessQueue  # noqa: E402
from ywd1278.tx.broker import TXBroker, TXReceipt  # noqa: E402
from ywd1278.tx.channel_busy import ChannelBusyState  # noqa: E402
from ywd1278.tx.csma import CSMAState  # noqa: E402

TARGET_ID = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
DEVICE = "/dev/ttyAMA0"
STAGING = ROOT / "firmware" / "qualification" / "0c-p4d-live-csma-single-tx.json"
CONFIRMATION_TOKEN = "P4D-145050-P200-CSMA-VERIFY-1"
INTERACTIVE_CONFIRMATION = "TRANSMIT-P4D-CSMA-VERIFY-ONE"
RSSI_POLL_SECONDS = 0.050
COMPLETION_TIMEOUT_SECONDS = 5.0


def uart_is_free() -> bool:
    if shutil.which("fuser") is None:
        return True
    result = subprocess.run(
        ["fuser", DEVICE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode != 0


def load_target() -> dict:
    data = json.loads((ROOT / "firmware" / "targets.json").read_text(encoding="utf-8"))
    matches = [item for item in data.get("targets", []) if item.get("id") == TARGET_ID]
    if len(matches) != 1:
        raise SystemExit("FAIL: exact P4d target not found exactly once")
    target = matches[0]
    if target.get("status") != "0c-p2-channel-busy-detector-qualified":
        raise SystemExit("FAIL: current physical target boundary is not qualified 0C-P2")
    if target.get("flash_enabled") is not False or target.get("option_bytes_permitted") is not False:
        raise SystemExit("FAIL: target flash/option-byte safety gates changed")

    rssi = target.get("packet_rssi_qualification") or {}
    if rssi.get("phase") != "0C-P2" or rssi.get("status") != "physically-qualified-correlation":
        raise SystemExit("FAIL: target lacks qualified AX25R4 RSSI evidence")
    if rssi.get("firmware_left_installed") is not True:
        raise SystemExit("FAIL: AX25R4 firmware is not recorded as left installed")
    if rssi.get("receive_frequency_hz") != P13B_TX_FREQUENCY_HZ:
        raise SystemExit("FAIL: qualified RSSI frequency changed")

    p13b = target.get("packet_live_tx_qualification") or {}
    if p13b.get("phase") != "0B-P13b" or p13b.get("status") != "qualified":
        raise SystemExit("FAIL: target lacks qualified P13b physical TX evidence")
    if p13b.get("transmit_frequency_hz") != P13B_TX_FREQUENCY_HZ:
        raise SystemExit("FAIL: P13b qualified TX frequency changed")
    if p13b.get("rf_power") != P13B_TX_POWER:
        raise SystemExit("FAIL: P13b qualified RF power changed")
    if p13b.get("automatic_tx_retry") is not False:
        raise SystemExit("FAIL: frozen P13b no-retry evidence changed")
    return target


def load_stage() -> dict:
    stage = json.loads(STAGING.read_text(encoding="utf-8"))
    required = {
        "phase": "0C-P4d",
        "status": "staged",
        "base_checkpoint": "checkpoint/0c-p4c-real-owner-fake-transport-qualified",
        "base_checkpoint_sha": "e137b98b86b70b6835990c35f192741f0cb496e8",
        "target_id": TARGET_ID,
        "device": DEVICE,
        "transmit_frequency_hz": P13B_TX_FREQUENCY_HZ,
        "rf_power": P13B_TX_POWER,
        "source": "KJ6YWD-10",
        "destination": "YWD4D",
        "information_text": "YWD-1278 P4D CSMA VERIFY 1/1",
        "pre_flags": 45,
        "post_flags": 3,
        "initial_tone": "MARK",
        "samples_per_selector": 16,
        "requires_live_busy_before_dispatch": True,
        "maximum_transmit_submissions": 1,
        "automatic_tx_retry": False,
        "requires_external_decode": True,
        "minimum_external_decodes_required": 1,
        "confirmation_token": CONFIRMATION_TOKEN,
        "interactive_confirmation": INTERACTIVE_CONFIRMATION,
        "kiss_tx_connected": False,
        "daemon_tx_connected": False,
        "product_tx_enabled": False,
        "flash_permitted": False,
        "gpio_reset_permitted": False,
        "option_bytes_permitted": False,
    }
    for key, expected in required.items():
        if stage.get(key) != expected:
            raise SystemExit(
                f"FAIL: P4d staging mismatch for {key}: expected={expected!r} actual={stage.get(key)!r}"
            )
    if stage.get("qualification_randomness") != {
        "before_first_live_busy": 255,
        "post_busy_sequence": [255, 0],
    }:
        raise SystemExit("FAIL: P4d deterministic qualification randomness changed")
    return stage


def build_vector(stage: dict) -> bytes:
    frame = build_ui_frame(
        source=Address.parse(stage["source"]),
        destination=Address.parse(stage["destination"]),
        info=stage["information_text"].encode("ascii"),
        include_fcs=True,
    )
    if not verify_fcs(frame):
        raise SystemExit("FAIL: P4d fixed frame FCS is invalid")
    selectors = frame_to_selectors(
        frame,
        pre_flags=stage["pre_flags"],
        post_flags=stage["post_flags"],
        initial_tone=MARK,
    )
    packed = pack_selectors(selectors)
    checks = (
        (len(frame), stage["frame_bytes"], "frame bytes"),
        (frame.hex(), stage["frame_hex"], "frame hex"),
        (hashlib.sha256(frame).hexdigest(), stage["frame_sha256"], "frame SHA256"),
        (len(selectors), stage["selector_count"], "selector count"),
        (len(packed), stage["packed_selector_bytes"], "packed selector bytes"),
        (
            hashlib.sha256(packed).hexdigest(),
            stage["packed_selector_sha256"],
            "packed selector SHA256",
        ),
        (
            len(selectors) * stage["samples_per_selector"],
            stage["expected_generated_samples"],
            "generated samples",
        ),
    )
    for actual, expected, label in checks:
        if actual != expected:
            raise SystemExit(
                f"FAIL: P4d {label} changed: expected={expected!r} actual={actual!r}"
            )
    return frame


def wait_for_idle(owner: TXModemOwner, nominal_seconds: float):
    time.sleep(nominal_seconds + 0.10)
    deadline = time.monotonic() + COMPLETION_TIMEOUT_SECONDS
    while True:
        status = owner.rf_status(timeout=1.5)
        diag = owner.rf_diagnostics(timeout=1.5)
        if status.remaining_selectors == 0 and diag.tx_active == 0:
            return status, diag
        if time.monotonic() >= deadline:
            raise RuntimeError("timed out waiting for P4d RF burst to finish")
        time.sleep(0.05)


def print_plan(stage: dict) -> None:
    print("=== YWD-1278 0C-P4d GUARDED LIVE CSMA SINGLE TX ===")
    print(f"Target                 : {TARGET_ID}")
    print(f"Device                 : {DEVICE}")
    print(f"AX25R4 identity        : {stage['runtime_identity']}")
    print(f"TX/RX frequency        : {stage['transmit_frequency_hz']} Hz")
    print(f"RF power byte          : {stage['rf_power']}/255 (frozen P13b-qualified level)")
    print("Detector               : busy<=83 clear>=90 hold=250ms")
    print("P1                     : PERSIST=63 SLOTTIME=100ms max-wait=30s")
    print("Qualification RNG      : 255 until first LIVE BUSY; then 255,0")
    print("Live BUSY before TX    : REQUIRED")
    print("Maximum TX submissions : 1")
    print("Automatic TX retry     : NO")
    print("KISS/product TX        : DISCONNECTED")
    print("Flash/GPIO/options     : FORBIDDEN")
    print("Independent decode     : REQUIRED before qualification promotion")
    print(
        f"Fixed packet            : {stage['source']}>{stage['destination']}:"
        f"{stage['information_text']}"
    )
    print(f"Frame bytes/selectors  : {stage['frame_bytes']} / {stage['selector_count']}")
    print(f"Packed selector bytes  : {stage['packed_selector_bytes']}")
    print(f"Expected TX samples    : {stage['expected_generated_samples']}")
    print(
        "ACTION after LIVE_WINDOW=OPEN: create or allow one independent packet/RF burst on "
        "145.050 MHz so the qualified detector observes BUSY."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 P4d guarded live-CSMA single-TX qualification")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()

    target = load_target()
    stage = load_stage()
    frame = build_vector(stage)
    print_plan(stage)
    print(f"FRAME_HEX={frame.hex()}")
    print(
        f"EXPECTED_EXTERNAL_DECODE={stage['source']}>{stage['destination']}:"
        f"{stage['information_text']}"
    )

    if not args.transmit:
        print("P4D_DRY_RUN=PASS")
        print("TX_MODEM_OWNER_CONSTRUCTED=NO")
        print("HARDWARE_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if args.confirm != CONFIRMATION_TOKEN:
        raise SystemExit(
            "FAIL: physical TX requires exact confirmation token "
            f"--confirm {CONFIRMATION_TOKEN}"
        )
    if not uart_is_free():
        raise SystemExit(f"FAIL: modem UART already has an owner: {DEVICE}")

    typed = input(f"Type exactly {INTERACTIVE_CONFIRMATION} to arm this one-shot test: ").strip()
    if typed != INTERACTIVE_CONFIRMATION:
        raise SystemExit("FAIL: interactive P4d confirmation did not match; no UART opened")

    expected_identity = stage["runtime_identity"]
    owner = TXModemOwner(
        posix_serial_transport_factory(DEVICE),
        queue_capacity=8,
        submit_timeout=0.20,
        default_transaction_timeout=1.50,
    )
    broker: TXBroker | None = None
    access_queue: BoundedChannelAccessQueue | None = None
    owner_started = False

    samples = 0
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

    before_keyups = 0
    before_generated = 0
    final_keyups = 0
    final_generated = 0
    receipt: TXReceipt | None = None
    started_at = 0.0
    last_state: tuple[ChannelBusyState, CSMAState] | None = None

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
        raise RuntimeError("P4d attempted more than two post-busy persistence trials")

    try:
        owner.start(timeout=2.0)
        owner_started = True
        version = owner.get_version(timeout=1.5)
        if version.identity != expected_identity:
            raise RuntimeError(
                "running firmware identity is not exact qualified AX25R4 image: "
                f"{version.identity!r}"
            )

        status_initial = owner.rf_status(timeout=1.5)
        diag_initial = owner.rf_diagnostics(timeout=1.5)
        if status_initial.remaining_selectors != 0 or diag_initial.tx_active != 0:
            raise RuntimeError("modem is not idle before P4d setup")

        # Reuse the exact physically qualified P13b 145.050 MHz / power-200 profile.
        owner.apply_tx_qualification_profile(timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)
        status_armed = owner.rf_status(timeout=1.5)
        diag_armed = owner.rf_diagnostics(timeout=1.5)
        if status_armed.remaining_selectors != 0 or diag_armed.tx_active != 0:
            raise RuntimeError("modem became TX-busy while arming P4d RX/RSSI")
        if diag_armed.keyups != diag_initial.keyups:
            raise RuntimeError("RF keyup diagnostic changed during P4d setup")
        if diag_armed.generated_samples != diag_initial.generated_samples:
            raise RuntimeError("generated-sample diagnostic changed during P4d setup")
        before_keyups = diag_armed.keyups
        before_generated = diag_armed.generated_samples

        broker = TXBroker(
            owner,
            transmit_enabled=True,
            queue_capacity=1,
            submit_timeout=0.05,
            default_transaction_timeout=1.5,
            thread_name="ywd1278-0c-p4d-single-tx",
        )
        broker.start()
        access_queue = BoundedChannelAccessQueue(
            broker,
            queue_capacity=1,
            request_timeout_seconds=stage["csma"]["maximum_wait_seconds"],
            downstream_timeout_seconds=1.5,
        )

        started_at = time.monotonic()
        queued = access_queue.enqueue(frame, now=started_at)
        if queued.frame_bytes != stage["frame_bytes"]:
            raise RuntimeError("P4d queued frame size changed")
        deadline = queued.deadline_at
        next_sample = started_at
        print("LIVE_WINDOW=OPEN")

        while not dispatched:
            now = time.monotonic()
            if now >= deadline:
                break
            if now < next_sample:
                time.sleep(min(next_sample - now, 0.005))
                continue

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
                    raise RuntimeError("P4d downstream TX was reached before required live BUSY")
                if obs.request_state is not AccessRequestState.DISPATCHED:
                    raise RuntimeError(
                        f"P4d downstream call did not dispatch: {obs.request_state} {obs.downstream_error}"
                    )
                if not isinstance(obs.downstream_result, TXReceipt):
                    raise RuntimeError("P4d broker returned unexpected receipt type")
                receipt = obs.downstream_result
                dispatch_elapsed = elapsed
                dispatched = True
                break

            if obs.request_state in {AccessRequestState.TIMED_OUT, AccessRequestState.DOWNSTREAM_FAILED}:
                raise RuntimeError(
                    f"P4d request terminated before successful dispatch: "
                    f"{obs.request_state.value} {obs.downstream_error}"
                )

            next_sample += RSSI_POLL_SECONDS
            while next_sample <= now:
                next_sample += RSSI_POLL_SECONDS

        if not seen_busy:
            raise RuntimeError("P4d observed no live BUSY event; no TX was permitted")
        if not dispatched or receipt is None:
            raise RuntimeError("P4d did not dispatch the one-shot frame within the bounded window")
        if transmit_submissions != 1:
            raise RuntimeError(f"P4d expected exactly one TX submission; observed {transmit_submissions}")
        if not busy_forced_wait_clear:
            raise RuntimeError("live BUSY did not force P1 WAIT_CLEAR")
        if not recent_after_busy:
            raise RuntimeError("post-busy RECENT_RX was not observed as busy-for-access")
        if not clear_after_busy or not post_busy_full_slot:
            raise RuntimeError("P4d did not observe fresh full-slot gating after detector CLEAR")
        if not post_busy_defer:
            raise RuntimeError("first post-busy persistence byte 255 did not defer")
        if post_busy_trials != 2:
            raise RuntimeError(f"expected exactly two post-busy trials; observed {post_busy_trials}")

        if receipt.frame_bytes != stage["frame_bytes"]:
            raise RuntimeError("P4d broker receipt frame byte count changed")
        if receipt.selector_count != stage["selector_count"]:
            raise RuntimeError("P4d broker receipt selector count changed")
        if receipt.packed_selector_bytes != stage["packed_selector_bytes"]:
            raise RuntimeError("P4d broker receipt packed selector byte count changed")
        if receipt.packed_selector_sha256 != stage["packed_selector_sha256"]:
            raise RuntimeError("P4d broker receipt packed selector SHA256 changed")

        post_status, post_diag = wait_for_idle(owner, receipt.nominal_duration_seconds)
        if post_status.remaining_selectors != 0 or post_diag.tx_active != 0:
            raise RuntimeError("P4d burst did not return to modem idle")
        # AX25R3/R4 firmware resets these diagnostics on every accepted burst.
        if post_diag.keyups != 1:
            raise RuntimeError(f"expected P4d completed-burst keyups=1; actual={post_diag.keyups}")
        if post_diag.generated_samples != stage["expected_generated_samples"]:
            raise RuntimeError(
                "unexpected P4d generated samples: "
                f"expected={stage['expected_generated_samples']} actual={post_diag.generated_samples}"
            )
        final_keyups = post_diag.keyups
        final_generated = post_diag.generated_samples

        # After the completed burst, one fresh RSSI observation must find no
        # queued request and therefore cannot create a duplicate transmission.
        final_rssi = owner.rx_rssi(timeout=1.25)
        no_request = access_queue.observe_rssi(
            now=time.monotonic(),
            raw_magnitude=final_rssi.raw_magnitude,
            random_byte_source=lambda: (_ for _ in ()).throw(RuntimeError("unexpected RNG use")),
        )
        if no_request.request_id is not None or no_request.downstream_called:
            raise RuntimeError("P4d queue retained a request after one-shot dispatch")
        if broker.snapshot.submitted != 1 or broker.snapshot.accepted != 1:
            raise RuntimeError("P4d broker did not record exactly one accepted submission")

        broker.stop(timeout=2.0)
        broker = None
        owner.stop(timeout=2.0)
        owner_started = False
        if owner.snapshot.running:
            raise RuntimeError("TXModemOwner still running after P4d stop")
        if owner.snapshot.owner_thread_id is None:
            raise RuntimeError("single modem owner thread ID was never established")

        print("YWD1278_0C_P4D_LIVE_CSMA_SINGLE_TX_EXECUTION=PASS")
        print(f"RSSI_SAMPLES={samples}")
        print(f"PRE_BUSY_DEFER_TRIALS={pre_busy_trials}")
        print(f"POST_BUSY_PERSIST_TRIALS={post_busy_trials}")
        print(f"BUSY_ELAPSED={busy_elapsed:.3f}" if busy_elapsed is not None else "BUSY_ELAPSED=-")
        print(f"CLEAR_ELAPSED={clear_elapsed:.3f}" if clear_elapsed is not None else "CLEAR_ELAPSED=-")
        print(f"DEFER_ELAPSED={defer_elapsed:.3f}" if defer_elapsed is not None else "DEFER_ELAPSED=-")
        print(f"DISPATCH_ELAPSED={dispatch_elapsed:.3f}" if dispatch_elapsed is not None else "DISPATCH_ELAPSED=-")
        print("LIVE_BUSY_OBSERVED=YES")
        print("BUSY_FORCED_CSMA_WAIT_CLEAR=YES")
        print("RECENT_RX_BUSY_FOR_ACCESS=YES")
        print("POST_BUSY_CLEAR_OBSERVED=YES")
        print("POST_BUSY_FULL_100MS_SLOT=YES")
        print("POST_BUSY_PERSIST_255_DEFER=YES")
        print("POST_BUSY_PERSIST_0_DISPATCH=YES")
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
            try:
                owner.stop(timeout=2.0)
            except BaseException:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
