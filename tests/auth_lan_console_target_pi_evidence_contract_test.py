#!/usr/bin/env python3
"""Immutable target-Pi evidence contract for 0E-P3 authenticated LAN console."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0e-p3-auth-lan-console-target-pi.json"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert data["schema"] == 1
    assert data["phase"] == "0E-P3"
    assert data["stage"] == "target-pi-private-lan-authenticated-telnet-console"
    assert data["status"] == "target-pi-qualified"
    assert data["qualification_date"] == "2026-09-03"
    assert data["timezone"] == "America/Los_Angeles"
    assert data["tested_branch"] == "dev-0e-p3-auth-lan-console"
    assert data["tested_staging_head"] == "1da631ca2c9dca8359c8d0655fb82259708355c8"
    assert data["qualified_implementation_head"] == "dd58fbd3f1eade8227c0514751046201d2fb1e07"

    listener = data["listener"]
    assert listener["target_pi_address"] == "192.168.1.11"
    assert listener["port"] == 8023
    assert listener["bind_scope"] == "rfc1918-private-ipv4"
    assert listener["banner"] == "YWD-1278 0E-P3 AUTHENTICATED LAN TNC CONSOLE"
    assert listener["plaintext_transport_warning_present"] is True
    assert listener["wildcard_active_listener_absent"] is True
    assert listener["wildcard_bind_rejected"] is True
    assert listener["public_bind_rejected"] is True

    assert data["remote_host"] == {
        "source_address": "192.168.1.15",
        "source_scope": "rfc1918-private-ipv4",
        "separate_host_from_target": True,
    }

    auth = data["authentication"]
    assert auth["username"] == "ywd"
    assert auth["auth_file_mode"] == "0600"
    assert auth["password_storage"] == "pbkdf2-sha256-hash-only"
    assert auth["bad_auth_attempt_observed"] == "AUTH FAIL 1/3"
    assert auth["bad_auth_reached_command_mode"] is False
    assert auth["good_auth_observed"] == "AUTH OK"
    assert auth["reconnect_required_authentication"] is True

    session_1 = data["session_1"]
    assert session_1["version"] == "YWD-1278 0.1.0-alpha0"
    assert session_1["mcom_default"] == "OFF"
    assert session_1["mcon_default"] == "OFF"
    assert session_1["mrpt_default"] == "ON"
    assert session_1["mcom_set_on"] is True
    assert session_1["monitor_generation_after_mcom_on"] == 1
    assert session_1["connect_command_rejected"] is True
    assert session_1["tx_command_rejected"] is True
    assert session_1["quit_returned_bye"] is True

    assert data["session_2"] == {
        "reconnect_authentication_succeeded": True,
        "mcom_reset_to_default_off": True,
        "quit_returned_bye": True,
    }

    final_pi = data["final_pi_safety"]
    assert final_pi["private_rfc1918_bind"] == "pass"
    assert final_pi["wildcard_bind_rejected"] == "pass"
    assert final_pi["public_bind_rejected"] == "pass"
    assert final_pi["auth_file_protection"] == "pass"
    assert final_pi["temporary_qualification_credential_removed"] is True
    assert final_pi["tx_rf_hardware_test_required"] is False

    cleanup = data["cleanup_observation"]
    assert cleanup["stale_saved_pid_observed"] == 100200
    assert cleanup["stale_saved_pid_running"] is False
    assert cleanup["actual_listener_pid_observed"] == 100607
    assert cleanup["listener_remained_available_for_remote_test_after_stale_pid_cleanup_attempt"] is True
    assert cleanup["qualification_behavior_affected"] is False
    assert cleanup["residual_listener_cleanup_followup_required"] is False
    assert cleanup["followup_cleanup_tool"] == "tools/cleanup_0e_p3_lan.py"
    assert cleanup["followup_listener_pid_terminated"] == 100607
    assert cleanup["followup_state_removed"] == "/tmp/ywd1278-0e-p3-lan-state.json"
    assert cleanup["followup_listener_process_absent"] is True
    assert cleanup["followup_tcp_8023_not_listening"] is True
    assert cleanup["followup_temp_auth_state_removed"] is True
    assert cleanup["followup_result"] == "pass"

    expected_impl = {
        "src/ywd1278/console/auth.py": "0bdacaca9807012954c3362a8c0d92c4c1e21d40",
        "src/ywd1278/console/lan_telnet.py": "a53bad81aa3ffa167375517bb48a19e8ac9143f3",
        "tests/auth_lan_console_test.py": "b25c7753cec4ec8c0f8136a230e59a35b6ae8a41",
        "tests/auth_lan_console_contract_test.py": "49fd1c2c5774aaa4744335a98532e2f6aced3eff",
    }
    assert data["implementation_blobs"] == expected_impl
    for path, expected in expected_impl.items():
        assert git_blob(path) == expected, (path, git_blob(path), expected)

    assert git_blob("src/ywd1278/console/telnet.py") == "d15669eb61f2afdf4d0d177191124ef8f13713e0"
    assert git_blob("src/ywd1278/console/local.py") == "9fed5416ca9123811413f4ef284abff0006a48dd"
    assert git_blob("pyproject.toml") == "9331c09b7f1e3c7111e437f3007e1e2c14716eb3"

    for key, value in data["safety"].items():
        assert value is False, (key, value)

    assert data["target_pi_private_lan_qualification_complete"] is True
    assert data["cleanup_followup_complete"] is True
    assert data["phase_complete"] is True

    print("YWD1278_0E_P3_TARGET_PI_LAN_EVIDENCE=PASS")
    print("TARGET_PI=192.168.1.11:8023")
    print("REMOTE_SOURCE=192.168.1.15")
    print("SEPARATE_HOST_AUTH=PASS")
    print("BAD_AUTH_BEFORE_P1=PASS")
    print("GOOD_AUTH_FROZEN_P1=PASS")
    print("RECONNECT_REAUTH=PASS")
    print("MONITOR_STATE_RESET=PASS")
    print("FUTURE_TX_COMMANDS_REJECTED=PASS")
    print("WILDCARD_PUBLIC_BINDS_REJECTED=PASS")
    print("CLEANUP_STALE_PID_ANOMALY=RECORDED")
    print("CLEANUP_FOLLOWUP=PASS")
    print("P3_PHASE_COMPLETE=YES")
    print("TX_RF_HARDWARE_TEST_REQUIRED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
