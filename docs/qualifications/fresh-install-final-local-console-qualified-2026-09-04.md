# YWD-1278 fresh-install final local-console qualification

Date: 2026-09-04 (America/Los_Angeles)

## Result

**PHYSICALLY QUALIFIED.**

This closes the last open interactive-console gate in the fresh-install / flash / run appliance qualification.

## Product under test

- Installed product commit: `2f5299e65add072fea6ee55a54dc421faf00c276`
- Installed local console entrypoint: `/opt/ywd-1278/venv/bin/ywd1278-console`
- Frame database: `/var/lib/ywd-1278/ywd-1278.sqlite3`
- Local console implementation blob: `9fed5416ca9123811413f4ef284abff0006a48dd`

The implementation blob is the same frozen local console previously qualified at 0E-P1. No local-console implementation change was made for this final appliance gate.

## Physical interactive session

The operator launched the installed console directly on the target Pi while `ywd-1278.service` remained enabled and active.

Observed banner:

`YWD-1278 0.1.0-alpha0 LOCAL TNC CONSOLE`

Manually exercised commands:

- `VERSION` -> `YWD-1278 0.1.0-alpha0`
- `HEALTH` -> `HEALTH OK`, `PROBLEMS NONE`, `SOURCES 1/10`
- `MHEARD 5` -> two persisted stations including `KJ6YWD-5` and `KJ6YWD`
- `HELP` -> expected frozen local-console command surface
- `QUIT` -> `BYE`, followed by clean return to the Pi shell

The MHEARD view remained read-only and the running packet service was not stopped or restarted for the test.

## TTY wrapper-probe note

The shell precheck reported `TTY_STDIN=YES` and `TTY_STDOUT=NO`. The latter is treated as an imperfect shell/capture probe rather than a product failure because the installed console itself demonstrably emitted its banner/prompt and synchronous responses over the interactive session, accepted five manually entered commands, and returned cleanly to the shell after `QUIT`.

The qualification claim is therefore grounded in the direct interactive console transcript, not in the wrapper's `test -t 1` result.

## Safety boundary

This console path is host-only and read-only with respect to packet state. The test:

- did not open the modem UART through the console,
- did not create a KISS session,
- did not open a network listener,
- did not open a TX path,
- did not mutate persistent configuration,
- did not transmit RF,
- did not write firmware or option bytes.

## Conclusion

The installed local classic console is physically qualified on the fresh-install appliance. Together with the previously frozen Stage H fresh-OS qualification and Stage I single-shot TX qualification, all integration gates in GitHub issue #35 are now complete.
