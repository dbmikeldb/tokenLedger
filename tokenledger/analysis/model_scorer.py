"""Rule-based model efficiency scorer.

Scores a proxied call using signals available without an extra API call and
returns a recommendation when a cheaper model tier would likely suffice.
No LLM calls are made.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from tokenledger.config.models import MODEL_DISPLAY_NAME, MODEL_PRICING, MODEL_TIERS

# ---------------------------------------------------------------------------
# Keyword patterns
# ---------------------------------------------------------------------------

_DOWNGRADE = re.compile(
    r"\b(translat[ei]|format|reformat|summaris[ei]|summariz[ei]|extract|convert"
    r"|fix\s+typo|spell\s*check|what\s+is|how\s+many|how\s+do\s+i|list\s+the)\b",
    re.IGNORECASE,
)
_UPGRADE = re.compile(
    r"\b(implement|write\s+code|debug|refactor|analys[ei]|analyz[ei]|compare"
    r"|function|algorithm|class\b|explain|test\b)\b",
    re.IGNORECASE,
)
_PREMIUM = re.compile(
    r"\b(architecture|design\s+system|trade.?off|implication|evaluate|strategy"
    r"|research|nuanced|reasoning|comprehensive)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class EfficiencyFlag:
    current_model: str
    current_display: str
    recommended_model: str
    recommended_display: str
    score: int
    reason: str
    estimated_savings: float   # per-call worst-case


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_call(
    model: str,
    input_tokens: int,
    max_tokens: int,
    tool_tokens: int,
    messages: list[dict],
    system: str | None = None,
) -> EfficiencyFlag | None:
    """Return an EfficiencyFlag if a cheaper model tier would likely suffice,
    or None if the current model is already appropriate."""
    score, reason = _score(input_tokens, max_tokens, tool_tokens, messages, system)

    if score <= 33:
        tier_idx = 0
    elif score <= 66:
        tier_idx = 1
    else:
        tier_idx = 2

    recommended = MODEL_TIERS[tier_idx]
    current_idx = _tier_index(model)

    if current_idx <= tier_idx:
        return None  # already at or below the recommended tier

    current_display = MODEL_DISPLAY_NAME.get(model, model)
    rec_display     = MODEL_DISPLAY_NAME.get(recommended, recommended)

    # Estimate per-call savings (input + worst-case output)
    def cost(m: str) -> float:
        p = MODEL_PRICING.get(m, MODEL_PRICING[MODEL_TIERS[1]])
        return (input_tokens / 1_000_000 * p["input_per_1m"]
                + max_tokens / 1_000_000 * p["output_per_1m"])

    savings = cost(model) - cost(recommended)

    return EfficiencyFlag(
        current_model=model,
        current_display=current_display,
        recommended_model=recommended,
        recommended_display=rec_display,
        score=score,
        reason=reason,
        estimated_savings=max(0.0, savings),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _score(
    input_tokens: int,
    max_tokens: int,
    tool_tokens: int,
    messages: list[dict],
    system: str | None,
) -> tuple[int, str]:
    score = 0
    reasons: list[str] = []

    if input_tokens > 0:
        score += min(40, int(math.log10(max(input_tokens, 1)) * 13))
        if input_tokens >= 5_000:
            reasons.append(f"{input_tokens:,} input tokens")

    if max_tokens >= 2_000:
        score += 20
        reasons.append("large output requested")
    elif max_tokens >= 500:
        score += 10

    if tool_tokens > 500:
        score += 20
        reasons.append("heavy tool use")
    elif tool_tokens > 0:
        score += 10

    text = _flatten(messages, system)
    if _PREMIUM.search(text):
        score += 25
        reasons.append("complex reasoning keywords")
    elif _UPGRADE.search(text):
        score += 15
        reasons.append("code/analysis keywords")
    elif _DOWNGRADE.search(text):
        score -= 15
        reasons.append("simple task keywords")

    reason = "; ".join(reasons) if reasons else "low complexity"
    return max(0, min(100, score)), reason


def _flatten(messages: list[dict], system: str | None) -> str:
    parts: list[str] = []
    if system:
        parts.append(system)
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
    return " ".join(parts)


def _tier_index(model: str) -> int:
    try:
        return MODEL_TIERS.index(model)
    except ValueError:
        return 1
