#!/usr/bin/env python3
"""Post-qualification safety contract for 0C-P8 R3 sustained KISS."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools" / "qualify_live_p8_r3_sustained_kiss_tnc.py"
R2_WRAPPER = ROOT / "tools" / "qualify_live_p8_r2_sustained_kiss_tnc.py"
R3_MANIFEST = ROOT / "firmware" / "qualification" / "0c-p8-r3-live-sustained-kiss-tnc.json"
R3_EVIDENCE = ROOT / "firmware" / "qualification" / "0c-p8-r3-live-physical-evidence.json"
R2_MANIFEST = ROOT / "firmware" / "qualification" / "0c-p8-r2-live-sustained-kiss-tnc.json"
R2_EVIDENCE = ROOT / "firmware" / "qualification" / "0c-p8-r2-live-physical-evidence.json"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    r3 = json.loads(R3_MANIFEST.read_text(encoding="utf-8"))
    r3e = json.loads(R3_EVIDENCE.read_text(encoding="utf-8"))
    r2 = json.loads(R2_MANIFEST.read_text(encoding="utf-8"))
    r2e = json.loads(R2_EVIDENCE.read_text(encoding="utf-8"))
    wrapper = WRAPPER.read_text(encoding="utf-8")

    assert r2["status"] == "invalidated-self-echo-gate"
    assert r2["runnable"] is False
    assert r2["r2_accepted_tx"] == 3
    assert r2["r2_rerun_permitted"] is False
    assert r2e["qualification_complete"] is False
    assert r2e["external_direct_decode_observed"] == 3

    assert r3["schema"] == 1
    assert r3["phase"] == "0C-P8-R3-live"
    assert r3["stage"] == "sustained-kiss-three-cycle-r3"
    assert r3["status"] == "physically-qualified"
    assert r3["runnable"] is False
    assert r3["qualification_complete"] is True
    assert r3["execution_head_sha"] == "b301e9098aedf64e4eb9adf746b93a8f7a7482ac"
    assert r3["physical_evidence"] == "firmware/qualification/0c-p8-r3-live-physical-evidence.json"
    assert r3["base_checkpoint"] == "checkpoint/0c-p8-sustained-kiss-tnc-r1-host-qualified"
    assert r3["base_checkpoint_sha"] == "e8d104b2c6a295219e34733d2541f89ee90318f3"
    assert r3["r3_accepted_tx"] == 3
    assert r3["r3_external_direct_decodes"] == 3
    assert r3["r3_rerun_permitted"] is False
    assert r3["semantic_self_echo_filter_required"] is True
    assert r3["semantic_echo_ignores_address_ch_flags"] is True
    assert r3["frequency_hz"] == 145050000
    assert r3["rf_power"] == 200
    assert r3["packet_count"] == 3
    assert r3["txdelay_sequence"] == [30, 50, 30]
    assert r3["persist"] == 63
    assert r3["slottime"] == 10
    assert r3["automatic_tx_retry"] is False
    assert r3["maximum_transmit_submissions"] == 3
    assert [x["information_text"] for x in r3["frames"]] == [
        "YWD-1278 P8 R3 SUSTAINED 1/3",
        "YWD-1278 P8 R3 SUSTAINED 2/3",
        "YWD-1278 P8 R3 SUSTAINED 3/3",
    ]
    assert [x["expected_generated_samples"] for x in r3["frames"]] == [12960, 16784, 12944]

    assert r3e["status"] == "physically-qualified"
    assert r3e["qualification_complete"] is True
    assert r3e["external_direct_decode_observed"] == 3
    assert r3e["inbound_non_p8_fcs_valid_frames"] == 4
    assert r3e["semantic_self_echo_filter"]["result"] == "pass"
    assert r3e["final_queue_empty_proof"]["qualification_echo_counted_as_non_qualification"] is False

    # R3 changed only the qualification classifier. The corrected host scheduler
    # remains the exact host-qualified R1 blob.
    assert git_blob("src/ywd1278/service/tnc_runtime.py") == "f1a74ae44824bafc2b89c09e77fa416ac26bb4f1"
    for required in (
        "semantic_frame_key",
        "semantic_is_qualification_body",
        "_address_key",
        "base.is_qualification_body = semantic_is_qualification_body",
        "P8_R3_SELF_ECHO_CLASSIFIER=SEMANTIC_AX25",
        "P8_R3_ADDRESS_CH_FLAGS=IGNORED_FOR_ECHO_IDENTITY",
    ):
        assert required in wrapper, required

    # The exact regression that reproduced R2's raw-body defect remains green.
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

    # Both stages that accepted RF are now fail-closed before LIVE_RUNTIME/UART.
    for command, marker in (
        (R2_WRAPPER, "P8-R2 staging mismatch for status"),
        (WRAPPER, "P8-R3 staging mismatch for status"),
    ):
        run = subprocess.run(
            [sys.executable, str(command)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        assert run.returncode != 0, run.stdout
        assert marker in run.stdout, run.stdout
        assert "LIVE_RUNTIME=OPEN" not in run.stdout
        assert "KISS_LISTENER=" not in run.stdout

    print("P8_R3_POST_QUALIFICATION_SAFETY=PASS")
    print("R2_HISTORY=INVALIDATED_FAIL_CLOSED")
    print("R3_PHYSICAL_QUALIFICATION=PASS")
    print("R3_ACCEPTED_TX=3_NO_RERUN")
    print("SEMANTIC_SELF_ECHO_FILTER=PASS")
    print("R1_CONTINUOUS_RX_DRAIN_HASH=PASS")
    print("R3_ENTRYPOINT=FAIL_CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
