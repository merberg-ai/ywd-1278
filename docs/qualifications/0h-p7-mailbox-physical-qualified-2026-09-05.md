# 0H-P7 mailbox physical qualification

Candidate `33d49c2b6c0824cf6b182e1a5636ee0250a189bb` passed the guarded mailbox RF round trip at 145.050 MHz from the deployed LinBPQ node's `KJ6YWD-15` downlink identity.

The session proved HELP, an empty LIST, exact self-addressed SP composition and deposit, a populated LIST, owner-authorized READ with exact subject and body, acknowledged BYE, and orderly DISC/UA. The harness submitted 25 link actions and reported `YWD1278_0H_P7_MAILBOX_ACCEPTANCE=PASS`.

The disposable `/run` mailbox was removed, normal service was restored, persistent TX remained disabled, configuration SHA-256 remained `2c073d8f022c7174027a0cf424c6e285ffcb0ff3375f9baf6d4553cab2ff3b76`, and neither flash nor option bytes were written. Operator evidence also showed that full `LIST` and `READ 1` work while optional LinBPQ-style `L` and `R 1` aliases are not yet implemented.
