#!/usr/bin/env python3
"""Frozen host-qualification evidence contract for 0D-P1."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0d-p1-monitor-stream-host.json"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["schema"] == 1
    assert evidence["phase"] == "0D-P1"
    assert evidence["status"] == "host-qualified"
    assert evidence["qualification_complete"] is True
    assert evidence["base_checkpoint"] == "checkpoint/0c-complete-p8-physical-qualified"
    assert evidence["base_checkpoint_sha"] == "fc70386a3857e69437641d1be6f9f8cd0a6e7a13"
    assert evidence["qualified_implementation_head_sha"] == "164f0a6b5d8976f94f5824c1224d778a2ef40e99"
    assert git_blob("src/ywd1278/monitor/stream.py") == evidence["monitor_stream_blob"]

    for key in (
        "history_before_live",
        "structured_ax25_records",
        "ui_tnc2_style_rendering",
        "connected_control_metadata_preserved",
        "repeated_path_flag_rendering",
        "single_line_binary_escaping",
        "malformed_internal_events_counted_and_skipped",
        "metadata_consistency_checked",
        "source_queue_bounded",
        "source_subscriber_drop_accounting_reused",
    ):
        assert evidence[key] is True, key

    for key in (
        "additional_worker_thread",
        "additional_monitor_queue",
        "monitor_tx_capability",
        "modem_dependency",
        "uart_access",
        "rf_access",
        "flash_gpio_option_byte_activity",
    ):
        assert evidence[key] is False, key

    assert evidence["dedicated_push_ci"] == {"run_id": 33814562850, "result": "success"}
    pr = evidence["pull_request_ci"]
    assert pr["pull_request"] == 25
    assert pr["workflow_runs"] == 14
    assert pr["framework_run_id"] == 33814566960
    assert pr["framework_result"] == "success"
    assert pr["pending_runs"] == 0
    assert pr["failed_runs"] == 0

    for path, expected in evidence["frozen_0c_blobs"].items():
        assert git_blob(path) == expected, path

    print("YWD1278_0D_P1_HOST_QUALIFICATION=PASS")
    print("QUALIFIED_IMPLEMENTATION_HEAD=164f0a6b5d8976f94f5824c1224d778a2ef40e99")
    print("DEDICATED_CI_RUN=33814562850_SUCCESS")
    print("FRAMEWORK_PR_CI_RUN=33814566960_SUCCESS")
    print("FROZEN_0C_CORE_HASHES=PASS")
    print("MONITOR_TX_CAPABILITY=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
