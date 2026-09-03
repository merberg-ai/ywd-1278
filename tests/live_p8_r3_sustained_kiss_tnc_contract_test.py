#!/usr/bin/env python3
"""Static/dry-run contract for guarded 0C-P8 R3 physical qualification."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools" / "qualify_live_p8_r3_sustained_kiss_tnc.py"
R2_WRAPPER = ROOT / "tools" / "qualify_live_p8_r2_sustained_kiss_tnc.py"
R3_MANIFEST = ROOT / "firmware" / "qualification" / "0c-p8-r3-live-sustained-kiss-tnc.json"
R2_MANIFEST = ROOT / "firmware" / "qualification" / "0c-p8-r2-live-sustained-kiss-tnc.json"
R2_EVIDENCE = ROOT / "firmware" / "qualification" / "0c-p8-r2-live-physical-evidence.json"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    r3 = json.loads(R3_MANIFEST.read_text(encoding="utf-8"))
    r2 = json.loads(R2_MANIFEST.read_text(encoding="utf-8"))
    evidence = json.loads(R2_EVIDENCE.read_text(encoding="utf-8"))
    wrapper = WRAPPER.read_text(encoding="utf-8")

    assert r2["status"] == "invalidated-self-echo-gate"
    assert r2["runnable"] is False
    assert r2["r2_accepted_tx"] == 3
    assert r2["r2_rerun_permitted"] is False
    assert r2["superseded_by"] == "0C-P8-R3-live"
    assert evidence["qualification_complete"] is False
    assert evidence["external_direct_decode_observed"] == 3

    assert r3["schema"] == 1
    assert r3["phase"] == "0C-P8-R3-live"
    assert r3["stage"] == "sustained-kiss-three-cycle-r3"
    assert r3["status"] == "staged"
    assert r3["base_checkpoint"] == "checkpoint/0c-p8-sustained-kiss-tnc-r1-host-qualified"
    assert r3["base_checkpoint_sha"] == "e8d104b2c6a295219e34733d2541f89ee90318f3"
    assert r3["supersedes_physical_stage"] == "0C-P8-R2-live"
    assert r3["r2_execution_head_sha"] == "69eaec38efe6d3ab1f97c1f09d082e04a632567c"
    assert r3["r2_accepted_tx"] == 3
    assert r3["r2_external_direct_decodes"] == 3
    assert r3["r2_rerun_permitted"] is False
    assert r3["semantic_self_echo_filter_required"] is True
    assert r3["semantic_echo_ignores_address_ch_flags"] is True
    assert r3["semantic_echo_matches_source_callsign_ssid"] is True
    assert r3["semantic_echo_matches_destination_callsign_ssid"] is True
    assert r3["semantic_echo_matches_path_callsign_ssid"] is True
    assert r3["semantic_echo_matches_frame_type_pid_info"] is True
    assert r3["frequency_hz"] == 145050000
    assert r3["rf_power"] == 200
    assert r3["packet_count"] == 3
    assert r3["txdelay_sequence"] == [30, 50, 30]
    assert r3["persist"] == 63
    assert r3["slottime"] == 10
    assert r3["rx_fifo_drain_read_limit"] == 4
    assert r3["rx_fifo_zero_length_read_required"] is False
    assert r3["qualification_echo_must_not_count_as_rx_proof"] is True
    assert r3["automatic_tx_retry"] is False
    assert r3["maximum_transmit_submissions"] == 3
    assert r3["confirmation_token"] == "P8-R3-LIVE-145050-P200-SUSTAINED-3"
    assert r3["interactive_phrase"] == "TRANSMIT-P8-R3-SUSTAINED-KISS-THREE"
    assert [x["information_text"] for x in r3["frames"]] == [
        "YWD-1278 P8 R3 SUSTAINED 1/3",
        "YWD-1278 P8 R3 SUSTAINED 2/3",
        "YWD-1278 P8 R3 SUSTAINED 3/3",
    ]
    assert [x["expected_generated_samples"] for x in r3["frames"]] == [12960, 16784, 12944]
    assert r3["product_tx_enabled"] is False
    assert r3["daemon_tx_enabled"] is False
    assert r3["systemd_tx_enabled"] is False
    assert r3["flash_permitted"] is False
    assert r3["gpio_reset_permitted"] is False
    assert r3["option_bytes_permitted"] is False

    # The host-qualified scheduler stays exact; R3 changes only qualification
    # staging/classification around the preserved graph.
    assert git_blob("src/ywd1278/service/tnc_runtime.py") == "f1a74ae44824bafc2b89c09e77fa416ac26bb4f1"

    for required in (
        "semantic_frame_key",
        "semantic_is_qualification_body",
        "_address_key",
        "base.is_qualification_body = semantic_is_qualification_body",
        "base.QualificationBackend = r2.DiagnosticQualificationBackend",
        "base.verify_cycle = r2.health_aware_verify_cycle",
        "P8_R3_SELF_ECHO_CLASSIFIER=SEMANTIC_AX25",
        "P8_R3_ADDRESS_CH_FLAGS=IGNORED_FOR_ECHO_IDENTITY",
        "P8_R3_R2_RERUN=FORBIDDEN",
    ):
        assert required in wrapper, required

    # No user-adjustable RF/frame/count/retry bypasses are introduced.
    assert "argparse" not in wrapper
    for forbidden in (
        "--frequency",
        "--freq",
        "--power",
        "--payload",
        "--frame",
        "--source",
        "--destination",
        "--path",
        "--count",
        "--retry",
        ".transmit_selector_burst(",
        ".transact(",
        "rf_abort(",
        "rf_exit(",
        "stm32flash",
        "RPi.GPIO",
        "/sys/class/gpio",
        "gpiozero",
        "flash.sh",
        "restore-stock",
    ):
        assert forbidden not in wrapper, forbidden

    # Superseded R2 entrypoint must remain unusable before UART access.
    old = subprocess.run(
        [sys.executable, str(R2_WRAPPER)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=15,
    )
    assert old.returncode != 0, old.stdout
    assert "P8-R2 staging mismatch for status" in old.stdout
    assert "LIVE_RUNTIME=OPEN" not in old.stdout

    # The semantic echo regression must reproduce the R2 raw-byte mismatch and
    # prove that C/H-only changes cannot arm fresh RX in R3.
    regression = subprocess.run(
        [sys.executable, str(ROOT / "tests" / "live_p8_r3_semantic_echo_filter_test.py")],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=15,
        check=True,
    )
    assert "P8_R3_SEMANTIC_ECHO_FILTER=PASS" in regression.stdout
    assert "QUALIFICATION_ECHO_ARMS_FRESH_RX=NO" in regression.stdout
    assert "GENUINE_NONQUAL_PACKET_ARMS_FRESH_RX=YES" in regression.stdout

    # R3 default invocation validates all locks and returns before UART/RF.
    dry = subprocess.run(
        [sys.executable, str(WRAPPER)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=15,
        check=True,
    )
    for token in (
        "P8_R3_HARNESS=ACTIVE",
        "P8_R3_BASE_CHECKPOINT=checkpoint/0c-p8-sustained-kiss-tnc-r1-host-qualified",
        "P8_R3_R2_ACCEPTED_TX=3",
        "P8_R3_R2_RERUN=FORBIDDEN",
        "P8_R3_SELF_ECHO_CLASSIFIER=SEMANTIC_AX25",
        "P8_R3_ADDRESS_CH_FLAGS=IGNORED_FOR_ECHO_IDENTITY",
        "P8_LIVE_SUSTAINED_KISS_DRY_RUN=PASS",
        "TX_MODEM_OWNER_CONSTRUCTED=NO",
        "KISS_LISTENER_OPENED=NO",
        "HARDWARE_UART_OPENED=NO",
        "RF_TRANSMITTED=NO",
        "P8_R3_WRAPPER_RESULT=PASS",
    ):
        assert token in dry.stdout, (token, dry.stdout)

    print("P8_R3_LIVE_SUSTAINED_KISS_CONTRACT=PASS")
    print("R2_HISTORY=INVALIDATED_FAIL_CLOSED")
    print("R2_ACCEPTED_TX=3_NO_RERUN")
    print("SEMANTIC_SELF_ECHO_FILTER=PASS")
    print("ADDRESS_CH_FLAG_MUTATION_REGRESSION=PASS")
    print("R1_CONTINUOUS_RX_DRAIN_HASH=PASS")
    print("R3_NEW_UNIQUE_VECTORS=PASS")
    print("R3_DRY_RUN_NO_UART_RF=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
