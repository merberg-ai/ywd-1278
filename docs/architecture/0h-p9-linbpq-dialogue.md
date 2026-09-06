# 0H-P9 classic LinBPQ delivery dialogue

The deployed target identifies itself with `[BPQ-6.0.25.30-IHJM$]`, `YWDBBS:KJ6YWD-1}`, and the command prompt `de KJ6YWD>`. Its help advertises classic interactive `SP` personal-message submission, `R` message reading, and `B` logoff rather than requiring an FBB-only forwarding port.

0H-P9 is a caller-driven state machine for one prepared P8 message. It requires a BPQ SID before the exact configured command prompt, then prepares `SP <destination>`, title, exact body byte chunks, a line boundary, and `/EX` only after the corresponding prompts. A returned command prompt after submission completes the dialogue. Explicit rejection text, non-ASCII input, more than 64 remote lines, or more than 512 buffered bytes fails closed.

Every returned action is inert. This layer opens no link, socket, service, store, modem, thread, or RF path; it does not delete or acknowledge the stored message. Exact title/body prompt text remains a physical P10 acceptance item because the supplied transcript characterized the banner, command set, and prompt but did not submit a message.
