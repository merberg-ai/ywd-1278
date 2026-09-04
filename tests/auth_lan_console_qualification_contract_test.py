#!/usr/bin/env python3
"""Immutable host-qualification contract for 0E-P3 authenticated LAN console."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0e-p3-auth-lan-console-host.json"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert data["schema"] == 1
    assert data["phase"] == "0E-P3"
    assert data["stage"] == "authenticated-private-lan-telnet-console"
    assert data["status"] == "host-qualified"
    assert data["qualification_date"] == "2026-09-03"
    assert data["timezone"] == "America/Los_Angeles"
    assert data["base_checkpoint"] == "checkpoint/0e-p2-telnet-console-target-pi-qualified"
    assert data["base_sha"] == "ef374e86b36ba4252d899acbe211084e293b190f"
    assert data["qualified_implementation_head"] == "dd58fbd3f1eade8227c0514751046201d2fb1e07"
    assert data["dedicated_ci"] == {
        "workflow": "0e-p3-auth-lan-console-ci",
        "run_id": 33832163068,
        "result": "success",
    }

    expected_blobs = {
        "src/ywd1278/console/auth.py": "0bdacaca9807012954c3362a8c0d92c4c1e21d40",
        "src/ywd1278/console/lan_telnet.py": "a53bad81aa3ffa167375517bb48a19e8ac9143f3",
        "tests/auth_lan_console_test.py": "b25c7753cec4ec8c0f8136a230e59a35b6ae8a41",
        "tests/auth_lan_console_contract_test.py": "49fd1c2c5774aaa4744335a98532e2f6aced3eff",
    }
    assert data["implementation_blobs"] == expected_blobs
    for path, expected in expected_blobs.items():
        assert git_blob(path) == expected, path

    frozen = data["frozen_lower_layers"]
    assert frozen == {
        "p2_telnet_module": "src/ywd1278/console/telnet.py",
        "p2_telnet_blob": "d15669eb61f2afdf4d0d177191124ef8f13713e0",
        "p1_parser_module": "src/ywd1278/console/local.py",
        "p1_parser_blob": "9fed5416ca9123811413f4ef284abff0006a48dd",
        "package_manifest_blob": "9331c09b7f1e3c7111e437f3007e1e2c14716eb3",
        "modified": False,
    }
    assert git_blob(frozen["p2_telnet_module"]) == frozen["p2_telnet_blob"]
    assert git_blob(frozen["p1_parser_module"]) == frozen["p1_parser_blob"]
    assert git_blob("pyproject.toml") == frozen["package_manifest_blob"]

    assert data["credential_policy"] == {
        "hash_scheme": "pbkdf2-sha256",
        "default_iterations": 310000,
        "minimum_iterations": 200000,
        "maximum_iterations": 1000000,
        "salt_bytes": 16,
        "digest_bytes": 32,
        "username_max_chars": 32,
        "password_min_chars": 10,
        "password_max_chars": 128,
        "auth_file_max_bytes": 1024,
        "auth_file_mode": "0600",
        "auth_file_symlink_follow": False,
        "plaintext_password_persisted": False,
    }

    assert data["authentication_policy"] == {
        "mandatory_before_shell_construction": True,
        "default_timeout_seconds": 30,
        "maximum_timeout_seconds": 300,
        "default_attempts": 3,
        "maximum_attempts": 5,
        "reconnect_requires_authentication": True,
        "failed_auth_reaches_command_parser": False,
    }

    assert data["network_policy"] == {
        "transport": "plaintext-telnet",
        "transport_encrypted": False,
        "private_lan_only": True,
        "default_bind": "127.0.0.1",
        "default_port": 8023,
        "allowed_bind_scopes": [
            "ipv4-loopback",
            "rfc1918-10.0.0.0/8",
            "rfc1918-172.16.0.0/12",
            "rfc1918-192.168.0.0/16",
        ],
        "allowed_client_scopes": [
            "ipv4-loopback",
            "rfc1918-10.0.0.0/8",
            "rfc1918-172.16.0.0/12",
            "rfc1918-192.168.0.0/16",
        ],
        "wildcard_bind": False,
        "public_bind": False,
        "hostname_bind": False,
        "ipv6_bind": False,
        "wan_exposure_qualified": False,
    }

    for key, value in data["session_policy"].items():
        assert value is True, (key, value)

    tests = data["host_tests"]
    assert tests["regression_tests_run"] == 11
    assert tests["regression_tests_passed"] == 11
    for key, value in tests.items():
        if key not in {"regression_tests_run", "regression_tests_passed"}:
            assert value == "pass", (key, value)

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

    for key, value in data["safety"].items():
        assert value is False, (key, value)

    assert data["host_qualification_complete"] is True
    assert data["target_pi_private_lan_smoke_pending"] is True
    assert data["phase_complete"] is False

    print("YWD1278_0E_P3_HOST_QUALIFICATION=PASS")
    print("QUALIFIED_IMPLEMENTATION_HEAD=dd58fbd3f1eade8227c0514751046201d2fb1e07")
    print("DEDICATED_CI_RUN=33832163068_SUCCESS")
    print("P3_REGRESSION_TESTS=11_OF_11_PASS")
    print("FROZEN_0E_P1_P2_HASHES=PASS")
    print("AUTH_BEFORE_COMMAND_SHELL=YES")
    print("AUTH_FILE_MODE=0600_NO_SYMLINK_FOLLOW")
    print("BIND_CLIENT_SCOPE=LOOPBACK_OR_RFC1918_IPV4_ONLY")
    print("TELNET_ENCRYPTION=NO_PRIVATE_LAN_ONLY")
    print("PUBLIC_WILDCARD_WAN_BIND=ABSENT")
    print("PTY_SERIAL_DATABASE_WRITE_TX=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    print("TARGET_PI_PRIVATE_LAN_SMOKE=PENDING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
