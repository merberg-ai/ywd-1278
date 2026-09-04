#!/usr/bin/env python3
"""Architecture/safety contract for fresh-install Stage B product daemon."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
STAGE_A = ROOT / "firmware/qualification/0b-product-packet-engine-stage-a.json"
STAGE_B = ROOT / "firmware/qualification/0b-product-daemon-stage-b.json"

STAGE_A_MANIFEST_BLOB = "d7eaa4c24bd4fa8f9066403153be534a3d40a81b"
FROZEN_EXAMPLE_CONFIG_BLOB = "bfe240d1dbb52733bb396081bab7ff13a5c1f408"
FROZEN_SYSTEMD_UNIT_BLOB = "ab7dc6aa6af8237d20e41a1357083f0321fd7062"


def git_blob(path: str) -> str:
    return subprocess.check_output(
        ["git", "hash-object", path], cwd=ROOT, text=True
    ).strip()


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    stage_a = json.loads(STAGE_A.read_text(encoding="utf-8"))
    stage_b = json.loads(STAGE_B.read_text(encoding="utf-8"))

    assert git_blob("firmware/qualification/0b-product-packet-engine-stage-a.json") == STAGE_A_MANIFEST_BLOB
    assert stage_a["status"] == "qualified"
    assert stage_a["component_count"] == 29
    assert stage_a["integration_status"]["packet_engine_component_boundary_frozen"] is True
    for path, expected in stage_a["components"].items():
        actual = git_blob(path)
        assert actual == expected, f"Stage-A frozen component drifted: {path} {actual} != {expected}"

    assert git_blob("config/ywd-1278.example.toml") == FROZEN_EXAMPLE_CONFIG_BLOB
    assert git_blob("systemd/ywd-1278.service") == FROZEN_SYSTEMD_UNIT_BLOB

    assert stage_b["schema"] == 1
    assert stage_b["phase"] == "fresh-install-stage-b-product-daemon"
    assert stage_b["status"] in {"staged", "host-qualified"}
    assert stage_b["base_checkpoint"] == {
        "branch": "checkpoint/product-packet-engine-stage-a-qualified",
        "sha": "704814a7c68099ca6bc7aef041d531014cb47d78",
    }
    assert stage_b["stage_a_component_count"] == 29
    assert stage_b["stage_a_components_modified"] is False
    assert stage_b["hardware_activity"]["uart"] is False
    assert stage_b["hardware_activity"]["rf"] is False
    assert stage_b["hardware_activity"]["flash"] is False
    assert stage_b["hardware_activity"]["gpio"] is False
    assert stage_b["product_policy"]["safe_default_tx_disabled"] is True
    assert stage_b["product_policy"]["tx_disabled_data_rejected_at_ingress"] is True
    assert stage_b["product_policy"]["tx_enabled_profile"] == {
        "frequency_hz": 145050000,
        "power": 200,
        "arbitrary_profile_permitted": False,
    }
    assert stage_b["product_policy"]["automatic_flash_permitted"] is False
    assert stage_b["product_policy"]["beacon_permitted"] is False
    assert stage_b["product_policy"]["kiss_bind_scope"] == "127.0.0.1-only"

    appliance = text("src/ywd1278/service/appliance.py")
    daemon = text("src/ywd1278/daemon.py")

    required_appliance = (
        "class ProductPacketEngine",
        "class ProductTNCBackend",
        "TXModemOwner(",
        "ContextualTXDelayRouter(",
        "ContextualHalfDuplexSubmitter(",
        "ThreadSafeKISSDataAdmissionQueue(",
        "SustainedTNCRuntime(",
        "TNCControlBackend.reject_client_message(self, message)",
        "QUALIFIED_TX_FREQUENCY_HZ = 145_050_000",
        "QUALIFIED_TX_POWER = 200",
        "owner.apply_tx_qualification_profile(timeout=1.5)",
        "owner.set_rx_frequency(self.config.frequency_hz, timeout=1.5)",
        "runtime.start(timeout=1.5)",
        "start_server_thread(",
        "stop_server_thread(self.kiss_server, self.kiss_thread)",
        "self.runtime.stop(timeout=3.0)",
        "self.router.close()",
        "self.owner.rx_stop(timeout=1.5)",
        "self.owner.stop(timeout=2.0)",
    )
    for marker in required_appliance:
        assert marker in appliance, marker

    # Product startup exposes KISS only after the sustained runtime has passed
    # its initial exact-firmware/RX-active gate.
    start_body = appliance[appliance.index("    def start(self) -> None:"):appliance.index("    def check_health(self) -> None:")]
    assert start_body.index("runtime.start(timeout=1.5)") < start_body.index("start_server_thread(")

    # Shutdown first closes ingress, then the scheduler/router, then RX/UART.
    cleanup = appliance[appliance.index("    def _cleanup("):]
    assert cleanup.index("stop_server_thread") < cleanup.index("self.runtime.stop")
    assert cleanup.index("self.runtime.stop") < cleanup.index("self.router.close")
    assert cleanup.index("self.router.close") < cleanup.index("self.owner.rx_stop")
    assert cleanup.index("self.owner.rx_stop") < cleanup.index("self.owner.stop")

    # This orchestration layer is not allowed to become a firmware programmer,
    # GPIO helper, shell runner, or arbitrary modem-transaction escape hatch.
    forbidden_appliance = (
        "import subprocess",
        "from subprocess",
        "import RPi.GPIO",
        "/sys/class/gpio",
        "firmware.flash",
        "installer.",
        "raw_transact",
        "def transmit_selector_burst",
        "def apply_tx_qualification_profile",
    )
    for marker in forbidden_appliance:
        assert marker not in appliance, marker

    required_daemon = (
        "def run_daemon(",
        "ProductPacketEngine(",
        "signal.SIGINT",
        "signal.SIGTERM",
        "stop_event.set()",
        "YWD1278_PRODUCT_PACKET_ENGINE=RUNNING",
        "YWD1278_PRODUCT_PACKET_ENGINE=STOPPED",
        "--framework-self-test",
        "YWD1278_FRAMEWORK_SELF_TEST=PASS",
        "MODEM_UART_OPENED=NO",
        "RF_TRANSMITTED=NO",
    )
    for marker in required_daemon:
        assert marker in daemon, marker
    assert "--transmit" not in daemon
    assert "--tx" not in daemon
    assert "p8_fake_modem" not in daemon
    assert "qualify_live" not in daemon
    assert "TXModemOwner" not in daemon
    assert "posix_serial_transport_factory" not in daemon

    print("YWD1278_FRESH_INSTALL_STAGE_B_DAEMON_CONTRACT=PASS")
    print("STAGE_A_COMPONENT_BLOBS=29_OF_29_FROZEN")
    print("PRODUCT_DAEMON=ASSEMBLED_BY_COMPOSITION")
    print("TX_DISABLED_DATA=REJECT_AT_INGRESS")
    print("TX_PROFILE=145050000_HZ_POWER_200_ONLY")
    print("KISS_BIND=127.0.0.1_ONLY")
    print("SIGINT_SIGTERM=GRACEFUL_STOP_EVENT")
    print("FLASH_GPIO_OPTION_BYTES=ABSENT")
    print("STAGE_B_HARDWARE_ACTIVITY=NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
