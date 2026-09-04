"""Token-cost estimation.

Prices are USD per one million tokens, copied from provider pricing pages on
2026-09-04. Update the table (and the date) when a provider changes prices;
never guess a price for an unlisted model - return ``None`` so the caller can
record "cost not estimated" instead of a wrong number.
"""

from __future__ import annotations

from dataclasses import dataclass

PRICES_RECORDED_ON = "2026-09-04"


@dataclass(frozen=True)
class TokenPrice:
    """USD per one million tokens."""

    input_per_million: float
    output_per_million: float


_PRICES: dict[str, TokenPrice] = {
    "stub": TokenPrice(0.0, 0.0),
    "gpt-4o-mini": TokenPrice(0.15, 0.60),
    "gpt-4o": TokenPrice(2.50, 10.00),
    "gpt-4.1": TokenPrice(2.00, 8.00),
    "gpt-4.1-mini": TokenPrice(0.40, 1.60),
}


def estimate_cost_usd(
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> float | None:
    """Return the estimated USD cost of one call, or ``None`` for an unlisted model."""
    price = _PRICES.get(model)
    if price is None:
        return None
    prompt = prompt_tokens or 0
    completion = completion_tokens or 0
    cost = (
        prompt / 1_000_000 * price.input_per_million
        + completion / 1_000_000 * price.output_per_million
    )
    return round(cost, 6)
