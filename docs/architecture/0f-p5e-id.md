# 0F-P5e manual station identification

P5e adds one operator-requested `ID` command to the classic console. It is a
host composition layer only; it does not add a transmitter, queue, timer, or
hardware path.

## Fixed frame

`ID` accepts no arguments and constructs one AX.25 UI frame without an FCS:

- source: the configured classic station address
- destination: `ID`
- path: direct (empty)
- information: `YWD-1278 ID <source>`

The frame is offered exactly once to the P4-qualified product submitter. A
rejection or exception is returned to the operator and is never retried.

## Safety boundary

The command fails closed when `radio.tx_enabled=false`, when the product
submitter is unavailable, or when the fixed information text exceeds PACLEN.
It does not change UNPROTO, converse, beacon text, or beacon scheduling state.
It has no periodic mode. Persistent configuration remains unchanged.

P5e selects the extended console in the daemon while sharing the existing
P5c2 coordinator and P4 transmitter graph. Host qualification uses only a fake
HAT. A later, separately sealed acceptance harness may authorize one physical
ID frame and must independently prove exact decode, no duplicate dispatch, RX
recovery, and restoration of the no-TX service state.
