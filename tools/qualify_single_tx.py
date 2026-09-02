#!/usr/bin/env python3
"""0B-P13b guarded single YWD-generated RF transmit proof.

This harness is intentionally one-purpose and one-shot.  It uses the exact
packet firmware already left installed by P12a/P12b, configures the frozen
simplex MMDVM setup at 145.050 MHz, and submits exactly one known FCS-bearing
AX.25 frame through the P13a bounded TX broker and typed TX owner.

Ordinary TCP KISS/product TX remains disconnected.  There is no flash, GPIO,
reset, option-byte, abort, exit, retry, looped transmit, or arbitrary payload
path here.  A separate receiver/TNC must independently decode the packet before
P13b can be called physically qualified.
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
from ywd1278.modem.tx_owner import TXModemOwner  # noqa: E402
from ywd1278.phy import MARK, frame_to_selectors, pack_selectors  # noqa: E402
from ywd1278.tx import TXBroker  # noqa: E402

P13B_FREQUENCY_HZ = 145050000
P13B_CONFIRMATION_TOKEN = "P13B-145050-ONE-SHOT"
COMPLETION_TIMEOUT_SECONDS = 5.0


def load_target(path: Path, target_id: str) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    matches = [item for item in data.get("targets", []) if item.get("id") == target_id]
    if len(matches) != 1:
        raise SystemExit(f"FAIL: target not found exactly once: {target_id}")
    target = matches[0]

    # P13b starts from the frozen P12b physical boundary.  Host-only P13a did
    # not advance this target status and must not rewrite historical evidence.
    if target.get("status") != "0b-p12b-live-rf-kiss-qualified":
        raise SystemExit(f"FAIL: target is not at frozen P12b boundary: {target.get('status')}")
    if target.get("flash_enabled") is not False:
        raise SystemExit("FAIL: normal product flashing must remain disabled")
    if target.get("option_bytes_permitted") is not False:
        raise SystemExit("FAIL: target permits option-byte writes")

    p12a = target.get("packet_live_rx_qualification") or {}
    if p12a.get("phase") != "0B-P12a" or p12a.get("status") != "qualified":
        raise SystemExit("FAIL: target lacks qualified P12a packet activation evidence")
    if p12a.get("packet_firmware_left_installed") is not True:
        raise SystemExit("FAIL: P12a did not leave the exact packet firmware installed")

    p12b = target.get("packet_live_rf_kiss_qualification") or {}
    if p12b.get("phase") != "0B-P12b" or p12b.get("status") != "qualified":
        raise SystemExit("FAIL: target lacks physical P12b live RF-to-KISS evidence")
    if p12b.get("receive_frequency_hz") != P13B_FREQUENCY_HZ:
        raise SystemExit("FAIL: frozen P12b local packet frequency is not 145.050 MHz")
    if p12b.get("rf_transmitted") is not False:
        raise SystemExit("FAIL: P12b evidence unexpectedly contains RF transmission")
    if p12b.get("option_bytes_written") is not False:
        raise SystemExit("FAIL: P12b evidence unexpectedly contains option-byte writes")

    packet = target.get("packet_firmware_candidate") or {}
    if packet.get("status") != "deterministic-build-and-runtime-qualified":
        raise SystemExit("FAIL: exact packet firmware candidate is not qualified")
    if not packet.get("expected_identity"):
        raise SystemExit("FAIL: packet firmware expected identity is missing")
    return target


def load_staging(path: Path, target_id: str) -> dict:
    stage = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "phase": "0B-P13b",
        "status": "staged",
        "target_id": target_id,
        "transmit_frequency_hz": P13B_FREQUENCY_HZ,
        "source": "KJ6YWD-10",
        "destination": "YWD13B",
        "information_text": "YWD-1278 P13B SINGLE TX TEST",
        "frame_type": "UI",
        "pid": "0xF0",
        "frame_bytes": 46,
        "frame_hex": "b2ae88626684e096946cb2ae887503f05957442d3132373820503133422053494e474c4520545820544553545c59",
        "frame_sha256": "06e5d50cdcde68658c43f31f65126fbe90bb240594f1f2effe95a27a2bd90e87",
        "pre_flags": 45,
        "post_flags": 3,
        "initial_tone": "MARK",
        "selector_count": 753,
        "packed_selector_bytes": 95,
        "packed_selector_sha256": "7b99563d208029084af0559484ed38afbced3d01e9ec28610883efb5931e88b1",
        "samples_per_selector": 16,
        "expected_generated_samples_delta": 12048,
        "maximum_transmissions": 1,
        "retry_transmit_on_failure": False,
        "requires_exact_packet_identity": True,
        "requires_idle_modem": True,
        "requires_external_decode": True,
        "kiss_tx_connected": False,
        "product_tx_enabled": False,
        "flash_permitted": False,
        "gpio_reset_permitted": False,
        "option_bytes_permitted": False,
        "confirmation_token": P13B_CONFIRMATION_TOKEN,
    }
    for key, expected in required.items():
        if stage.get(key) != expected:
            raise SystemExit(
                f"FAIL: P13b staging mismatch for {key}: "
                f"expected={expected!r} actual={stage.get(key)!r}"
            )
    return stage


def build_known_frame(stage: dict) -> tuple[bytes, bytes]:
    frame = build_ui_frame(
        source=Address.parse(stage["source"]),
        destination=Address.parse(stage["destination"]),
        info=stage["information_text"].encode("ascii"),
        include_fcs=True,
    )
    if not verify_fcs(frame):
        raise SystemExit("FAIL: locally constructed P13b AX.25 frame has invalid FCS")
    if len(frame) != stage["frame_bytes"] or frame.hex() != stage["frame_hex"]:
        raise SystemExit("FAIL: P13b AX.25 frame no longer matches the frozen staging vector")
    if hashlib.sha256(frame).hexdigest() != stage["frame_sha256"]:
        raise SystemExit("FAIL: P13b AX.25 frame SHA256 no longer matches staging")

    selectors = frame_to_selectors(
        frame,
        pre_flags=stage["pre_flags"],
        post_flags=stage["post_flags"],
        initial_tone=MARK,
    )
    packed = pack_selectors(selectors)
    if len(selectors) != stage["selector_count"]:
        raise SystemExit("FAIL: P13b selector count changed")
    if len(packed) != stage["packed_selector_bytes"]:
        raise SystemExit("FAIL: P13b packed selector length changed")
    if hashlib.sha256(packed).hexdigest() != stage["packed_selector_sha256"]:
        raise SystemExit("FAIL: P13b packed selector SHA256 changed")
    return frame, packed


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


def counter_delta(before: int, after: int, modulus: int) -> int:
    return (int(after) - int(before)) % modulus


def print_plan(*, target_id: str, device: str, expected_identity: str, stage: dict) -> None:
    print("=== YWD-1278 0B-P13b GUARDED SINGLE RF TX ===")
    print(f"Target                    : {target_id}")
    print(f"Device                    : {device}")
    print(f"Packet identity           : {expected_identity}")
    print(f"TX frequency              : {stage['transmit_frequency_hz']} Hz")
    print("RF power byte             : 1/255 (frozen simplex SET_FREQ profile)")
    print(f"Known packet              : {stage['source']}>{stage['destination']}:{stage['information_text']}")
    print(f"AX.25 frame bytes         : {stage['frame_bytes']}")
    print(f"AX.25 frame SHA256        : {stage['frame_sha256']}")
    print(f"Bell-202 selectors        : {stage['selector_count']}")
    print(f"Packed selector bytes     : {stage['packed_selector_bytes']}")
    print(f"Packed selector SHA256    : {stage['packed_selector_sha256']}")
    print(f"Nominal burst             : {stage['selector_count'] / 1200.0:.4f} s")
    print(f"Expected generated samples: {stage['expected_generated_samples_delta']}")
    print("Maximum TX submissions    : 1")
    print("Automatic TX retry        : NO")
    print("KISS-originated TX        : DISCONNECTED")
    print("Persistent product TX     : DISABLED")
    print("Firmware flash            : NO")
    print("GPIO/reset                : NO")
    print("Option-byte write         : NO")
    print("Independent decode        : REQUIRED")


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 0B-P13b guarded single TX qualification")
    ap.add_argument("--targets", default=str(ROOT / "firmware" / "targets.json"))
    ap.add_argument(
        "--staging",
        default=str(ROOT / "firmware" / "qualification" / "p13b-single-tx.json"),
    )
    ap.add_argument("--target", required=True)
    ap.add_argument("--device", default="/dev/ttyAMA0")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()

    target = load_target(Path(args.targets), args.target)
    stage = load_staging(Path(args.staging), args.target)
    frame, _packed = build_known_frame(stage)
    expected_identity = target["packet_firmware_candidate"]["expected_identity"]

    print_plan(
        target_id=args.target,
        device=args.device,
        expected_identity=expected_identity,
        stage=stage,
    )
    print(f"FRAME_HEX={frame.hex()}")

    if not args.transmit:
        print("P13B_DRY_RUN=PASS")
        print("HARDWARE_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if args.confirm != P13B_CONFIRMATION_TOKEN:
        raise SystemExit(
            "FAIL: physical TX requires exact confirmation token "
            f"--confirm {P13B_CONFIRMATION_TOKEN}"
        )
    if not uart_is_free(args.device):
        raise SystemExit(f"FAIL: modem UART already has an owner: {args.device}")

    owner = TXModemOwner(
        posix_serial_transport_factory(args.device),
        queue_capacity=4,
        submit_timeout=0.20,
        default_transaction_timeout=1.50,
    )
    broker = None
    receipt = None
    diag_before = None
    diag_armed = None
    diag_after = None
    status_before = None
    status_after = None
    transmit_submissions = 0

    try:
        owner.start(timeout=2.0)
        version = owner.get_version(timeout=1.5)
        if version.identity != expected_identity:
            raise RuntimeError(
                "running firmware identity is not the exact qualified packet image: "
                f"{version.identity!r}"
            )

        status_before = owner.rf_status(timeout=1.5)
        diag_before = owner.rf_diagnostics(timeout=1.5)
        if status_before.remaining_selectors != 0 or diag_before.tx_active != 0:
            raise RuntimeError("modem is not idle before P13b setup")

        # This frozen helper writes the requested simplex frequency into both
        # RX and TX fields and uses the already-qualified minimum power byte 1.
        owner.set_rx_frequency(P13B_FREQUENCY_HZ, timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)

        armed_status = owner.rf_status(timeout=1.5)
        diag_armed = owner.rf_diagnostics(timeout=1.5)
        if armed_status.remaining_selectors != 0 or diag_armed.tx_active != 0:
            raise RuntimeError("modem became TX-busy while arming P13b")
        if diag_armed.keyups != diag_before.keyups:
            raise RuntimeError("RF keyup counter changed before the one permitted TX submission")
        if diag_armed.generated_samples != diag_before.generated_samples:
            raise RuntimeError("RF generated-sample counter changed before the permitted TX submission")

        broker = TXBroker(
            owner,
            transmit_enabled=True,
            queue_capacity=1,
            submit_timeout=0.05,
            default_transaction_timeout=1.5,
            thread_name="ywd1278-p13b-one-shot",
        )
        broker.start()

        # THE ONLY TRANSMIT SUBMISSION IN THIS HARNESS.  Never retry this call.
        transmit_submissions += 1
        receipt = broker.submit_frame(frame, timeout=1.5)
        broker.stop(timeout=2.0)
        broker = None

        if receipt.selector_count != stage["selector_count"]:
            raise RuntimeError("broker receipt selector count differs from frozen P13b vector")
        if receipt.packed_selector_sha256 != stage["packed_selector_sha256"]:
            raise RuntimeError("broker receipt selector SHA256 differs from frozen P13b vector")

        # Give the known 0.6275 s burst time to complete before polling.  All
        # subsequent modem operations are read-only status/diagnostic queries.
        time.sleep(receipt.nominal_duration_seconds + 0.10)
        deadline = time.monotonic() + COMPLETION_TIMEOUT_SECONDS
        while True:
            status_after = owner.rf_status(timeout=1.5)
            diag_after = owner.rf_diagnostics(timeout=1.5)
            if status_after.remaining_selectors == 0 and diag_after.tx_active == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("timed out waiting for the one P13b selector burst to finish")
            time.sleep(0.05)

        keyup_delta = counter_delta(diag_before.keyups, diag_after.keyups, 1 << 8)
        generated_delta = counter_delta(
            diag_before.generated_samples,
            diag_after.generated_samples,
            1 << 16,
        )
        if keyup_delta != 1:
            raise RuntimeError(f"expected exactly one RF keyup; observed delta={keyup_delta}")
        if generated_delta != stage["expected_generated_samples_delta"]:
            raise RuntimeError(
                "unexpected RF generated-sample delta: "
                f"expected={stage['expected_generated_samples_delta']} actual={generated_delta}"
            )
        if transmit_submissions != 1:
            raise RuntimeError(f"unexpected P13b transmit submission count: {transmit_submissions}")

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

    if not uart_is_free(args.device):
        raise RuntimeError("modem UART still has an owner after P13b shutdown")
    if receipt is None or diag_before is None or diag_armed is None or diag_after is None:
        raise RuntimeError("P13b completed without all required internal evidence")
    if status_before is None or status_after is None:
        raise RuntimeError("P13b completed without RF status evidence")

    keyup_delta = counter_delta(diag_before.keyups, diag_after.keyups, 1 << 8)
    generated_delta = counter_delta(
        diag_before.generated_samples,
        diag_after.generated_samples,
        1 << 16,
    )

    print(f"TRANSMIT_SUBMISSIONS={transmit_submissions}")
    print(f"BROKER_FRAME_BYTES={receipt.frame_bytes}")
    print(f"BROKER_FRAME_SHA256={receipt.frame_sha256}")
    print(f"BROKER_SELECTOR_COUNT={receipt.selector_count}")
    print(f"BROKER_PACKED_SELECTOR_BYTES={receipt.packed_selector_bytes}")
    print(f"BROKER_PACKED_SELECTOR_SHA256={receipt.packed_selector_sha256}")
    print(f"RF_KEYUPS={diag_before.keyups}->{diag_after.keyups}")
    print(f"RF_KEYUP_DELTA={keyup_delta}")
    print(
        "RF_TX_GENERATED_SAMPLES="
        f"{diag_before.generated_samples}->{diag_after.generated_samples}"
    )
    print(f"RF_TX_GENERATED_SAMPLES_DELTA={generated_delta}")
    print(f"RF_STATUS_REMAINING={status_before.remaining_selectors}->{status_after.remaining_selectors}")
    print(f"RF_TX_ACTIVE={diag_before.tx_active}->{diag_after.tx_active}")
    print(
        "EXPECTED_EXTERNAL_DECODE="
        f"{stage['source']}>{stage['destination']}:{stage['information_text']}"
    )
    print("YWD1278_0B_P13B_INTERNAL_SINGLE_TX=PASS")
    print("EXACT_PACKET_FIRMWARE_IDENTITY=PASS")
    print("P13A_BOUNDED_BROKER_PATH=PASS")
    print("ONE_TX_SUBMISSION_ONLY=PASS")
    print("EXPECTED_ONE_RF_KEYUP=PASS")
    print("EXPECTED_GENERATED_SAMPLES=PASS")
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
