#!/usr/bin/env python3
"""Frozen host qualification evidence contract for 0D-P2."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0d-p2-monitor-controls-host.json"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    d = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert d["schema"] == 1
    assert d["phase"] == "0D-P2"
    assert d["status"] == "host-qualified"
    assert d["qualification_complete"] is True
    assert d["base_checkpoint"] == "checkpoint/0d-p1-decoded-monitor-host-qualified"
    assert d["base_checkpoint_sha"] == "1972f4c92552085202c810e3b605c8e46275634c"
    assert d["qualified_implementation_head_sha"] == "b42842b36ff29dee146a2c74ede1e98bb7d144ba"
    assert git_blob("src/ywd1278/monitor/policy.py") == d["policy_blob"]
    assert git_blob("src/ywd1278/monitor/stream.py") == d["p1_monitor_stream_blob"]
    assert d["defaults"] == {"mcom": False, "mcon": False, "mrpt": True}

    for key in (
        "mcom_control_frame_gate",
        "mcon_connected_context_gate",
        "mrpt_presentation_only",
        "connected_mode_context_injected",
        "thread_safe",
        "generation_tagged",
    ):
        assert d[key] is True, key

    for key in (
        "connected_mode_engine_present",
        "text_command_parser_present",
        "idempotent_update_increments_generation",
        "monitor_tx_capability",
        "modem_dependency",
        "uart_access",
        "rf_access",
        "flash_gpio_option_byte_activity",
    ):
        assert d[key] is False, key

    assert d["dedicated_push_ci"] == {"run_id": 33815606268, "result": "success"}
    pr = d["pull_request_ci"]
    assert pr["pull_request"] == 26
    assert pr["workflow_runs"] == 15
    assert pr["framework_run_id"] == 33815650153
    assert pr["framework_result"] == "success"
    assert pr["pending_runs"] == 0
    assert pr["failed_runs"] == 0

    print("YWD1278_0D_P2_HOST_QUALIFICATION=PASS")
    print("MCOM_DEFAULT=OFF")
    print("MCON_DEFAULT=OFF")
    print("MRPT_DEFAULT=ON")
    print("FROZEN_P1_MONITOR_STREAM_HASH=PASS")
    print("MONITOR_TX_CAPABILITY=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
