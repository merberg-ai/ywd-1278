#!/usr/bin/env python3
"""Architecture/safety contract for fresh-install Stage E installer integration."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

FROZEN_STAGE_D = {
    "src/ywd1278/service/appliance.py": "fa1b086d6d8fa40b537c002dbeec34fdc6532396",
    "src/ywd1278/service/observability.py": "ead3167c67a49e993e42bdb2f3710096bfa0f99a",
    "src/ywd1278/service/classic_console.py": "7763a0973f81b69cbdd91de375aaac09d4b0ff77",
    "src/ywd1278/daemon.py": "eec0c9b574d47b6ee0e6d7492d811156d6b76b86",
    "config/ywd-1278.example.toml": "6dbb2edcba96040c71b81778d4fa969cea15baa0",
    "systemd/ywd-1278.service": "ab7dc6aa6af8237d20e41a1357083f0321fd7062",
    "systemd/ywd-1278-install-resume.service": "b366117e2423ffff7e47dd807179f856edaaa76a",
    "firmware/qualification/0b-product-classic-console-stage-d.json": "1a02419245d41968a13b84ed5bdae6f116c1fd36",
    "tests/product_classic_console_stage_d_test.py": "22545d4dcb67dc65b8aebb2272a6731df1bb6199",
    "tests/product_full_daemon_stage_d_test.py": "cb7fa0922494b86f009cd87992fa7dce824318e5",
    "tests/product_classic_console_stage_d_contract_test.py": "dfcb41431d60ea1e44ca1af968767bbfad897999",
}

FROZEN_INSTALLER_SUPPORT = {
    "installer/bootstrap.sh": "6907a539cbc10a9e750c6dba975f5a87c3fd1db1",
    "installer/hardware-detect.sh": "9406e6c6f929244afadd2eca14ebeacbf364f2f4",
    "installer/platform.sh": "db62d5d4682df163691bcfbb7e8f659867f10b0c",
    "installer/lib/ui.sh": "014ad542a7fe68b73160b44650b89716263fb980",
}


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
    assert_blobs(FROZEN_STAGE_D, "frozen Stage D")
    assert_blobs(FROZEN_INSTALLER_SUPPORT, "frozen installer support")

    install = (ROOT / "installer/install.sh").read_text(encoding="utf-8")
    setup = (ROOT / "installer/setup.sh").read_text(encoding="utf-8")
    resume = (ROOT / "installer/resume.sh").read_text(encoding="utf-8")
    readiness_path = ROOT / "src/ywd1278/install/readiness.py"
    readiness = readiness_path.read_text(encoding="utf-8")

    # Stage E may stage/configure the qualified runtime, but it still has no
    # authority to enable/start the packet service or write firmware.
    required_install = (
        "systemctl disable --now ywd-1278.service",
        "ywd1278.install.readiness",
        'YWD1278_RUNTIME_CONFIG_READY=',
        'SERVICE_ENABLED=NO',
        'RF_TRANSMITTED=NO',
        'FLASH_WRITTEN=NO',
        "Product runtime readiness",
        "pending guarded firmware verification",
    )
    for token in required_install:
        assert token in install, f"missing Stage-E installer token: {token}"

    required_resume = (
        "systemctl disable --now ywd-1278.service",
        "ywd1278.install.readiness",
        'YWD1278_RUNTIME_CONFIG_READY=',
        'SERVICE_ENABLED=NO',
        'RF_TRANSMITTED=NO',
        'FLASH_WRITTEN=NO',
    )
    for token in required_resume:
        assert token in resume, f"missing Stage-E resume token: {token}"

    for source_name, source in (("install", install), ("resume", resume)):
        for forbidden in (
            "systemctl start ywd-1278.service",
            "systemctl enable ywd-1278.service",
            "systemctl enable --now ywd-1278.service",
            "hat_control.py flash",
            "firmware_flash",
            "flash-qualified",
        ):
            assert forbidden not in source, f"{source_name} gained forbidden authority: {forbidden}"

    # The interactive setup must now emit the exact product PTY profile and
    # preserve the no-TX/no-auto-flash boundary.
    for token in (
        "tx_enabled = false",
        "allow_automatic_flash = false",
        "pty_enabled = true",
        'pty_link = "/run/ywd-1278/tnc"',
        "Pseudo-serial TNC: /run/ywd-1278/tnc",
    ):
        assert token in setup, f"setup missing product safety/profile token: {token}"

    # Runtime readiness happens only after interactive setup had a chance to
    # write the final product configuration.
    assert install.index('bash "$SOURCE_ROOT/installer/setup.sh"') < install.index(
        'section "Product runtime readiness"'
    )
    assert resume.index('ok "Configuration bound to detected HAT target: $target"') < resume.index(
        'section "Product runtime readiness"'
    )
    assert resume.index('section "Product runtime readiness"') < resume.index('rm -f "$STATE_FILE"')

    # The readiness checker itself is configuration-only.  Importing the
    # qualified typed config loaders is allowed; direct runtime capabilities are not.
    modules = imported_modules(readiness_path)
    for forbidden_prefix in (
        "ywd1278.modem",
        "ywd1278.tx",
        "ywd1278.kiss.server",
        "socket",
        "subprocess",
        "serial",
        "threading",
    ):
        assert not any(module.startswith(forbidden_prefix) for module in modules), (
            f"readiness checker gained forbidden dependency: {forbidden_prefix}"
        )
    for forbidden_token in (
        "/dev/ttyAMA0",
        "os.open(",
        "serve_forever",
        "openpty",
        "systemctl",
        "stm32flash",
        "RX_START",
        "TX_ACCEPT",
    ):
        assert forbidden_token not in readiness, (
            f"readiness checker gained runtime/hardware token: {forbidden_token}"
        )

    for required in (
        'YWD1278_INSTALL_RUNTIME_READINESS=',
        'MODEM_UART_OPENED=NO',
        'RF_TRANSMITTED=NO',
        'FLASH_WRITTEN=NO',
        'TX_ENABLED',
        'AUTO_FLASH_ENABLED',
        'KISS_CONSOLE_PORT_COLLISION',
        'PTY_LINK_NONPRODUCT',
    ):
        assert required in readiness, f"missing readiness contract token: {required}"

    print("YWD1278_STAGE_E_INSTALLER_RUNTIME_CONTRACT=PASS")
    print("FROZEN_STAGE_D_DAEMON_GRAPH=PASS")
    print("FROZEN_SYSTEMD_PRODUCT_UNIT=PASS")
    print("FROZEN_HARDWARE_PLATFORM_DETECTION=PASS")
    print("SETUP_PRODUCT_PTY_PROFILE=PASS")
    print("INSTALLER_RUNTIME_READINESS_ZERO_IO=PASS")
    print("UNSAFE_CONFIG_FAILS_CLOSED=REQUIRED")
    print("INCOMPLETE_CONFIG_STAYS_DISABLED=REQUIRED")
    print("SERVICE_ENABLE_AUTHORITY=ABSENT")
    print("FIRMWARE_WRITE_AUTHORITY=ABSENT")
    print("RF_UART_ACTIVITY_REQUIRED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
