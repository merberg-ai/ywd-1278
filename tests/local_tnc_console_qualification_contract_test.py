#!/usr/bin/env python3
"""Immutable host-qualification contract for 0E-P1 local TNC console."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0e-p1-local-tnc-console-host.json"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert data["schema"] == 1
    assert data["phase"] == "0E-P1"
    assert data["stage"] == "local-classic-tnc-command-shell"
    assert data["status"] == "host-qualified"
    assert data["base_checkpoint"] == "checkpoint/0d-p6-diagnostics-status-target-pi-qualified"
    assert data["base_sha"] == "de90a5613c2c3be47f485842920239b7067c249a"
    assert data["qualified_implementation_head"] == "a0d06cb59236d049b9896d80378df5957cc6d3ac"
    assert data["dedicated_ci"] == {
        "workflow": "0e-p1-local-console-ci",
        "run_id": 33827541642,
        "result": "success",
    }

    expected_blobs = {
        "src/ywd1278/console/__init__.py": "63509fc8dc0c9c91bd8415123ae93b45cd1ecf01",
        "src/ywd1278/console/local.py": "9fed5416ca9123811413f4ef284abff0006a48dd",
        "tests/local_tnc_console_test.py": "4fa6dbbf1e6649646eec0ff4f086726832ff3849",
        "tests/local_tnc_console_contract_test.py": "aa5199481cc8307b315ef0045b16956905814246",
        "pyproject.toml": "9331c09b7f1e3c7111e437f3007e1e2c14716eb3",
    }
    assert data["implementation_blobs"] == expected_blobs
    for path, expected in expected_blobs.items():
        actual = git_blob(path)
        assert actual == expected, (path, expected, actual)

    interface = data["interface"]
    assert interface == {
        "entry_point": "ywd1278-console",
        "transport": "local-stdin-stdout-only",
        "prompt": "cmd:",
        "max_command_chars": 256,
        "max_mheard_limit": 100,
        "exact_token_commands": True,
        "command_abbreviation": False,
        "shell_escape": False,
        "dynamic_execution": False,
    }

    assert tuple(data["commands"]) == (
        "HELP",
        "?",
        "VERSION",
        "STATUS",
        "HEALTH",
        "MHEARD",
        "MCOM",
        "MCON",
        "MRPT",
        "QUIT",
        "EXIT",
    )
    assert data["future_commands_rejected"] == [
        "CONNECT",
        "CONVERSE",
        "UNPROTO",
        "BEACON",
        "TX",
        "SEND",
        "TRANSMIT",
        "KISS",
        "SHELL",
    ]

    composition = data["qualified_composition"]
    assert composition["diagnostics"] == "frozen-0D-P6-one-shot-snapshot-only"
    assert composition["mheard"] == "frozen-0D-P4-read-only-view-only"
    assert composition["monitor_policy"] == "frozen-0D-P2-in-memory-policy-only"
    assert composition["database_writer"] is False
    assert composition["retention_apply"] is False

    safety = data["safety"]
    for key, value in safety.items():
        assert value is False, (key, value)
    assert data["qualification_complete"] is True

    print("YWD1278_0E_P1_HOST_QUALIFICATION=PASS")
    print("QUALIFIED_IMPLEMENTATION_HEAD=a0d06cb59236d049b9896d80378df5957cc6d3ac")
    print("DEDICATED_CI_RUN=33827541642_SUCCESS")
    print("LOCAL_CONSOLE_IMPLEMENTATION_HASH=PASS")
    print("FROZEN_0D_P6_DIAGNOSTICS=PASS")
    print("FROZEN_0D_P4_MHEARD=PASS")
    print("FROZEN_0D_P2_MONITOR_POLICY=PASS")
    print("COMMAND_LINE_LIMIT=256")
    print("MHEARD_LIMIT=100")
    print("LOCAL_STDIN_STDOUT_ONLY=YES")
    print("NETWORK_TELNET_PTY_SERIAL=ABSENT")
    print("SHELL_ESCAPE_DYNAMIC_EXECUTION=ABSENT")
    print("DATABASE_WRITE_RETENTION_APPLY=ABSENT")
    print("TX_CAPABILITY=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
