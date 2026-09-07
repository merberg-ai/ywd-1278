# 0I-P5 persistent BBS physical qualification — staging

Date: 2026-09-07 UTC

Authoritative host-qualified base:

- `checkpoint/0i-p4c2-mailbox-product-composition-host-qualified`
- commit `dd2f96f27050bf24c57e24a9b2b3a2ba86688b27`
- tree `e6cd8d7081990cd435f92db0c578b6f14de5cc5a`

Physical staging branch:

- `dev-0i-p5-persistent-bbs-physical-staging`

## Scope

P5 is a bounded physical qualification of the already host-qualified P4c2
persistent BBS composition on the exact supported Pi/HAT product path. No P4c2
runtime implementation is changed for this stage.

The physical profile is fixed to:

- station: `KJ6YWD-10`
- RF: `145.050 MHz`
- TX power: `200/255`
- node alias: `YWDNOD`
- one direct connected-mode peer at a time
- mailbox database: `/var/lib/ywd-1278/mailbox.sqlite3`
- mailbox PACLEN: `128`
- forwarding: disabled
- beacon: disabled
- automatic firmware flash: disabled

Connected BBS qualification is direct only. No digipeater path is part of P5.

## Installation/update boundary

The normal curl installer owns `/opt/ywd-1278`; a separate development clone may
exist at `~/ywd-1278`. Before P5, the development clone and installed software
must both resolve to the same exact pre-live staging commit.

The installed appliance is updated only with the already-qualified
`installer/update-installed-software.sh` path. Persistent TX must be disabled
before that update. The updater performs no firmware action, modem UART access,
or RF transmission.

The normal product service remains `ywd-1278.service`.

## Bounded configuration staging

`installer/persistent-bbs-physical-control.sh stage` is the only new staging
helper. It:

1. requires an exact installed commit;
2. requires the exact KJ6YWD-10 / 145.050 MHz / qualified-HAT profile;
3. requires `radio.tx_enabled=false`;
4. requires node and mailbox to be disabled before staging;
5. changes only `[node].enabled` and `[mailbox].enabled` to `true`;
6. validates the staged file through the installed product configuration
   loaders;
7. stops `ywd-1278.service` and leaves it stopped;
8. records the previous service active/enabled policy and a config backup;
9. opens no modem UART and transmits no RF.

It does **not** enable TX. Persistent TX authority remains owned by the frozen
0F-P9 `product-tx-control.sh` gate, including exact live firmware identity,
145.050 MHz, power 200, authorization token, and arm phrase.

## Physical activation sequence

After exact-tip staging CI is green, the operator may perform these phases in
order:

1. update `~/ywd-1278` to the exact staging tip;
2. explicitly revoke persistent TX if necessary;
3. software-only update `/opt/ywd-1278` to the exact same tip;
4. run P5 staging control and confirm TX remains disabled / service stopped;
5. run the existing guarded 0F-P9 TX enable operation;
6. verify normal `ywd-1278.service` reports:
   - `PRODUCT_TX=ENABLED`
   - `PERSISTENT_BBS=ENABLED`
   - `MBOX=ENABLED`
   - `FORWARDING=DISABLED`;
7. exercise local MBOX from the normal product terminal;
8. establish one **direct** AX.25 connection from an independent station to
   `KJ6YWD-10` on 145.050 MHz;
9. observe the connected BBS banner and prompt;
10. deposit/read at least one persistent message and prove the same mailbox is
    visible through local MBOX after the RF session;
11. exit the remote BBS with `BYE` and confirm the link closes normally;
12. run P5 cleanup and verify TX/node/mailbox are disabled while the mailbox
    SQLite database remains present.

## Expected remote BBS behavior

A successful direct connection should produce the frozen P4a/P2 personality,
including records equivalent to:

- `YWDNOD:KJ6YWD-10} Connected to BBS`
- `YWD BBS:KJ6YWD-10`
- a caller-specific `Hello ...` line
- `de KJ6YWD-10>`

The physical test should exercise at minimum:

- `SP <callsign>` message composition;
- title entry;
- message body entry;
- `/EX` save;
- `LN` or `L` listing;
- `R <message-number>` read;
- `BYE` orderly close.

## Cleanup boundary

`installer/persistent-bbs-physical-control.sh cleanup`:

1. stops the normal product service;
2. revokes persistent TX using the existing frozen 0F-P9 disable operation;
3. changes only `[node].enabled` and `[mailbox].enabled` back to `false`;
4. validates the RX-safe configuration;
5. restores the service active/enabled policy captured by staging;
6. preserves `/var/lib/ywd-1278/mailbox.sqlite3`;
7. performs no firmware or option-byte write and no cleanup RF transmission.

If cleanup fails after TX revocation, it fails closed with persistent TX still
disabled; the stage-state file is retained so the operator can diagnose before
restarting service.

## Evidence required to close P5

Capture the following from the same physical session:

- exact staging source commit and installed commit;
- P5 stage PASS markers;
- 0F-P9 TX-enable PASS markers and live firmware identity verification;
- normal service startup markers showing BBS/MBOX enabled;
- local MBOX banner/prompt and clean return to `cmd:`;
- independent RF evidence of a direct connection to KJ6YWD-10;
- connected BBS banner/prompt;
- successful SP save plus LN/L and R behavior;
- proof that the RF-created message is visible in local MBOX;
- orderly BYE/disconnect;
- P5 cleanup PASS markers;
- final `radio.tx_enabled=false`, `node.enabled=false`,
  `mailbox.enabled=false`;
- final normal service state;
- mailbox database still present.

## Preserved exclusions

P5 does not qualify:

- arbitrary digipeater paths for connected mode;
- more than one simultaneous connected BBS owner;
- forwarding;
- beacon scheduling;
- a new scheduler or application-level retry;
- any alternate modem/UART/RF path;
- firmware or option-byte writes;
- automatic TX retry beyond already-qualified connected AX.25 link semantics.
