#!/usr/bin/env python3
"""Freeze the 0E-P5 target-Pi classic vocabulary qualification evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET_EVIDENCE = ROOT / "firmware/qualification/0e-p5-classic-vocabulary-target-pi.json"
HOST_EVIDENCE = ROOT / "firmware/qualification/0e-p5-classic-vocabulary-host.json"

EXPECTED_BLOBS = {
    "src/ywd1278/console/classic.py": "4d6dfd5d439fb5dfd6ff586c2a47c37724381b2e",
    "tests/classic_tnc_vocabulary_test.py": "d8e10890759d9d48ef8891be3cc4c74d58d3acc3",
    "tests/classic_tnc_vocabulary_contract_test.py": "620b8900c15044130d7da954c85bc39847c54dae",
    "tools/qualify_0e_p5_classic.py": "648b0b2165ac9a10aa0a0041da50e63aafeb17e1",
    "src/ywd1278/console/local.py": "9fed5416ca9123811413f4ef284abff0006a48dd",
    "src/ywd1278/console/telnet.py": "d15669eb61f2afdf4d0d177191124ef8f13713e0",
    "src/ywd1278/console/auth.py": "0bdacaca9807012954c3362a8c0d92c4c1e21d40",
    "src/ywd1278/console/lan_telnet.py": "a53bad81aa3ffa167375517bb48a19e8ac9143f3",
    "src/ywd1278/console/pty_serial.py": "c0ba2a3278ac1e790bf383fc12a220ae327255ba",
    "pyproject.toml": "9331c09b7f1e3c7111e437f3007e1e2c14716eb3",
}


def git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def main() -> int:
    target = json.loads(TARGET_EVIDENCE.read_text(encoding="utf-8"))
    host = json.loads(HOST_EVIDENCE.read_text(encoding="utf-8"))

    assert target["schema"] == 1
    assert target["phase"] == "0E-P5"
    assert target["stage"] == "classic-tnc2-mfj-command-vocabulary"
    assert target["status"] == "target-pi-qualified"
    assert target["host_evidence"] == "firmware/qualification/0e-p5-classic-vocabulary-host.json"

    qualified = target["qualified_implementation"]
    assert qualified["head_sha"] == "ab9e922b31bfb57b9a8be11c70a812dc1b0c0da3"
    assert qualified["dedicated_ci_run"] == 33836726120
    assert qualified["dedicated_ci_conclusion"] == "success"
    assert host["qualified_implementation"] == qualified
    assert host["host_qualification_complete"] is True
    assert host["target_pi_classic_vocabulary_smoke_pending"] is True
    assert host["phase_complete"] is False

    tested = target["target_tested_tree"]
    assert tested["branch"] == "dev-0e-p5-classic-vocabulary"
    assert tested["head_sha"] == "a0d102778c9da3be180dcdae7c1f455f66e72e91"
    assert tested["branch_pull_result"] == "already up to date"
    assert tested["working_tree_clean_before_test"] is True
    assert tested["working_tree_clean_after_test"] is True

    for relative, expected in EXPECTED_BLOBS.items():
        actual = git_blob_sha(ROOT / relative)
        assert actual == expected, f"frozen blob changed: {relative}: {actual} != {expected}"
    for relative, expected in target["p5_blobs"].items():
        assert EXPECTED_BLOBS[relative] == expected
    for relative, expected in target["frozen_boundaries"].items():
        assert EXPECTED_BLOBS[relative] == expected

    environment = target["target_environment"]
    assert environment["python"] == "3.13.5"
    assert environment["kernel_pty_slave"] == "/dev/pts/1"
    assert environment["pty_slave_mode_octal"] == "0600"
    assert "aarch64 GNU/Linux" in environment["kernel"]

    results = target["target_results"]
    assert results["regression_tests_passed"] == 10
    assert results["regression_tests_total"] == 10
    for key in (
        "architecture_contract",
        "host_evidence_contract",
        "safe_aliases",
        "display_monitor",
        "frozen_p2_real_telnet_composition",
        "frozen_p4_real_kernel_pty_composition",
        "pty_termios_api",
        "stable_link_cleanup",
        "detach_reopen_state_reset",
        "ambiguous_abbreviations_fail_closed",
        "connect_converse_unproto_beacon_deferred",
        "tx_xmitok_kiss_deferred",
        "mhclear_disabled_read_only",
        "safe_child_wrapper",
    ):
        assert results[key] == "pass", key
    assert results["hardware_serial_opened"] is False
    assert results["modem_kiss_tx_path"] == "absent"
    assert results["tx_rf_hardware_test_required"] is False
    assert results["safe_child_wrapper_exit_code"] == 0
    assert results["putty_session_remained_open"] is True

    policy = target["vocabulary_policy"]
    assert policy["safe_aliases"] == ["DISP", "MH", "VER", "STAT", "HEAL"]
    assert policy["display_scope"] == "MONITOR only"
    assert policy["generic_abbreviation_engine"] is False
    assert policy["ambiguous_abbreviations_fail_closed"] is True
    assert policy["tx_and_link_commands_operational"] is False
    assert policy["destructive_mhclear_operational"] is False

    assert all(value is False for value in target["safety"].values())
    assert target["target_pi_classic_vocabulary_smoke_complete"] is True
    assert target["phase_complete"] is True

    print("YWD1278_0E_P5_TARGET_PI_EVIDENCE=PASS")
    print("TARGET_PI_TESTED_SHA=a0d102778c9da3be180dcdae7c1f455f66e72e91")
    print("QUALIFIED_IMPLEMENTATION_HEAD=ab9e922b31bfb57b9a8be11c70a812dc1b0c0da3")
    print("TARGET_PI_PYTHON=3.13.5")
    print("TARGET_PI_PTY=/dev/pts/1")
    print("TARGET_PI_REGRESSION_TESTS=10_OF_10_PASS")
    print("TARGET_PI_TREE_CLEAN=PASS")
    print("SAFE_ALIASES=DISP_MH_VER_STAT_HEAL")
    print("DISPLAY_SCOPE=MONITOR_ONLY")
    print("AMBIGUOUS_ABBREVIATIONS=FAIL_CLOSED")
    print("TX_LINK_COMMANDS=RECOGNIZED_BUT_DEFERRED")
    print("MHCLEAR=DISABLED_READ_ONLY")
    print("FROZEN_P2_TELNET_P4_PTY_COMPOSITION=PASS")
    print("NETWORK_HARDWARE_SERIAL_MODEM_KISS_TX=ABSENT")
    print("TX_RF_HARDWARE_TEST_REQUIRED=NO")
    print("P5_PHASE_COMPLETE=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
