# YWD-1278 0B-P7b-1 single-UART-owner architecture qualification — 2026-09-02

Status: **QUALIFIED — deterministic fake-transport ownership gate**

This checkpoint qualifies the host-side ownership architecture that will later own `/dev/ttyAMA0`. It does not open a real modem device and it does not transmit RF.

## Qualifying code boundary

- code head before this evidence document: `a359b2ffd39d62d4d1d591f81af55798358ebbbd`
- CI run: `33653052572`
- CI result: PASS

## Qualified implementation

- `src/ywd1278/modem/owner.py`
- `tests/modem_owner_test.py`

The transport factory is executed inside the dedicated owner thread. The resulting transport object is retained only inside that thread's worker loop. Public callers receive typed request methods rather than a raw serial transaction primitive.

The P7b-1 reachable command surface is intentionally receive/control-only:

- GET_VERSION
- YWD_RX/START
- YWD_RX/READ
- YWD_RX/STATUS revision 3
- YWD_RX/STOP
- YWD_RF/GET_DIAG read-only diagnostic

There is intentionally no owner API for `YWD_RF/TX_TONES`, `RF_ABORT`, `RF_EXIT`, arbitrary modem frames, or direct transport access.

## Deterministic ownership evidence

The fake transport binds itself to the thread in which it is constructed and rejects any transaction or close call from another thread. Regression coverage proves:

- transport construction occurs in the modem-owner thread;
- the owner thread differs from the calling/client thread;
- every modem transaction occurs on exactly that one owner thread;
- transport close occurs on the same owner thread;
- a retained fake-transport reference rejects direct access from the client thread;
- the owner exposes no public raw `transact()` method;
- the owner exposes no `rf_tx_tones` method;
- typed GET_VERSION, RX start/status/read/stop, and RF diagnostics all round-trip through the owner;
- parser/transport failures are returned to the requesting caller through the owner boundary.

## Bounded queue evidence

A one-entry queue is deliberately saturated while the owner thread is held inside a fake modem transaction. A third client request is rejected with `ModemOwnerQueueFull` rather than growing an unbounded backlog.

This establishes the structural invariant:

```text
clients / DSP / future KISS / future console
                |
                v
        bounded owner queue
                |
                v
      exactly one owner thread
                |
                v
         modem transport
```

## Safety markers

```text
MODEM_DEVICE_OPENED=NO
MODEM_UART_OPENED=NO
OWNER_THREADS=1
OWNER_QUEUE_BOUNDED=YES
RAW_CLIENT_TRANSACT=NO
RF_TX_OWNER_API=NO
RF_TRANSMITTED=NO
FLASH_WRITTEN=NO
OPTION_BYTES_WRITTEN=NO
```

## Scope boundary

P7b-1 qualifies the ownership architecture only. The next gate adds a thread-bound POSIX serial transport and proves a guarded live **read-only identity transaction** against the currently stock HAT. Live YWD_RX operation remains blocked until the packet-capable YWD-1278 firmware port is built and qualified.
