"""0F-P9 persistent product-TX configuration control.

This module owns no UART, modem, RF, systemd, firmware, retry, or scheduler
behavior.  It provides a small, host-testable configuration boundary used by
the root-only product TX activation wrapper.

Enabling TX is deliberately restricted to the already physically-qualified
145.050 MHz / power-200 product profile.  Disabling TX changes only the
``radio.tx_enabled`` boolean.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import tomllib

from ywd1278.service.appliance import (
    PRODUCT_TARGET,
    QUALIFIED_TX_FREQUENCY_HZ,
    QUALIFIED_TX_POWER,
    load_product_packet_engine_config,
)
from ywd1278.service.classic_tx_console import load_product_classic_tx_config


class ProductTXControlError(ValueError):
    pass


_RADIO_SECTION_RE = re.compile(r"(?ms)^\[radio\]\s*$\n(?P<body>.*?)(?=^\[[^\n]+\]\s*$|\Z)")


def _load_text(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ProductTXControlError(f"cannot read configuration: {exc}") from exc


def _parse(text: str) -> dict:
    try:
        root = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ProductTXControlError(f"invalid TOML: {exc}") from exc
    if not isinstance(root, dict):
        raise ProductTXControlError("configuration root must be a table")
    return root


def _replace_radio_key(text: str, key: str, rendered_value: str) -> str:
    match = _RADIO_SECTION_RE.search(text)
    if match is None:
        raise ProductTXControlError("missing [radio] table")
    body = match.group("body")
    pattern = re.compile(rf"(?m)^(?P<indent>[ \t]*){re.escape(key)}[ \t]*=[ \t]*[^\r\n#]*(?P<comment>[ \t]*#.*)?$")
    matches = list(pattern.finditer(body))
    if len(matches) != 1:
        raise ProductTXControlError(f"[radio] must contain exactly one {key} assignment")
    item = matches[0]
    replacement = f"{item.group('indent')}{key} = {rendered_value}{item.group('comment') or ''}"
    new_body = body[: item.start()] + replacement + body[item.end() :]
    return text[: match.start("body")] + new_body + text[match.end("body") :]


def _require_enable_prerequisites(root: dict) -> None:
    station = root.get("station")
    hardware = root.get("hardware")
    radio = root.get("radio")
    firmware = root.get("firmware")
    beacon = root.get("beacon")
    forwarding = root.get("forwarding")

    if not isinstance(station, dict):
        raise ProductTXControlError("persistent TX requires [station]")
    callsign = station.get("callsign")
    ssid = station.get("ssid", 0)
    if not isinstance(callsign, str) or not callsign.strip():
        raise ProductTXControlError("persistent TX requires station.callsign")
    if isinstance(ssid, bool) or not isinstance(ssid, int) or not 0 <= ssid <= 15:
        raise ProductTXControlError("station.ssid must be 0..15")

    if not isinstance(hardware, dict) or hardware.get("target") != PRODUCT_TARGET:
        raise ProductTXControlError("persistent TX requires the qualified product HAT target")
    if not isinstance(radio, dict):
        raise ProductTXControlError("persistent TX requires [radio]")
    frequency = radio.get("frequency_mhz")
    if isinstance(frequency, bool) or not isinstance(frequency, (int, float)):
        raise ProductTXControlError("radio.frequency_mhz must be numeric")
    frequency_hz = int(round(float(frequency) * 1_000_000))
    if frequency_hz != QUALIFIED_TX_FREQUENCY_HZ:
        raise ProductTXControlError("persistent TX is qualified only at 145.050 MHz")
    if not isinstance(radio.get("tx_enabled"), bool):
        raise ProductTXControlError("radio.tx_enabled must be true or false")

    if not isinstance(firmware, dict):
        raise ProductTXControlError("persistent TX requires [firmware]")
    if firmware.get("required_product") != "YWD-1278":
        raise ProductTXControlError("firmware.required_product must be 'YWD-1278'")
    if firmware.get("allow_automatic_flash") is not False:
        raise ProductTXControlError("automatic firmware flash must remain disabled")
    if not isinstance(beacon, dict) or beacon.get("enabled") is not False:
        raise ProductTXControlError("beacon must remain disabled for 0F-P9")
    if forwarding is not None:
        if not isinstance(forwarding, dict) or forwarding.get("enabled") is not False:
            raise ProductTXControlError("forwarding must remain disabled for 0F-P9")


def render_tx_state(text: str, *, enabled: bool) -> str:
    """Return one validated config with only the P9 TX state/profile mutations."""

    root = _parse(text)
    if enabled:
        _require_enable_prerequisites(root)
        text = _replace_radio_key(text, "tx_power", str(QUALIFIED_TX_POWER))
        text = _replace_radio_key(text, "tx_enabled", "true")
    else:
        # Disabling is intentionally available even if another product setting
        # is currently invalid.  The emergency-safe operation only needs a
        # syntactically valid [radio].tx_enabled boolean to turn authority off.
        radio = root.get("radio")
        if not isinstance(radio, dict) or not isinstance(radio.get("tx_enabled"), bool):
            raise ProductTXControlError("cannot disable TX without boolean radio.tx_enabled")
        text = _replace_radio_key(text, "tx_enabled", "false")
    _parse(text)
    return text


def prepare_file(config: str | Path, output: str | Path, *, enabled: bool) -> None:
    source = _load_text(config)
    rendered = render_tx_state(source, enabled=enabled)
    Path(output).write_text(rendered, encoding="utf-8")


def validate_candidate(config: str | Path, *, expect_enabled: bool) -> tuple[str, int, int]:
    """Validate a candidate through the real product configuration loaders."""

    packet = load_product_packet_engine_config(config)
    classic = load_product_classic_tx_config(config)
    if classic.source is None:
        raise ProductTXControlError("classic product TX requires configured station identity")
    if packet.tx_enabled is not bool(expect_enabled):
        raise ProductTXControlError("candidate TX state does not match requested state")
    if expect_enabled:
        if packet.frequency_hz != QUALIFIED_TX_FREQUENCY_HZ:
            raise ProductTXControlError("candidate frequency is outside qualified TX profile")
        if packet.tx_power != QUALIFIED_TX_POWER:
            raise ProductTXControlError("candidate power is outside qualified TX profile")
    return str(classic.source), packet.frequency_hz, packet.tx_power


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m ywd1278.install.tx_control")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("action", choices=("enable", "disable"))
    prepare.add_argument("--config", required=True)
    prepare.add_argument("--output", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--config", required=True)
    validate.add_argument("--expect", choices=("enabled", "disabled"), required=True)

    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare_file(args.config, args.output, enabled=args.action == "enable")
            print(f"PERSISTENT_TX_CANDIDATE={'ENABLED' if args.action == 'enable' else 'DISABLED'}")
        else:
            source, frequency_hz, tx_power = validate_candidate(
                args.config,
                expect_enabled=args.expect == "enabled",
            )
            print("PRODUCT_TX_CONFIG_VALID=YES")
            print(f"STATION_SOURCE={source}")
            print(f"TX_FREQUENCY_HZ={frequency_hz}")
            print(f"TX_POWER={tx_power}")
    except (ProductTXControlError, ValueError, OSError) as exc:
        parser.exit(2, f"TX_CONTROL_ERROR={exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
