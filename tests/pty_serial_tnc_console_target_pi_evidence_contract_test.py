#!/usr/bin/env python3
"""Freeze the 0E-P4 target-Pi virtual PTY qualification evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET_EVIDENCE = ROOT / "firmware/qualification/0e-p4-virtual-pty-console-target-pi.json"
HOST_EVIDENCE = ROOT / "firmware/qualification/0e-p4-virtual-pty-console-host.json"

EXPECTED_BLOBS = {
    "src/ywd1278/console/pty_serial.py": "c0ba2a3278ac1e790bf383fc12a220ae327255ba",
    "tests/pty_serial_tnc_console_test.py": "8acba59b456b2224dbb0e64b76b7f7ef0bfc4b94",
    "tests/pty_serial_tnc_console_contract_test.py": "cff343aa56a6c20f9cb539bb95d4765ebdeb1da7",
    "tools/qualify_0e_p4_pty.py": "1740249933aa0ab8f8201f0bf5b136f86e3c8cbe",
    "src/ywd1278/console/local.py": "9fed5416ca9123811413f4ef284abff0006a48dd",
    "src/ywd1278/console/telnet.py": "d15669eb61f2afdf4d0d177191124ef8f13713e0",
    "src/ywd1278/console/auth.py": "0bdacaca9807012954c3362a8c0d92c4c1e21d40",
    "src/ywd1278/console/lan_telnet.py": "a53bad81aa3ffa167375517bb48a19e8ac9143f3",
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
    assert target["phase"] == "0E-P4"
    assert target["stage"] == "virtual-pty-serial-tnc-personality"
    assert target["status"] == "target-pi-qualified"
    assert target["host_evidence"] == "firmware/qualification/0e-p4-virtual-pty-console-host.json"

    qualified = target["qualified_implementation"]
    assert qualified["head_sha"] == "aba04bc61810c8038ce6890e6bc9c634088690db"
    assert qualified["dedicated_ci_run"] == 33834928723
    assert qualified["dedicated_ci_conclusion"] == "success"
    assert host["qualified_implementation"] == qualified
    assert host["host_qualification_complete"] is True

    tested = target["target_tested_tree"]
    assert tested["branch"] == "dev-0e-p4-virtual-pty-console"
    assert tested["head_sha"] == "1be7340d920bb64251245b67ce1c4fb32da15486"
    assert tested["branch_pull_result"] == "already up to date"
    assert tested["working_tree_clean_asserted_by_reduced_wrapper"] is False

    for relative, expected in EXPECTED_BLOBS.items():
        actual = git_blob_sha(ROOT / relative)
        assert actual == expected, f"frozen blob changed: {relative}: {actual} != {expected}"

    for relative, expected in target["p4_blobs"].items():
        assert EXPECTED_BLOBS[relative] == expected
    for relative, expected in target["frozen_boundaries"].items():
        assert EXPECTED_BLOBS[relative] == expected

    environment = target["target_environment"]
    assert environment["python"] == "3.13.5"
    assert environment["kernel_pty_slave"] == "/dev/pts/1"
    assert environment["pty_slave_prefix"] == "/dev/pts/"
    assert environment["pty_slave_mode_octal"] == "0600"

    results = target["target_results"]
    for key in (
        "deterministic_helper",
        "termios_tty_api",
        "stable_link_create_resolve",
        "stable_link_cleanup",
        "frozen_p1_commands",
        "detach_reopen_state_reset",
        "quit_logical_session_reset",
        "future_connect_tx_commands_rejected",
        "safe_child_wrapper",
    ):
        assert results[key] == "pass", key
    assert results["network_listener_required"] is False
    assert results["hardware_serial_opened"] is False
    assert results["modem_kiss_tx_path"] == "absent"
    assert results["tx_rf_hardware_test_required"] is False
    assert results["safe_child_wrapper_exit_code"] == 0
    assert results["putty_session_remained_open"] is True

    sigterm = target["sigterm_cleanup_proof"]
    assert sigterm["target_pi_helper_exercised_sigterm"] is False
    assert sigterm["host_ci_exercised_sigterm"] is True
    assert sigterm["host_ci_result"] == "pass"

    assert all(value is False for value in target["safety"].values())
    assert target["target_pi_virtual_pty_smoke_complete"] is True
    assert target["phase_complete"] is True

    print("YWD1278_0E_P4_TARGET_PI_EVIDENCE=PASS")
    print("TARGET_PI_TESTED_SHA=1be7340d920bb64251245b67ce1c4fb32da15486")
    print("QUALIFIED_IMPLEMENTATION_HEAD=aba04bc61810c8038ce6890e6bc9c634088690db")
    print("TARGET_PI_PYTHON=3.13.5")
    print("TARGET_PI_PTY=/dev/pts/1")
    print("PTY_MODE_0600_TERMIOS=PASS")
    print("STABLE_LINK_CREATE_RESOLVE_CLEANUP=PASS")
    print("DETACH_REOPEN_STATE_RESET=PASS")
    print("QUIT_LOGICAL_SESSION_RESET=PASS")
    print("FUTURE_CONNECT_TX_COMMANDS_REJECTED=PASS")
    print("TARGET_SIGTERM_RECLAIMED=NO_HOST_CI_ONLY")
    print("NETWORK_HARDWARE_SERIAL_MODEM_KISS_TX=ABSENT")
    print("TX_RF_HARDWARE_TEST_REQUIRED=NO")
    print("P4_PHASE_COMPLETE=YES")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
