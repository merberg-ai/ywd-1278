#!/usr/bin/env python3
"""Immutable contract for the supplementary 0D-P5 target-Pi retention sanity run."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0d-p5-retention-target-pi-sanity-2026-09-03.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    require(data["schema"] == 1, "unexpected evidence schema")
    require(data["phase"] == "0D-P5", "wrong phase")
    require(data["stage"] == "retention-target-pi-sanity", "wrong stage")
    require(data["status"] == "supplementary-target-host-pass", "target-Pi evidence is not passing")
    require(data["checkpoint"] == "checkpoint/0d-p5-retention-host-qualified", "wrong checkpoint")
    require(data["checkpoint_sha"] == "b330e52bdf5eb902135138e32d91ff6538d5cf3c", "wrong checkpoint SHA")
    require(data["python_version"] == "3.13.5", "wrong target Python")

    tests = data["tests"]
    require(all(value == "pass" for value in tests.values()), "one or more target-Pi tests did not pass")

    retention = data["retention"]
    require(retention["default_enabled"] is False, "retention must remain disabled by default")
    require(retention["age_limit"] == "pass", "age retention not proven")
    require(retention["max_rows"] == "pass", "row retention not proven")
    require(retention["combined_semantics"] == "age-or-row-limit", "combined semantics changed")
    require(retention["default_max_delete_per_run"] == 1000, "default delete bound changed")
    require(retention["automatic_loop"] is False, "automatic retention loop forbidden")
    require(retention["busy_writer"] == "fail-closed", "busy-writer behavior changed")
    require(retention["automatic_vacuum"] is False, "automatic VACUUM forbidden")
    require(retention["packet_subscriber"] is False, "retention packet subscriber forbidden")
    require(retention["worker_thread"] is False, "retention worker thread forbidden")
    require(retention["tx_capability"] is False, "retention TX capability forbidden")

    smoke = data["smoke_database"]
    require(smoke["copy_created_with_sqlite_backup"] is True, "smoke copy method changed")
    require(smoke["before"] == {"station_count": 2, "frame_count": 2}, "unexpected smoke pre-state")
    require(smoke["policy"] == {"max_rows": 1}, "unexpected smoke retention policy")
    require(smoke["plan"]["eligible_rows"] == 1, "expected exactly one eligible row")
    require(smoke["plan"]["next_batch_rows"] == 1, "expected exactly one next-batch row")
    require(smoke["result"]["deleted_rows"] == 1, "expected exactly one deletion")
    require(smoke["result"]["remaining_rows"] == 1, "expected one retained row")
    require(smoke["result"]["remaining_eligible_rows"] == 0, "eligible rows must drain to zero")
    require(smoke["result"]["more_eligible"] is False, "smoke run must finish in one bounded batch")
    require(smoke["after"]["station_count"] == 1, "MHEARD station count did not follow retention")
    require(smoke["after"]["frame_count"] == 1, "MHEARD frame count did not follow retention")
    require(smoke["after"]["survivor_source"] == "KJ6YWD", "unexpected retained station")
    require(smoke["after"]["survivor_line"] == "KJ6YWD>JIM:YWD-1278 P3 SQLITE TEST TWO", "unexpected retained frame")
    require(smoke["original_row_count_after_test"] == 2, "original P3 smoke DB changed")
    require(smoke["retention_copy_row_count_after_test"] == 1, "retention copy count mismatch")
    require(smoke["original_database_preserved"] is True, "original smoke database not preserved")

    require(data["uart_activity"] is False, "target-Pi retention sanity must not open UART")
    require(data["rf_activity"] is False, "target-Pi retention sanity must not transmit RF")
    require(data["qualification_complete"] is True, "target-Pi retention evidence incomplete")

    print("YWD1278_0D_P5_TARGET_PI_SANITY=PASS")
    print("TARGET_PI_CHECKPOINT=b330e52bdf5eb902135138e32d91ff6538d5cf3c")
    print("TARGET_PI_PYTHON=3.13.5")
    print("TARGET_PI_RETENTION_DELETED_ROWS=1")
    print("TARGET_PI_RETENTION_REMAINING_ROWS=1")
    print("TARGET_PI_MHEARD_POST_RETENTION=1_STATION_1_FRAME")
    print("TARGET_PI_ORIGINAL_DATABASE_PRESERVED=YES")
    print("TARGET_PI_UART_RF_ACTIVITY=NONE")


if __name__ == "__main__":
    main()
