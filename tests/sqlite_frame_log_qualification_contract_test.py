#!/usr/bin/env python3
"""Frozen host qualification contract for 0D-P3 SQLite frame logging."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0d-p3-sqlite-frame-log-host.json"
PI_SANITY = ROOT / "firmware" / "qualification" / "0d-p1-p2-target-pi-sanity-2026-09-03.json"

FROZEN_BLOBS = {
    "src/ywd1278/monitor/sqlite_log.py": "cd43f6e284061c19bd8bade8e1449986a9f99374",
    "src/ywd1278/monitor/stream.py": "703b7e803d39d915b60d79c30c154151e3820098",
    "src/ywd1278/monitor/policy.py": "f7d105554f682dfc533a09bff8823b192e5debe9",
}


def blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["schema"] == 1
    assert evidence["phase"] == "0D-P3"
    assert evidence["stage"] == "sqlite-frame-log-host"
    assert evidence["status"] == "host-qualified"
    assert evidence["base_checkpoint"] == "checkpoint/0d-p2-monitor-controls-host-qualified"
    assert evidence["base_checkpoint_sha"] == "d34db7292750b67384667d99eef897b9306d0113"
    assert evidence["qualified_implementation_head_sha"] == "3cfb55bb504025c8b00263d5b646a71d14f2ea45"
    assert evidence["schema_version"] == 1
    assert evidence["journal_mode"] == "WAL"
    assert evidence["synchronous_mode"] == "NORMAL"
    assert evidence["dedicated_sqlite_worker_threads"] == 1
    assert evidence["additional_in_memory_queue"] is False
    assert evidence["source_backpressure"] == "existing-bounded-backend-subscriber"
    assert evidence["backend_history_replayed_to_sqlite"] is False
    assert evidence["restart_duplicate_history"] is False
    assert evidence["exact_frame_no_fcs_bytes_persisted"] is True
    assert evidence["exact_information_bytes_persisted"] is True
    assert evidence["structured_ax25_fields_persisted"] is True
    assert evidence["unsupported_schema_fails_closed"] is True
    assert evidence["unversioned_nonempty_database_fails_closed"] is True
    assert evidence["sqlite_write_failure_isolated"] is True
    assert evidence["packet_backend_remains_usable_after_sink_failure"] is True
    assert evidence["monitor_tx_capability"] is False
    assert evidence["modem_dependency"] is False
    assert evidence["uart_access"] is False
    assert evidence["rf_access"] is False
    assert evidence["flash_gpio_option_byte_activity"] is False
    assert evidence["dedicated_push_ci"] == {"run_id": 33819172303, "result": "success"}
    assert evidence["pull_request_ci"] == {
        "pull_request": 27,
        "workflow_runs": 16,
        "framework_run_id": 33819204017,
        "framework_result": "success",
        "pending_runs": 0,
        "failed_runs": 0,
    }
    assert evidence["qualification_complete"] is True

    for path, expected in FROZEN_BLOBS.items():
        actual = blob(path)
        assert actual == expected, (path, expected, actual)

    sanity = json.loads(PI_SANITY.read_text(encoding="utf-8"))
    assert sanity["status"] == "supplementary-target-host-pass"
    assert sanity["deployed_checkout_sha"] == "fc70386a3857e69437641d1be6f9f8cd0a6e7a13"
    assert sanity["isolated_worktree_sha"] == "d34db7292750b67384667d99eef897b9306d0113"
    assert sanity["python_version"] == "3.13.5"
    assert sanity["p1"]["uart_activity"] is False
    assert sanity["p1"]["rf_activity"] is False
    assert sanity["p2"]["uart_activity"] is False
    assert sanity["p2"]["rf_activity"] is False
    assert sanity["frozen_p8_preservation"]["uart_opened"] is False
    assert sanity["frozen_p8_preservation"]["rf_transmitted"] is False

    print("YWD1278_0D_P3_HOST_QUALIFICATION=PASS")
    print("QUALIFIED_IMPLEMENTATION_HEAD=3cfb55bb504025c8b00263d5b646a71d14f2ea45")
    print("DEDICATED_CI_RUN=33819172303_SUCCESS")
    print("FRAMEWORK_PR_CI_RUN=33819204017_SUCCESS")
    print("FULL_PR_MATRIX=16_OF_16_SUCCESS")
    print("FROZEN_P1_MONITOR_STREAM_HASH=PASS")
    print("FROZEN_P2_MONITOR_POLICY_HASH=PASS")
    print("SQLITE_LOG_IMPLEMENTATION_HASH=PASS")
    print("TARGET_PI_P1_P2_PYTHON_3_13_5_SANITY=PASS")
    print("MONITOR_TX_CAPABILITY=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
