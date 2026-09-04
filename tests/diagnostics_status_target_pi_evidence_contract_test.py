#!/usr/bin/env python3
"""Immutable contract for the supplementary 0D-P6 target-Pi diagnostics sanity run."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0d-p6-diagnostics-status-target-pi-sanity-2026-09-03.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    require(data["schema"] == 1, "unexpected evidence schema")
    require(data["phase"] == "0D-P6", "wrong phase")
    require(data["stage"] == "diagnostics-status-target-pi-sanity", "wrong stage")
    require(data["status"] == "supplementary-target-host-pass", "target-Pi evidence is not passing")
    require(data["checkpoint"] == "checkpoint/0d-p6-diagnostics-status-host-qualified", "wrong checkpoint")
    require(data["checkpoint_sha"] == "1c20585af6a782af83817beeaa3df6f42f378de5", "wrong checkpoint SHA")
    require(data["qualified_implementation_head"] == "0c83530d2565cff22eef9b61dc05b6fa77890d34", "wrong P6 implementation head")
    require(data["python_version"] == "3.13.5", "wrong target Python")
    require(all(value == "pass" for value in data["tests"].values()), "one or more target-Pi preservation tests did not pass")

    diagnostics = data["diagnostics"]
    require(diagnostics["source"] == "existing-snapshots-only", "diagnostics source boundary changed")
    require(diagnostics["mode"] == "one-shot-read-only", "diagnostics mode changed")
    require(diagnostics["runtime_accounting"] == "pass", "runtime accounting not preserved")
    require(diagnostics["kiss_control_ingress_queue_connections"] == "pass", "KISS diagnostics not preserved")
    require(diagnostics["backend_subscriber_drops"] == "pass", "backend drop diagnostics not preserved")
    require(diagnostics["sqlite_mheard_retention"] == "pass", "SQLite/MHEARD/retention diagnostics not preserved")
    for key in (
        "database_mutation",
        "sampling_thread",
        "packet_subscriber",
        "worker_thread",
        "additional_in_memory_queue",
        "database_write_capability",
        "retention_apply_capability",
        "tx_capability",
    ):
        require(diagnostics[key] is False, f"target-Pi safety boundary changed: {key}")

    smoke = data["smoke_database"]
    require(smoke["path"] == "/tmp/ywd1278-p3-smoke.sqlite3", "wrong smoke database")
    require(smoke["unattached_sources"] == [
        "runtime",
        "backend",
        "parameters",
        "control",
        "ingress",
        "queue",
        "connections",
        "sqlite_log",
    ], "unexpected unattached diagnostics source set")
    require(smoke["mheard"] == {
        "station_count": 2,
        "frame_count": 2,
        "latest_heard_ns": 1788480434979489748,
    }, "unexpected MHEARD snapshot")
    require(smoke["retention_plan"] == {
        "enabled": False,
        "total_rows": 2,
        "eligible_rows": 0,
        "next_batch_rows": 0,
        "cutoff_ns": None,
        "max_rows": None,
        "max_delete_per_run": 1000,
    }, "unexpected retention plan")
    require(smoke["healthy"] is True, "target-Pi diagnostics snapshot was not healthy")
    require(smoke["problems"] == [], "target-Pi diagnostics reported problems")
    require(smoke["row_count_before"] == 2, "unexpected pre-snapshot row count")
    require(smoke["row_count_after"] == 2, "unexpected post-snapshot row count")
    require(smoke["database_mutated"] is False, "diagnostics mutated the target-Pi database")

    require(data["prior_evidence"] == {
        "p5_target_pi": "pass",
        "p4_target_pi": "pass",
        "p3_target_pi": "pass",
    }, "prior target-Pi evidence was not preserved")
    require(data["uart_activity"] is False, "target-Pi P6 sanity must not open UART")
    require(data["rf_activity"] is False, "target-Pi P6 sanity must not transmit RF")
    require(data["qualification_complete"] is True, "target-Pi P6 evidence incomplete")

    print("YWD1278_0D_P6_TARGET_PI_SANITY=PASS")
    print("TARGET_PI_CHECKPOINT=1c20585af6a782af83817beeaa3df6f42f378de5")
    print("TARGET_PI_PYTHON=3.13.5")
    print("TARGET_PI_DIAGNOSTICS_HEALTHY=YES")
    print("TARGET_PI_MHEARD_STATIONS=2")
    print("TARGET_PI_MHEARD_FRAMES=2")
    print("TARGET_PI_RETENTION_ENABLED=NO")
    print("TARGET_PI_DATABASE_MUTATED=NO")
    print("TARGET_PI_UART_RF_ACTIVITY=NONE")


if __name__ == "__main__":
    main()
