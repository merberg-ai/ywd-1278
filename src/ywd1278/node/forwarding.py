"""0H-P3 deterministic mailbox forwarding decisions; no dispatcher."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ywd1278.ax25 import Address


MAX_FORWARD_ROUTES = 32
MAX_FORWARD_HOPS = 8


class ForwardDisposition(Enum):
    DELIVER_LOCAL = "DELIVER_LOCAL"
    FORWARD = "FORWARD"
    HOLD = "HOLD"
    REJECT = "REJECT"


@dataclass(frozen=True)
class ForwardRoute:
    destination: Address
    next_hop: Address
    enabled: bool = True


@dataclass(frozen=True)
class ForwardEnvelope:
    message_id: int
    destination: Address
    trace: tuple[Address, ...] = ()


@dataclass(frozen=True)
class ForwardDecision:
    disposition: ForwardDisposition
    reason: str
    next_hop: Address | None = None
    next_trace: tuple[Address, ...] = ()


class StaticForwardingPolicy:
    """Evaluate exact routes without scheduling or mutating message storage."""

    def __init__(
        self,
        *,
        node: Address,
        local_destinations: tuple[Address, ...],
        routes: tuple[ForwardRoute, ...] = (),
        max_hops: int = 4,
    ) -> None:
        self._node = self._address(node, "node")
        if isinstance(max_hops, bool) or not isinstance(max_hops, int) or not 1 <= max_hops <= MAX_FORWARD_HOPS:
            raise ValueError(f"max_hops must be an integer 1..{MAX_FORWARD_HOPS}")
        if not isinstance(local_destinations, tuple) or not local_destinations:
            raise ValueError("local_destinations must be a non-empty tuple")
        if len(local_destinations) > 8:
            raise ValueError("local_destinations exceeds 8 entries")
        locals_normalized = tuple(self._address(item, "local destination") for item in local_destinations)
        if len(set(locals_normalized)) != len(locals_normalized):
            raise ValueError("local_destinations must be unique")
        if not isinstance(routes, tuple) or len(routes) > MAX_FORWARD_ROUTES:
            raise ValueError(f"routes must be a tuple with at most {MAX_FORWARD_ROUTES} entries")
        route_map: dict[Address, ForwardRoute] = {}
        for route in routes:
            if not isinstance(route, ForwardRoute):
                raise TypeError("routes must contain ForwardRoute")
            destination = self._address(route.destination, "route destination")
            next_hop = self._address(route.next_hop, "route next_hop")
            if destination in route_map:
                raise ValueError(f"duplicate route for {destination}")
            if destination in locals_normalized:
                raise ValueError(f"route shadows local destination {destination}")
            if next_hop == self._node:
                raise ValueError("route next_hop must not be this node")
            route_map[destination] = ForwardRoute(destination, next_hop, bool(route.enabled))
        self._locals = frozenset(locals_normalized)
        self._routes = route_map
        self._max_hops = max_hops

    def decide(self, envelope: ForwardEnvelope) -> ForwardDecision:
        if not isinstance(envelope, ForwardEnvelope):
            raise TypeError("envelope must be ForwardEnvelope")
        if isinstance(envelope.message_id, bool) or not isinstance(envelope.message_id, int) or envelope.message_id < 1:
            raise ValueError("message_id must be a positive integer")
        destination = self._address(envelope.destination, "destination")
        if not isinstance(envelope.trace, tuple) or len(envelope.trace) > MAX_FORWARD_HOPS:
            raise ValueError(f"trace must be a tuple with at most {MAX_FORWARD_HOPS} entries")
        trace = tuple(self._address(item, "trace hop") for item in envelope.trace)
        if len(set(trace)) != len(trace):
            return ForwardDecision(ForwardDisposition.REJECT, "trace contains a loop")
        if destination in self._locals:
            return ForwardDecision(ForwardDisposition.DELIVER_LOCAL, "destination is local", next_trace=trace)
        if self._node in trace:
            return ForwardDecision(ForwardDisposition.REJECT, "message already traversed this node", next_trace=trace)
        if len(trace) >= self._max_hops:
            return ForwardDecision(ForwardDisposition.REJECT, "forward hop limit reached", next_trace=trace)
        route = self._routes.get(destination)
        if route is None:
            return ForwardDecision(ForwardDisposition.HOLD, "no exact route", next_trace=trace)
        if not route.enabled:
            return ForwardDecision(ForwardDisposition.HOLD, "route is disabled", next_trace=trace)
        if route.next_hop in trace:
            return ForwardDecision(ForwardDisposition.REJECT, "next hop already appears in trace", next_trace=trace)
        return ForwardDecision(
            ForwardDisposition.FORWARD,
            "exact enabled route selected",
            next_hop=route.next_hop,
            next_trace=trace + (self._node,),
        )

    @staticmethod
    def _address(value: Address, name: str) -> Address:
        if not isinstance(value, Address):
            raise TypeError(f"{name} must be an AX.25 Address")
        return Address(value.callsign, value.ssid)


__all__ = ["MAX_FORWARD_ROUTES", "MAX_FORWARD_HOPS", "ForwardDisposition", "ForwardRoute", "ForwardEnvelope", "ForwardDecision", "StaticForwardingPolicy"]
