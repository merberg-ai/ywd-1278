from __future__ import annotations

import threading

from ywd1278.modem import protocol

IDENTITY = (
    "MMDVM_HS_Hat-YWD-1278-AX25R4-v0.1.0-alpha1 "
    "14.7456MHz ADF7021 FW based on CA6JAU GitID #7ff74ed"
)
ACTIVE_FLAGS = 0x0D
IDLE_FLAGS = 0x04
CLEAR_RSSI_RAW = 106


def version_response() -> bytes:
    return protocol.build_frame(
        protocol.GET_VERSION,
        bytes((1,)) + IDENTITY.encode("ascii") + b"\0",
    )


def rx_status_response(*, active: bool, available: int, samples: int, dropped: int = 0) -> bytes:
    flags = ACTIVE_FLAGS if active else IDLE_FLAGS
    payload = bytes((
        protocol.RX_STATUS,
        protocol.RX_PROTOCOL_REVISION,
        flags,
        available & 0xFF,
        (available >> 8) & 0xFF,
        samples & 0xFF,
        (samples >> 8) & 0xFF,
        (samples >> 16) & 0xFF,
        (samples >> 24) & 0xFF,
        dropped & 0xFF,
        (dropped >> 8) & 0xFF,
    ))
    return protocol.build_frame(protocol.YWD_RX, payload)


def rf_status_response(*, remaining: int) -> bytes:
    return protocol.build_frame(
        protocol.YWD_RF,
        bytes((
            protocol.RF_GET_STATUS,
            1,
            0x08 if remaining else 0x04,
            remaining & 0xFF,
            (remaining >> 8) & 0xFF,
            3 if remaining else 0,
        )),
    )


def rf_diag_response(*, active: bool, generated_samples: int) -> bytes:
    return protocol.build_frame(
        protocol.YWD_RF,
        bytes((
            protocol.RF_GET_DIAG,
            0,
            0,
            1 if generated_samples else 0,
            generated_samples & 0xFF,
            (generated_samples >> 8) & 0xFF,
            1 if active else 0,
        )),
    )


class P8ThreadBoundTransport:
    """Stateful in-memory AX25R4 endpoint for sustained P8 host tests."""

    def __init__(self) -> None:
        self.owner_thread_id = threading.get_ident()
        self.call_thread_ids: list[int] = []
        self.requests: list[bytes] = []
        self.close_thread_id: int | None = None
        self.rf_ready = False
        self.rx_active = False
        self.rx_start_count = 0
        self.rx_stop_count = 0
        self.tx_accept_count = 0
        self.tx_selector_counts: list[int] = []
        self.busy_pairs_remaining = 0
        self.last_status_busy = False
        self.generated_samples = 0
        self.samples = 0
        self._rx_lock = threading.Lock()
        self._rx_buffer = bytearray()

    def inject_rx_packed(self, packed: bytes) -> None:
        with self._rx_lock:
            self._rx_buffer.extend(bytes(packed))

    def _available(self) -> int:
        with self._rx_lock:
            return len(self._rx_buffer)

    def _read(self, maximum: int) -> bytes:
        with self._rx_lock:
            count = min(int(maximum), len(self._rx_buffer))
            chunk = bytes(self._rx_buffer[:count])
            del self._rx_buffer[:count]
            return chunk

    def _assert_owner(self) -> None:
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError("fake P8 transport escaped the modem owner thread")

    def transact(self, request: bytes, *, timeout: float) -> bytes:
        self._assert_owner()
        self.call_thread_ids.append(threading.get_ident())
        self.requests.append(bytes(request))
        frame = protocol.parse_frame(request)

        if frame.command == protocol.GET_VERSION:
            return version_response()

        if frame.command == protocol.SET_CONFIG:
            self.rf_ready = True
            return protocol.ack_for(protocol.SET_CONFIG)

        if frame.command == protocol.YWD_RX:
            sub = frame.payload[0]
            if sub == protocol.RX_START:
                if not self.rf_ready or self.rx_active or self.busy_pairs_remaining:
                    return protocol.nak_for(protocol.YWD_RX, 5)
                self.rx_active = True
                self.rx_start_count += 1
                return protocol.ack_for(protocol.YWD_RX)
            if sub == protocol.RX_STOP:
                if not self.rx_active:
                    return protocol.nak_for(protocol.YWD_RX, 5)
                self.rx_active = False
                self.rx_stop_count += 1
                return protocol.ack_for(protocol.YWD_RX)
            if sub == protocol.RX_STATUS:
                self.samples += 100
                return rx_status_response(
                    active=self.rx_active,
                    available=self._available(),
                    samples=self.samples,
                )
            if sub == protocol.RX_READ:
                if not self.rx_active:
                    return protocol.nak_for(protocol.YWD_RX, 5)
                maximum = frame.payload[1]
                chunk = self._read(maximum)
                self.samples += len(chunk) * 8
                return protocol.build_frame(
                    protocol.YWD_RX,
                    bytes((protocol.RX_READ, len(chunk))) + chunk,
                )
            if sub == protocol.RX_RSSI:
                if not self.rx_active or self.busy_pairs_remaining:
                    return protocol.nak_for(protocol.YWD_RX, 5)
                return protocol.build_frame(
                    protocol.YWD_RX,
                    bytes((protocol.RX_RSSI, CLEAR_RSSI_RAW & 0xFF, CLEAR_RSSI_RAW >> 8)),
                )
            raise AssertionError("unexpected fake P8 YWD_RX request")

        if frame.command == protocol.YWD_RF:
            sub = frame.payload[0]
            if sub == protocol.RF_GET_STATUS:
                busy = self.busy_pairs_remaining > 0
                self.last_status_busy = busy
                remaining = self.tx_selector_counts[-1] if busy and self.tx_selector_counts else 0
                return rf_status_response(remaining=remaining)
            if sub == protocol.RF_GET_DIAG:
                busy = self.last_status_busy
                if busy and self.busy_pairs_remaining > 0:
                    self.busy_pairs_remaining -= 1
                return rf_diag_response(active=busy, generated_samples=self.generated_samples)
            if sub == protocol.RF_TX_TONES:
                if self.rx_active or self.busy_pairs_remaining:
                    return protocol.nak_for(protocol.YWD_RF, 5)
                selector_count = frame.payload[1] | (frame.payload[2] << 8)
                self.tx_accept_count += 1
                self.tx_selector_counts.append(selector_count)
                self.generated_samples = selector_count * 16
                self.busy_pairs_remaining = 2
                return protocol.ack_for(protocol.YWD_RF)
            raise AssertionError("unexpected fake P8 YWD_RF request")

        raise AssertionError(f"unexpected fake P8 modem command: {request.hex()}")

    def close(self) -> None:
        self._assert_owner()
        self.close_thread_id = threading.get_ident()
