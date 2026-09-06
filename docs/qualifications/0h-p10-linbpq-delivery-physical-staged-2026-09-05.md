# 0H-P10 LinBPQ delivery physical qualification

0H-P10 is the physical acceptance boundary for the host-qualified 0H-P9 classic LinBPQ personal-message dialogue.

The test starts from frozen checkpoint `checkpoint/0h-p9-linbpq-dialogue-host-qualified` at `618585fd2588235296a281022cf39feb5f2ba8e9`. It does not alter P9, P8, P7, persistent mailbox storage, or the normal appliance configuration.

## Physical target

- RF frequency: 145.050 MHz
- RF power: 200/255
- local AX.25 source: `KJ6YWD-10`
- LinBPQ listener: `KJ6YWD-5`
- BBS identity advertised by the observed transcript: `KJ6YWD-1`
- BBS command prompt: `de KJ6YWD>`
- one personal-message destination: `KJ6YWD-15`
- subject: `P10 TEST`
- body: `YWD-1278 0H-P10 LINBPQ DELIVERY 1/1`

The guarded harness opens one outbound AX.25 link to the LinBPQ listener, sends one `BBS<CR>` entry command, then gives the raw delivered BBS bytes to the frozen P9 state machine. Only the inert actions returned by P9 are submitted: `SP`, title, one body fragment, body line boundary, and `/EX`. No message scheduler, mailbox enumeration, storage mutation, acknowledgement/deletion, or persistent runtime wiring is added.

## Safety boundary

Without `--transmit` the harness exits after a dry-run plan and does not stop the service, open the modem UART, or transmit RF.

The physical path additionally requires:

1. root;
2. exact ancestry from the frozen P9 checkpoint;
3. a healthy enabled/active qualified appliance;
4. the exact packet firmware/eligibility checks;
5. `--authorize 0H-P10-LINBPQ-145050-KJ6YWD5-ONE`;
6. the interactive phrase `TRANSMIT-0H-P10-LINBPQ-KJ6YWD-5-ONE`.

The persistent service is stopped only for the disposable `/run/ywd-1278-0h-p10` runtime, then restored from the original config hash in `finally`. No flash, option-byte, or persistent configuration write is part of P10.

## Pass criteria

Physical qualification requires all of the following in one bounded run:

- SABM/UA to `KJ6YWD-5`;
- BBS entry submitted;
- live BPQ SID observed before the exact BBS prompt;
- live title/subject prompt drives exactly one P9 `TITLE` action;
- live message/body prompt drives the exact P9 body stream and `/EX`;
- the BBS command prompt returns after submission, completing frozen P9;
- exact P9 action sequence `SP,TITLE,BODY,BODY_END,END`;
- outstanding I frames reach zero;
- orderly DISC/UA completes;
- normal persistent service is restored;
- persistent TX remains disabled and persistent config hash is unchanged.

The physical run prints an escaped `REMOTE_TRANSCRIPT=` capture so the exact live title/body/acceptance text can be frozen as evidence after the run.
