#!/usr/bin/env python3
"""Target-aware Raspberry Pi control-line helper for supported YWD-1278 HATs.

This helper never communicates with the modem UART, configures RF, enters the
STM32 bootloader, writes flash, or touches option bytes.  It only places a
qualified HAT control profile into normal application state: BOOT0 at the
application level and RESET released. RESET is never pulsed by these operations.
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
    if not path.exists():
        return ""
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


def compatible_auto_release_targets(targets: list[dict]) -> list[dict]:
    model = read_model()
    matches: list[dict] = []
    for item in targets:
        control = item.get("host_control")
        if not isinstance(control, dict):
            continue
        expected = control.get("platform_model_contains")
        if (
            control.get("installer_auto_release_candidate") is True
            and isinstance(expected, str)
            and expected
            and expected in model
        ):
            matches.append(item)
    if not matches:
        raise RuntimeError(f"no installer auto-release profile is qualified for host '{model}'")

    # Auto-release is allowed only when every compatible target agrees on the
    # exact same host-control behavior. Adding a second incompatible target to
    # the manifest therefore makes this path fail closed until explicitly
    # resolved.
    keys = (
        "tool",
        "boot0_gpio",
        "reset_gpio",
        "application_boot0_level",
        "application_reset_level",
        "application_release_pulses_reset",
    )
    signatures = {tuple(item["host_control"].get(k) for k in keys) for item in matches}
    if len(signatures) != 1:
        raise RuntimeError("compatible targets disagree on automatic application-release GPIO behavior")
    return matches


def pinctrl_get(tool: str, gpio: int) -> str:
    proc = subprocess.run([tool, "get", str(gpio)], check=True, text=True, capture_output=True)
    return proc.stdout.strip()


def pinctrl_set(tool: str, gpio: int, level: str) -> None:
    if level not in {"low", "high"}:
        raise RuntimeError(f"unsupported GPIO level in target manifest: {level}")
    subprocess.run([tool, "set", str(gpio), "op", "dl" if level == "low" else "dh"], check=True)


def release_with_profile(label: str, control: dict) -> None:
    expected_model = control.get("platform_model_contains")
    if not isinstance(expected_model, str) or not expected_model:
        raise RuntimeError("target host_control lacks platform_model_contains")
    model = read_model()
    if expected_model not in model:
        raise RuntimeError(f"host model mismatch: expected '{expected_model}' in '{model}'")

    if control.get("tool") != "pinctrl":
        raise RuntimeError(f"unsupported host-control tool: {control.get('tool')!r}")
    tool = shutil.which("pinctrl")
    if not tool:
        raise RuntimeError("pinctrl is required for this hardware target")

    boot0 = control.get("boot0_gpio")
    reset = control.get("reset_gpio")
    boot0_level = control.get("application_boot0_level")
    reset_level = control.get("application_reset_level")
    if not isinstance(boot0, int) or not isinstance(reset, int):
        raise RuntimeError("target host_control GPIO numbers are invalid")
    if control.get("application_release_pulses_reset") is not False:
        raise RuntimeError("application release must be explicitly qualified as no-reset-pulse")

    print(f"HAT_CONTROL_TARGET={label}")
    print(f"HAT_CONTROL_HOST={model}")
    print(f"HAT_CONTROL_BOOT0_BEFORE={pinctrl_get(tool, boot0)}")
    print(f"HAT_CONTROL_RESET_BEFORE={pinctrl_get(tool, reset)}")
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


def application_release(target: dict) -> None:
    control = target.get("host_control")
    if not isinstance(control, dict):
        raise RuntimeError("target has no qualified host_control definition")
    release_with_profile(str(target["id"]), control)


def auto_detect_release(targets: list[dict]) -> None:
    candidates = compatible_auto_release_targets(targets)
    ids = ",".join(str(item["id"]) for item in candidates)
    print(f"HAT_CONTROL_CANDIDATES={ids}")
    release_with_profile("AUTO-CANDIDATE", candidates[0]["host_control"])


def main() -> int:
    ap = argparse.ArgumentParser(description="YWD-1278 target-aware HAT control")
    ap.add_argument("operation", choices=["application-release", "auto-detect-release"])
    ap.add_argument("--targets", default=str(Path(__file__).with_name("targets.json")))
    ap.add_argument("--target", default="")
    ap.add_argument("--config", default="")
    args = ap.parse_args()

    targets = load_targets(Path(args.targets))
    if args.operation == "auto-detect-release":
        auto_detect_release(targets)
        return 0

    target_id = args.target
    if not target_id and args.config:
        target_id = config_target(Path(args.config))
    if not target_id:
        raise RuntimeError("hardware target is required; use --target or configure [hardware].target")
    application_release(find_target(target_id, targets))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"HAT_CONTROL_ERROR={exc}", file=sys.stderr)
        raise SystemExit(2)
