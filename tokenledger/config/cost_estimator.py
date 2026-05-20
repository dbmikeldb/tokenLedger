"""Cost calculation from static Anthropic pricing table."""

from __future__ import annotations

from dataclasses import dataclass

from tokenledger.config.models import DEFAULT_MODEL, MODEL_PRICING


@dataclass
class CostEstimate:
    input_cost: float
    output_cost_worst: float
    total_worst: float
    model: str
    input_tokens: int
    max_tokens: int


def estimate_cost(
    *,
    model: str,
    input_tokens: int,
    max_tokens: int,
) -> CostEstimate:
    """Estimate cost for an API call.

    input_cost is exact (based on counted tokens).
    output_cost_worst is a worst-case estimate based on max_tokens.
    """
    pricing = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])

    input_cost = input_tokens / 1_000_000 * pricing["input_per_1m"]
    output_cost_worst = max_tokens / 1_000_000 * pricing["output_per_1m"]

    return CostEstimate(
        input_cost=input_cost,
        output_cost_worst=output_cost_worst,
        total_worst=input_cost + output_cost_worst,
        model=model,
        input_tokens=input_tokens,
        max_tokens=max_tokens,
    )
