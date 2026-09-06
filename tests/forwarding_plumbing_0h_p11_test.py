#!/usr/bin/env python3
from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from ywd1278.ax25 import Address
from ywd1278.node.forwarding import (
    ForwardDecision,
    ForwardDisposition,
    ForwardEnvelope,
)
from ywd1278.node.forwarding_coordinator import (
    ForwardDeliveryDisposition,
    ForwardDeliveryReceipt,
    HostForwardingCoordinator,
)
from ywd1278.node.forwarding_integration import (
    ForwardBatchResult,
    ForwardPreparation,
    PreparedForwardMessage,
)
from ywd1278.service.forwarding_config import (
    ProductForwardingConfigurationError,
    load_product_forwarding_config,
)


LOCAL = Address.parse("KJ6YWD-10")
DEST = Address.parse("KJ6YWD-15")
NEXT = Address.parse("KJ6YWD-1")


class FakePlanner:
    def __init__(self, preparations: tuple[ForwardPreparation, ...]) -> None:
        self.preparations = preparations
        self.calls: list[tuple[ForwardEnvelope, ...]] = []

    def prepare_batch(self, envelopes: tuple[ForwardEnvelope, ...]) -> ForwardBatchResult:
        self.calls.append(envelopes)
        return ForwardBatchResult(True, "fake prepared", self.preparations)


def prepared(message_id: int) -> ForwardPreparation:
    envelope = ForwardEnvelope(message_id, DEST)
    decision = ForwardDecision(
        ForwardDisposition.FORWARD,
        "test",
        next_hop=NEXT,
        next_trace=(LOCAL,),
    )
    message = PreparedForwardMessage(
        message_id,
        LOCAL,
        DEST,
        NEXT,
        f"P11 {message_id}",
        (b"body",),
        (LOCAL,),
    )
    return ForwardPreparation(envelope, decision, message)


class P11ForwardingPlumbingTests(unittest.TestCase):
    def write_config(self, text: str) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="ywd-p11-"))
        path = directory / "config.toml"
        path.write_text(text, encoding="ascii")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        self.addCleanup(lambda: directory.rmdir())
        return path

    def test_missing_table_defaults_disabled(self) -> None:
        config = load_product_forwarding_config(self.write_config("[station]\ncallsign='KJ6YWD'\n"))
        self.assertFalse(config.enabled)
        self.assertEqual(config.interval_seconds, 900)
        self.assertEqual(config.max_batch, 8)

    def test_explicit_safe_config_is_disabled(self) -> None:
        path = self.write_config(
            "[forwarding]\nenabled=false\ninterval_seconds=600\nmax_batch=4\n"
        )
        config = load_product_forwarding_config(path)
        self.assertFalse(config.enabled)
        self.assertEqual((config.interval_seconds, config.max_batch), (600, 4))

    def test_live_activation_fails_closed(self) -> None:
        path = self.write_config(
            "[forwarding]\nenabled=true\ninterval_seconds=900\nmax_batch=8\n"
        )
        with self.assertRaisesRegex(
            ProductForwardingConfigurationError, "not physically qualified"
        ):
            load_product_forwarding_config(path)

    def test_disabled_coordinator_never_plans_or_delivers(self) -> None:
        planner = FakePlanner((prepared(1),))
        calls: list[int] = []

        def driver(message: PreparedForwardMessage) -> ForwardDeliveryReceipt:
            calls.append(message.message_id)
            return ForwardDeliveryReceipt(ForwardDeliveryDisposition.ACCEPTED, "accepted")

        result = HostForwardingCoordinator(
            planner=planner, delivery_driver=driver, enabled=False
        ).run_once((ForwardEnvelope(1, DEST),))
        self.assertTrue(result.accepted)
        self.assertEqual(planner.calls, [])
        self.assertEqual(calls, [])
        self.assertEqual(result.attempts, ())
        self.assertEqual(result.commit_intents, ())

    def test_accepted_delivery_emits_inert_commit_intent_once(self) -> None:
        planner = FakePlanner((prepared(1), prepared(2)))
        calls: list[int] = []

        def driver(message: PreparedForwardMessage) -> ForwardDeliveryReceipt:
            calls.append(message.message_id)
            return ForwardDeliveryReceipt(ForwardDeliveryDisposition.ACCEPTED, "prompt returned")

        result = HostForwardingCoordinator(
            planner=planner, delivery_driver=driver, enabled=True
        ).run_once((ForwardEnvelope(1, DEST), ForwardEnvelope(2, DEST)))
        self.assertTrue(result.accepted)
        self.assertEqual(calls, [1, 2])
        self.assertEqual([x.message_id for x in result.commit_intents], [1, 2])
        self.assertEqual(len(result.attempts), 2)

    def test_uncertain_delivery_stops_without_retry_or_commit(self) -> None:
        planner = FakePlanner((prepared(1), prepared(2)))
        calls: list[int] = []

        def driver(message: PreparedForwardMessage) -> ForwardDeliveryReceipt:
            calls.append(message.message_id)
            raise RuntimeError("link vanished after submit")

        result = HostForwardingCoordinator(
            planner=planner, delivery_driver=driver, enabled=True
        ).run_once((ForwardEnvelope(1, DEST), ForwardEnvelope(2, DEST)))
        self.assertFalse(result.accepted)
        self.assertEqual(calls, [1])
        self.assertEqual(len(result.attempts), 1)
        self.assertIs(
            result.attempts[0].receipt.disposition,
            ForwardDeliveryDisposition.UNCERTAIN,
        )
        self.assertEqual(result.commit_intents, ())

    def test_non_forwardable_preparation_never_reaches_driver(self) -> None:
        envelope = ForwardEnvelope(9, DEST)
        hold = ForwardPreparation(
            envelope,
            ForwardDecision(ForwardDisposition.HOLD, "no exact route"),
        )
        planner = FakePlanner((hold,))
        calls: list[int] = []

        def driver(message: PreparedForwardMessage) -> ForwardDeliveryReceipt:
            calls.append(message.message_id)
            return ForwardDeliveryReceipt(ForwardDeliveryDisposition.ACCEPTED, "accepted")

        result = HostForwardingCoordinator(
            planner=planner, delivery_driver=driver, enabled=True
        ).run_once((envelope,))
        self.assertTrue(result.accepted)
        self.assertEqual(calls, [])
        self.assertEqual(result.skipped_message_ids, (9,))

    def test_coordinator_batch_cap_is_bounded(self) -> None:
        planner = FakePlanner(())
        result = HostForwardingCoordinator(
            planner=planner,
            delivery_driver=lambda message: ForwardDeliveryReceipt(
                ForwardDeliveryDisposition.ACCEPTED, "accepted"
            ),
            enabled=True,
            max_batch=2,
        ).run_once(
            (ForwardEnvelope(1, DEST), ForwardEnvelope(2, DEST), ForwardEnvelope(3, DEST))
        )
        self.assertFalse(result.accepted)
        self.assertEqual(planner.calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
