# YWD-1278 fresh install / flash / run qualification preparation

Date: 2026-09-03 (America/Los_Angeles)

## Frozen starting point

This work starts from the exact post-0E qualified tree:

- `dev`: `383de08ede7b452fc773bc5cb6803e4a5acd39cf`
- checkpoint: `checkpoint/pre-fresh-install-flash-run`
- preparation branch: `dev-fresh-install-flash-run`

The checkpoint is immutable. Appliance integration work must not rewrite historical 0B/0C/0D/0E qualification evidence or silently modify frozen qualified boundaries.

## What is already qualified

The fresh-appliance effort is integration/productization, not a repeat of modem/RF engineering.

Already qualified before this stage:

- YWD-1278 packet firmware lineage and protected firmware backup/restore mechanics.
- AX.25 codec/FCS/parser and Bell-202 RX/TX serialization.
- single-owner modem transport and real Raspberry Pi UART ownership.
- live RX at 145.050 MHz through `YWD_RX -> Bell-202 -> AX.25 -> TCP KISS`.
- physically qualified AX25R4 raw-RSSI/channel-busy firmware, SHA256 `b06fcbf0baa36e865198091cee27c66e1624ef08117ee685253a7a5613c7c616`.
- p-persistent CSMA, half-duplex RX/TX/RX lifecycle, TXDELAY, KISS control plane, bounded KISS DATA admission, and sustained bidirectional KISS sessions.
- monitor stream, MCOM/MCON/MRPT, SQLite logging, MHEARD, retention and diagnostics.
- classic TNC console P1-P5: local shell, loopback Telnet, authenticated private-LAN Telnet, virtual PTY/serial personality, and explicit TNC2/MFJ-style vocabulary.

No RF qualification above is reopened merely by assembling the product daemon/installer. Any new behavior that changes the qualified modem, access, TX or RF boundary must receive its own qualification.

## Current product gap

At this starting point the appliance deliberately fails closed:

1. `installer/install.sh` installs the framework but never flashes firmware.
2. `installer/install.sh` leaves `ywd-1278.service` disabled/inactive.
3. `src/ywd1278/daemon.py` only supports the framework self-test; normal execution exits with code 78 because the qualified packet runtime is not yet wired into the product daemon.
4. Safe configuration defaults keep `radio.tx_enabled = false` and `firmware.allow_automatic_flash = false`.
5. The systemd unit structure exists, but its `ywd1278d` target is still the fail-closed framework daemon.

These are the exact boundaries this preparation branch is intended to close.

## Qualification strategy

### Stage A — freeze the first product packet-engine boundary

Goal: name and pin the exact qualified runtime components the appliance is allowed to compose.

Requirements:

- preserve existing 0B/0C physical evidence;
- pin the AX25R4 firmware identity/hash used by the appliance;
- pin the qualified sustained KISS/CSMA/TX/RX runtime components;
- pin monitor/logging/diagnostics and console components;
- add a preservation contract so appliance work cannot silently mutate those frozen components.

No UART, flash or RF action is required for Stage A.

### Stage B — assemble the production daemon, host-only first

Goal: replace the code-78 framework stub with a bounded appliance runtime composed from the frozen qualified pieces.

The daemon must:

- parse `/etc/ywd-1278/config.toml` fail-closed;
- own the modem UART through exactly one qualified owner;
- configure 1200-baud packet RX on the configured frequency;
- run the qualified sustained RX -> CSMA -> RX_STOP -> TX -> RF-idle -> RX_START lifecycle;
- expose TCP KISS using configured loopback/private policy;
- compose monitor/logging/MHEARD/diagnostics;
- compose the qualified classic console transports/personality;
- shut down cleanly on SIGTERM;
- keep TX disabled unless configuration and product safety gates explicitly authorize it;
- never create an automatic-retry path for a frame whose TX outcome is uncertain.

Qualification begins with fake/thread-bound transports only. No physical UART/RF until the exact host graph is green.

### Stage C — product installer + guarded firmware deployment

Goal: turn the existing safe installer into the appliance installer without weakening its protections.

Required order for any real firmware write:

1. identify Raspberry Pi/platform and supported HAT;
2. audit/release the UART;
3. identify current HAT firmware state;
4. create and verify the protected stock firmware backup before any write;
5. select only the exact allowlisted qualified YWD-1278 AX25R4 artifact;
6. require an explicit guarded flash authorization for the qualification run;
7. flash;
8. read back and verify exact programmed hash;
9. verify exact runtime/product identity;
10. preserve the stock backup and rollback path;
11. only then allow the product service to be enabled.

Unknown/ambiguous hardware or firmware identity must remain fail-closed. The normal safe default remains no automatic flash.

### Stage D — installed-appliance rehearsal on the existing Pi

Goal: prove `/opt/ywd-1278`, `/etc/ywd-1278`, systemd, state/log directories and service lifecycle before wiping a card.

Use the already-qualified HAT/runtime state where possible; do not repeat destructive flash work merely to test filesystem/systemd integration.

Minimum proof:

- install from the preparation candidate;
- service start/stop/restart works;
- SIGTERM releases UART and PTY/link resources;
- RX starts at 145.050 MHz;
- a live FCS-valid packet reaches KISS and monitor/MHEARD;
- console local/Telnet/PTTY surfaces work from the installed environment;
- TX remains disabled for the first installed-appliance rehearsal;
- reboot returns the service to the expected configured state.

### Stage E — fresh Raspberry Pi OS / flash / run physical qualification

This is the first true from-scratch appliance acceptance test.

Starting state:

- freshly written supported Raspberry Pi OS image;
- supported Raspberry Pi + supported MMDVM HAT;
- HAT in a known supported pre-product/stock state appropriate for the flash qualification;
- repository cloned as `~/ywd-1278` on the target operator account;
- no pre-existing `/opt/ywd-1278`, `/etc/ywd-1278`, YWD virtualenv or service state.

Expected flow:

1. clone/check out the exact candidate SHA;
2. run the normal installer entrypoint;
3. install dependencies and product files;
4. repair UART/serial-console settings if required and survive the reboot/resume path;
5. detect the supported HAT;
6. configure station/frequency/KISS/console with RF TX still disabled;
7. make and verify the protected original-firmware backup;
8. perform the explicitly authorized qualified AX25R4 flash;
9. verify readback hash and product identity;
10. enable/start `ywd-1278.service` only after all preconditions pass;
11. prove automatic startup after reboot;
12. receive a live 145.050 MHz packet through RF -> HAT -> daemon -> KISS;
13. prove monitor/MHEARD/diagnostics and classic console surfaces;
14. explicitly authorize the TX subtest;
15. submit a bounded KISS DATA frame;
16. require real CSMA/channel-access gating;
17. independently decode the exact transmitted frame on a separate receiver;
18. prove RX resumes afterward and another non-self live packet can be decoded;
19. reboot again and prove service/config/state recovery;
20. verify no duplicate dispatch, no automatic retry, zero unexpected FIFO/subscriber drops, and UART released cleanly on service stop.

## Safety gates for the fresh test

- No wildcard/public console exposure as part of this milestone.
- No beacon scheduler, UNPROTO/converse TX, connected-mode AX.25, node or mailbox behavior is required.
- `0F` and `0G` are explicitly not prerequisites for this appliance qualification.
- TX is disabled during install and first boot; the physical TX acceptance subtest requires a separate explicit authorization step.
- A failed/uncertain flash must stop before service enable.
- A failed/uncertain TX must never trigger an automatic retry.
- Historical physical evidence is never edited to make the appliance test pass.

## Pass condition

The milestone passes only when a fresh Raspberry Pi OS installation can, using the normal product installer and no manual source-tree qualification scripts, safely reach a verified YWD-1278 firmware/runtime state, start the product service automatically, receive live packet RF, expose the qualified TNC interfaces, perform one explicitly authorized CSMA-controlled KISS-originated TX with independent decode proof, resume RX, and survive a subsequent reboot with the same configured behavior.

## Immediate next work

1. Freeze the first product packet-engine component manifest/contract.
2. Replace the `ywd1278d` framework stub with the composed host-qualified appliance runtime.
3. Update installer/systemd integration around that runtime while preserving default no-flash/no-TX safety.
4. Run the installed-appliance rehearsal.
5. Only then perform the fresh-image/flash/run physical qualification.
