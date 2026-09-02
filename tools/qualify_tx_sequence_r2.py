#!/usr/bin/env python3
"""0B-P13b-R2 guarded three-packet external-decode verification.

R2 corrects two issues discovered during physical P13b/R1 work:

* YWD RF diagnostics reset keyups/generated-samples when each selector burst is
  accepted, so multi-burst qualification must validate the absolute completed
  values for each burst rather than compute lifetime deltas.
* the frozen YWD-MMDVM AX25-5B independent over-air proof at 145.050 MHz used
  RF power 200/255.  R2 reuses that exact qualified RF level rather than the
  RX-only helper's minimum nonzero 1/255 value.

This remains a fixed qualification harness, not a transmitter UI: exact target,
device, frequency, power, three frames, serializer timing, and 5 s pauses are
hard-coded/staged.  There is no KISS input, arbitrary payload/count/frequency,
automatic retry, flash, GPIO/reset, or option-byte path.
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
from ywd1278.tx import TXBroker  # noqa: E402

TARGET_ID = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
DEVICE = "/dev/ttyAMA0"
STAGING = ROOT / "firmware" / "qualification" / "p13b-r2-three-tx.json"
CONFIRMATION_TOKEN = "P13B-R2-145050-P200-VERIFY-3"
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
        raise SystemExit("FAIL: exact P13b-R2 target not found exactly once")
    target = matches[0]
    if target.get("status") != "0b-p12b-live-rf-kiss-qualified":
        raise SystemExit("FAIL: physical target boundary is not frozen P12b")
    if target.get("flash_enabled") is not False or target.get("option_bytes_permitted") is not False:
        raise SystemExit("FAIL: target flash/option-byte safety gates changed")
    p12a = target.get("packet_live_rx_qualification") or {}
    p12b = target.get("packet_live_rf_kiss_qualification") or {}
    if p12a.get("packet_firmware_left_installed") is not True:
        raise SystemExit("FAIL: exact packet firmware was not recorded as left installed")
    if p12b.get("phase") != "0B-P12b" or p12b.get("status") != "qualified":
        raise SystemExit("FAIL: target lacks frozen qualified P12b evidence")
    if p12b.get("receive_frequency_hz") != P13B_TX_FREQUENCY_HZ:
        raise SystemExit("FAIL: frozen local packet frequency changed")
    if p12b.get("rf_transmitted") is not False or p12b.get("option_bytes_written") is not False:
        raise SystemExit("FAIL: frozen P12b TX/option-byte evidence changed")
    packet = target.get("packet_firmware_candidate") or {}
    if packet.get("status") != "deterministic-build-and-runtime-qualified":
        raise SystemExit("FAIL: packet firmware candidate is not qualified")
    return target


def load_stage() -> dict:
    stage = json.loads(STAGING.read_text(encoding="utf-8"))
    required = {
        "phase": "0B-P13b-R2",
        "status": "staged",
        "target_id": TARGET_ID,
        "transmit_frequency_hz": P13B_TX_FREQUENCY_HZ,
        "rf_power": P13B_TX_POWER,
        "source": "KJ6YWD-10",
        "destination": "YWD13B",
        "pre_flags": 45,
        "post_flags": 3,
        "initial_tone": "MARK",
        "samples_per_selector": 16,
        "inter_packet_pause_seconds": 5.0,
        "maximum_transmissions": 3,
        "retry_transmit_on_failure": False,
        "diagnostic_counter_semantics": "reset-on-accepted-burst",
        "expected_keyups_per_completed_burst": 1,
        "requires_external_decode": True,
        "minimum_external_decodes_required": 1,
        "kiss_tx_connected": False,
        "product_tx_enabled": False,
        "flash_permitted": False,
        "gpio_reset_permitted": False,
        "option_bytes_permitted": False,
        "confirmation_token": CONFIRMATION_TOKEN,
    }
    for key, expected in required.items():
        if stage.get(key) != expected:
            raise SystemExit(
                f"FAIL: P13b-R2 staging mismatch for {key}: expected={expected!r} actual={stage.get(key)!r}"
            )
    frames = stage.get("frames")
    if not isinstance(frames, list) or len(frames) != 3:
        raise SystemExit("FAIL: P13b-R2 requires exactly three staged frames")
    return stage


def build_vectors(stage: dict) -> list[tuple[dict, bytes]]:
    vectors: list[tuple[dict, bytes]] = []
    for index, vector in enumerate(stage["frames"], start=1):
        if vector.get("sequence") != index:
            raise SystemExit("FAIL: P13b-R2 frame sequence changed")
        frame = build_ui_frame(
            source=Address.parse(stage["source"]),
            destination=Address.parse(stage["destination"]),
            info=vector["information_text"].encode("ascii"),
            include_fcs=True,
        )
        if not verify_fcs(frame):
            raise SystemExit(f"FAIL: R2 frame {index} FCS invalid")
        selectors = frame_to_selectors(
            frame,
            pre_flags=stage["pre_flags"],
            post_flags=stage["post_flags"],
            initial_tone=MARK,
        )
        packed = pack_selectors(selectors)
        checks = (
            (len(frame), vector["frame_bytes"], "frame bytes"),
            (frame.hex(), vector["frame_hex"], "frame hex"),
            (hashlib.sha256(frame).hexdigest(), vector["frame_sha256"], "frame SHA256"),
            (len(selectors), vector["selector_count"], "selector count"),
            (len(packed), vector["packed_selector_bytes"], "packed bytes"),
            (
                hashlib.sha256(packed).hexdigest(),
                vector["packed_selector_sha256"],
                "packed SHA256",
            ),
            (
                len(selectors) * stage["samples_per_selector"],
                vector["expected_generated_samples"],
                "generated samples",
            ),
        )
        for actual, expected, label in checks:
            if actual != expected:
                raise SystemExit(
                    f"FAIL: R2 frame {index} {label} changed: expected={expected!r} actual={actual!r}"
                )
        vectors.append((vector, frame))
    return vectors


def wait_for_idle(owner: TXModemOwner, nominal_seconds: float):
    time.sleep(nominal_seconds + 0.10)
    deadline = time.monotonic() + COMPLETION_TIMEOUT_SECONDS
    while True:
        status = owner.rf_status(timeout=1.5)
        diag = owner.rf_diagnostics(timeout=1.5)
        if status.remaining_selectors == 0 and diag.tx_active == 0:
            return status, diag
        if time.monotonic() >= deadline:
            raise RuntimeError("timed out waiting for P13b-R2 burst to finish")
        time.sleep(0.05)


def print_plan(stage: dict, expected_identity: str) -> None:
    print("=== YWD-1278 0B-P13b-R2 CORRECTED THREE-PACKET RF VERIFY ===")
    print(f"Target                    : {TARGET_ID}")
    print(f"Device                    : {DEVICE}")
    print(f"Packet identity           : {expected_identity}")
    print(f"TX frequency              : {P13B_TX_FREQUENCY_HZ} Hz")
    print(f"RF power byte             : {P13B_TX_POWER}/255 (frozen AX25-5B qualified level)")
    print(f"Diagnostic counters       : {stage['diagnostic_counter_semantics']}")
    print(f"Inter-packet pause        : {stage['inter_packet_pause_seconds']:.1f} s")
    print("Maximum TX submissions    : 3")
    print("Automatic TX retry        : NO")
    print("KISS-originated TX        : DISCONNECTED")
    print("Persistent product TX     : DISABLED")
    print("Firmware flash            : NO")
    print("GPIO/reset                : NO")
    print("Option-byte write         : NO")
    print("Independent decode        : REQUIRED (minimum one exact R2 frame)")
    for index, vector in enumerate(stage["frames"], start=1):
        print(
            f"Known R2 packet {index}/3       : "
            f"{stage['source']}>{stage['destination']}:{vector['information_text']}"
        )
        print(
            f"Frame {index} bytes/selectors    : "
            f"{vector['frame_bytes']} / {vector['selector_count']}"
        )
        print(
            f"Expected samples burst {index} : "
            f"{vector['expected_generated_samples']}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 P13b-R2 corrected guarded TX verification")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()

    target = load_target()
    stage = load_stage()
    vectors = build_vectors(stage)
    expected_identity = target["packet_firmware_candidate"]["expected_identity"]
    print_plan(stage, expected_identity)
    for index, (vector, frame) in enumerate(vectors, start=1):
        print(f"FRAME_HEX[{index}]={frame.hex()}")
        print(
            f"EXPECTED_EXTERNAL_DECODE[{index}]="
            f"{stage['source']}>{stage['destination']}:{vector['information_text']}"
        )

    # Dry-run exits before TXModemOwner construction, so it cannot open UART.
    if not args.transmit:
        print("P13B_R2_DRY_RUN=PASS")
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

    owner = TXModemOwner(
        posix_serial_transport_factory(DEVICE),
        queue_capacity=4,
        submit_timeout=0.20,
        default_transaction_timeout=1.50,
    )
    broker = None
    transmit_submissions = 0
    completed = []

    try:
        owner.start(timeout=2.0)
        version = owner.get_version(timeout=1.5)
        if version.identity != expected_identity:
            raise RuntimeError(
                "running firmware identity is not exact qualified packet image: "
                f"{version.identity!r}"
            )

        status_initial = owner.rf_status(timeout=1.5)
        diag_initial = owner.rf_diagnostics(timeout=1.5)
        if status_initial.remaining_selectors != 0 or diag_initial.tx_active != 0:
            raise RuntimeError("modem is not idle before P13b-R2 setup")

        # Fixed, argument-free qualification profile: 145.050 MHz, power 200.
        owner.apply_tx_qualification_profile(timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)
        status_armed = owner.rf_status(timeout=1.5)
        diag_armed = owner.rf_diagnostics(timeout=1.5)
        if status_armed.remaining_selectors != 0 or diag_armed.tx_active != 0:
            raise RuntimeError("modem became TX-busy while arming P13b-R2")
        if diag_armed.keyups != diag_initial.keyups:
            raise RuntimeError("RF keyup diagnostic changed during R2 setup")
        if diag_armed.generated_samples != diag_initial.generated_samples:
            raise RuntimeError("generated-sample diagnostic changed during R2 setup")

        broker = TXBroker(
            owner,
            transmit_enabled=True,
            queue_capacity=1,
            submit_timeout=0.05,
            default_transaction_timeout=1.5,
            thread_name="ywd1278-p13b-r2-verify3",
        )
        broker.start()

        previous_completed_diag = diag_armed
        for index, (vector, frame) in enumerate(vectors, start=1):
            pre_status = owner.rf_status(timeout=1.5)
            pre_diag = owner.rf_diagnostics(timeout=1.5)
            if pre_status.remaining_selectors != 0 or pre_diag.tx_active != 0:
                raise RuntimeError(f"modem not idle before P13b-R2 burst {index}")
            if pre_diag != previous_completed_diag:
                raise RuntimeError(
                    f"RF diagnostics changed unexpectedly before P13b-R2 burst {index}"
                )

            # Exactly one submission for this fixed vector. Never retry a failed call.
            transmit_submissions += 1
            receipt = broker.submit_frame(frame, timeout=1.5)
            if receipt.selector_count != vector["selector_count"]:
                raise RuntimeError(f"broker selector count differs for R2 burst {index}")
            if receipt.packed_selector_sha256 != vector["packed_selector_sha256"]:
                raise RuntimeError(f"broker selector SHA256 differs for R2 burst {index}")

            post_status, post_diag = wait_for_idle(owner, receipt.nominal_duration_seconds)

            # Firmware semantics: writeSelectors() resets these counters to zero
            # for every accepted burst.  Validate the absolute completed-burst
            # values, NOT a delta against the retained prior-burst diagnostics.
            if post_diag.keyups != stage["expected_keyups_per_completed_burst"]:
                raise RuntimeError(
                    f"expected completed R2 burst {index} keyups=1; actual={post_diag.keyups}"
                )
            if post_diag.generated_samples != vector["expected_generated_samples"]:
                raise RuntimeError(
                    f"unexpected completed R2 burst {index} generated samples: "
                    f"expected={vector['expected_generated_samples']} actual={post_diag.generated_samples}"
                )
            if post_status.remaining_selectors != 0 or post_diag.tx_active != 0:
                raise RuntimeError(f"R2 burst {index} did not return to idle")

            completed.append((receipt, post_status, post_diag))
            previous_completed_diag = post_diag
            print(f"BURST[{index}]_TX=COMPLETE")
            print(f"BURST[{index}]_KEYUPS_ABSOLUTE={post_diag.keyups}")
            print(f"BURST[{index}]_GENERATED_SAMPLES_ABSOLUTE={post_diag.generated_samples}")
            print(f"BURST[{index}]_COUNTERS_RESET_ON_ACCEPT=PASS")

            if index < 3:
                print(f"PAUSE_AFTER[{index}]={stage['inter_packet_pause_seconds']:.1f}s")
                time.sleep(stage["inter_packet_pause_seconds"])

        broker.stop(timeout=2.0)
        broker = None

        if transmit_submissions != 3 or len(completed) != 3:
            raise RuntimeError(
                f"unexpected completed R2 sequence: submissions={transmit_submissions} completed={len(completed)}"
            )
        final_status = owner.rf_status(timeout=1.5)
        final_diag = owner.rf_diagnostics(timeout=1.5)
        if final_status.remaining_selectors != 0 or final_diag.tx_active != 0:
            raise RuntimeError("modem not idle after final P13b-R2 burst")
        if final_diag != completed[-1][2]:
            raise RuntimeError("final R2 diagnostics changed after last completed burst")

    finally:
        if broker is not None:
            try:
                broker.stop(timeout=2.0)
            except BaseException:
                pass
        try:
            owner.stop(timeout=2.0)
        except BaseException:
            pass

    if not uart_is_free():
        raise RuntimeError("modem UART still has an owner after P13b-R2 shutdown")

    print(f"TRANSMIT_SUBMISSIONS={transmit_submissions}")
    print(f"COMPLETED_BURSTS={len(completed)}")
    print("YWD1278_0B_P13B_R2_INTERNAL_THREE_TX=PASS")
    print("EXACT_PACKET_FIRMWARE_IDENTITY=PASS")
    print("QUALIFIED_RF_POWER_200_255=PASS")
    print("RESET_ON_ACCEPT_COUNTER_ACCOUNTING=PASS")
    print("THREE_FIXED_TX_SUBMISSIONS=PASS")
    print("THREE_COMPLETED_KEYUPS=PASS")
    print("THREE_EXACT_GENERATED_SAMPLE_COUNTS=PASS")
    print("FIXED_FIVE_SECOND_GAPS=PASS")
    print("MODEM_UART_RELEASED=YES")
    print("KISS_TX_CONNECTED=NO")
    print("PRODUCT_TX_ENABLED=NO")
    print("FLASH_WRITTEN=NO")
    print("GPIO_ACCESSED=NO")
    print("OPTION_BYTES_WRITTEN=NO")
    print("AUTOMATIC_TX_RETRY=NO")
    print("EXTERNAL_DECODE_REQUIRED=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
