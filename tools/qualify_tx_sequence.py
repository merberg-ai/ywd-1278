#!/usr/bin/env python3
"""0B-P13b-R1 guarded three-packet external-decode assist sequence.

This harness exists only because the first P13b one-shot test produced exact
internal RF counters but could not be independently decoded in time.  It sends
three fixed, uniquely labelled AX.25 UI packets on the already-qualified local
packet frequency, with a fixed five-second pause between bursts.

There is no user-selectable target, device, frequency, payload, serializer
profile, transmit count, or pause interval.  There is no automatic retry.  If
any broker submission or internal RF proof fails, the sequence stops and must
not silently repeat the failed burst.  KISS/product TX remains disconnected.
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

TARGET_ID = "mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021"
DEVICE = "/dev/ttyAMA0"
P13B_FREQUENCY_HZ = 145050000
P13B_R1_CONFIRMATION_TOKEN = "P13B-R1-145050-VERIFY-3"
TARGETS_PATH = ROOT / "firmware" / "targets.json"
STAGING_PATH = ROOT / "firmware" / "qualification" / "p13b-r1-three-tx.json"
COMPLETION_TIMEOUT_SECONDS = 5.0


def load_target() -> dict:
    data = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    matches = [item for item in data.get("targets", []) if item.get("id") == TARGET_ID]
    if len(matches) != 1:
        raise SystemExit(f"FAIL: target not found exactly once: {TARGET_ID}")
    target = matches[0]

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
    if p12b.get("option_bytes_written") is not False:
        raise SystemExit("FAIL: P12b evidence unexpectedly contains option-byte writes")

    packet = target.get("packet_firmware_candidate") or {}
    if packet.get("status") != "deterministic-build-and-runtime-qualified":
        raise SystemExit("FAIL: exact packet firmware candidate is not qualified")
    if not packet.get("expected_identity"):
        raise SystemExit("FAIL: packet firmware expected identity is missing")
    return target


def load_staging() -> dict:
    stage = json.loads(STAGING_PATH.read_text(encoding="utf-8"))
    if stage.get("phase") != "0B-P13b-R1" or stage.get("status") != "staged":
        raise SystemExit("FAIL: P13b-R1 staging state is not exact")
    if stage.get("purpose") != "external-decode-assist":
        raise SystemExit("FAIL: P13b-R1 staging purpose changed")
    if stage.get("target_id") != TARGET_ID:
        raise SystemExit("FAIL: P13b-R1 target changed")
    if stage.get("transmit_frequency_hz") != P13B_FREQUENCY_HZ:
        raise SystemExit("FAIL: P13b-R1 frequency changed")
    if stage.get("source") != "KJ6YWD-10" or stage.get("destination") != "YWD13B":
        raise SystemExit("FAIL: P13b-R1 fixed AX.25 addresses changed")
    if stage.get("pre_flags") != 45 or stage.get("post_flags") != 3:
        raise SystemExit("FAIL: P13b-R1 frozen P5 flag profile changed")
    if stage.get("initial_tone") != "MARK":
        raise SystemExit("FAIL: P13b-R1 initial tone changed")
    if stage.get("samples_per_selector") != 16:
        raise SystemExit("FAIL: P13b-R1 samples-per-selector changed")
    if stage.get("inter_packet_pause_seconds") != 5.0:
        raise SystemExit("FAIL: P13b-R1 inter-packet pause changed")
    if stage.get("maximum_transmissions") != 3:
        raise SystemExit("FAIL: P13b-R1 transmit bound changed")
    if stage.get("retry_transmit_on_failure") is not False:
        raise SystemExit("FAIL: P13b-R1 permits automatic TX retry")
    if stage.get("expected_keyup_delta") != 3:
        raise SystemExit("FAIL: P13b-R1 expected keyup delta changed")
    if stage.get("expected_generated_samples_delta") != 34608:
        raise SystemExit("FAIL: P13b-R1 expected generated-sample total changed")
    if stage.get("confirmation_token") != P13B_R1_CONFIRMATION_TOKEN:
        raise SystemExit("FAIL: P13b-R1 confirmation token changed")
    if stage.get("kiss_tx_connected") is not False or stage.get("product_tx_enabled") is not False:
        raise SystemExit("FAIL: P13b-R1 ordinary TX path became enabled")
    if stage.get("flash_permitted") is not False:
        raise SystemExit("FAIL: P13b-R1 permits flash")
    if stage.get("gpio_reset_permitted") is not False:
        raise SystemExit("FAIL: P13b-R1 permits GPIO/reset")
    if stage.get("option_bytes_permitted") is not False:
        raise SystemExit("FAIL: P13b-R1 permits option-byte writes")

    frames = stage.get("frames")
    if not isinstance(frames, list) or len(frames) != 3:
        raise SystemExit("FAIL: P13b-R1 must contain exactly three fixed frames")
    return stage


def build_vectors(stage: dict) -> list[tuple[dict, bytes]]:
    vectors: list[tuple[dict, bytes]] = []
    expected_texts = [
        "YWD-1278 P13B VERIFY 1/3",
        "YWD-1278 P13B VERIFY 2/3",
        "YWD-1278 P13B VERIFY 3/3",
    ]
    for index, vector in enumerate(stage["frames"], start=1):
        if vector.get("sequence") != index:
            raise SystemExit(f"FAIL: P13b-R1 sequence marker changed at frame {index}")
        if vector.get("information_text") != expected_texts[index - 1]:
            raise SystemExit(f"FAIL: P13b-R1 information text changed at frame {index}")
        frame = build_ui_frame(
            source=Address.parse(stage["source"]),
            destination=Address.parse(stage["destination"]),
            info=vector["information_text"].encode("ascii"),
            include_fcs=True,
        )
        if not verify_fcs(frame):
            raise SystemExit(f"FAIL: locally constructed P13b-R1 frame {index} has invalid FCS")
        if len(frame) != vector["frame_bytes"] or frame.hex() != vector["frame_hex"]:
            raise SystemExit(f"FAIL: P13b-R1 frame {index} no longer matches frozen vector")
        if hashlib.sha256(frame).hexdigest() != vector["frame_sha256"]:
            raise SystemExit(f"FAIL: P13b-R1 frame {index} SHA256 changed")

        selectors = frame_to_selectors(
            frame,
            pre_flags=stage["pre_flags"],
            post_flags=stage["post_flags"],
            initial_tone=MARK,
        )
        packed = pack_selectors(selectors)
        if len(selectors) != vector["selector_count"]:
            raise SystemExit(f"FAIL: P13b-R1 selector count changed at frame {index}")
        if len(packed) != vector["packed_selector_bytes"]:
            raise SystemExit(f"FAIL: P13b-R1 packed selector length changed at frame {index}")
        if hashlib.sha256(packed).hexdigest() != vector["packed_selector_sha256"]:
            raise SystemExit(f"FAIL: P13b-R1 packed selector SHA256 changed at frame {index}")
        if len(selectors) * stage["samples_per_selector"] != vector["expected_generated_samples"]:
            raise SystemExit(f"FAIL: P13b-R1 generated-sample expectation changed at frame {index}")
        vectors.append((vector, frame))
    return vectors


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


def counter_delta(before: int, after: int, modulus: int) -> int:
    return (int(after) - int(before)) % modulus


def wait_for_idle(owner: TXModemOwner, nominal_duration: float) -> tuple[object, object]:
    time.sleep(nominal_duration + 0.10)
    deadline = time.monotonic() + COMPLETION_TIMEOUT_SECONDS
    while True:
        status = owner.rf_status(timeout=1.5)
        diag = owner.rf_diagnostics(timeout=1.5)
        if status.remaining_selectors == 0 and diag.tx_active == 0:
            return status, diag
        if time.monotonic() >= deadline:
            raise RuntimeError("timed out waiting for P13b-R1 selector burst to finish")
        time.sleep(0.05)


def print_plan(stage: dict, expected_identity: str, vectors: list[tuple[dict, bytes]]) -> None:
    print("=== YWD-1278 0B-P13b-R1 GUARDED THREE-PACKET RF VERIFY ===")
    print(f"Target                    : {TARGET_ID}")
    print(f"Device                    : {DEVICE}")
    print(f"Packet identity           : {expected_identity}")
    print(f"TX frequency              : {P13B_FREQUENCY_HZ} Hz")
    print("RF power byte             : 1/255 (frozen simplex SET_FREQ profile)")
    print(f"Inter-packet pause        : {stage['inter_packet_pause_seconds']:.1f} s")
    print("Maximum TX submissions    : 3")
    print("Automatic TX retry        : NO")
    print("KISS-originated TX        : DISCONNECTED")
    print("Persistent product TX     : DISABLED")
    print("Firmware flash            : NO")
    print("GPIO/reset                : NO")
    print("Option-byte write         : NO")
    print("Independent decode        : REQUIRED (minimum one exact frame)")
    for vector, frame in vectors:
        seq = vector["sequence"]
        print(
            f"Known packet {seq}/3          : "
            f"{stage['source']}>{stage['destination']}:{vector['information_text']}"
        )
        print(f"Frame {seq} bytes/hash      : {len(frame)} / {vector['frame_sha256']}")
        print(
            f"Frame {seq} selectors/hash  : {vector['selector_count']} / "
            f"{vector['packed_selector_sha256']}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 0B-P13b-R1 guarded three-packet verification")
    ap.add_argument("--transmit", action="store_true")
    ap.add_argument("--confirm", default="")
    args = ap.parse_args()

    target = load_target()
    stage = load_staging()
    vectors = build_vectors(stage)
    expected_identity = target["packet_firmware_candidate"]["expected_identity"]

    print_plan(stage, expected_identity, vectors)
    for vector, frame in vectors:
        print(f"FRAME_HEX[{vector['sequence']}]={frame.hex()}")

    if not args.transmit:
        print("P13B_R1_DRY_RUN=PASS")
        print("HARDWARE_UART_OPENED=NO")
        print("RF_TRANSMITTED=NO")
        return 0

    if args.confirm != P13B_R1_CONFIRMATION_TOKEN:
        raise SystemExit(
            "FAIL: physical TX requires exact confirmation token "
            f"--confirm {P13B_R1_CONFIRMATION_TOKEN}"
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
    diag_before = None
    diag_after = None
    status_before = None
    status_after = None
    transmit_submissions = 0
    receipts = []
    per_burst_evidence = []

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
            raise RuntimeError("modem is not idle before P13b-R1 setup")

        owner.set_rx_frequency(P13B_FREQUENCY_HZ, timeout=1.5)
        owner.arm_rx_modem_io(timeout=1.5)

        armed_status = owner.rf_status(timeout=1.5)
        armed_diag = owner.rf_diagnostics(timeout=1.5)
        if armed_status.remaining_selectors != 0 or armed_diag.tx_active != 0:
            raise RuntimeError("modem became TX-busy while arming P13b-R1")
        if armed_diag.keyups != diag_before.keyups:
            raise RuntimeError("RF keyup counter changed before the first permitted R1 TX")
        if armed_diag.generated_samples != diag_before.generated_samples:
            raise RuntimeError("RF generated-sample counter changed before the first permitted R1 TX")

        broker = TXBroker(
            owner,
            transmit_enabled=True,
            queue_capacity=1,
            submit_timeout=0.05,
            default_transaction_timeout=1.5,
            thread_name="ywd1278-p13b-r1-verify3",
        )
        broker.start()

        previous_diag = armed_diag
        for index, (vector, frame) in enumerate(vectors, start=1):
            pre_status = owner.rf_status(timeout=1.5)
            pre_diag = owner.rf_diagnostics(timeout=1.5)
            if pre_status.remaining_selectors != 0 or pre_diag.tx_active != 0:
                raise RuntimeError(f"modem is not idle before P13b-R1 burst {index}")
            if pre_diag.keyups != previous_diag.keyups:
                raise RuntimeError(f"unexpected RF keyup activity before P13b-R1 burst {index}")
            if pre_diag.generated_samples != previous_diag.generated_samples:
                raise RuntimeError(f"unexpected generated-sample activity before P13b-R1 burst {index}")

            # One submission per fixed vector.  Never retry a failed call.
            transmit_submissions += 1
            receipt = broker.submit_frame(frame, timeout=1.5)
            receipts.append(receipt)
            if receipt.selector_count != vector["selector_count"]:
                raise RuntimeError(f"broker selector count differs for P13b-R1 burst {index}")
            if receipt.packed_selector_sha256 != vector["packed_selector_sha256"]:
                raise RuntimeError(f"broker selector SHA256 differs for P13b-R1 burst {index}")

            post_status, post_diag = wait_for_idle(owner, receipt.nominal_duration_seconds)
            burst_keyups = counter_delta(pre_diag.keyups, post_diag.keyups, 1 << 8)
            burst_samples = counter_delta(
                pre_diag.generated_samples,
                post_diag.generated_samples,
                1 << 16,
            )
            if burst_keyups != 1:
                raise RuntimeError(
                    f"expected one RF keyup for P13b-R1 burst {index}; observed delta={burst_keyups}"
                )
            if burst_samples != vector["expected_generated_samples"]:
                raise RuntimeError(
                    f"unexpected generated samples for P13b-R1 burst {index}: "
                    f"expected={vector['expected_generated_samples']} actual={burst_samples}"
                )
            per_burst_evidence.append((pre_diag, post_diag, post_status, burst_keyups, burst_samples))
            previous_diag = post_diag

            print(f"BURST[{index}]_TX=COMPLETE")
            print(f"BURST[{index}]_RF_KEYUP_DELTA={burst_keyups}")
            print(f"BURST[{index}]_GENERATED_SAMPLES_DELTA={burst_samples}")
            print(
                f"EXPECTED_EXTERNAL_DECODE[{index}]="
                f"{stage['source']}>{stage['destination']}:{vector['information_text']}"
            )

            if index < len(vectors):
                print(f"PAUSE_AFTER[{index}]={stage['inter_packet_pause_seconds']:.1f}s")
                time.sleep(stage["inter_packet_pause_seconds"])

        broker.stop(timeout=2.0)
        broker = None
        status_after = owner.rf_status(timeout=1.5)
        diag_after = owner.rf_diagnostics(timeout=1.5)
        if status_after.remaining_selectors != 0 or diag_after.tx_active != 0:
            raise RuntimeError("modem not idle after the final P13b-R1 burst")

        keyup_delta = counter_delta(diag_before.keyups, diag_after.keyups, 1 << 8)
        generated_delta = counter_delta(
            diag_before.generated_samples,
            diag_after.generated_samples,
            1 << 16,
        )
        if transmit_submissions != stage["maximum_transmissions"]:
            raise RuntimeError(
                f"unexpected P13b-R1 submission count: {transmit_submissions}"
            )
        if keyup_delta != stage["expected_keyup_delta"]:
            raise RuntimeError(
                f"unexpected total RF keyup delta: expected={stage['expected_keyup_delta']} actual={keyup_delta}"
            )
        if generated_delta != stage["expected_generated_samples_delta"]:
            raise RuntimeError(
                "unexpected total generated-sample delta: "
                f"expected={stage['expected_generated_samples_delta']} actual={generated_delta}"
            )

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
        raise RuntimeError("modem UART still has an owner after P13b-R1 shutdown")
    if diag_before is None or diag_after is None or status_before is None or status_after is None:
        raise RuntimeError("P13b-R1 completed without required aggregate evidence")
    if len(receipts) != 3 or len(per_burst_evidence) != 3:
        raise RuntimeError("P13b-R1 completed without all three fixed burst records")

    keyup_delta = counter_delta(diag_before.keyups, diag_after.keyups, 1 << 8)
    generated_delta = counter_delta(
        diag_before.generated_samples,
        diag_after.generated_samples,
        1 << 16,
    )

    print(f"TRANSMIT_SUBMISSIONS={transmit_submissions}")
    print(f"RF_KEYUPS={diag_before.keyups}->{diag_after.keyups}")
    print(f"RF_KEYUP_DELTA={keyup_delta}")
    print(
        "RF_TX_GENERATED_SAMPLES="
        f"{diag_before.generated_samples}->{diag_after.generated_samples}"
    )
    print(f"RF_TX_GENERATED_SAMPLES_DELTA={generated_delta}")
    print(f"RF_STATUS_REMAINING={status_before.remaining_selectors}->{status_after.remaining_selectors}")
    print(f"RF_TX_ACTIVE={diag_before.tx_active}->{diag_after.tx_active}")
    print("YWD1278_0B_P13B_R1_INTERNAL_THREE_TX=PASS")
    print("EXACT_PACKET_FIRMWARE_IDENTITY=PASS")
    print("P13A_BOUNDED_BROKER_PATH=PASS")
    print("FIXED_THREE_TX_SUBMISSIONS=PASS")
    print("EXPECTED_THREE_RF_KEYUPS=PASS")
    print("EXPECTED_GENERATED_SAMPLES=PASS")
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
