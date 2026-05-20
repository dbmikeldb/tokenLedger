"""Static Anthropic model pricing table.

Rates are in USD per 1 million tokens.
Verify current pricing at https://www.anthropic.com/pricing before updating.
Last verified: 2026-04-30.
"""

MODEL_PRICING: dict[str, dict[str, float | int]] = {
    "claude-opus-4-20250514": {
        "input_per_1m": 15.00,
        "output_per_1m": 75.00,
        "context_window": 200_000,
    },
    "claude-sonnet-4-20250514": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
        "context_window": 200_000,
    },
    "claude-haiku-4-5-20251001": {
        "input_per_1m": 0.80,
        "output_per_1m": 4.00,
        "context_window": 200_000,
    },
}

DEFAULT_MODEL = "claude-sonnet-4-20250514"

# Short display names for each model ID
MODEL_DISPLAY_NAME: dict[str, str] = {
    "claude-opus-4-20250514": "opus",
    "claude-sonnet-4-20250514": "sonnet",
    "claude-haiku-4-5-20251001": "haiku",
}

# Tiers ordered cheapest → most expensive; used by the recommender
MODEL_TIERS: list[str] = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-20250514",
    "claude-opus-4-20250514",
]


def get_context_window(model: str) -> int:
    """Return the context window size in tokens for the given model."""
    entry = MODEL_PRICING.get(model, MODEL_PRICING[DEFAULT_MODEL])
    return int(entry.get("context_window", 200_000))
