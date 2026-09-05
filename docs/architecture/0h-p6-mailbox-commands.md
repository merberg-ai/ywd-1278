# 0H-P6 mailbox command integration

0H-P6 composes the frozen P1 node commands and P2 mailbox store without changing either capability. The connected AX.25 peer is authoritative for mailbox ownership and message sender identity; typed callsigns never grant read access.

The session adds bounded `LIST [limit]`, `READ <id> [offset]`, and `SP <recipient> <subject>` commands. Composition ends with `/EX` or is discarded with `/ABORT`. LIST exposes at most 12 records, and READ exposes at most 512 body bytes per request in 96-byte chunks. These limits fit the frozen inbound coordinator queue and PACLEN boundary. Message time is caller-injected, composition is capped by the frozen 4096-byte body limit, and storage or clock failures clear composition and fail closed.

The P5 inbound coordinator now accepts an injected command-session factory and disconnects cleanly if a response set exceeds its queue. It still owns no socket, service, modem, RF dispatcher, thread, persistent configuration, or default runtime integration. Physical P5 evidence and its executed harness remain byte-exact.
