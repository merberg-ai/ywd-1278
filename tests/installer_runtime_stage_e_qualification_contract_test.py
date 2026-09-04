#!/usr/bin/env python3
"""Qualification-evidence contract for fresh-install Stage E."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "firmware/qualification/0b-product-installer-runtime-stage-e.json"


def git_blob(path: str) -> str:
    payload = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert data["schema"] == 1
    assert data["phase"] == "fresh-install-stage-e-installer-runtime"
    assert data["status"] == "host-qualified"
    assert data["base_checkpoint"] == {
        "branch": "checkpoint/product-classic-console-stage-d-host-qualified",
        "sha": "355d1f97a8bb8f9ce41b75b6ac1c0d576036d85a",
    }
    assert data["branch"] == "dev-fresh-install-stage-e-installer-runtime"

    implementation = data["implementation"]
    for prefix in ("readiness", "install", "setup", "resume", "regression", "contract", "workflow"):
        path = implementation[f"{prefix}_path"]
        expected = implementation[f"{prefix}_blob"]
        actual = git_blob(path)
        assert actual == expected, f"Stage-E evidence drift: {path}: {actual} != {expected}"

    frozen = data["frozen_stage_d"]
    expected_frozen = {
        "src/ywd1278/service/appliance.py": frozen["appliance_blob"],
        "src/ywd1278/service/observability.py": frozen["observability_blob"],
        "src/ywd1278/service/classic_console.py": frozen["classic_console_blob"],
        "src/ywd1278/daemon.py": frozen["daemon_blob"],
        "config/ywd-1278.example.toml": frozen["example_config_blob"],
        "systemd/ywd-1278.service": frozen["product_systemd_unit_blob"],
        "systemd/ywd-1278-install-resume.service": frozen["resume_systemd_unit_blob"],
        "firmware/qualification/0b-product-classic-console-stage-d.json": frozen["stage_d_manifest_blob"],
    }
    for path, expected in expected_frozen.items():
        assert git_blob(path) == expected, f"frozen Stage-D drift: {path}"
    assert frozen["modified"] is False

    support = data["frozen_installer_support"]
    expected_support = {
        "installer/bootstrap.sh": support["bootstrap_blob"],
        "installer/hardware-detect.sh": support["hardware_detect_blob"],
        "installer/platform.sh": support["platform_blob"],
        "installer/lib/ui.sh": support["ui_blob"],
    }
    for path, expected in expected_support.items():
        assert git_blob(path) == expected, f"frozen installer-support drift: {path}"
    assert support["modified"] is False

    readiness = data["runtime_readiness"]
    assert readiness["configuration_only"] is True
    assert readiness["ready_exit_code"] == 0
    assert readiness["incomplete_exit_code"] == 10
    assert readiness["unsafe_exit_code"] == 20
    assert readiness["safe_example_is_incomplete"] is True
    assert readiness["product_pty_link"] == "/run/ywd-1278/tnc"
    assert readiness["tx_enabled_is_unsafe"] is True
    assert readiness["automatic_flash_is_unsafe"] is True
    assert readiness["kiss_console_port_collision_rejected"] is True

    policy = data["installer_policy"]
    assert policy["setup_emits_product_pty_profile"] is True
    assert policy["setup_forces_tx_disabled"] is True
    assert policy["setup_forces_automatic_flash_disabled"] is True
    assert policy["unsafe_configuration_is_fatal"] is True
    assert policy["incomplete_configuration_keeps_service_disabled"] is True
    assert policy["ready_configuration_keeps_service_disabled"] is True
    assert policy["packet_service_enable_authority"] is False
    assert policy["packet_service_start_authority"] is False
    assert policy["firmware_write_authority"] is False
    assert policy["firmware_backup_authority_added"] is False

    host = data["host_qualification"]
    assert host["qualified_implementation_head"] == "68f52d6432c3d9580a9f5ecf7a3fe84f4d07d6d8"
    assert host["ci_run_id"] == 33876037818
    assert host["ci_conclusion"] == "success"
    for key in (
        "bash_syntax_install_setup_resume",
        "readiness_regression",
        "installer_architecture_contract",
        "packaged_temp_venv_install",
        "packaged_readiness_safe_example_incomplete",
        "stage_d_console_replay",
        "stage_d_full_daemon_graph_replay",
        "stage_d_contract_replay",
        "stage_c_behavior_preserved",
        "stage_a_freeze_preserved",
        "frozen_0e_evidence_replayed",
        "frozen_0d_evidence_preserved",
        "sustained_tnc_physical_evidence_preserved",
        "zero_io_daemon_self_test",
    ):
        assert host[key] == "pass", f"qualification evidence not pass: {key}"

    assert data["hardware_activity"] == {
        "uart": False,
        "rf": False,
        "flash": False,
        "gpio": False,
        "option_bytes": False,
        "systemd_service_started": False,
    }
    assert all(data["not_in_stage_e"].values())
    assert "protected-stock-backup" in data["next_stage"]
    assert "readback" in data["next_stage"]

    print("YWD1278_STAGE_E_INSTALLER_RUNTIME_EVIDENCE=PASS")
    print("QUALIFIED_IMPLEMENTATION_HEAD=68f52d6432c3d9580a9f5ecf7a3fe84f4d07d6d8")
    print("EXACT_HEAD_CI_RUN=33876037818")
    print("PACKAGED_TEMP_VENV=PASS")
    print("SAFE_EXAMPLE=INCOMPLETE_NOT_UNSAFE")
    print("TX_AUTOFLASH_UNSAFE=PASS")
    print("SERVICE_ENABLE_AUTHORITY=ABSENT")
    print("FIRMWARE_WRITE_AUTHORITY=ABSENT")
    print("STAGE_D_GRAPH_PRESERVED=PASS")
    print("RF_UART_FLASH_GPIO_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
