#!/usr/bin/env python3
"""Architecture/safety contract for fresh-install Stage C observability."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STAGE_A = ROOT / "firmware/qualification/0b-product-packet-engine-stage-a.json"
STAGE_B = ROOT / "firmware/qualification/0b-product-daemon-stage-b.json"
STAGE_C = ROOT / "firmware/qualification/0b-product-observability-stage-c.json"

STAGE_A_MANIFEST_BLOB = "d7eaa4c24bd4fa8f9066403153be534a3d40a81b"
STAGE_B_MANIFEST_BLOB = "7d3aa83b29b00a2f37de43f5db88fa4ebfa941c5"
STAGE_B_DAEMON_BLOB = "f080abda1792577269b11833deec45edd4e95535"
FROZEN_EXAMPLE_CONFIG_BLOB = "bfe240d1dbb52733bb396081bab7ff13a5c1f408"
FROZEN_SYSTEMD_UNIT_BLOB = "ab7dc6aa6af8237d20e41a1357083f0321fd7062"

FROZEN_0D_MODULES = {
    "src/ywd1278/monitor/__init__.py": "ae5cd85e43bf9da78d4fecad0954e6237427fe6c",
    "src/ywd1278/monitor/diagnostics.py": "0f23c1232b51e2f5fbd1a3d4c179e0c94ce4116a",
    "src/ywd1278/monitor/mheard.py": "09a9dd17cee8eff2ef9aa3df418a3e575e1f985e",
    "src/ywd1278/monitor/policy.py": "f7d105554f682dfc533a09bff8823b192e5debe9",
    "src/ywd1278/monitor/retention.py": "1e08367d98f39e15eaeb855ef5e6e6b39eef9302",
    "src/ywd1278/monitor/sqlite_log.py": "cd43f6e284061c19bd8bade8e1449986a9f99374",
    "src/ywd1278/monitor/stream.py": "703b7e803d39d915b60d79c30c154151e3820098",
}

FROZEN_0D_EVIDENCE = {
    "firmware/qualification/0d-p1-monitor-stream-host.json": "6058a5bde2c2045c1ed3d7b70ee69a1c8cc6cf88",
    "firmware/qualification/0d-p1-p2-target-pi-sanity-2026-09-03.json": "f5141f84a0ae5f1d6be131ace026d53fcd11d7e0",
    "firmware/qualification/0d-p2-monitor-controls-host.json": "f29589b801107d7c092dff0c35880fcf0110063e",
    "firmware/qualification/0d-p2-monitor-controls-stage.json": "d5cb8890afc87853c36e895f19c80b4905bfd1e8",
    "firmware/qualification/0d-p3-sqlite-frame-log-host.json": "1d19201fe08558a0d46f253df6102b38efe302cf",
    "firmware/qualification/0d-p3-target-pi-sanity-2026-09-03.json": "5f58e4b937d12b3bac473701e068af69159f9459",
    "firmware/qualification/0d-p4-mheard-host.json": "e84ec8d3c6f40bb68802146e790eb407d89e496e",
    "firmware/qualification/0d-p4-target-pi-sanity-2026-09-03.json": "af21bf50e3f2d3550862ee1296e87e9e57fe1050",
    "firmware/qualification/0d-p5-retention-host.json": "0971b77c4fe4e732287a2d4fa65d9224e81175c0",
    "firmware/qualification/0d-p5-retention-target-pi-sanity-2026-09-03.json": "ab0bc4c8fac6abe30f3c15a3dfd3c54332c56db3",
    "firmware/qualification/0d-p6-diagnostics-status-host.json": "b10ae7eaab1e37a3766d7b1249863b48ac6abfa9",
    "firmware/qualification/0d-p6-diagnostics-status-target-pi-sanity-2026-09-03.json": "13348ce0146cef7efde55e6da3262c63aabe3910",
}

EXPECTED_STAGE_C_IMPLEMENTATION = {
    "src/ywd1278/service/observability.py": "ead3167c67a49e993e42bdb2f3710096bfa0f99a",
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "tests/product_observability_stage_c_test.py": "7acac5cbac56c1a8a5d69e27f035a7b4c66be09f",
}


def git_blob(path: str) -> str:
    payload = (ROOT / path).read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def require_blob(path: str, expected: str, label: str) -> None:
    actual = git_blob(path)
    assert actual == expected, f"{label} drift: {path}: {actual} != {expected}"


def imported_modules(path: str) -> set[str]:
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def main() -> int:
    require_blob(
        "firmware/qualification/0b-product-packet-engine-stage-a.json",
        STAGE_A_MANIFEST_BLOB,
        "Stage-A manifest",
    )
    require_blob(
        "firmware/qualification/0b-product-daemon-stage-b.json",
        STAGE_B_MANIFEST_BLOB,
        "Stage-B manifest",
    )
    require_blob("src/ywd1278/daemon.py", STAGE_B_DAEMON_BLOB, "Stage-B daemon")
    require_blob("config/ywd-1278.example.toml", FROZEN_EXAMPLE_CONFIG_BLOB, "example config")
    require_blob("systemd/ywd-1278.service", FROZEN_SYSTEMD_UNIT_BLOB, "systemd unit")

    stage_a = json.loads(STAGE_A.read_text(encoding="utf-8"))
    assert stage_a["component_count"] == 29
    for relative, expected in stage_a["components"].items():
        require_blob(relative, expected, "Stage-A component")

    for relative, expected in FROZEN_0D_MODULES.items():
        require_blob(relative, expected, "0D monitor module")
    for relative, expected in FROZEN_0D_EVIDENCE.items():
        require_blob(relative, expected, "0D evidence")
    for relative, expected in EXPECTED_STAGE_C_IMPLEMENTATION.items():
        require_blob(relative, expected, "Stage-C implementation")

    stage_b = json.loads(STAGE_B.read_text(encoding="utf-8"))
    assert stage_b["status"] == "host-qualified"
    assert stage_b["base_checkpoint"]["branch"] == "checkpoint/product-packet-engine-stage-a-qualified"
    assert stage_b["stage_a_component_count"] == 29
    assert stage_b["stage_a_components_modified"] is False
    assert stage_b["hardware_activity"] == {
        "uart": False,
        "rf": False,
        "flash": False,
        "gpio": False,
        "option_bytes": False,
    }

    stage_c = json.loads(STAGE_C.read_text(encoding="utf-8"))
    assert stage_c["schema"] == 1
    assert stage_c["phase"] == "fresh-install-stage-c-product-observability"
    assert stage_c["status"] in {"staged", "host-qualified"}
    assert stage_c["base_checkpoint"] == {
        "branch": "checkpoint/product-daemon-stage-b-host-qualified",
        "sha": "f223737a001410d0ebeac221fd43722670c7ee03",
    }
    assert stage_c["stage_a_component_count"] == 29
    assert stage_c["stage_a_components_modified"] is False
    assert stage_c["frozen_0d_module_count"] == 7
    assert stage_c["frozen_0d_modules_modified"] is False

    obs_imports = imported_modules("src/ywd1278/service/observability.py")
    forbidden_prefixes = (
        "ywd1278.modem",
        "ywd1278.tx",
        "ywd1278.phy",
        "subprocess",
        "serial",
    )
    for module in obs_imports:
        assert not module.startswith(forbidden_prefixes), (
            f"Stage-C observability gained forbidden capability import: {module}"
        )
    assert "ywd1278.monitor.retention" not in obs_imports

    obs_source = (ROOT / "src/ywd1278/service/observability.py").read_text(encoding="utf-8")
    assert "SQLiteRetentionController" not in obs_source
    assert "RetentionPolicy" not in obs_source
    assert "apply_retention" not in obs_source

    policy = stage_c["product_policy"]
    assert policy["tx_policy_changed"] is False
    assert policy["automatic_flash_permitted"] is False
    assert policy["automatic_retention_permitted"] is False
    assert policy["monitor_uses_existing_bounded_backend"] is True
    assert policy["sqlite_logger_registered_before_rx_runtime"] is True
    assert policy["mheard_read_only"] is True
    assert policy["diagnostics_one_shot"] is True
    assert policy["observer_problems_do_not_automatically_halt_packet_service"] is True
    assert policy["configured_logger_failure_is_health_failure"] is True

    assert stage_c["hardware_activity"] == {
        "uart": False,
        "rf": False,
        "flash": False,
        "gpio": False,
        "option_bytes": False,
    }

    print("YWD1278_FRESH_INSTALL_STAGE_C_OBSERVABILITY_CONTRACT=PASS")
    print("STAGE_A_COMPONENT_BLOBS=29_OF_29_FROZEN")
    print("FROZEN_0D_MODULES=7_OF_7")
    print("MONITOR_PIPELINE=EXISTING_BOUNDED_PACKET_EVENT_BACKEND")
    print("SQLITE_LOGGER=LIVE_ONLY_BOUNDED_SUBSCRIBER")
    print("MHEARD=READ_ONLY_SQLITE_VIEW")
    print("DIAGNOSTICS=ONE_SHOT_OBSERVER")
    print("RETENTION_AUTOMATION=ABSENT")
    print("STAGE_C_UART_RF_FLASH_GPIO=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
