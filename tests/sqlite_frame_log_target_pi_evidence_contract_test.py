#!/usr/bin/env python3
"""Supplementary target-Pi evidence contract for merged 0D-P3."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0d-p3-target-pi-sanity-2026-09-03.json"


def main() -> int:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["schema"] == 1
    assert evidence["phase"] == "0D-P3"
    assert evidence["stage"] == "sqlite-frame-log-target-pi-sanity"
    assert evidence["status"] == "pass"
    assert evidence["tested_checkpoint_sha"] == "0c6778278469ab5f1608cdc9e38d02bc0987541f"
    assert evidence["python_version"] == "3.13.5"
    assert evidence["sqlite_frame_log_regression"] == "pass"
    assert evidence["sqlite_frame_log_contract"] == "pass"
    assert evidence["sqlite_frame_log_host_qualification_contract"] == "pass"
    assert evidence["preserved_p1_host_qualification"] == "pass"
    assert evidence["preserved_p2_host_qualification"] == "pass"
    assert evidence["sqlite_schema_version"] == 1
    assert evidence["sqlite_journal_mode"] == "wal"
    assert evidence["exact_frame_bytes_persisted"] is True
    assert evidence["structured_ax25_fields_persisted"] is True
    assert evidence["restart_history_replay_duplicates"] is False
    assert evidence["unsupported_schema_fails_closed"] is True
    assert evidence["sqlite_write_failure_isolated"] is True
    assert evidence["additional_in_memory_queue"] is False

    smoke = evidence["smoke_test"]
    assert smoke["rows_written"] == 2
    assert smoke["write_failures"] == 0
    assert smoke["source_subscriber_drops"] == 0
    assert smoke["fatal_error"] is None
    assert smoke["row_count"] == 2
    assert smoke["rows"] == [
        {
            "id": 1,
            "source": "KJ6YWD-9",
            "destination": "APRS",
            "path_json": "[\"WIDE1-1\",\"WIDE2-1\"]",
            "frame_type": "UI",
            "info_length": 27,
            "frame_no_fcs_length": 57,
            "line": "KJ6YWD-9>APRS,WIDE1-1,WIDE2-1:YWD-1278 P3 SQLITE TEST ONE",
        },
        {
            "id": 2,
            "source": "KJ6YWD",
            "destination": "JIM",
            "path_json": "[]",
            "frame_type": "UI",
            "info_length": 27,
            "frame_no_fcs_length": 43,
            "line": "KJ6YWD>JIM:YWD-1278 P3 SQLITE TEST TWO",
        },
    ]
    assert evidence["modem_uart_opened"] is False
    assert evidence["rf_transmitted"] is False
    assert evidence["flash_gpio_option_byte_activity"] is False
    assert evidence["qualification_scope"] == (
        "supplementary target-Pi sanity; frozen host qualification remains authoritative"
    )

    print("YWD1278_0D_P3_TARGET_PI_SANITY=PASS")
    print("TARGET_PI_CHECKPOINT=0c6778278469ab5f1608cdc9e38d02bc0987541f")
    print("TARGET_PI_PYTHON=3.13.5")
    print("TARGET_PI_SQLITE_ROWS=2")
    print("TARGET_PI_SQLITE_JOURNAL_MODE=WAL")
    print("TARGET_PI_UART_RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
