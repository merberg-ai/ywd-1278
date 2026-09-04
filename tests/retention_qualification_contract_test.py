#!/usr/bin/env python3
"""Frozen host qualification contract for 0D-P5 retention controls."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0d-p5-retention-host.json"
P4_PI = ROOT / "firmware" / "qualification" / "0d-p4-target-pi-sanity-2026-09-03.json"

FROZEN_BLOBS = {
    "src/ywd1278/monitor/retention.py": "1e08367d98f39e15eaeb855ef5e6e6b39eef9302",
    "src/ywd1278/monitor/mheard.py": "09a9dd17cee8eff2ef9aa3df418a3e575e1f985e",
    "src/ywd1278/monitor/sqlite_log.py": "cd43f6e284061c19bd8bade8e1449986a9f99374",
    "src/ywd1278/monitor/stream.py": "703b7e803d39d915b60d79c30c154151e3820098",
    "src/ywd1278/monitor/policy.py": "f7d105554f682dfc533a09bff8823b192e5debe9",
}


def blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["schema"] == 1
    assert evidence["phase"] == "0D-P5"
    assert evidence["stage"] == "retention-controls-host"
    assert evidence["status"] == "host-qualified"
    assert evidence["base_checkpoint"] == "checkpoint/0d-p4-mheard-host-qualified"
    assert evidence["base_checkpoint_sha"] == "d75e253003762d1077e7300da52980b1f4739963"
    assert evidence["qualified_implementation_head_sha"] == "61cd2ff68ad7b4be22185c7f50bdab6da8418c11"
    assert evidence["retention_implementation_blob_sha1"] == "1e08367d98f39e15eaeb855ef5e6e6b39eef9302"

    policy = evidence["policy"]
    assert policy["default_enabled"] is False
    assert policy["max_age_ns_optional"] is True
    assert policy["max_rows_optional"] is True
    assert policy["combined_semantics"] == "age-or-row-limit"
    assert policy["default_max_delete_per_run"] == 1000
    assert policy["absolute_max_delete_per_run"] == 10000

    execution = evidence["execution"]
    assert execution["plan_read_only"] is True
    assert execution["apply_explicit_only"] is True
    assert execution["automatic_scheduler"] is False
    assert execution["automatic_retry"] is False
    assert execution["transaction"] == "BEGIN IMMEDIATE"
    assert execution["oldest_eligible_first"] is True
    assert execution["busy_writer_fails_closed"] is True
    assert execution["schema_change"] is False
    assert execution["automatic_vacuum"] is False
    assert execution["automatic_wal_checkpoint"] is False

    architecture = evidence["architecture"]
    for key in (
        "packet_subscriber",
        "worker_thread",
        "additional_in_memory_queue",
        "modem_dependency",
        "tx_capability",
        "uart_access",
        "rf_access",
        "flash_gpio_option_byte_activity",
    ):
        assert architecture[key] is False, key

    integration = evidence["integration"]
    assert integration["p3_schema_version_unchanged"] == 1
    assert integration["p4_mheard_frozen"] is True
    assert integration["mheard_reflects_retained_frames"] is True
    assert integration["p4_target_pi_python_3_13_5_evidence_preserved"] is True

    assert evidence["dedicated_push_ci"] == {
        "run_id": 33823733130,
        "head_sha": "61cd2ff68ad7b4be22185c7f50bdab6da8418c11",
        "result": "success",
    }
    assert evidence["pull_request_ci"] == {
        "pull_request": 29,
        "head_sha": "61cd2ff68ad7b4be22185c7f50bdab6da8418c11",
        "workflow_runs": 18,
        "framework_run_id": 33823771799,
        "framework_result": "success",
        "p5_run_id": 33823771856,
        "p5_result": "success",
        "pending_runs": 0,
        "failed_runs": 0,
    }
    assert evidence["qualification_complete"] is True

    p4 = json.loads(P4_PI.read_text(encoding="utf-8"))
    assert p4["status"] == "supplementary-target-host-pass"
    assert p4["checkpoint_sha"] == "d75e253003762d1077e7300da52980b1f4739963"
    assert p4["python_version"] == "3.13.5"
    assert p4["uart_activity"] is False
    assert p4["rf_activity"] is False

    for path, expected in FROZEN_BLOBS.items():
        actual = blob(path)
        assert actual == expected, (path, expected, actual)

    print("YWD1278_0D_P5_HOST_QUALIFICATION=PASS")
    print("QUALIFIED_IMPLEMENTATION_HEAD=61cd2ff68ad7b4be22185c7f50bdab6da8418c11")
    print("DEDICATED_CI_RUN=33823733130_SUCCESS")
    print("FRAMEWORK_PR_CI_RUN=33823771799_SUCCESS")
    print("FULL_PR_MATRIX=18_OF_18_SUCCESS")
    print("RETENTION_IMPLEMENTATION_HASH=PASS")
    print("FROZEN_P4_MHEARD_HASH=PASS")
    print("FROZEN_P3_SQLITE_LOG_HASH=PASS")
    print("P4_TARGET_PI_PYTHON_3_13_5_EVIDENCE=PASS")
    print("RETENTION_DEFAULT=DISABLED")
    print("RETENTION_APPLY=EXPLICIT_BOUNDED")
    print("RETENTION_TX_CAPABILITY=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
