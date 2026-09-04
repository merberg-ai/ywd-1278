#!/usr/bin/env python3
"""Immutable target-Pi evidence contract for 0E-P2 loopback Telnet console."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0e-p2-telnet-console-target-pi.json"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert data["schema"] == 1
    assert data["phase"] == "0E-P2"
    assert data["stage"] == "target-pi-loopback-telnet-command-console"
    assert data["status"] == "target-pi-qualified"
    assert data["qualification_date"] == "2026-09-03"
    assert data["timezone"] == "America/Los_Angeles"
    assert data["tested_branch"] == "dev-0e-p2-telnet-console"
    assert data["tested_sha"] == "9f1e08a8c9aa5c3ffe7e96612a34cf7384fd6771"
    assert data["source_tree_clean"] is True

    assert data["host_qualification"] == {
        "evidence": "firmware/qualification/0e-p2-telnet-console-host.json",
        "qualified_implementation_head": "37bcc6808e5287bfd49ba37d56b1a7d5185f8b1c",
        "dedicated_ci_run": 33829902701,
        "result": "success",
    }
    assert data["tested_head_ci"] == {
        "workflow": "0e-p2-telnet-console-ci",
        "run_id": 33830066688,
        "result": "success",
    }

    assert data["target_contracts"] == {
        "telnet_regression_tests_run": 14,
        "telnet_regression_tests_passed": 14,
        "architecture_contract": "pass",
        "host_qualification_contract": "pass",
    }

    listener = data["listener"]
    assert listener["bind"] == "127.0.0.1"
    assert listener["port"] == 8023
    assert listener["banner"] == "YWD-1278 0.1.0-alpha0 TELNET TNC CONSOLE"
    assert listener["mode"] == "0E-P2 loopback-only command mode"
    assert listener["wildcard_bind_tested"] == "0.0.0.0"
    assert listener["wildcard_bind_rejected"] is True
    assert listener["wildcard_bind_error"] == "0E-P2 listener is restricted to IPv4 loopback addresses"

    s1 = data["session_1"]
    assert s1["version"] == "YWD-1278 0.1.0-alpha0"
    assert s1["status"] == "STATUS UNAVAILABLE"
    assert s1["health"] == "HEALTH UNAVAILABLE"
    assert s1["mheard"] == "MHEARD UNAVAILABLE"
    assert s1["mcom_default"] == "OFF"
    assert s1["mcon_default"] == "OFF"
    assert s1["mrpt_default"] == "ON"
    assert s1["mcom_set_on"] is True
    assert s1["monitor_generation_after_mcom_on"] == 1
    assert s1["connect_command_rejected"] is True
    assert s1["tx_command_rejected"] is True
    assert s1["quit_returned_bye"] is True

    assert data["session_2"] == {
        "reconnect_succeeded": True,
        "mcom_reset_to_default_off": True,
        "quit_returned_bye": True,
    }

    for key, value in data["proofs"].items():
        assert value is True or (key == "tx_rf_hardware_test_required" and value is False), (key, value)
    assert data["proofs"]["tx_rf_hardware_test_required"] is False

    for key, value in data["safety"].items():
        assert value is False, (key, value)

    # The target evidence must preserve the exact host-qualified implementation
    # and the frozen 0E-P1 parser/package identities.
    assert git_blob("src/ywd1278/console/telnet.py") == "d15669eb61f2afdf4d0d177191124ef8f13713e0"
    assert git_blob("tests/telnet_tnc_console_test.py") == "7ac266f0725eccf8981245ce0b80664617da7cf2"
    assert git_blob("tests/telnet_tnc_console_contract_test.py") == "8a904b0976f24c06092e170e5adb32fd4bc64d3b"
    assert git_blob("src/ywd1278/console/local.py") == "9fed5416ca9123811413f4ef284abff0006a48dd"
    assert git_blob("pyproject.toml") == "9331c09b7f1e3c7111e437f3007e1e2c14716eb3"

    assert data["qualification_complete"] is True

    print("YWD1278_0E_P2_TARGET_PI_EVIDENCE=PASS")
    print("TARGET_PI_TESTED_SHA=9f1e08a8c9aa5c3ffe7e96612a34cf7384fd6771")
    print("TARGET_PI_TELNET_TESTS=14_OF_14_PASS")
    print("TARGET_PI_LOOPBACK_SESSION=PASS")
    print("TARGET_PI_SESSION_RESET=PASS")
    print("TARGET_PI_WILDCARD_BIND_REJECTED=PASS")
    print("FROZEN_0E_P2_IMPLEMENTATION_HASHES=PASS")
    print("FROZEN_0E_P1_HASHES=PASS")
    print("TX_RF_HARDWARE_TEST_REQUIRED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
