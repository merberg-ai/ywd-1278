# 0F-P5a host-only beacon staging — 2026-09-05

Base checkpoint:

`checkpoint/0f-classic-unproto-converse-p4-qualified` @ `d5e7a38abb3e541345b926105b7fc3d83d1459d5`

Implementation commit:

`56ab18ce6762faf185a5a728ddef8f52dcbe6ac0`

Branch:

`dev-0f-classic-tx-p5-beacon`

## Staged scope

- bounded printable-ASCII BTEXT state;
- deterministic `BEACON EVERY <seconds>` and `BEACON OFF` state;
- default OFF;
- explicit polling with at most one inert due event;
- missed intervals discarded instead of replayed;
- TX-disabled due polling returns no event;
- no background timer, daemon composition, TX admission, UART, modem, target-Pi action, or RF;
- `ID` explicitly remains non-transmitting pending P5e semantics.

Local targeted behavior, architecture, P4 preservation, appliance-seal, Stage-I, and P7/P8 evidence tests passed before staging.

This record does not claim CI qualification. Record the GitHub Actions run separately only after it completes successfully.

**No P5 RF or periodic TX is authorized.**
