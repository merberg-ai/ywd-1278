#!/usr/bin/env python3
"""Freeze 0E-P5 host qualification evidence and implementation blobs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "firmware/qualification/0e-p5-classic-vocabulary-host.json"

EXPECTED = {
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
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert evidence["schema"] == 1
    assert evidence["phase"] == "0E-P5"
    assert evidence["stage"] == "classic-tnc2-mfj-command-vocabulary"
    assert evidence["status"] == "host-qualified"
    assert evidence["base_checkpoint"] == {
        "branch": "checkpoint/0e-p4-virtual-pty-console-target-pi-qualified",
        "sha": "b7b317ca7f6528ab344f22d78bfd10aa7afc55a0",
    }
    qualified = evidence["qualified_implementation"]
    assert qualified["head_sha"] == "ab9e922b31bfb57b9a8be11c70a812dc1b0c0da3"
    assert qualified["dedicated_ci_run"] == 33836726120
    assert qualified["dedicated_ci_conclusion"] == "success"

    for relative, expected in EXPECTED.items():
        actual = git_blob_sha(ROOT / relative)
        assert actual == expected, f"frozen blob changed: {relative}: {actual} != {expected}"
    for relative, expected in evidence["p5_blobs"].items():
        assert EXPECTED[relative] == expected
    for relative, expected in evidence["frozen_boundaries"].items():
        assert EXPECTED[relative] == expected

    policy = evidence["vocabulary_policy"]
    assert policy["generic_abbreviation_engine"] is False
    assert policy["safe_aliases"] == {
        "DISP": "DISPLAY",
        "MH": "MHEARD",
        "VER": "VERSION",
        "STAT": "STATUS",
        "HEAL": "HEALTH",
    }
    assert policy["display_scope"] == "MONITOR only"
    assert policy["display_values"] == ["MCOM", "MCON", "MRPT"]
    assert {"CONNECT", "DISCONNECT", "RECONNECT"} <= set(policy["deferred_0g"])
    assert {"UNPROTO", "CONVERSE", "BEACON", "BTEXT"} <= set(policy["deferred_0f"])
    assert {"TX", "XMITOK", "KISS", "TXDELAY"} <= set(
        policy["deferred_tx_parameter_or_mode_controls"]
    )
    assert set(policy["disabled_destructive_commands"]) == {
        "MHCLEAR",
        "RESET",
        "RESTART",
        "SHELL",
    }

    results = evidence["host_results"]
    assert results["regression_tests_passed"] == 10
    assert results["regression_tests_total"] == 10
    for key in (
        "architecture_contract",
        "safe_aliases",
        "display_monitor",
        "deferred_tx_link_commands_inert",
        "ambiguous_abbreviations_fail_closed",
        "frozen_p2_real_telnet_composition",
        "frozen_p4_real_kernel_pty_composition",
        "deterministic_target_helper_on_host",
        "detach_reopen_state_reset",
        "frozen_p4_preservation",
        "frozen_p3_preservation",
        "frozen_p2_preservation",
        "frozen_p1_preservation",
        "frozen_0d_preservation",
        "frozen_sustained_0c_runtime_preservation",
    ):
        assert results[key] == "pass", key

    assert all(value is False for value in evidence["safety"].values())
    assert evidence["host_qualification_complete"] is True
    assert evidence["target_pi_classic_vocabulary_smoke_pending"] is True
    assert evidence["phase_complete"] is False

    print("YWD1278_0E_P5_HOST_QUALIFICATION=PASS")
    print("QUALIFIED_IMPLEMENTATION_HEAD=ab9e922b31bfb57b9a8be11c70a812dc1b0c0da3")
    print("DEDICATED_CI_RUN=33836726120_SUCCESS")
    print("P5_REGRESSION_TESTS=10_OF_10_PASS")
    print("SAFE_ALIASES=DISP_MH_VER_STAT_HEAL")
    print("DISPLAY_SCOPE=MONITOR_ONLY")
    print("GENERIC_ABBREVIATION_ENGINE=ABSENT")
    print("TX_LINK_COMMANDS=RECOGNIZED_BUT_DEFERRED")
    print("FROZEN_0E_P1_P2_P3_P4_HASHES=PASS")
    print("NETWORK_HARDWARE_SERIAL_MODEM_KISS_TX=ABSENT")
    print("UART_RF_ACTIVITY=NONE")
    print("TARGET_PI_CLASSIC_VOCABULARY_SMOKE=PENDING")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
