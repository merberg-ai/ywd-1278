# Fresh-install Stage D classic console host qualification

Date: 2026-09-04 (America/Los_Angeles)

## Result

Stage D is host-qualified: the production `ywd1278d` daemon now composes the already-qualified 0E classic TNC console stack around the frozen Stage-C packet/observability runtime without modifying the Stage-C engine or any frozen 0E parser/transport/personality implementation.

Qualified implementation head:

`a5fef9102f4b7c00f79e75cc961683a921f7edc3`

Evidence-bearing GitHub Actions run:

`33873695993` — success

No physical UART, HAT, RF, flash, GPIO, option-byte, or TX test was performed or required for this host-only integration stage.

## Composition

The product daemon now owns these console surfaces:

- loopback Telnet through frozen 0E-P2 when no auth file is configured;
- authenticated Telnet through frozen 0E-P3 whenever an auth file is configured;
- RFC1918 binds only when a protected P3 auth file is supplied;
- local virtual pseudo-serial through frozen 0E-P4 `VirtualPTYTNC`;
- frozen 0E-P5 TNC2/MFJ-style vocabulary on every logical session;
- live Stage-C diagnostics and read-only MHEARD injected into each shell;
- a fresh `MonitorPolicyState` for every connection/logical PTY session.

The shipped example remains loopback-safe and now explicitly enables the PTY personality:

- Telnet: `127.0.0.1:8010`
- PTY stable link: `/run/ywd-1278/tnc`

The existing systemd unit already owns `/run/ywd-1278` through `RuntimeDirectory=ywd-1278`, so Stage D did not modify the unit.

## Network/authentication policy

The Stage-D product boundary rejects wildcard, public, CGNAT, link-local, hostname and IPv6 Telnet binds. Literal IPv4 loopback is permitted without authentication through the frozen P2 boundary. RFC1918 addresses require an absolute `console.auth_file` and therefore select the frozen P3 authenticated private-LAN server. Supplying an auth file on loopback also deliberately selects P3.

P3 remains plaintext Telnet. WAN/public exposure is not qualified and must not be configured or port-forwarded.

The qualification host exercised P3 authentication on loopback and separately validated the RFC1918-auth-required product policy. It did not bind a real RFC1918 interface during CI; prior frozen P3 qualification remains the authority for that transport boundary.

## Host regression proof

The Stage-D regression uses the existing thread-bound in-memory AX25R4 fake modem but real host TCP sockets and a real kernel PTY. It proved:

- loopback Telnet starts and serves the frozen classic shell;
- a protected P3 credential file selects mandatory authenticated Telnet;
- no command shell prompt is available before P3 authentication succeeds;
- a real kernel `/dev/pts/N` PTY is created and exposed through a stable symlink;
- one synthesized Bell-202/AX.25 receive reaches the Stage-C SQLite/MHEARD source;
- `MH`/`MHEARD`, `STAT`/`STATUS`, and `HEAL`/`HEALTH` expose live product state over Telnet and PTY;
- each new Telnet session starts with fresh monitor policy (`MCOM OFF` rather than inheriting another session's state);
- `UNPROTO`, `CONNECT`, and direct `TX` commands remain recognized but inert under the frozen P5 ownership/defer rules;
- fake-hardware TX acceptance remains exactly zero;
- shutdown removes the stable PTY link and releases the single modem owner on its owner thread.

A second full-graph regression strengthened the evidence by running KISS, Telnet, PTY, SQLite/MHEARD and the fake packet runtime simultaneously. The same injected packet was received as exact KISS DATA and then observed through the classic console's MHEARD/health path before clean shutdown. This is the host qualification for the assembled daemon graph.

## Preservation

The Stage-D architecture contract proves these lower boundaries remain exact:

- frozen Stage-C `src/ywd1278/service/appliance.py`;
- frozen Stage-C `src/ywd1278/service/observability.py`;
- frozen Stage-C qualification manifest and regression/contract;
- frozen 0E-P1 local shell;
- frozen 0E-P2 loopback Telnet;
- frozen 0E-P3 auth and private-LAN Telnet;
- frozen 0E-P4 virtual PTY;
- frozen 0E-P5 classic vocabulary;
- frozen `pyproject.toml` console entry-point boundary;
- frozen systemd unit.

The CI gate also replays Stage-C behavior, the Stage-A 29-component packet-engine freeze, P5/P3/P4 evidence, 0D logging/MHEARD/diagnostics evidence, sustained-TNC behavior and preserved physical evidence, plus the daemon zero-I/O framework self-test.

## Qualification-marker cleanup

The Stage-C checkpoint itself remains immutable at:

`checkpoint/product-observability-stage-c-host-qualified` @ `6651480fb7c4872fa2349ef0ad82f9d9920b7253`

Seven accidental one-line hidden marker files created during Stage-C checkpoint bookkeeping were removed only on the descendant Stage-D development branch. Stage D's architecture contract requires all seven to remain absent. No Stage-C historical checkpoint or evidence was rewritten.

Removed paths:

- `docs/qualifications/.checkpoint-final`
- `docs/qualifications/.no-more`
- `docs/qualifications/.oops`
- `docs/qualifications/.stage-c-checkpoint`
- `docs/qualifications/.stage-c-final`
- `docs/qualifications/.stop`
- `docs/qualifications/.this-is-bad`

## Safety boundary

Stage D adds no modem owner, hardware serial path, KISS DATA authority, packet decoder, TX path, automatic retry, beacon scheduler, UNPROTO/converse behavior, connected-mode AX.25, retention automation, firmware flash path, GPIO path, or RF operation.

Console sessions are observers/command interpreters only. TX/link/config commands that belong to 0F, 0G, or later product-control stages remain unavailable exactly as frozen in 0E-P5.

## Next stage

The next fresh-install integration stage can update the installer/product deployment around this fully host-qualified daemon graph while preserving the normal no-flash/no-TX defaults. Physical HAT/RF work remains deferred until the installed-appliance/fresh-OS qualification stages explicitly require it.
