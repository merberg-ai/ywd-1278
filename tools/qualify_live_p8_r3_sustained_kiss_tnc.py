#!/usr/bin/env python3
"""Guarded 0C-P8 R3 sustained KISS physical qualification.

R3 follows the physically useful R2 run but repairs one qualification-only
classifier defect: RF-heard qualification frames must be excluded semantically,
not by raw AX.25 body equality. AX.25 destination/source C bits and repeater H
bits may legitimately differ after a frame is heard over RF, while the frame is
still the same qualification packet.

R3 therefore compares decoded callsign/SSID identities, normalized path,
UI/PID, and information payload while deliberately ignoring Address.flag.
Everything below that gate remains the R1-qualified sustained scheduler and the
same preserved P8 KISS/CSMA/half-duplex physical graph.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import qualify_live_p8_sustained_kiss_tnc as base  # noqa: E402
import qualify_live_p8_r2_sustained_kiss_tnc as r2  # noqa: E402


R3_STAGE_PATH = ROOT / "firmware" / "qualification" / "0c-p8-r3-live-sustained-kiss-tnc.json"
R2_EVIDENCE_PATH = ROOT / "firmware" / "qualification" / "0c-p8-r2-live-physical-evidence.json"
R3_CONFIRMATION_TOKEN = "P8-R3-LIVE-145050-P200-SUSTAINED-3"
R3_INTERACTIVE_CONFIRMATION = "TRANSMIT-P8-R3-SUSTAINED-KISS-THREE"
R1_TNC_RUNTIME_BLOB = "f1a74ae44824bafc2b89c09e77fa416ac26bb4f1"
R1_CHECKPOINT = "checkpoint/0c-p8-sustained-kiss-tnc-r1-host-qualified"
R1_CHECKPOINT_SHA = "e8d104b2c6a295219e34733d2541f89ee90318f3"


def git_blob(path: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", path], cwd=ROOT, text=True
    ).strip()


def _address_key(address: base.Address) -> tuple[str, int]:
    """Return AX.25 identity while intentionally discarding C/H flag state."""

    return (address.callsign, int(address.ssid))


def semantic_frame_key(body_no_fcs: bytes) -> tuple:
    """Normalize the qualification-relevant semantics of one AX.25 body."""

    parsed = base.parse_ax25_frame(bytes(body_no_fcs), has_fcs=False)
    return (
        _address_key(parsed["destination"]),
        _address_key(parsed["source"]),
        tuple(_address_key(item) for item in parsed["path"]),
        parsed["frame_type"],
        parsed["pid"],
        bytes(parsed["info"]),
    )


def semantic_is_qualification_body(
    body_no_fcs: bytes,
    locked_bodies: tuple[bytes, ...],
) -> bool:
    """Recognize qualification echoes/repeats despite AX.25 C/H-bit changes."""

    try:
        observed = semantic_frame_key(body_no_fcs)
    except (TypeError, ValueError):
        return False

    for locked in locked_bodies:
        try:
            if observed == semantic_frame_key(locked):
                return True
        except (TypeError, ValueError):
            raise RuntimeError("locked P8-R3 qualification body is not valid AX.25")
    return False


def load_r3_stage() -> dict:
    stage = json.loads(R3_STAGE_PATH.read_text(encoding="utf-8"))
    evidence = json.loads(R2_EVIDENCE_PATH.read_text(encoding="utf-8"))

    required = {
        "schema": 1,
        "phase": "0C-P8-R3-live",
        "stage": "sustained-kiss-three-cycle-r3",
        "status": "staged",
        "base_checkpoint": R1_CHECKPOINT,
        "base_checkpoint_sha": R1_CHECKPOINT_SHA,
        "supersedes_physical_stage": "0C-P8-R2-live",
        "r2_execution_head_sha": "69eaec38efe6d3ab1f97c1f09d082e04a632567c",
        "r2_accepted_tx": 3,
        "r2_external_direct_decodes": 3,
        "r2_rerun_permitted": False,
        "semantic_self_echo_filter_required": True,
        "semantic_echo_ignores_address_ch_flags": True,
        "semantic_echo_matches_source_callsign_ssid": True,
        "semantic_echo_matches_destination_callsign_ssid": True,
        "semantic_echo_matches_path_callsign_ssid": True,
        "semantic_echo_matches_frame_type_pid_info": True,
        "target_id": base.p4d_r1.TARGET_ID,
        "device": base.p4d_r1.DEVICE,
        "expected_identity": (
            "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz "
            "ADF7021 FW based on CA6JAU GitID #7ff74ed"
        ),
        "frequency_hz": 145050000,
        "rf_power": 200,
        "packet_count": 3,
        "source": "KJ6YWD-10",
        "destination": "YWD8",
        "path": ["YWDNOD"],
        "kiss_listener_host": "127.0.0.1",
        "kiss_listener_port": 0,
        "kiss_listener_ephemeral": True,
        "kiss_client_sessions_required": 2,
        "kiss_client_reconnect_required": True,
        "kiss_data_payload_includes_fcs": False,
        "tnc_appends_fcs_exactly_once": True,
        "kiss_port": 0,
        "parameter_generations": [3, 4, 5],
        "persist": 63,
        "slottime": 10,
        "fullduplex": 0,
        "txdelay_sequence": [30, 50, 30],
        "request_timeout_seconds": 30.0,
        "downstream_timeout_seconds": 1.5,
        "rssi_poll_nominal_seconds": 0.05,
        "rx_status_interval_seconds": 0.25,
        "rx_read_maximum": 200,
        "rx_fifo_drain_read_limit": 4,
        "rx_fifo_drain_maximum_bytes_per_pass": 800,
        "rx_fifo_zero_length_read_required": False,
        "busy_assert_raw_maximum": 83,
        "clear_release_raw_minimum": 90,
        "recent_rx_hold_seconds": 0.25,
        "requires_live_busy_before_each_dispatch": True,
        "requires_fresh_non_qualification_fcs_valid_rx_before_each_tx": True,
        "minimum_full_slot_seconds": 0.1,
        "requires_rx_fifo_drained_before_tx_access": True,
        "requires_rx_active_after_each_tx": True,
        "rx_fifo_dropped_bytes_required": 0,
        "requires_final_queue_empty_fcs_valid_rx": True,
        "requires_final_queue_empty_kiss_delivery": True,
        "final_receive_timeout_seconds": 60.0,
        "required_non_qualification_inbound_frames": 4,
        "qualification_echo_must_not_count_as_rx_proof": True,
        "maximum_transmit_submissions": 3,
        "automatic_tx_retry": False,
        "health_checked_while_waiting_for_dispatch": True,
        "timeout_diagnostics_include_guard_runtime_queue": True,
        "live_rx_decode_visibility_required": True,
        "requires_direct_external_decode": True,
        "required_external_tx_decodes": 3,
        "require_ywdnod_repeated_decode": False,
        "confirmation_token": R3_CONFIRMATION_TOKEN,
        "interactive_phrase": R3_INTERACTIVE_CONFIRMATION,
        "product_tx_enabled": False,
        "daemon_tx_enabled": False,
        "systemd_tx_enabled": False,
        "flash_permitted": False,
        "gpio_reset_permitted": False,
        "option_bytes_permitted": False,
    }
    for key, expected in required.items():
        actual = stage.get(key)
        if actual != expected:
            raise SystemExit(
                f"FAIL: P8-R3 staging mismatch for {key}: expected={expected!r} actual={actual!r}"
            )

    if stage.get("qualification_randomness") != {
        "before_fresh_decoded_busy_trigger": 255,
        "after_fresh_decoded_busy_trigger": [255, 0],
    }:
        raise SystemExit("FAIL: P8-R3 qualification randomness changed")
    if len(stage.get("frames", [])) != 3:
        raise SystemExit("FAIL: P8-R3 requires exactly three locked frame vectors")

    if evidence.get("status") != "invalidated-self-echo-gate":
        raise SystemExit("FAIL: R2 invalidated evidence record changed")
    if evidence.get("r2_accepted_tx") != 3:
        raise SystemExit("FAIL: R2 accepted-TX evidence changed")
    if evidence.get("rerun_same_stage_permitted") is not False:
        raise SystemExit("FAIL: R2 must remain non-rerunnable")

    actual_blob = git_blob("src/ywd1278/service/tnc_runtime.py")
    if actual_blob != R1_TNC_RUNTIME_BLOB:
        raise SystemExit(
            "FAIL: P8-R3 corrected sustained runtime blob mismatch: "
            f"expected={R1_TNC_RUNTIME_BLOB} actual={actual_blob}"
        )

    # Reuse the original vector builder so body/FCS/selector/sample locks remain
    # verified by the same physical serialization code.
    base.build_vectors(stage)
    return stage


def install_r3_overrides() -> None:
    base.CONFIRMATION_TOKEN = R3_CONFIRMATION_TOKEN
    base.INTERACTIVE_CONFIRMATION = R3_INTERACTIVE_CONFIRMATION
    base.load_stage = load_r3_stage
    base.QualificationBackend = r2.DiagnosticQualificationBackend
    base.verify_cycle = r2.health_aware_verify_cycle
    base.is_qualification_body = semantic_is_qualification_body


def main() -> int:
    install_r3_overrides()
    print("P8_R3_HARNESS=ACTIVE", flush=True)
    print(f"P8_R3_BASE_CHECKPOINT={R1_CHECKPOINT}", flush=True)
    print(f"P8_R3_BASE_SHA={R1_CHECKPOINT_SHA}", flush=True)
    print("P8_R3_R2_ACCEPTED_TX=3", flush=True)
    print("P8_R3_R2_RERUN=FORBIDDEN", flush=True)
    print("P8_R3_SELF_ECHO_CLASSIFIER=SEMANTIC_AX25", flush=True)
    print("P8_R3_ADDRESS_CH_FLAGS=IGNORED_FOR_ECHO_IDENTITY", flush=True)
    print("P8_R3_LIVE_RX_DIAGNOSTICS=ENABLED", flush=True)
    rc = base.main()
    if rc == 0:
        print("P8_R3_WRAPPER_RESULT=PASS", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
