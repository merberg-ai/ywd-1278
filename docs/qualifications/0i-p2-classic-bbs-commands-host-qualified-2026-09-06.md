# 0I-P2 classic packet BBS commands — host qualified

Date: 2026-09-06 UTC

Base checkpoint: `checkpoint/0i-p1-persistent-mailbox-core-host-qualified`
(`44ec69e30ab9db16415a060a1b4c2c1a659b23c4`)

Candidate head: `516a3e8960b542b69dd043713a20250e49db055d`

Candidate CI: `34008133364` — PASS

Qualified source blob:

- `src/ywd1278/node/classic_bbs.py`
- Git blob `e9ebd80b07f9e91cb6f57ca61c2a010b5e17f3fd`

## Qualified behavior

P2 supplies a bounded classic packet BBS personality over the frozen P1
persistent mailbox store:

- banner with connected-user new/visible counts and `de <bbs>` prompt;
- explicit `H`/`HELP`/`?`, `I`/`INFO`, and `B`/`BYE` commands;
- `L`, `LN`, `LR`, and `LM` list views;
- `R <n>` message reads with familiar headers, body, and end marker;
- owner-safe `K <n>` message kill delegated to frozen P1 authorization;
- `SP <call>` personal-message composition;
- `SB <topic>` bulletin composition;
- separate title/body prompts, `/EX` save, and `/ABORT` cancellation;
- fragmented input and multiple commands per connected information payload;
- 512-byte bounded input buffer and 256-byte bounded command lines;
- all response actions are chunked to configured PACLEN 32..256;
- no partial deposit on composition abort or input-buffer failure;
- `BYE` produces an explicit terminal close action.

All ten functional host tests pass, including cross-SSID mailbox identity,
independent bulletin read state, personal/bulletin kill authorization,
fragmentation, composition abort, list ordering, and orderly close.

The first CI attempt exposed only a contract-test false positive because the
source docstring contained the words `KISS socket`; the import-aware contract was
corrected without changing the P2 implementation.

## Preserved boundaries

The P1 store remains byte-exact at
`f9e948ebc0da19ede88dfad97eddbf7eb15dc4fc`.  P2 is not imported by the daemon
or product appliance and owns no connected link, modem, KISS transport, UART,
TX, RF, scheduler, service lifecycle, forwarding dispatch, flash, GPIO/reset,
or option-byte path.

No target-Pi or RF test is required for P2.  The first persistent service RF
qualification remains 0I-P5 after configuration and runtime composition are
host-qualified.
