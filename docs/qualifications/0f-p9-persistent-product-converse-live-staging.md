# 0F-P9 persistent product UNPROTO/CONVERSE live staging

Status: **pre-RF staging only**. This document does not constitute physical evidence.

## Qualification boundary

0F-P9 qualifies the already-physical 0F-P8 UNPROTO/CONVERSE implementation through the **normal installed appliance**:

`/opt/ywd-1278/source` -> `/opt/ywd-1278/venv` -> `ywd-1278.service` -> normal product Telnet console -> existing product TX admission/channel-access/modem graph.

P9 does not add or requalify another frame builder, KISS injection path, modem owner, UART owner, CSMA engine, scheduler, automatic retry, firmware writer, or option-byte writer.

The live test is bounded to **one manually entered converse line** at the already-qualified product TX profile:

- frequency: `145.050 MHz`
- TX power: `200/255`
- source: `KJ6YWD-10`
- command: `UNPROTO JIM VIA YWDNOD`
- information: `YWD-1278 P9 PERSISTENT SERVICE 1/1`
- exact source-frame decode expected: `KJ6YWD-10>JIM,YWDNOD:YWD-1278 P9 PERSISTENT SERVICE 1/1`
- automatic TX retry: **none**
- maximum P9 qualification TX lines: **one**

A later digipeated copy with `YWDNOD*` is acceptable as same-session RX evidence but does not replace the required independent exact source-frame decode.

## Required order

1. Check out the exact P9 branch tip that has passed `0f-p9-ci`; the tracked tree must be clean.
2. Run `installer/update-installed-software.sh --dry-run`. It must report zero installed-source/config/systemd/UART/RF/firmware mutation.
3. Run the software-only updater with `--expected-source-commit` set to that exact green tip. Persistent TX must still be disabled. No HAT firmware action is permitted.
4. Confirm `/opt/ywd-1278/installed-commit` equals that exact green tip.
5. With persistent TX still disabled, connect to the normal product Telnet console, set `UNPROTO JIM VIA YWDNOD`, and verify `CONVERSE` fails closed with the TX-disabled response. Do not enter converse text in this phase.
6. Run `installer/product-tx-control.sh enable --dry-run` against the exact installed commit. It must report zero mutation/RF I/O.
7. Explicitly enable persistent TX using the exact P9 authorization and arm phrase. This operation itself sends no packet.
8. Connect to the **normal installed** product Telnet console and execute only:

   ```text
   UNPROTO JIM VIA YWDNOD
   CONVERSE
   YWD-1278 P9 PERSISTENT SERVICE 1/1
   ```

   No second converse text line is permitted during P9 qualification.
9. Independently decode the exact source frame once. The test is failed rather than retried if that one source frame is not observed.
10. While remaining in the same CONVERSE session, observe one `RX ...` line from normal 145.050 traffic. An echoed/digipeated copy of the P9 frame is valid live-RX evidence.
11. Enter `/CMD`; the normal `cmd:` prompt must return.
12. Run `STATUS` and retain the output. The fresh normal-service runtime must show exactly one TX dispatch/admission/dispatch, zero queue depth, zero drops/failures, and no second internal dispatch after a short hold.
13. Do not send another RF line. Exit the Telnet session.
14. Immediately run `installer/product-tx-control.sh disable`.
15. Verify persistent configuration is `frequency_mhz = 145.050`, `tx_power = 200`, `tx_enabled = false`; installed P9 source remains deployed; service policy is healthy; no firmware or option-byte write occurred.

## Required evidence to freeze P9

The target-Pi record must capture, at minimum:

- exact checked-out/installed P9 commit;
- prior installed commit;
- software-only updater PASS and its no-RF/no-firmware markers;
- RX-safe `CONVERSE` rejection before enabling TX;
- persistent TX enable PASS at 145.050 MHz / power 200;
- `UNPROTO DEST=JIM VIA=YWDNOD` response;
- exactly one converse TX queue response;
- independent exact source-frame decode count = 1;
- same-session live RX line;
- `/CMD` command-mode restoration;
- STATUS accounting showing exactly one dispatch and no retry/drop/failure;
- persistent TX disable PASS;
- final `tx_enabled=false`, `tx_power=200`, `frequency=145.050 MHz`;
- installed source remains exact P9 commit;
- firmware flash = NO;
- option-byte write = NO.

After those facts are recorded, P9 physical evidence can be committed, contract-locked, checkpointed, exact-tip CI-qualified, and only then fast-forwarded to `dev`.
