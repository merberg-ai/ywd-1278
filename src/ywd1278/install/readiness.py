"""Zero-I/O product-runtime readiness checks used by the appliance installer.

This module is intentionally configuration-only.  It never opens the modem,
starts a listener, touches GPIO, flashes firmware, or transmits RF.  READY
means only that the installed configuration is coherent enough for a later
firmware/service gate to consider starting the already-qualified product
runtime.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import tomllib

from ywd1278.console.auth import load_credential_file
from ywd1278.service.appliance import (
    PRODUCT_TARGET,
    ProductConfigurationError,
    load_product_packet_engine_config,
)
from ywd1278.service.classic_console import (
    ProductClassicConsoleConfigurationError,
    load_product_classic_console_config,
)


READY = "READY"
INCOMPLETE = "INCOMPLETE"
UNSAFE = "UNSAFE"
EXIT_READY = 0
EXIT_INCOMPLETE = 10
EXIT_UNSAFE = 20
DEFAULT_PTY_LINK = Path("/run/ywd-1278/tnc")
_CALLSIGN_RE = re.compile(r"^[A-Z0-9]{1,6}$")


@dataclass(frozen=True)
class RuntimeReadiness:
    status: str
    reasons: tuple[str, ...]

    @property
    def exit_code(self) -> int:
        if self.status == READY:
            return EXIT_READY
        if self.status == INCOMPLETE:
            return EXIT_INCOMPLETE
        return EXIT_UNSAFE


def _table(root: dict, name: str) -> dict | None:
    value = root.get(name)
    return value if isinstance(value, dict) else None


def _bool(table: dict | None, key: str, default: bool) -> bool | None:
    if table is None:
        return default
    value = table.get(key, default)
    return value if isinstance(value, bool) else None


def _string(table: dict | None, key: str, default: str = "") -> str | None:
    if table is None:
        return default
    value = table.get(key, default)
    return value if isinstance(value, str) else None


def _number(table: dict | None, key: str, default: float = 0.0) -> float | None:
    if table is None:
        return default
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def inspect_runtime_readiness(path: str | Path) -> RuntimeReadiness:
    """Inspect one product config without opening any runtime/hardware resource."""

    config_path = Path(path)
    try:
        with config_path.open("rb") as handle:
            root = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return RuntimeReadiness(UNSAFE, (f"CONFIG_LOAD:{exc}",))

    incomplete: list[str] = []
    unsafe: list[str] = []

    station = _table(root, "station")
    hardware = _table(root, "hardware")
    radio = _table(root, "radio")
    kiss = _table(root, "kiss")
    console = _table(root, "console")
    monitor = _table(root, "monitor")
    firmware = _table(root, "firmware")

    callsign = _string(station, "callsign", "")
    if callsign is None:
        unsafe.append("STATION_CALLSIGN_TYPE")
    else:
        callsign = callsign.strip().upper()
        if not callsign or callsign == "N0CALL":
            incomplete.append("STATION_CALLSIGN")
        elif not _CALLSIGN_RE.fullmatch(callsign):
            unsafe.append("STATION_CALLSIGN_FORMAT")

    ssid = station.get("ssid", 0) if station is not None else 0
    if isinstance(ssid, bool) or not isinstance(ssid, int) or not 0 <= ssid <= 15:
        unsafe.append("STATION_SSID")

    target = _string(hardware, "target", "")
    if target is None:
        unsafe.append("HARDWARE_TARGET_TYPE")
    else:
        target = target.strip()
        if not target:
            incomplete.append("HARDWARE_TARGET")
        elif target != PRODUCT_TARGET:
            unsafe.append("HARDWARE_TARGET_UNSUPPORTED")

    frequency = _number(radio, "frequency_mhz", 0.0)
    if frequency is None:
        unsafe.append("RADIO_FREQUENCY_TYPE")
    elif frequency == 0.0:
        incomplete.append("RADIO_FREQUENCY")

    tx_enabled = _bool(radio, "tx_enabled", False)
    if tx_enabled is None:
        unsafe.append("TX_ENABLED_TYPE")
    elif tx_enabled:
        unsafe.append("TX_ENABLED")

    auto_flash = _bool(firmware, "allow_automatic_flash", False)
    if auto_flash is None:
        unsafe.append("AUTO_FLASH_TYPE")
    elif auto_flash:
        unsafe.append("AUTO_FLASH_ENABLED")

    required_product = _string(firmware, "required_product", "")
    if required_product is None:
        unsafe.append("FIRMWARE_REQUIRED_PRODUCT_TYPE")
    elif required_product != "YWD-1278":
        unsafe.append("FIRMWARE_REQUIRED_PRODUCT")

    kiss_enabled = _bool(kiss, "enabled", False)
    if kiss_enabled is None:
        unsafe.append("KISS_ENABLED_TYPE")
    elif not kiss_enabled:
        incomplete.append("KISS_DISABLED")

    monitor_enabled = _bool(monitor, "enabled", False)
    log_frames = _bool(monitor, "log_frames", False)
    if monitor_enabled is None or log_frames is None:
        unsafe.append("MONITOR_BOOLEAN_TYPE")
    else:
        if not monitor_enabled:
            incomplete.append("MONITOR_DISABLED")
        if not log_frames:
            incomplete.append("MHEARD_LOGGING_DISABLED")

    console_enabled = _bool(console, "enabled", False)
    pty_enabled = _bool(console, "pty_enabled", False)
    pty_link = _string(console, "pty_link", "")
    if console_enabled is None or pty_enabled is None or pty_link is None:
        unsafe.append("CONSOLE_FIELD_TYPE")
    else:
        if not console_enabled:
            incomplete.append("CONSOLE_DISABLED")
        if not pty_enabled:
            incomplete.append("PTY_DISABLED")
        if pty_enabled:
            if not pty_link:
                incomplete.append("PTY_LINK")
            elif Path(pty_link) != DEFAULT_PTY_LINK:
                unsafe.append("PTY_LINK_NONPRODUCT")

    # The qualified typed loaders are the final static authority for packet and
    # console policy once the operator has supplied the minimum identity/radio
    # fields they require.  Avoid reporting expected placeholder values as
    # malformed configuration.
    if "HARDWARE_TARGET" not in incomplete and "RADIO_FREQUENCY" not in incomplete:
        try:
            packet = load_product_packet_engine_config(config_path)
        except ProductConfigurationError as exc:
            unsafe.append(f"PACKET_CONFIG:{exc}")
        else:
            if not packet.kiss_enabled:
                incomplete.append("KISS_DISABLED")

    try:
        classic = load_product_classic_console_config(config_path)
    except ProductClassicConsoleConfigurationError as exc:
        unsafe.append(f"CONSOLE_CONFIG:{exc}")
    else:
        if classic.enabled and classic.auth_file is not None:
            if not classic.auth_file.exists():
                incomplete.append("CONSOLE_AUTH_FILE_MISSING")
            else:
                try:
                    load_credential_file(classic.auth_file)
                except (OSError, ValueError) as exc:
                    unsafe.append(f"CONSOLE_AUTH_FILE:{exc}")

    kiss_port = kiss.get("port") if kiss is not None else None
    console_port = console.get("port") if console is not None else None
    if (
        isinstance(kiss_port, int)
        and not isinstance(kiss_port, bool)
        and isinstance(console_port, int)
        and not isinstance(console_port, bool)
        and kiss_port == console_port
    ):
        unsafe.append("KISS_CONSOLE_PORT_COLLISION")

    if unsafe:
        return RuntimeReadiness(UNSAFE, tuple(dict.fromkeys(unsafe)))
    if incomplete:
        return RuntimeReadiness(INCOMPLETE, tuple(dict.fromkeys(incomplete)))
    return RuntimeReadiness(READY, ())


def _print_result(result: RuntimeReadiness) -> None:
    print(f"YWD1278_INSTALL_RUNTIME_READINESS={result.status}")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
    print("FLASH_WRITTEN=NO")
    if result.reasons:
        for reason in result.reasons:
            print(f"READINESS_REASON={reason}")
    else:
        print("READINESS_REASON=NONE")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m ywd1278.install.readiness")
    parser.add_argument("--config", required=True, metavar="PATH")
    args = parser.parse_args(argv)
    result = inspect_runtime_readiness(args.config)
    _print_result(result)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
