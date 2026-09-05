# 0H-P5 inbound node physical qualification

Candidate `07ca06cc0cd5b7b05de4dce4d3ca1e7c452caf2a` passed the guarded physical acceptance at 145.050 MHz against the deployed LinBPQ node. LinBPQ listens as `KJ6YWD-5` and originated the tested outgoing downlink as `KJ6YWD-15`.

The independent packet log captured SABM/UA, the exact two-line YWDNOD banner, complete HELP and INFO responses, the VERSION response, BYE, acknowledgement of the BYE I frame, and the subsequent DISC/UA exchange. The harness submitted 12 link actions and reported `YWD1278_0H_P5_INBOUND_NODE_ACCEPTANCE=PASS`.

The persistent configuration SHA-256 remained `2c073d8f022c7174027a0cf424c6e285ffcb0ff3375f9baf6d4553cab2ff3b76`, persistent TX remained disabled, normal service was restored, and neither flash nor option bytes were written.
