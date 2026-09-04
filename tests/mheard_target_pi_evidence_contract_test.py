#!/usr/bin/env python3
"""Supplementary target-Pi evidence contract for 0D-P4 MHEARD."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0d-p4-target-pi-sanity-2026-09-03.json"

FROZEN_BLOBS = {
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
    assert evidence["phase"] == "0D-P4"
    assert evidence["stage"] == "mheard-target-pi-sanity"
    assert evidence["status"] == "supplementary-target-host-pass"
    assert evidence["checkpoint"] == "checkpoint/0d-p4-mheard-host-qualified"
    assert evidence["checkpoint_sha"] == "d75e253003762d1077e7300da52980b1f4739963"
    assert evidence["python_version"] == "3.13.5"
    assert all(value == "pass" for value in evidence["tests"].values())

    mheard = evidence["mheard"]
    assert mheard["source"] == "sqlite-frame-log-read-only"
    assert mheard["aggregation"] == "source-callsign-ssid"
    assert mheard["database_write_capability"] is False
    assert mheard["packet_subscriber"] is False
    assert mheard["worker_thread"] is False
    assert mheard["additional_in_memory_queue"] is False
    assert mheard["tx_capability"] is False

    smoke = evidence["smoke_database"]
    assert smoke["station_count"] == 2
    assert smoke["frame_count"] == 2
    assert smoke["ssid_identity_preserved"] is True
    stations = {item["source"]: item for item in smoke["stations"]}
    assert set(stations) == {"KJ6YWD", "KJ6YWD-9"}
    assert stations["KJ6YWD"]["heard_count"] == 1
    assert stations["KJ6YWD-9"]["heard_count"] == 1
    assert stations["KJ6YWD"]["destination"] == "JIM"
    assert stations["KJ6YWD-9"]["destination"] == "APRS"
    assert stations["KJ6YWD-9"]["path"] == ["WIDE1-1", "WIDE2-1"]

    assert evidence["uart_activity"] is False
    assert evidence["rf_activity"] is False
    assert evidence["qualification_complete"] is True

    for path, expected in FROZEN_BLOBS.items():
        actual = blob(path)
        assert actual == expected, (path, expected, actual)

    print("YWD1278_0D_P4_TARGET_PI_SANITY=PASS")
    print("TARGET_PI_CHECKPOINT=d75e253003762d1077e7300da52980b1f4739963")
    print("TARGET_PI_PYTHON=3.13.5")
    print("TARGET_PI_MHEARD_STATIONS=2")
    print("TARGET_PI_MHEARD_FRAMES=2")
    print("TARGET_PI_SSID_IDENTITY=PASS")
    print("TARGET_PI_DATABASE_WRITE_CAPABILITY=ABSENT")
    print("TARGET_PI_UART_RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
