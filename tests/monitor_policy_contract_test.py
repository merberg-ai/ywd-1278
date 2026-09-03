#!/usr/bin/env python3
"""Architecture/safety contract for 0D-P2 monitor controls."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "src" / "ywd1278" / "monitor" / "policy.py"
sys.path.insert(0, str(ROOT / "src"))

from ywd1278.monitor import MonitorPolicyState  # noqa: E402


FROZEN_BLOBS = {
    "src/ywd1278/monitor/stream.py": "703b7e803d39d915b60d79c30c154151e3820098",
    "src/ywd1278/ax25/codec.py": "866a500d9f3a5d3fc80f6918d07ff83a6672ad64",
    "src/ywd1278/kiss/server.py": "d586fe9cbef9f42c5ec4d2e18880dfad32548b33",
    "src/ywd1278/kiss/control.py": "b6c23879027c15ef944a9e411429694a312d606e",
    "src/ywd1278/kiss/sustained.py": "63cf33f4b6d4cedd091af0349a8037669d45e84d",
    "src/ywd1278/kiss/tx_path.py": "44f4b6c0bddd6ac0977646ac417e448c9a1398ea",
    "src/ywd1278/service/rx_runtime.py": "ea63eb82cb82ed273cab8d393aedf797b46ff123",
    "src/ywd1278/service/tnc_runtime.py": "f1a74ae44824bafc2b89c09e77fa416ac26bb4f1",
}


def git_blob(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", path], cwd=ROOT, text=True).strip()


def main() -> int:
    source = POLICY.read_text(encoding="utf-8")
    for path, expected in FROZEN_BLOBS.items():
        assert git_blob(path) == expected, (path, expected, git_blob(path))

    for required in (
        "mcom: bool = False",
        "mcon: bool = False",
        "mrpt: bool = True",
        "local_connected",
        "addressed_to_local",
        "suppression_reason=\"MCON\"",
        "suppression_reason=\"MCOM\"",
        "self._generation += 1",
        "record.path",
    ):
        assert required in source, required

    for forbidden in (
        "argparse",
        "socket",
        "subprocess",
        "ywd1278.modem",
        "ywd1278.tx",
        "TXBroker",
        "TXModemOwner",
        "ModemOwner",
        "posix_serial_transport_factory",
        "/dev/tty",
        "RPi.GPIO",
        "gpiozero",
        ".transmit_selector_burst(",
        ".transact(",
        "rx_start(",
        "rx_stop(",
    ):
        assert forbidden not in source, forbidden

    state = MonitorPolicyState()
    snap = state.snapshot
    assert (snap.mcom, snap.mcon, snap.mrpt) == (False, False, True)
    assert not hasattr(state, "publish")
    assert not hasattr(state, "transmit")
    assert not hasattr(state, "send")

    print("YWD1278_0D_P2_MONITOR_POLICY_CONTRACT=PASS")
    print("FROZEN_P1_MONITOR_STREAM_HASH=PASS")
    print("FROZEN_0C_CORE_HASHES=PASS")
    print("MCOM_MCON_MRPT_TYPED_POLICY_ONLY=PASS")
    print("COMMAND_SHELL_ADDED=NO")
    print("MODEM_UART_OPENED=NO")
    print("RF_TRANSMITTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
