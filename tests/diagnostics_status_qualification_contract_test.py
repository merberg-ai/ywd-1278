#!/usr/bin/env python3
"""Immutable host-qualification contract for 0D-P6 diagnostics/status."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0d-p6-diagnostics-status-host.json"
IMPLEMENTATION = "src/ywd1278/monitor/diagnostics.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> None:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    require(data["schema"] == 1, "unexpected evidence schema")
    require(data["phase"] == "0D-P6", "wrong phase")
    require(data["stage"] == "diagnostics-status-host", "wrong stage")
    require(data["status"] == "host-qualified", "P6 is not host-qualified")
    require(data["base_checkpoint"] == "checkpoint/0d-p5-retention-host-qualified", "wrong P5 base checkpoint")
    require(data["base_sha"] == "b330e52bdf5eb902135138e32d91ff6538d5cf3c", "wrong P5 base SHA")
    require(data["qualified_implementation_head"] == "0c83530d2565cff22eef9b61dc05b6fa77890d34", "wrong implementation head")

    implementation = data["implementation"]
    require(implementation["path"] == IMPLEMENTATION, "wrong diagnostics implementation path")
    require(implementation["git_blob_sha1"] == "0f23c1232b51e2f5fbd1a3d4c179e0c94ce4116a", "wrong locked diagnostics blob")
    require(git_blob(IMPLEMENTATION) == implementation["git_blob_sha1"], "diagnostics implementation changed after qualification")

    behavior = data["behavior"]
    require(behavior["snapshot_mode"] == "one-shot-read-only", "diagnostics mode changed")
    require(len(behavior["sources"]) == 11, "qualified source set changed")
    require(behavior["health_problem_markers"] == [
        "runtime-failure",
        "subscriber-drops",
        "tx-access-timeouts",
        "tx-downstream-failures",
        "sqlite-write-failures",
        "sqlite-fatal-error",
    ], "health problem markers changed")
    for key in (
        "database_mutation",
        "retention_apply",
        "sampling_thread",
        "worker_thread",
        "packet_subscriber",
        "additional_in_memory_queue",
        "modem_dependency",
        "uart_access",
        "rf_access",
        "tx_capability",
    ):
        require(behavior[key] is False, f"qualified safety boundary changed: {key}")

    require(all(value == "pass" for value in data["tests"].values()), "one or more qualification tests did not pass")

    ci = data["ci"]
    require(ci["dedicated_workflow"] == "0d-p6-diagnostics-ci", "wrong dedicated workflow")
    require(ci["dedicated_run_id"] == 33825023698, "wrong dedicated CI run")
    require(ci["dedicated_run_result"] == "success", "dedicated CI was not successful")
    require(ci["exact_head_workflow_count"] == 14, "unexpected exact-head workflow count")
    require(ci["exact_head_matrix_result"] == "14_of_14_success", "exact-head CI matrix incomplete")
    flake = ci["p3_preservation_flake"]
    require(flake["run_id"] == 33825023633, "wrong preserved rerun")
    require(flake["same_frozen_test_passed_in_dedicated_p6_run"] is True, "timing failure was not independently cleared")
    require(flake["attempt_2"] == "success", "failed P3 preservation job did not clear on rerun")
    require(flake["frozen_p8_source_changed"] is False, "frozen P8 must not be changed for CI timing")

    require(data["p5_target_pi_evidence_preserved"] is True, "P5 target-Pi evidence not preserved")
    require(data["uart_rf_activity"] == "none", "P6 host qualification must not use UART/RF")
    require(data["qualification_complete"] is True, "P6 host qualification incomplete")

    print("YWD1278_0D_P6_HOST_QUALIFICATION=PASS")
    print("QUALIFIED_IMPLEMENTATION_HEAD=0c83530d2565cff22eef9b61dc05b6fa77890d34")
    print("DEDICATED_CI_RUN=33825023698_SUCCESS")
    print("FULL_HEAD_MATRIX=14_OF_14_SUCCESS")
    print("DIAGNOSTICS_IMPLEMENTATION_HASH=PASS")
    print("P5_TARGET_PI_PYTHON_3_13_5_EVIDENCE=PASS")
    print("DIAGNOSTICS_MODE=ONE_SHOT_READ_ONLY")
    print("DIAGNOSTICS_DATABASE_WRITE_CAPABILITY=ABSENT")
    print("DIAGNOSTICS_RETENTION_APPLY_CAPABILITY=ABSENT")
    print("DIAGNOSTICS_PACKET_SUBSCRIBER=ABSENT")
    print("DIAGNOSTICS_WORKER_THREAD=ABSENT")
    print("DIAGNOSTICS_TX_CAPABILITY=ABSENT")
    print("UART_RF_ACTIVITY=NONE")


if __name__ == "__main__":
    main()
