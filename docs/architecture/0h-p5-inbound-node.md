# 0H-P5 inbound node integration

0H-P5 composes the frozen modulo-8 timed link and frozen node-command session into one caller-driven inbound session. It accepts only a direct connection from the configured peer, returns inert AX.25 actions, and owns no socket, modem, service, thread, persistent configuration, or RF dispatch.

The single bounded response queue holds at most 16 records and 2048 bytes. A valid incoming SABM resets ephemeral command state, prepares UA, and queues the two-line node banner. HELP and INFO responses are sent within the negotiated MAXFRAME window. BYE queues its response, and DISC is not prepared until that I frame is acknowledged and the queue is empty.

The physical harness is disabled by default. Live operation requires root, an exact CLI authorization, an exact interactive phrase, the recognized test firmware, the qualified persistent no-TX appliance, and an exact `KJ6YWD-5` remote. It temporarily enables the existing product TX graph at 145.050 MHz and restores the byte-identical persistent configuration and normal service on every exit path. It does not flash firmware or write option bytes.
