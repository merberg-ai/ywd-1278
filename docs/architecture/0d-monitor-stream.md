# 0D monitor/logging architecture

## 0D-P1 decoded monitor stream

0D starts by observing the already-qualified packet event boundary.  It does **not** add another Bell-202 decoder, modem owner, serial transport, RF loop, or transmit path.

The P1 flow is:

```text
qualified RX/TNC runtime
        |
        v
   PacketEvent backend
        |
        +---- existing KISS client subscriber
        |
        +---- 0D monitor subscriber
                  |
                  +-- parse existing AX.25 body (no FCS)
                  +-- structured MonitorRecord
                  +-- deterministic one-line monitor text
```

Each monitor reader calls the existing backend `open_stream()` API.  That API already provides bounded history plus one bounded subscriber queue.  The monitor does not allocate a second queue or worker thread.  If a monitor consumer stalls, the existing backend `subscriber_drops` counter remains the visible loss signal instead of memory growing without bound.

`MonitorRecord` keeps source, destination, repeated-path `*` state, frame class/type, P/F, N(S), N(R), PID, information bytes, the original no-FCS frame body and a rendered one-line representation.  UI/PID-F0 traffic uses the familiar `SOURCE>DEST,PATH:payload` shape.  I/S/U control traffic retains explicit frame metadata so later MCOM/MCON policy can filter structured records rather than trying to reverse-engineer display strings.

Arbitrary information bytes are escaped into one line (`\\r`, `\\n`, `\\t`, `\\xNN`) so binary/control bytes cannot corrupt a terminal or log format.

### Safety boundary

P1 is host-only and observation-only:

- no modem import or modem-owner reference;
- no UART or POSIX serial access;
- no RX/TX radio configuration;
- no broker or TX submitter;
- no new KISS command handling;
- no GPIO, flash or option-byte work;
- the 0C/P8 core source blobs are hash-locked in the P1 contract.

### Deliberately deferred

P1 does not implement MCOM/MCON/MRPT filtering, SQLite persistence, MHEARD, retention, or a network/local command console.  Those later 0D/0E stages will consume the structured monitor record boundary qualified here.
