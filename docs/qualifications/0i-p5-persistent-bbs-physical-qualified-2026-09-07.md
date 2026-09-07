# 0I-P5 persistent BBS physical qualification

Date: 2026-09-07 UTC

Status: **PHYSICALLY QUALIFIED**

## Tested source

The live Pi/HAT/RF session exercised the exact installed source:

- branch: `dev-0i-p5-persistent-bbs-physical-staging`
- commit: `9c02f01515a0ae3a933c4471409673c7c67425c9`
- tree: `f6893210da62cdee00559085d850678f599b5e28`

Host-qualified base:

- `checkpoint/0i-p4c2-mailbox-product-composition-host-qualified`
- commit `dd2f96f27050bf24c57e24a9b2b3a2ba86688b27`
- tree `e6cd8d7081990cd435f92db0c578b6f14de5cc5a`

The P4c2 runtime remained frozen during P5. Post-test commits only repair the
P5 staging helper's shell invocation and record qualification evidence.

## Physical product profile

- station/BBS: `KJ6YWD-10`
- RF: `145.050 MHz`
- qualified TX power: `200/255`
- node alias: `YWDNOD`
- direct connected-mode peer used: `KJ6YWD`
- connected-mode digipeater path: none
- mailbox database: `/var/lib/ywd-1278/mailbox.sqlite3`
- mailbox PACLEN: `128`
- normal daemon: `ywd-1278.service`
- forwarding: disabled
- beacon: disabled

Live HAT identity was verified by the existing 0F-P9 TX authority gate:

`MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed`

Target:

`mmdvm-hs-hat-stm32f103-simplex-14.7456-adf7021`

No firmware or option-byte write was required for P5.

## Installation and staging

The development clone in `~/ywd-1278` and the curl-installed product source in
`/opt/ywd-1278/source` were aligned to the exact tested commit.

The software-only installed update reported PASS with:

- persistent TX disabled during update;
- config mutation: no;
- firmware action: no;
- modem UART access: no;
- RF transmission: no.

The existing persistent config predated 0I and did not contain `[node]` or
`[mailbox]`. The bounded legacy bootstrap added the exact disabled P5 profile,
kept TX disabled, did not mutate the service, and reported PASS.

P5 staging then reported:

- `PERSISTENT_BBS_CONFIG_VALID=YES`
- `NODE_MAILBOX_ENABLED=YES`
- `PERSISTENT_TX_ENABLED=NO`
- `SERVICE_ACTIVE=NO`
- no UART/RF/flash/option-byte activity.

The frozen 0F-P9 TX gate then verified the live HAT identity and enabled the
already-qualified 145.050 MHz / power-200 product TX authority. It reported:

- `YWD1278_0F_P9_PERSISTENT_TX_ENABLED=PASS`
- `RUNTIME_IDENTITY_VERIFIED=YES`
- `SERVICE_ENABLED=YES`
- `SERVICE_ACTIVE=YES`
- `TX_FREQUENCY_HZ=145050000`
- `TX_POWER=200`
- `PERSISTENT_TX_ENABLED=YES`
- `AUTOMATIC_TX_RETRY=NO_NEW_RETRY`
- no firmware or option-byte write.

With TX live, status showed the intended product composition:

- `CONFIG_TX_ENABLED=TRUE`
- `CONFIG_NODE_ENABLED=TRUE`
- `CONFIG_MAILBOX_ENABLED=TRUE`
- `CONFIG_NODE_ALIAS=YWDNOD`
- mailbox database `/var/lib/ywd-1278/mailbox.sqlite3`
- service active/enabled.

## Direct connected BBS qualification

An independent packet endpoint issued a direct connection to `KJ6YWD-10` on
145.050 MHz. The connected session produced:

```text
YWDNOD:KJ6YWD-10} Connected to BBS
YWD BBS:KJ6YWD-10
Hello KJ6YWD - 0 new / 0 visible message(s)
Type H for help
de KJ6YWD-10>
```

The help interface exposed the expected classic BBS commands including
`L/LN/LR/LM`, `R`, `K`, `SP`, `SB`, `INFO`, and `BYE`.

The RF session successfully exercised:

1. empty `L` -> `No messages`;
2. `SB ALL`;
3. title `HELLO WORLD!`;
4. body `HELLO PACKET WORLD!`;
5. `/EX` -> bulletin 1 saved;
6. `SP KJ6YWD`;
7. title `IT WORKS!`;
8. body `This is a test of my custom firmware and os for the raspberry pi with mmdvm hat on 2 meters.`;
9. `/EX` -> personal message 2 saved;
10. `L` showing both messages;
11. `R 1` returning the bulletin body and headers;
12. `R 2` returning the personal-message body and headers;
13. `INFO` reporting two visible messages and forwarding disabled;
14. `BYE` -> `73 - disconnecting from YWD BBS` and orderly link close.

The final RF-side mailbox view was:

```text
Msg#  TS  Size  To/Topic      From    Subject
    2  PN    92  KJ6YWD        KJ6YWD  IT WORKS!
    1  BN    19  ALL           KJ6YWD  HELLO WORLD!
```

## Independent RF monitor evidence

An independent 145.050 MHz packet monitor observed the actual connected-mode
traffic from `KJ6YWD-10` to `KJ6YWD`, including:

- UA establishing the session;
- numbered I frames carrying the BBS banner, prompt and responses;
- RR supervisory traffic;
- the saved-message/list/read responses;
- `73 - disconnecting from YWD BBS`;
- final `DISC+`.

Representative monitor observations included:

```text
KJ6YWD-10 to KJ6YWD ctl UA-
KJ6YWD-10 to KJ6YWD ctl I00^ pid=F0(Text)
YWDNOD:KJ6YWD-10} Connected to BBS
...
KJ6YWD-10 to KJ6YWD ctl I11^ pid=F0(Text)
73 - disconnecting from YWD BBS
KJ6YWD-10 to KJ6YWD ctl DISC+
```

Other live packet activity on 145.050 remained visible during the test, further
showing that qualification occurred in the normal live packet environment.

## Shared local MBOX qualification

While the same product service and mailbox database remained active, the local
loopback product console at `127.0.0.1:8010` entered `MBOX` and reported:

```text
YWD BBS:KJ6YWD-10
Hello KJ6YWD - 0 new / 2 visible message(s)
```

`L` displayed the exact two RF-created messages:

```text
    2  PR    92  KJ6YWD        KJ6YWD  IT WORKS!
    1  BR    19  ALL           KJ6YWD  HELLO WORLD!
```

`R 1` returned `HELLO PACKET WORLD!` and `R 2` returned the full personal
message body created over RF. `COMMAND` then returned the local terminal to
`COMMAND MODE` without dropping the terminal connection.

This physically proves that the connected RF BBS and local `MBOX` personality
share the same persistent mailbox store.

## Cleanup and final safe state

The first automated cleanup attempt stopped `ywd-1278.service` and then hit a
staging-helper packaging issue: `product-tx-control.sh` was installed without an
executable bit, while the helper attempted direct execution. The failure
occurred with the product service already stopped, so no running TX path
remained.

Persistent TX was explicitly revoked through the already-qualified control by
invoking it with `bash`. Cleanup then completed successfully. The operator's
final state re-check showed:

```text
CONFIG_TX_ENABLED=FALSE
CONFIG_NODE_ENABLED=FALSE
CONFIG_MAILBOX_ENABLED=FALSE
CONFIG_NODE_ALIAS=YWDNOD
CONFIG_MAILBOX_DATABASE=/var/lib/ywd-1278/mailbox.sqlite3
CONFIG_MAILBOX_PACLEN=128
SERVICE_ACTIVE=active
SERVICE_ENABLED=enabled
P4C2_STAGE_STATE=ABSENT
INSTALLED_COMMIT=9c02f01515a0ae3a933c4471409673c7c67425c9
```

Direct TOML inspection independently reported:

```text
TX_ENABLED=FALSE
NODE_ENABLED=FALSE
MAILBOX_ENABLED=FALSE
MAILBOX_DB=/var/lib/ywd-1278/mailbox.sqlite3
```

The persistent database remained present with mode `0600`; observed size was
40960 bytes.

## Post-test staging-helper repair

The cleanup failure was not a P4c2 runtime/BBS defect. The staging helper was
subsequently changed to invoke the frozen TX authority script as:

```text
bash "$TX_CONTROL" disable --expected-installed-commit "$installed_commit"
```

rather than relying on its executable bit.

Relevant closure commits:

- helper repair: `7bb9d973e129c93c263fa12ed39157884a59aa29`
- exact-line contract repair: `962cbafc4563abe04b30ed9cf99a2eecc50d46fd`

Exact-tip P5 CI run `34129834195` passed at `962cbafc4563abe04b30ed9cf99a2eecc50d46fd`,
including legacy-config bootstrap safety, P5 staging safety, zero-I/O dry runs,
all frozen P4c2/P4b/P4a/P3/P2/P1 regressions, product terminal regressions, and
package/framework self-test.

No qualified P4c2 runtime source was changed by this repair.

## Qualified scope

0I-P5 physically qualifies:

- normal installed product service on the supported MMDVM HAT;
- direct AX.25 connected BBS access to `KJ6YWD-10` on 145.050 MHz / power 200;
- real connected-mode UA/I/RR/DISC behavior through the existing product path;
- classic persistent BBS `H`, `L`, `SB`, `SP`, `R`, `INFO`, and `BYE` behavior;
- persistent personal mail and bulletin deposit/read;
- shared persistent storage between RF BBS and local `MBOX`;
- clean local `COMMAND` return;
- orderly remote disconnect;
- bounded staging and return to the RX-safe persistent configuration;
- mailbox database preservation after cleanup.

0I-P5 does **not** qualify:

- connected BBS sessions through digipeater paths;
- more than one simultaneous connected BBS owner;
- mailbox forwarding;
- beacon scheduling;
- arbitrary hardware targets;
- any new automatic TX retry beyond the already-qualified AX.25 connected-link
  semantics.

## Result

**0I-P5 persistent BBS physical qualification: PASS.**

The product now has a physically demonstrated persistent packet BBS reachable
over real 2-meter AX.25 and a local `MBOX` personality backed by the same
persistent mailbox database.
