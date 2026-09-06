#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


install = text("installer/install.sh")
resume = text("installer/resume.sh")
continuation = text("installer/continue-install.sh")
finalizer = text("installer/finalize-product-service.sh")
hat = text("installer/setup-hat.sh")
deploy = text("installer/deploy-product-firmware.sh")
enable = text("installer/enable-product-service.sh")

# The normal installer must prepare/audit the Pi UART before any HAT firmware or
# station configuration work. The interactive work is delegated to one shared
# continuation rather than duplicated in install.sh.
assert 'stage "2/4  Prepare the radio UART"' in install
assert "continue-install.sh" in install
assert "setup-hat.sh" not in install
assert 'bash "$SOURCE_ROOT/installer/setup.sh"' not in install
assert install.index('stage "2/4  Prepare the radio UART"') < install.index("continue-install.sh")
assert "STATE_VERSION=2" in install
assert "RUN_SETUP=$RUN_SETUP" in install
assert "BUILD_USER=$quoted_user" in install
assert "After reboot, reconnect and run:" in install

# Boot-time resume is intentionally noninteractive and must never reach HAT
# setup, station setup, firmware programming, or product service activation.
auto_start = resume.index('if [[ $AUTOMATIC -eq 1 ]]')
auto_end = resume.index("fi", auto_start)
auto_block = resume[auto_start:auto_end]
assert "continue-install.sh" not in auto_block
assert "setup-hat.sh" not in auto_block
assert "deploy-product-firmware.sh" not in auto_block
assert "setup.sh" not in auto_block
assert "finalize-product-service.sh" not in auto_block
assert "INTERACTIVE_CONTINUATION_REQUIRED=YES" in auto_block
assert "SERVICE_ENABLED=NO" in auto_block
assert "RF_TRANSMITTED=NO" in auto_block
assert "FLASH_WRITTEN=NO" in auto_block
assert resume.index("continue-install.sh") > auto_end

# Both direct/manual interactive flows use the same order: prove the HAT first,
# configure station identity second, then promote and activate RX-safe service.
hat_pos = continuation.index("setup-hat.sh")
setup_pos = continuation.index('bash "$SOURCE_ROOT/installer/setup.sh"')
final_pos = continuation.index("finalize-product-service.sh")
assert hat_pos < setup_pos < final_pos
assert "YWD1278_HAT_READY=YES" in continuation
assert "RF_TRANSMITTED=NO" in continuation

# HAT setup retains the qualified low-level firmware path and the old supported
# GPIO-release recovery behavior, but only in the interactive path.
assert "--hardware-only" in hat
assert "--preconfirmed-write" in hat
assert "--allow-candidate-release" in hat
assert "firmware-hardware-qualified.json" in hat
assert "qualified-ax25r4.bin" in hat
assert "Install YWD-1278 packet firmware on this HAT now?" in hat

# Hardware-only deployment must defer service eligibility and remain no-RF.
assert "--hardware-only" in deploy
assert "write-hardware" in deploy
assert 'echo "SERVICE_ELIGIBLE=NO"' in deploy
assert 'echo "SERVICE_ENABLED=NO"' in deploy
assert 'echo "RF_TRANSMITTED=NO"' in deploy

# Finalization is a promotion of already-verified evidence, not a second flash.
promote_pos = finalizer.index("hardware_trust --profile")
enable_pos = finalizer.index("enable-product-service.sh")
assert promote_pos < enable_pos
assert "deploy-product-firmware.sh" not in finalizer
assert "stm32flash" not in finalizer
assert "TX_ENABLED=NO" in finalizer
assert "RF_TRANSMITTED=NO" in finalizer

# The permanent RX-safe activation gate must no longer contain the historical
# Redding/Stage-G test-frequency lock. Runtime readiness remains the authority.
assert "Stage G rehearsal requires 145.050 MHz" not in enable
assert 'frequency_mhz" == "145.05"' not in enable
assert "check-eligibility" in enable
assert '[[ "$tx_enabled" == false ]]' in enable
assert '[[ "$auto_flash" == false ]]' in enable

print("INSTALLER_HAT_FIRST_SEQUENCE_CONTRACT=PASS")
print("BOOT_RESUME_UART_ONLY=PASS")
print("HAT_BEFORE_STATION=PASS")
print("SERVICE_ACTIVATION_RX_SAFE=PASS")
