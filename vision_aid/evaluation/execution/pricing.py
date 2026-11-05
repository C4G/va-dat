"""Estimate request cost from the saved price schedule."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

DEFAULT_SCHEDULE = Path(__file__).with_name("pricing.json")
MILLION = Decimal(1_000_000)
_RATE_KEYS = {
    "input_tokens": "input_per_million_usd",
    "cached_input_tokens": "cached_input_per_million_usd",
    "cache_creation_input_tokens": "cache_creation_input_per_million_usd",
    "output_tokens": "output_per_million_usd",
}


@dataclass(frozen=True)
class PriceSchedule:
    """Model rates plus the SHA-256 of the file they came from."""

    data: dict[str, Any]
    identity: str

    @classmethod
    def load(cls, path: Path) -> PriceSchedule:
        """Load a price schedule JSON file."""
        raw = path.read_bytes()
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
            raise TypeError("Price schedule must contain a models object.")
        return cls(data=data, identity=hashlib.sha256(raw).hexdigest())

    @property
    def version(self) -> str:
        """Return the schedule's version string."""
        return str(self.data["version"])

    @property
    def price_description(self) -> str:
        """Describe when the prices were captured."""
        if "captured_at" in self.data:
            return f"published prices captured on {self.data['captured_at']}"
        return f"published prices dated {self.data['published_at']}"

    def estimate(self, model: str, usage: Mapping[str, int | None]) -> str:
        """Price one request, using the long-context rates above their threshold."""
        try:
            rates = self.data["models"][model]
        except KeyError as error:
            raise ValueError(
                f"No versioned pricing exists for model {model!r}."
            ) from error
        tokens = {key: Decimal(usage.get(key) or 0) for key in _RATE_KEYS}
        upper = rates.get("long_context")
        if upper and sum(tokens.values()) - tokens["output_tokens"] > upper["above_input_tokens"]:
            rates = upper
        cost = sum(
            tokens[key] * Decimal(rates[rate]) for key, rate in _RATE_KEYS.items()
        ) / MILLION
        return format(cost.normalize(), "f")
