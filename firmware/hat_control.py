#!/usr/bin/env python3
"""Target-aware Raspberry Pi control-line helper for supported YWD-1278 HATs.

This helper does not communicate with the modem UART, configure RF, enter the
STM32 bootloader, write flash, or touch option bytes.  Its initial operation is
strictly an application-state release for an explicitly selected allowlisted
hardware target: BOOT0 is driven to the target's normal-application level and
RESET is driven to its released level.  RESET is not pulsed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib


def load_targets(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != 1 or not isinstance(payload.get("targets"), list):
        raise RuntimeError("unsupported targets manifest schema")
    return payload["targets"]


def config_target(path: Path) -> str:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    target = data.get("hardware", {}).get("target", "")
    return target if isinstance(target, str) else ""


def read_model() -> str:
    path = Path("/proc/device-tree/model")
    if not path.exists():
        raise RuntimeError("Raspberry Pi model is unavailable")
    return path.read_bytes().replace(b"\0", b"").decode("ascii", "replace").strip()


def find_target(target_id: str, targets: list[dict]) -> dict:
    matches = [item for item in targets if item.get("id") == target_id]
    if len(matches) != 1:
        raise RuntimeError(f"unknown or ambiguous hardware target: {target_id or '<empty>'}")
    return matches[0]


def pinctrl_get(tool: str, gpio: int) -> str:
    proc = subprocess.run([tool, "get", str(gpio)], check=True, text=True, capture_output=True)
    return proc.stdout.strip()


def pinctrl_set(tool: str, gpio: int, level: str) -> None:
    if level not in {"low", "high"}:
        raise RuntimeError(f"unsupported GPIO level in target manifest: {level}")
    state = "dl" if level == "low" else "dh"
    subprocess.run([tool, "set", str(gpio), "op", state], check=True)


def application_release(target: dict) -> None:
    control = target.get("host_control")
    if not isinstance(control, dict):
        raise RuntimeError("target has no qualified host_control definition")

    expected_model = control.get("platform_model_contains")
    if not isinstance(expected_model, str) or not expected_model:
        raise RuntimeError("target host_control lacks platform_model_contains")
    model = read_model()
    if expected_model not in model:
        raise RuntimeError(f"host model mismatch: expected '{expected_model}' in '{model}'")

    requested_tool = control.get("tool")
    if requested_tool != "pinctrl":
        raise RuntimeError(f"unsupported host-control tool: {requested_tool!r}")
    tool = shutil.which("pinctrl")
    if not tool:
        raise RuntimeError("pinctrl is required for this hardware target")

    boot0 = control.get("boot0_gpio")
    reset = control.get("reset_gpio")
    boot0_level = control.get("application_boot0_level")
    reset_level = control.get("application_reset_level")
    pulses_reset = control.get("application_release_pulses_reset")
    if not isinstance(boot0, int) or not isinstance(reset, int):
        raise RuntimeError("target host_control GPIO numbers are invalid")
    if pulses_reset is not False:
        raise RuntimeError("application release must be explicitly qualified as no-reset-pulse")

    print(f"HAT_CONTROL_TARGET={target['id']}")
    print(f"HAT_CONTROL_HOST={model}")
    print(f"HAT_CONTROL_BOOT0_BEFORE={pinctrl_get(tool, boot0)}")
    print(f"HAT_CONTROL_RESET_BEFORE={pinctrl_get(tool, reset)}")

    # Put BOOT0 into the normal application state first, then release RESET.
    # There is deliberately no low->high reset pulse here.
    pinctrl_set(tool, boot0, str(boot0_level))
    pinctrl_set(tool, reset, str(reset_level))

    print(f"HAT_CONTROL_BOOT0_AFTER={pinctrl_get(tool, boot0)}")
    print(f"HAT_CONTROL_RESET_AFTER={pinctrl_get(tool, reset)}")
    print("HAT_APPLICATION_STATE_RELEASED=YES")
    print("STM32_RESET_PULSED=NO")
    print("MODEM_UART_OPENED=NO")
    print("RF_CONFIGURED=NO")
    print("FLASH_WRITTEN=NO")
    print("OPTION_BYTES_WRITTEN=NO")


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 target-aware HAT control")
    ap.add_argument("operation", choices=["application-release"])
    ap.add_argument("--targets", default=str(Path(__file__).with_name("targets.json")))
    ap.add_argument("--target", default="")
    ap.add_argument("--config", default="")
    args = ap.parse_args()

    target_id = args.target
    if not target_id and args.config:
        target_id = config_target(Path(args.config))
    if not target_id:
        raise RuntimeError("hardware target is required; use --target or configure [hardware].target")

    target = find_target(target_id, load_targets(Path(args.targets)))
    if args.operation == "application-release":
        application_release(target)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"HAT_CONTROL_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2)
