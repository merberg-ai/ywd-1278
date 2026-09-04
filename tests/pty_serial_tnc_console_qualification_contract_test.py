#!/usr/bin/env python3
"""Freeze the 0E-P4 host qualification evidence and implementation blobs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0e-p4-virtual-pty-console-host.json"

EXPECTED = {
    "src/ywd1278/console/pty_serial.py": "701bfca3b01ded1d9c0a590e78272cfa6907301a",
    "tests/pty_serial_tnc_console_test.py": "8acba59b456b2224dbb0e64b76b7f7ef0bfc4b94",
    "tests/pty_serial_tnc_console_contract_test.py": "9582d141c38e2ea0395d7a836625ac8db9f0c133",
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
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["schema"] == 1
    assert evidence["phase"] == "0E-P4"
    assert evidence["stage"] == "virtual-pty-serial-tnc-personality"
    assert evidence["status"] == "host-qualified"
    assert evidence["base_checkpoint"] == {
        "branch": "checkpoint/0e-p3-auth-lan-console-target-pi-qualified",
        "sha": "3571031f65f65f410600b90b625e35440bc59778",
    }
    qualified = evidence["qualified_implementation"]
    assert qualified["head_sha"] == "2f8bf6aff6cc95c7553a6344ac0d7313c1d21ba4"
    assert qualified["dedicated_ci_run"] == 33834614216
    assert qualified["dedicated_ci_conclusion"] == "success"

    for relative, expected in EXPECTED.items():
        actual = git_blob_sha(ROOT / relative)
        assert actual == expected, f"frozen blob changed: {relative}: {actual} != {expected}"

    for relative, expected in evidence["p4_blobs"].items():
        assert EXPECTED[relative] == expected
    for relative, expected in evidence["frozen_boundaries"].items():
        assert EXPECTED[relative] == expected

    pty = evidence["pty_policy"]
    assert pty["implementation"] == "kernel os.openpty only"
    assert pty["slave_path_prefix"] == "/dev/pts/"
    assert pty["slave_mode_octal"] == "0600"
    assert pty["slave_raw_mode"] is True
    assert pty["stable_link_existing_object_replaced"] is False
    assert pty["hardware_serial_path_opened"] is False

    command = evidence["serial_command_policy"]
    assert command["max_command_characters"] == 256
    assert command["default_max_commands_per_logical_session"] == 1024
    assert command["hard_max_commands_per_logical_session"] == 10000
    assert command["parser"] == "frozen 0E-P1 LocalTNCCommandShell"
    assert command["detach_reopen_resets_monitor_policy"] is True
    assert command["quit_resets_logical_session"] is True
    assert set(command["future_commands_rejected"]) >= {"CONNECT", "UNPROTO", "TX", "KISS"}

    results = evidence["host_results"]
    assert results["regression_tests_passed"] == 11
    assert results["regression_tests_total"] == 11
    for key in (
        "architecture_contract",
        "real_kernel_pty_helper",
        "stable_link_create_resolve_cleanup",
        "termios_tty_api",
        "detach_reopen_state_reset",
        "quit_logical_session_reset",
        "future_connect_tx_rejected",
        "frozen_p3_preservation",
        "frozen_p2_preservation",
        "frozen_p1_preservation",
        "frozen_0d_preservation",
        "frozen_sustained_0c_runtime_preservation",
    ):
        assert results[key] == "pass", key

    assert all(value is False for value in evidence["safety"].values())
    assert evidence["host_qualification_complete"] is True
    assert evidence["target_pi_virtual_pty_smoke_pending"] is True
    assert evidence["phase_complete"] is False

    print("YWD1278_0E_P4_HOST_QUALIFICATION=PASS")
    print("QUALIFIED_IMPLEMENTATION_HEAD=2f8bf6aff6cc95c7553a6344ac0d7313c1d21ba4")
    print("DEDICATED_CI_RUN=33834614216_SUCCESS")
    print("P4_REGRESSION_TESTS=11_OF_11_PASS")
    print("REAL_KERNEL_PTY_HELPER=PASS")
    print("FROZEN_0E_P1_P2_P3_HASHES=PASS")
    print("FROZEN_PYPROJECT_HASH=PASS")
    print("PTY_SLAVE_MODE=0600_RAW")
    print("DETACH_REOPEN_STATE_RESET=PASS")
    print("FUTURE_CONNECT_TX_COMMANDS_REJECTED=PASS")
    print("NETWORK_HARDWARE_SERIAL_MODEM_KISS_TX=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    print("TARGET_PI_VIRTUAL_PTY_SMOKE=PENDING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
