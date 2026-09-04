#!/usr/bin/env python3
"""Architecture/safety contract for fresh-install Stage D classic console composition."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FROZEN_STAGE_C = {
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/service/observability.py": "ead3167c67a49e993e42bdb2f3710096bfa0f99a",
    "firmware/qualification/0b-product-observability-stage-c.json": "9ceac951d6a5aa900c06cbd74201d7b1a1ac920a",
    "tests/product_observability_stage_c_test.py": "7acac5cbac56c1a8a5d69e27f035a7b4c66be09f",
    "tests/product_observability_stage_c_contract_test.py": "8300eb6a5dc1c1ffb7a0f1ead8b221fe296cd1ad",
}

FROZEN_0E = {
    "src/ywd1278/console/local.py": "9fed5416ca9123811413f4ef284abff0006a48dd",
    "src/ywd1278/console/telnet.py": "d15669eb61f2afdf4d0d177191124ef8f13713e0",
    "src/ywd1278/console/auth.py": "0bdacaca9807012954c3362a8c0d92c4c1e21d40",
    "src/ywd1278/console/lan_telnet.py": "a53bad81aa3ffa167375517bb48a19e8ac9143f3",
    "src/ywd1278/console/pty_serial.py": "c0ba2a3278ac1e790bf383fc12a220ae327255ba",
    "src/ywd1278/console/classic.py": "4d6dfd5d439fb5dfd6ff586c2a47c37724381b2e",
    "tests/classic_tnc_vocabulary_test.py": "d8e10890759d9d48ef8891be3cc4c74d58d3acc3",
    "tests/classic_tnc_vocabulary_contract_test.py": "620b8900c15044130d7da954c85bc39847c54dae",
    "tests/classic_tnc_vocabulary_qualification_contract_test.py": "5d50464e23cd76bb610f42aab4a70e2436fc1296",
    "tests/classic_tnc_vocabulary_target_pi_evidence_contract_test.py": "151248d796721f4f5d604a24107ef9564637a0a5",
    "pyproject.toml": "9331c09b7f1e3c7111e437f3007e1e2c14716eb3",
}

FROZEN_SYSTEMD = {
    "systemd/ywd-1278.service": "ab7dc6aa6af8237d20e41a1357083f0321fd7062",
}

ACCIDENTAL_MARKERS = (
    "docs/qualifications/.checkpoint-final",
    "docs/qualifications/.no-more",
    "docs/qualifications/.oops",
    "docs/qualifications/.stage-c-checkpoint",
    "docs/qualifications/.stage-c-final",
    "docs/qualifications/.stop",
    "docs/qualifications/.this-is-bad",
)


def git_blob(path: str) -> str:
    payload = (ROOT / path).read_bytes()
    return hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()


def assert_blobs(expected: dict[str, str], label: str) -> None:
    for path, blob in expected.items():
        actual = git_blob(path)
        assert actual == blob, f"{label} drift: {path}: expected {blob}, got {actual}"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def main() -> int:
    assert_blobs(FROZEN_STAGE_C, "frozen Stage C")
    assert_blobs(FROZEN_0E, "frozen 0E")
    assert_blobs(FROZEN_SYSTEMD, "frozen systemd")

    for marker in ACCIDENTAL_MARKERS:
        assert not (ROOT / marker).exists(), f"accidental marker still present: {marker}"

    console_path = ROOT / "src/ywd1278/service/classic_console.py"
    daemon_path = ROOT / "src/ywd1278/daemon.py"
    console_source = console_path.read_text(encoding="utf-8")
    daemon_source = daemon_path.read_text(encoding="utf-8")
    modules = imported_modules(console_path)

    forbidden_import_prefixes = (
        "ywd1278.modem",
        "ywd1278.kiss",
        "ywd1278.tx",
        "serial",
        "sqlite3",
        "subprocess",
    )
    for module in modules:
        assert not module.startswith(forbidden_import_prefixes), (
            f"Stage-D console acquired forbidden dependency: {module}"
        )

    for token in (
        "/dev/ttyAMA0",
        "/dev/serial",
        "GPIO",
        "RX_START",
        "RX_STOP",
        "TX_ACCEPT",
        "set_rx_frequency",
        "apply_tx_qualification_profile",
        "flash",
        "option_bytes",
        "retention.apply",
    ):
        assert token not in console_source, f"forbidden capability token in console owner: {token}"

    required_console_tokens = (
        "make_classic_shell",
        "MonitorPolicyState()",
        "TelnetTNCServer",
        "AuthenticatedLanTNCServer",
        "VirtualPTYTNC",
        "load_credential_file",
        "RFC1918 console listener requires console.auth_file",
        "console listener is restricted to loopback or RFC1918 IPv4",
        "self._pty_stop.set()",
        "server.shutdown()",
        "server.server_close()",
    )
    for token in required_console_tokens:
        assert token in console_source, f"missing Stage-D console contract token: {token}"

    required_daemon_tokens = (
        "load_product_classic_console_config",
        "ProductClassicConsole(",
        "diagnostics_snapshot=engine.diagnostics_snapshot",
        "mheard_db=engine.mheard_db",
        "console.start()",
        "console.check_health()",
        "console.stop()",
        "engine.stop()",
    )
    for token in required_daemon_tokens:
        assert token in daemon_source, f"missing daemon composition token: {token}"
    assert daemon_source.index("console.stop()") < daemon_source.index("engine.stop()"), (
        "classic consoles must stop before Stage-C packet/observability teardown"
    )

    # Stage D changes daemon composition and the example configuration only;
    # the Stage-C engine and every frozen 0E parser/transport/personality stay exact.
    print("YWD1278_STAGE_D_CLASSIC_CONSOLE_CONTRACT=PASS")
    print("FROZEN_STAGE_C_ENGINE_OBSERVABILITY=PASS")
    print("FROZEN_0E_P1_P2_P3_P4_P5=PASS")
    print("ACCIDENTAL_QUALIFICATION_MARKERS=ABSENT")
    print("CONSOLE_MODEM_KISS_TX_DEPENDENCY=ABSENT")
    print("LOOPBACK_P2_PRIVATE_AUTH_P3_PTY_P4_CLASSIC_P5=COMPOSED")
    print("CONSOLE_SHUTDOWN_BEFORE_STAGE_C_TEARDOWN=PASS")
    print("RF_UART_FLASH_GPIO_ACTIVITY_REQUIRED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
