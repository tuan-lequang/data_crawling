"""Provider-agnostic cost estimation helpers for Demo and configured Live providers."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    provider_name: str
    currency: str = "USD"
    per_1000_delivered: float = 0.0
    start_fee: float = 0.0
    is_synthetic: bool = True


def estimate_max_charge(requested_reviews: int, model: CostModel) -> float:
    """Estimate an upper bound for tests or future configured providers; no vendor rate is bundled."""
    if isinstance(requested_reviews, bool) or not isinstance(requested_reviews, int) or requested_reviews < 1:
        raise ValueError("Review count must be a whole number greater than zero.")
    if model.per_1000_delivered < 0 or model.start_fee < 0:
        raise ValueError("Cost model values must be non-negative.")
    return round(model.start_fee + requested_reviews * model.per_1000_delivered / 1000.0, 6)


def demo_cost_message() -> str:
    return "Demo data: generated locally; no Apify run and no charge."
