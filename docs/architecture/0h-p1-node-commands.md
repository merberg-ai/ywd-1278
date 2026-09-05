# 0H-P1 node command layer

P1 is a pure, per-connection command stream above the qualified 0G link. It
assembles fragmented CR/LF-delimited input with a 256-byte buffer and 128-byte
command limit. Exact HELP, INFO, VERSION, and BYE commands return bounded ASCII
response records. Control and non-ASCII input, overflow, arguments, and unknown
commands fail closed.

The layer has no socket, timer, shared registry, database, mailbox, forwarding,
sysop, modem, or RF owner. It is not imported by the product runtime. Returned
bytes remain inert for a later integration stage to place into connected I
frames. BYE requests link closure but cannot perform it itself.
