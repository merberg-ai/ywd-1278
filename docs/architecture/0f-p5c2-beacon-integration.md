# 0F-P5c2 shared console and daemon integration

P5c2 composes the frozen P5b coordinator and P5c scheduler into the product
daemon. One thread-safe coordinator is constructed and shared by every Telnet
and PTY command session and by the single scheduler worker.

`BTEXT` and `BEACON` therefore operate on product state rather than disposable
session state. `UNPROTO` remains per-session as qualified in P4; arming a beacon
atomically snapshots that session's destination/path into shared beacon state.
Any session can query or cancel the shared schedule.

The daemon starts the console before the scheduler. During shutdown it stops
new console commands first, joins/disarms the scheduler second, and stops the
packet engine last. The same clock is supplied to command arming and scheduler
polling; production uses `time.monotonic`, while host tests inject a controlled
clock.

Persistent `[beacon].enabled=true` remains rejected by the frozen appliance
configuration gate. Startup is always OFF, restart creates new OFF state, and
only an explicit runtime `BEACON EVERY` command can arm the scheduler.

The complete command-to-scheduler-to-existing-DATA-admission graph is tested
against the qualified fake HAT. No target Pi, UART, firmware, or RF is used.
