"""0H-P11 product forwarding configuration gate.

Forwarding plumbing is host-qualified, but live forwarding remains physically
unqualified.  The product therefore understands a bounded [forwarding] table
while refusing activation until the deferred physical qualification stage.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


DEFAULT_FORWARD_INTERVAL_SECONDS = 900
DEFAULT_FORWARD_MAX_BATCH = 8
MAX_FORWARD_INTERVAL_SECONDS = 86_400


class ProductForwardingConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ProductForwardingConfig:
    enabled: bool = False
    interval_seconds: int = DEFAULT_FORWARD_INTERVAL_SECONDS
    max_batch: int = DEFAULT_FORWARD_MAX_BATCH


def _integer(table: dict, key: str, default: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProductForwardingConfigurationError(f"forwarding.{key} must be an integer")
    return int(value)


def load_product_forwarding_config(path: str | Path) -> ProductForwardingConfig:
    config_path = Path(path)
    try:
        with config_path.open("rb") as handle:
            root = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ProductForwardingConfigurationError(
            f"cannot load forwarding configuration {config_path}: {exc}"
        ) from exc

    raw = root.get("forwarding")
    if raw is None:
        return ProductForwardingConfig()
    if not isinstance(raw, dict):
        raise ProductForwardingConfigurationError("invalid [forwarding] table")

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ProductForwardingConfigurationError("forwarding.enabled must be true or false")

    interval_seconds = _integer(
        raw, "interval_seconds", DEFAULT_FORWARD_INTERVAL_SECONDS
    )
    max_batch = _integer(raw, "max_batch", DEFAULT_FORWARD_MAX_BATCH)

    if not 60 <= interval_seconds <= MAX_FORWARD_INTERVAL_SECONDS:
        raise ProductForwardingConfigurationError(
            f"forwarding.interval_seconds must be 60..{MAX_FORWARD_INTERVAL_SECONDS}"
        )
    if not 1 <= max_batch <= DEFAULT_FORWARD_MAX_BATCH:
        raise ProductForwardingConfigurationError(
            f"forwarding.max_batch must be 1..{DEFAULT_FORWARD_MAX_BATCH}"
        )
    if enabled:
        raise ProductForwardingConfigurationError(
            "forwarding.enabled=true is not physically qualified; keep forwarding disabled "
            "until the deferred physical forwarding stage"
        )

    return ProductForwardingConfig(
        enabled=False,
        interval_seconds=interval_seconds,
        max_batch=max_batch,
    )


__all__ = [
    "DEFAULT_FORWARD_INTERVAL_SECONDS",
    "DEFAULT_FORWARD_MAX_BATCH",
    "MAX_FORWARD_INTERVAL_SECONDS",
    "ProductForwardingConfigurationError",
    "ProductForwardingConfig",
    "load_product_forwarding_config",
]
