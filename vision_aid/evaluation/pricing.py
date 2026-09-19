"""Reproducible cost estimates from a versioned public price schedule."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

DEFAULT_SCHEDULE = Path(__file__).with_name("pricing.v1.json")
MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class PriceSchedule:
    """Immutable model rates and their content identity."""

    data: dict[str, Any]
    identity: str

    @classmethod
    def load(cls, path: Path) -> PriceSchedule:
        """Load and content-address one JSON price schedule."""
        raw = path.read_bytes()
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(
            data.get("models"), dict
        ):
            raise TypeError("Price schedule must contain a models object.")
        return cls(data=data, identity=hashlib.sha256(raw).hexdigest())

    @classmethod
    def default(cls) -> PriceSchedule:
        """Load the committed public pricing schedule."""
        return cls.load(DEFAULT_SCHEDULE)

    @property
    def version(self) -> str:
        """Return the curator-assigned price-schedule version."""
        return str(self.data["version"])

    def estimate(self, model: str, usage: Mapping[str, int]) -> str:
        """Price reported categories without rounding away tie precision."""
        try:
            rates = self.data["models"][model]
        except KeyError as error:
            raise ValueError(
                f"No versioned pricing exists for model {model!r}."
            ) from error
        input_tokens = Decimal(usage.get("input_tokens", 0))
        cached_tokens = Decimal(usage.get("cached_input_tokens", 0))
        cache_creation_tokens = Decimal(
            usage.get("cache_creation_input_tokens", 0)
        )
        output_tokens = Decimal(usage.get("output_tokens", 0))
        uncached_tokens = max(Decimal(0), input_tokens - cached_tokens)
        input_multiplier = Decimal(1)
        output_multiplier = Decimal(1)
        threshold = Decimal(rates.get("long_context_threshold_tokens", 0))
        if threshold and input_tokens > threshold:
            input_multiplier = Decimal(rates["long_context_input_multiplier"])
            output_multiplier = Decimal(
                rates["long_context_output_multiplier"]
            )
        cost = (
            uncached_tokens
            * Decimal(rates["input_per_million_usd"])
            * input_multiplier
            + cached_tokens
            * Decimal(rates["cached_input_per_million_usd"])
            * input_multiplier
            + cache_creation_tokens
            * Decimal(rates["cache_creation_input_per_million_usd"])
            * input_multiplier
            + output_tokens
            * Decimal(rates["output_per_million_usd"])
            * output_multiplier
        ) / MILLION
        return format(cost.normalize(), "f")
