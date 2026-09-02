# Firmware Flash Safety Contract

Firmware programming is the highest-risk operation in YWD-1278. The tooling is therefore designed to fail closed rather than attempt generic MMDVM flashing.

## Required gates before any YWD-1278 write

A target may be flashed only when all of the following are true:

1. the Raspberry Pi-side UART is known and free;
2. the running MMDVM application responds to a read-only `GET_VERSION` probe, unless an explicit recovery path is being used;
3. that identity matches exactly one allowlisted target;
4. the target manifest says `flash_enabled=true`;
5. exact flash geometry is known;
6. option-byte operations are forbidden;
7. a deterministic YWD-1278 firmware artifact exists;
8. its SHA256 matches the manifest;
9. the target's required rollback backup exists or is successfully captured and verified;
10. the user explicitly confirms the actual write after entering bootloader mode.

If any gate fails, no write occurs.

## Hardware detection philosophy

`MMDVM_HS` is an ecosystem, not one guaranteed board design. A product name such as "MMDVM HAT" is not enough evidence to flash.

Target definitions should eventually include as many positive signals as are practical:

- exact running firmware identity families;
- MCU/bootloader response and reported device ID;
- TCXO frequency;
- RF chip;
- simplex/duplex layout;
- known reset/boot method;
- flash geometry;
- known-good deterministic build target.

Unknown clones remain unsupported until physically qualified.

## Backups

Protected backups live under:

`/var/lib/ywd-1278/firmware-backups/`

They are mode `0700`/`0600` because they may contain vendor firmware from the user's own device.

Each backup is accompanied by metadata including:

- target ID;
- captured application identity;
- flash base/size;
- SHA256;
- capture time;
- statement that option bytes were not read/written by YWD-1278 tooling.

A backup is called **stock** only when its captured identity is explicitly listed in the target manifest's `stock_identities`.

## Stock restoration

`restore-stock.sh` will not accept an arbitrary `.bin` file. It requires a YWD-1278 protected backup directory with valid metadata and checksum, and the recorded identity must be an allowlisted stock identity for that target.

For an unresponsive application, recovery requires the explicit `--allow-unresponsive` path plus the same target-bound backup metadata and manual bootloader confirmation.

## Option bytes

YWD-1278 firmware tools must not issue STM32 option-byte write/erase commands. A target manifest that permits option-byte operations is rejected by the current flash framework.

## Service ownership

Before programmer access, known YWD/MMDVM services are stopped and their enable/active states are recorded. The script refuses to continue if another process still owns the UART. Recorded service state is restored through an exit trap on success or failure.

## Current alpha0 state

The first reference target is intentionally `flash_enabled=false` and has no qualified flash geometry/artifact hash yet. This means the initial framework can perform identity probing, but a YWD-1278 firmware write remains unreachable until the firmware port is built and requalified.
