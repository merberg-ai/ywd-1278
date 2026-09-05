# 0F-P5a host-only BTEXT / BEACON / ID design

0F-P5a adds an inert classic-command and scheduler model above the frozen P4
implementation. It does not compose that model into the daemon or product TX
backend.

## Commands

- `BTEXT` queries the current text. `BTEXT <text>` atomically replaces it after
  printable-ASCII and configured `PACLEN` validation.
- `BEACON` reports schedule state.
- `BEACON EVERY <seconds>` replaces the current schedule. The accepted range is
  10 through 86,400 seconds. Arming requires both BTEXT and an UNPROTO
  destination. It never changes the construction-time TX policy.
- `BEACON OFF` cancels the schedule and clears its due time.
- `ID` is deliberately non-transmitting in P5a. Its RF payload, destination,
  and admission semantics remain owned by the separate P5e decision.

## Scheduler contract

The schedule owns no thread and reads no clock implicitly except when a command
is issued or a caller explicitly polls it. Boot state is OFF. A due poll returns
at most one immutable AX.25 UI frame body without FCS and never invokes the
existing submit callback. If several intervals were missed, the next deadline
is scheduled from the observation time; missed events are discarded, so there
is no catch-up burst.

When `radio.tx_enabled=false`, due polling returns nothing and does not consume
the pending deadline. Reissuing `EVERY` replaces the old deadline and advances
a generation counter. `OFF` invalidates the deadline immediately.

## Deferred boundaries

P5b must decide where product-owned schedule state lives and connect one due
event to the already-qualified KISS DATA admission boundary. P5c must qualify
lifecycle and shutdown behavior at that composed boundary. Neither step exists
in P5a. There is no daemon wiring, periodic task, TX queue, CSMA owner, modem
owner, UART access, target-Pi change, or RF authorization here.
