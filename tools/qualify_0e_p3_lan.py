#!/usr/bin/env python3
"""Safe interactive qualification helper for 0E-P3 authenticated LAN console.

This helper deliberately avoids shell `set -e` behavior. Failures are reported
as normal process errors so an interactive terminal stays open.

Modes:
  stage   Run on the target Raspberry Pi. Verifies contracts, creates a
          temporary protected credential, starts the P3 server on an RFC1918
          address, and leaves it running for a second-host test.
  remote  Run on a different LAN machine. Proves failed authentication cannot
          reach the command shell, proves successful authentication, verifies
          frozen P1 behavior, reconnect authentication, policy reset, and TX
          command rejection.
  finish  Run back on the Pi. Re-checks listener/bind safety, stops the server,
          and removes the temporary credential and state files.
"""

from __future__ import annotations

import argparse
import getpass
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import time


PORT = 8023
USERNAME = "ywd"
RFC1918 = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)
STATE_PATH = Path("/tmp/ywd1278-0e-p3-lan-state.json")
AUTH_PATH = Path("/tmp/ywd1278-p3.auth")
LOG_PATH = Path("/tmp/ywd1278-0e-p3-lan.log")
WILDCARD_LOG = Path("/tmp/ywd1278-p3-wildcard.log")
PUBLIC_LOG = Path("/tmp/ywd1278-p3-public.log")


class QualificationError(RuntimeError):
    pass


def _is_rfc1918(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return parsed.version == 4 and any(parsed in network for network in RFC1918)


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = False,
    expect_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=capture,
        check=False,
    )
    if expect_success and result.returncode != 0:
        if capture:
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
        raise QualificationError(
            f"command failed with exit {result.returncode}: {' '.join(args)}"
        )
    return result


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    root = here.parents[1]
    if not (root / "src" / "ywd1278").is_dir():
        raise QualificationError(f"cannot locate ywd-1278 repo root from {here}")
    return root


def _python_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    source = str(root / "src")
    env["PYTHONPATH"] = source if not existing else source + os.pathsep + existing
    return env


def _discover_lan_ip() -> str:
    result = _run(
        ["ip", "-j", "-4", "addr", "show", "scope", "global"],
        capture=True,
    )
    try:
        interfaces = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise QualificationError("could not parse `ip -j` output") from exc
    candidates: list[str] = []
    for interface in interfaces:
        for info in interface.get("addr_info", []):
            address = info.get("local")
            if isinstance(address, str) and _is_rfc1918(address):
                candidates.append(address)
    if not candidates:
        raise QualificationError("no RFC1918 IPv4 address found on the Pi")
    return candidates[0]


def _wait_for_listener(host: str, port: int, pid: int) -> None:
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError as exc:
            raise QualificationError(
                f"P3 server exited before becoming ready; inspect {LOG_PATH}"
            ) from exc
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise QualificationError(f"P3 server did not become reachable on {host}:{port}")


def _state() -> dict[str, object]:
    if not STATE_PATH.exists():
        raise QualificationError(f"qualification state file is missing: {STATE_PATH}")
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise QualificationError(f"cannot read qualification state: {exc}") from exc
    if not isinstance(data, dict):
        raise QualificationError("qualification state has invalid format")
    return data


def _stop_existing() -> None:
    if not STATE_PATH.exists():
        return
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0))
    except Exception:
        return
    if pid > 1:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError:
            pass
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except OSError:
                break
            time.sleep(0.05)


def stage() -> int:
    if os.name != "posix":
        raise QualificationError("stage mode must be run on the Raspberry Pi/Linux target")

    root = _repo_root()
    env = _python_env(root)

    print("===== 0E-P3 TARGET-PI PRIVATE-LAN STAGING =====")
    head = _run(["git", "rev-parse", "HEAD"], cwd=root, capture=True).stdout.strip()
    branch = _run(
        ["git", "branch", "--show-current"], cwd=root, capture=True
    ).stdout.strip()
    dirty = _run(["git", "status", "--porcelain"], cwd=root, capture=True).stdout
    print(f"BRANCH={branch}")
    print(f"HEAD={head}")
    if branch != "dev-0e-p3-auth-lan-console":
        raise QualificationError(
            "wrong branch; switch to dev-0e-p3-auth-lan-console first"
        )
    if dirty.strip():
        print(dirty, end="")
        raise QualificationError("working tree is not clean")

    print("\n===== P3 CONTRACTS ON PI =====")
    for test in (
        "tests/auth_lan_console_test.py",
        "tests/auth_lan_console_contract_test.py",
        "tests/auth_lan_console_qualification_contract_test.py",
    ):
        print(f"--- {test} ---")
        _run([sys.executable, test], cwd=root, env=env)

    lan_ip = _discover_lan_ip()
    print("\n===== PRIVATE LAN ADDRESS =====")
    print(f"P3_LAN_IP={lan_ip}")

    _stop_existing()
    for path in (AUTH_PATH, LOG_PATH, STATE_PATH):
        try:
            path.unlink()
        except FileNotFoundError:
            pass

    print("\n===== CREATE TEMPORARY QUALIFICATION CREDENTIAL =====")
    print("Use a temporary password for this test; recommended: YWD-P3-QUAL-1278!")
    first = getpass.getpass("New P3 qualification password: ")
    second = getpass.getpass("Confirm P3 qualification password: ")
    if first != second:
        raise QualificationError("passwords do not match")

    from ywd1278.console.auth import CredentialRecord, hash_password, write_credential_file

    record = CredentialRecord(USERNAME, hash_password(first))
    write_credential_file(AUTH_PATH, record)
    first = ""
    second = ""

    mode = stat.S_IMODE(AUTH_PATH.stat().st_mode)
    if mode != 0o600:
        raise QualificationError(f"auth file mode is {mode:o}, expected 600")
    auth_text = AUTH_PATH.read_text(encoding="ascii")
    if not auth_text.startswith("ywd:pbkdf2-sha256$310000$"):
        raise QualificationError("auth file does not contain qualified PBKDF2 verifier")
    print("AUTH_FILE_MODE=600")
    print("PASSWORD_HASH_ONLY=PASS")

    print("\n===== START AUTHENTICATED LAN CONSOLE =====")
    log_handle = LOG_PATH.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [
            sys.executable,
            "-u",
            "-m",
            "ywd1278.console.lan_telnet",
            "--bind",
            lan_ip,
            "--port",
            str(PORT),
            "--auth-file",
            str(AUTH_PATH),
        ],
        cwd=root,
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    log_handle.close()

    try:
        _wait_for_listener(lan_ip, PORT, proc.pid)
    except Exception:
        try:
            proc.terminate()
        except OSError:
            pass
        raise

    state = {
        "schema": 1,
        "head": head,
        "branch": branch,
        "lan_ip": lan_ip,
        "port": PORT,
        "pid": proc.pid,
        "auth_file": str(AUTH_PATH),
        "log_file": str(LOG_PATH),
    }
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    os.chmod(STATE_PATH, 0o600)

    print(f"P3_SERVER_PID={proc.pid}")
    print(f"P3_SERVER_LOG={LOG_PATH}")
    print("WILDCARD_LISTENER=ABSENT_BY_BIND_POLICY")
    print("\n===== READY FOR SECOND HOST =====")
    print("YWD1278_0E_P3_PI_STAGE=READY")
    print(f"P3_LAN_IP={lan_ip}")
    print("\nThe server is running in the background. This terminal may be closed safely.")
    print("Run remote mode from a DIFFERENT machine on the same private LAN.")
    return 0


def _recv_until(sock: socket.socket, marker: bytes, timeout: float = 5.0) -> bytes:
    data = bytearray()
    sock.settimeout(timeout)
    while marker not in data:
        chunk = sock.recv(4096)
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def _show(label: str, data: bytes) -> None:
    print(f"--- {label} ---")
    text = data.decode("ascii", "replace")
    print(text, end="" if text.endswith("\n") else "\n")


def _command(sock: socket.socket, text: str, marker: bytes = b"cmd:") -> bytes:
    sock.sendall(text.encode("ascii") + b"\r\n")
    data = _recv_until(sock, marker)
    _show(text, data)
    return data


def remote(host: str) -> int:
    if not _is_rfc1918(host):
        raise QualificationError(f"target must be an RFC1918 IPv4 address, got {host}")

    password = getpass.getpass("P3 qualification password: ")

    def connect() -> socket.socket:
        sock = socket.create_connection((host, PORT), timeout=5.0)
        sock.settimeout(5.0)
        return sock

    print("===== REMOTE HOST / BAD AUTH PROOF =====")
    sock = connect()
    source = sock.getsockname()[0]
    print(f"TARGET_PI={host}")
    print(f"REMOTE_SOURCE={source}")
    if not _is_rfc1918(source):
        raise QualificationError(f"remote source is not RFC1918: {source}")
    if source == host:
        raise QualificationError("remote test is running on the Pi itself, not a second host")

    banner = _recv_until(sock, b"Username:")
    _show("PRE-AUTH BANNER", banner)
    if b"AUTHENTICATED LAN TNC CONSOLE" not in banner or b"cmd:" in banner:
        raise QualificationError("pre-auth banner did not enforce authentication boundary")
    if b"NOT encrypted" not in banner:
        raise QualificationError("plaintext Telnet warning missing")

    sock.sendall(USERNAME.encode("ascii") + b"\r\n")
    prompt = _recv_until(sock, b"Password:")
    if b"Password:" not in prompt:
        raise QualificationError("password prompt missing")
    wrong = password + "!" if len(password) < 128 else ("X" + password[1:])
    sock.sendall(wrong.encode("ascii") + b"\r\n")
    failed = _recv_until(sock, b"Username:")
    _show("INTENTIONALLY WRONG PASSWORD", failed)
    if b"AUTH FAIL 1/3" not in failed or b"cmd:" in failed:
        raise QualificationError("failed authentication reached command mode or lacked failure marker")
    sock.close()

    print("\n===== REMOTE HOST / AUTHENTICATED SESSION 1 =====")
    sock = connect()
    _recv_until(sock, b"Username:")
    sock.sendall(USERNAME.encode("ascii") + b"\r\n")
    _recv_until(sock, b"Password:")
    sock.sendall(password.encode("ascii") + b"\r\n")
    authenticated = _recv_until(sock, b"cmd:")
    _show("AUTH SUCCESS", authenticated)
    if b"AUTH OK" not in authenticated or b"YWD-1278 0.1.0-alpha0" not in authenticated:
        raise QualificationError("valid credentials did not reach frozen P1 command shell")

    checks = (
        ("VERSION", b"YWD-1278 0.1.0-alpha0"),
        ("MCOM", b"MCOM OFF"),
        ("MCON", b"MCON OFF"),
        ("MRPT", b"MRPT ON"),
        ("MCOM ON", b"MONITOR_GENERATION 1"),
        ("CONNECT KJ6YWD", b"ERROR UNKNOWN COMMAND CONNECT"),
        ("TX hello", b"ERROR UNKNOWN COMMAND TX"),
    )
    for command, expected in checks:
        result = _command(sock, command)
        if expected not in result:
            raise QualificationError(f"{command!r} missing expected response {expected!r}")
    bye = _command(sock, "QUIT", marker=b"BYE\r\n")
    if b"BYE" not in bye:
        raise QualificationError("QUIT did not return BYE")
    sock.close()

    print("\n===== REMOTE HOST / RECONNECT AUTH + STATE RESET =====")
    sock = connect()
    preauth = _recv_until(sock, b"Username:")
    if b"Username:" not in preauth or b"cmd:" in preauth:
        raise QualificationError("reconnect bypassed authentication")
    sock.sendall(USERNAME.encode("ascii") + b"\r\n")
    _recv_until(sock, b"Password:")
    sock.sendall(password.encode("ascii") + b"\r\n")
    authenticated = _recv_until(sock, b"cmd:")
    if b"AUTH OK" not in authenticated:
        raise QualificationError("reconnect authentication failed")
    reset = _command(sock, "MCOM")
    if b"MCOM OFF" not in reset:
        raise QualificationError("monitor policy did not reset across reconnect")
    _command(sock, "QUIT", marker=b"BYE\r\n")
    sock.close()
    password = ""

    print("\n===== REMOTE FINAL =====")
    print("YWD1278_0E_P3_REMOTE_LAN=PASS")
    print("REMOTE_SOURCE_PRIVATE_RFC1918=PASS")
    print("SEPARATE_HOST_SOURCE=PASS")
    print("BAD_AUTH_BLOCKED_BEFORE_CMD=PASS")
    print("GOOD_AUTH_REACHED_FROZEN_P1=PASS")
    print("RECONNECT_REAUTH_REQUIRED=PASS")
    print("SESSION_MONITOR_STATE_RESET=PASS")
    print("FUTURE_TX_COMMANDS_REJECTED=PASS")
    return 0


def _assert_server_alive(pid: int) -> None:
    try:
        os.kill(pid, 0)
    except OSError as exc:
        raise QualificationError(f"staged P3 server PID {pid} is not running") from exc


def _prove_bad_bind(root: Path, env: dict[str, str], address: str, log_path: Path) -> None:
    result = _run(
        [
            sys.executable,
            "-m",
            "ywd1278.console.lan_telnet",
            "--auth-file",
            str(AUTH_PATH),
            "--bind",
            address,
            "--port",
            str(PORT + 1),
        ],
        cwd=root,
        env=env,
        capture=True,
        expect_success=False,
    )
    log_path.write_text((result.stdout or "") + (result.stderr or ""), encoding="utf-8")
    print(log_path.read_text(encoding="utf-8"), end="")
    if result.returncode == 0:
        raise QualificationError(f"unsafe bind unexpectedly accepted: {address}")
    if "restricted to loopback or RFC1918 IPv4 addresses" not in log_path.read_text(encoding="utf-8"):
        raise QualificationError(f"unsafe bind {address} failed for an unexpected reason")


def finish() -> int:
    if os.name != "posix":
        raise QualificationError("finish mode must be run on the Raspberry Pi/Linux target")
    root = _repo_root()
    env = _python_env(root)
    state = _state()
    lan_ip = str(state.get("lan_ip"))
    pid = int(state.get("pid", 0))
    head = str(state.get("head"))

    print("===== 0E-P3 FINAL PI SAFETY PROOFS =====")
    print(f"STAGED_HEAD={head}")
    print(f"P3_LAN_IP={lan_ip}")
    print(f"P3_SERVER_PID={pid}")
    _assert_server_alive(pid)

    if not AUTH_PATH.exists():
        raise QualificationError("temporary auth file disappeared before final proof")
    mode = stat.S_IMODE(AUTH_PATH.stat().st_mode)
    if mode != 0o600:
        raise QualificationError(f"auth file mode changed to {mode:o}")
    text = AUTH_PATH.read_text(encoding="ascii")
    if not text.startswith("ywd:pbkdf2-sha256$310000$"):
        raise QualificationError("auth file verifier format changed")
    print("AUTH_FILE_MODE=600")
    print("PASSWORD_HASH_ONLY=PASS")

    print("\n===== WILDCARD BIND MUST FAIL =====")
    _prove_bad_bind(root, env, "0.0.0.0", WILDCARD_LOG)
    print("WILDCARD_BIND_REJECTED=PASS")

    print("\n===== PUBLIC BIND MUST FAIL =====")
    _prove_bad_bind(root, env, "8.8.8.8", PUBLIC_LOG)
    print("PUBLIC_BIND_REJECTED=PASS")

    print("\n===== SERVER LOG =====")
    if LOG_PATH.exists():
        print(LOG_PATH.read_text(encoding="utf-8"), end="")

    print("\n===== CLEANUP =====")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        time.sleep(0.05)

    for path in (AUTH_PATH, STATE_PATH, WILDCARD_LOG, PUBLIC_LOG):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    if AUTH_PATH.exists():
        raise QualificationError("temporary qualification credential was not removed")

    print("\n===== FINAL =====")
    print("YWD1278_0E_P3_TARGET_PI_LAN=PASS")
    print("PRIVATE_RFC1918_BIND=PASS")
    print("WILDCARD_BIND_REJECTED=PASS")
    print("PUBLIC_BIND_REJECTED=PASS")
    print("AUTH_FILE_PROTECTION=PASS")
    print("TEMP_QUALIFICATION_CREDENTIAL_REMOVED=PASS")
    print("TX_RF_HARDWARE_TEST_REQUIRED=NO")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("stage", help="stage authenticated LAN console on the target Pi")
    remote_parser = sub.add_parser("remote", help="test from a second private-LAN host")
    remote_parser.add_argument("host", help="RFC1918 IPv4 address printed by stage mode")
    sub.add_parser("finish", help="finish safety proofs and clean up on the Pi")
    args = parser.parse_args(argv)

    try:
        if args.mode == "stage":
            return stage()
        if args.mode == "remote":
            return remote(args.host)
        if args.mode == "finish":
            return finish()
        raise QualificationError(f"unknown mode: {args.mode}")
    except KeyboardInterrupt:
        print("\nABORTED by user. Your terminal remains open.", file=sys.stderr)
        return 130
    except QualificationError as exc:
        print(f"\nQUALIFICATION FAILED: {exc}", file=sys.stderr)
        if LOG_PATH.exists() and args.mode in {"stage", "finish"}:
            print(f"Server log: {LOG_PATH}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"\nUNEXPECTED QUALIFICATION ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
