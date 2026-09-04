#!/usr/bin/env python3
"""Immutable host-qualification contract for 0E-P2 loopback Telnet console."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware" / "qualification" / "0e-p2-telnet-console-host.json"


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    data = json.loads(EVIDENCE.read_text(encoding="utf-8"))

    assert data["schema"] == 1
    assert data["phase"] == "0E-P2"
    assert data["stage"] == "loopback-telnet-command-console"
    assert data["status"] == "host-qualified"
    assert data["base_checkpoint"] == "checkpoint/0e-p1-local-tnc-console-host-qualified"
    assert data["base_sha"] == "c51484fce731fea0bb62ab923f3aa66ef214a1b5"
    assert data["qualified_implementation_head"] == "37bcc6808e5287bfd49ba37d56b1a7d5185f8b1c"
    assert data["dedicated_ci"] == {
        "workflow": "0e-p2-telnet-console-ci",
        "run_id": 33829902701,
        "result": "success",
    }

    expected_blobs = {
        "src/ywd1278/console/telnet.py": "d15669eb61f2afdf4d0d177191124ef8f13713e0",
        "tests/telnet_tnc_console_test.py": "7ac266f0725eccf8981245ce0b80664617da7cf2",
        "tests/telnet_tnc_console_contract_test.py": "8a904b0976f24c06092e170e5adb32fd4bc64d3b",
    }
    assert data["implementation_blobs"] == expected_blobs
    for path, expected in expected_blobs.items():
        actual = git_blob(path)
        assert actual == expected, (path, expected, actual)

    frozen = data["frozen_p1"]
    assert frozen == {
        "parser_module": "src/ywd1278/console/local.py",
        "parser_blob": "9fed5416ca9123811413f4ef284abff0006a48dd",
        "package_manifest_blob": "9331c09b7f1e3c7111e437f3007e1e2c14716eb3",
        "modified": False,
    }
    assert git_blob("src/ywd1278/console/local.py") == frozen["parser_blob"]
    assert git_blob("pyproject.toml") == frozen["package_manifest_blob"]

    interface = data["interface"]
    assert interface == {
        "entry_point": "python -m ywd1278.console.telnet",
        "transport": "ipv4-loopback-telnet-only",
        "default_bind": "127.0.0.1",
        "default_port": 8023,
        "prompt": "cmd:",
        "max_command_chars": 256,
        "default_max_clients": 4,
        "hard_max_clients": 16,
        "default_idle_timeout_seconds": 300,
        "default_max_session_seconds": 3600,
        "default_max_commands": 1024,
        "recv_chunk_bytes": 512,
        "max_telnet_negotiations": 32,
        "exact_token_commands": True,
        "command_abbreviation": False,
        "shell_escape": False,
        "dynamic_execution": False,
    }

    assert data["telnet_policy"] == {
        "optional_features_enabled": False,
        "will_wont_do_dont_refused": True,
        "unsupported_control_sequence_fatal": True,
        "nul_data_fatal": True,
        "non_nvt_control_fatal": True,
        "oversized_line_discard_then_recover": True,
        "crlf_supported": True,
        "backspace_supported": True,
    }

    assert data["session_policy"] == {
        "shell_per_connection": True,
        "monitor_policy_per_connection": True,
        "disconnect_reconnect_resets_session_monitor_policy": True,
        "shared_modem_owner": False,
        "shared_packet_subscriber": False,
        "shared_tx_path": False,
    }

    assert data["exposure"] == {
        "wildcard_bind": False,
        "lan_bind": False,
        "public_bind": False,
        "hostname_bind": False,
        "ipv6_bind": False,
        "authentication": False,
        "authentication_required_before_broader_bind": True,
    }

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
    assert data["target_pi_loopback_smoke_pending"] is True
    assert data["phase_complete"] is False

    print("YWD1278_0E_P2_HOST_QUALIFICATION=PASS")
    print("QUALIFIED_IMPLEMENTATION_HEAD=37bcc6808e5287bfd49ba37d56b1a7d5185f8b1c")
    print("DEDICATED_CI_RUN=33829902701_SUCCESS")
    print("FROZEN_0E_P1_PARSER_HASH=PASS")
    print("FROZEN_0E_P1_PACKAGE_MANIFEST_HASH=PASS")
    print("TELNET_IPV4_LOOPBACK_ONLY=YES")
    print("TELNET_DEFAULT_PORT=8023")
    print("CLIENT_IDLE_SESSION_COMMAND_NEGOTIATION_BOUNDS=PASS")
    print("AUTHENTICATION=ABSENT_WHILE_NON_LOOPBACK_BIND_IS_REJECTED")
    print("PTY_SERIAL_DATABASE_WRITE_TX=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    print("TARGET_PI_LOOPBACK_SMOKE=PENDING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
