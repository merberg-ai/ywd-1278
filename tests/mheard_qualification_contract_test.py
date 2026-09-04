#!/usr/bin/env python3
"""Frozen host qualification contract for 0D-P4 MHEARD."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0d-p4-mheard-host.json"
P3_PI = ROOT / "firmware" / "qualification" / "0d-p3-target-pi-sanity-2026-09-03.json"

FROZEN_BLOBS = {
    "src/ywd1278/monitor/mheard.py": "09a9dd17cee8eff2ef9aa3df418a3e575e1f985e",
    "tests/mheard_test.py": "f2e364068bfd79750fd5d64e518ec517aac3ba00",
    "tests/mheard_contract_test.py": "8eeb99cbf45934e0c81ce3b3f6bf31085950d82c",
    "src/ywd1278/monitor/sqlite_log.py": "cd43f6e284061c19bd8bade8e1449986a9f99374",
    "src/ywd1278/monitor/stream.py": "703b7e803d39d915b60d79c30c154151e3820098",
    "src/ywd1278/monitor/policy.py": "f7d105554f682dfc533a09bff8823b192e5debe9",
}


def blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["schema"] == 1
    assert evidence["phase"] == "0D-P4"
    assert evidence["stage"] == "mheard-read-only-host"
    assert evidence["status"] == "host-qualified"
    assert evidence["base_checkpoint"] == "checkpoint/0d-p3-sqlite-frame-log-host-qualified"
    assert evidence["base_checkpoint_sha"] == "0c6778278469ab5f1608cdc9e38d02bc0987541f"
    assert evidence["qualified_implementation_head_sha"] == "b32f070611075634507b089e9dcee86122ac5a58"
    assert evidence["mheard_blob"] == FROZEN_BLOBS["src/ywd1278/monitor/mheard.py"]
    assert evidence["mheard_test_blob"] == FROZEN_BLOBS["tests/mheard_test.py"]
    assert evidence["mheard_contract_blob"] == FROZEN_BLOBS["tests/mheard_contract_test.py"]
    assert evidence["source_database"] == "0D-P3 SQLite frames table"
    assert evidence["source_schema_version"] == 1
    assert evidence["sqlite_open_mode"] == "read-only-uri"
    assert evidence["sqlite_query_only"] is True
    assert evidence["station_identity"] == "exact-source-callsign-plus-ssid"
    assert evidence["latest_record_order"] == "observed_at_ns-desc-id-desc"
    assert evidence["since_filter"] is True
    assert evidence["list_limit_min"] == 1
    assert evidence["list_limit_max"] == 1000
    assert evidence["unsupported_schema_fails_closed"] is True
    assert evidence["additional_packet_subscriber"] is False
    assert evidence["additional_worker_thread"] is False
    assert evidence["additional_in_memory_queue"] is False
    assert evidence["database_write_capability"] is False
    assert evidence["monitor_tx_capability"] is False
    assert evidence["modem_dependency"] is False
    assert evidence["uart_access"] is False
    assert evidence["rf_access"] is False
    assert evidence["flash_gpio_option_byte_activity"] is False
    assert evidence["p3_target_pi_supplementary_evidence_preserved"] is True
    assert evidence["dedicated_push_ci"] == {
        "run_id": 33820815962,
        "result": "success",
    }
    assert evidence["pull_request_ci"] == {
        "pull_request": 28,
        "workflow_runs": 17,
        "framework_run_id": 33820856458,
        "framework_result": "success",
        "pending_runs": 0,
        "failed_runs": 0,
    }
    assert evidence["qualification_complete"] is True

    for path, expected in FROZEN_BLOBS.items():
        actual = blob(path)
        assert actual == expected, (path, expected, actual)

    p3_pi = json.loads(P3_PI.read_text(encoding="utf-8"))
    assert p3_pi["status"] == "pass"
    assert p3_pi["tested_checkpoint_sha"] == "0c6778278469ab5f1608cdc9e38d02bc0987541f"
    assert p3_pi["python_version"] == "3.13.5"
    assert p3_pi["smoke_test"]["row_count"] == 2
    assert p3_pi["modem_uart_opened"] is False
    assert p3_pi["rf_transmitted"] is False

    print("YWD1278_0D_P4_HOST_QUALIFICATION=PASS")
    print("QUALIFIED_IMPLEMENTATION_HEAD=b32f070611075634507b089e9dcee86122ac5a58")
    print("DEDICATED_CI_RUN=33820815962_SUCCESS")
    print("FRAMEWORK_PR_CI_RUN=33820856458_SUCCESS")
    print("FULL_PR_MATRIX=17_OF_17_SUCCESS")
    print("FROZEN_P3_SQLITE_LOG_HASH=PASS")
    print("MHEARD_IMPLEMENTATION_HASH=PASS")
    print("P3_TARGET_PI_PYTHON_3_13_5_EVIDENCE=PASS")
    print("MHEARD_DATABASE_WRITE_CAPABILITY=ABSENT")
    print("MHEARD_PACKET_SUBSCRIBER=ABSENT")
    print("MHEARD_WORKER_THREAD=ABSENT")
    print("MHEARD_TX_CAPABILITY=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
