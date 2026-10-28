"""Budgets: limits the harness enforces, so the model never has to be trusted to stop.

A run may use so many passes, so many dollars, so many minutes, and so many
rejected reviews. The loop checks before every model call (can the next one
start?) and right after it (did that one go over?). One call can overshoot the
money limit; no call starts once it's spent. Passes and dollars carry over
when a run resumes from the spine; minutes are per process.

Going over any of them doesn't fail silently and doesn't loop on: it
*escalates*, a defined state that hands the run to a human with a reason.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

# Dollars per million tokens (input, output). Unknown models are priced like the
# most expensive one, so a missing entry can only make a budget stricter.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    price_in, price_out = PRICES.get(model, max(PRICES.values()))
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000


@dataclass
class Spend:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    rejections: int = 0
    started: float = field(default_factory=time.monotonic)

    def add(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Count one model call; returns what it cost."""
        spent = cost(model, input_tokens, output_tokens)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cost_usd += spent
        return spent

    @property
    def minutes(self) -> float:
        return (time.monotonic() - self.started) / 60


@dataclass(frozen=True)
class Budget:
    max_passes: int = 8  # across every run of the same spine
    max_cost_usd: float = 1.00
    max_minutes: float = 15.0
    # Reviews (fixed rules, checker, gate) rejected in this run. A review that passes ends the run,
    # so every rejection counted here came in a row: the actor isn't converging.
    max_rejections: int = 3

    def exceeded(self, spend: Spend, passes_used: int) -> Optional[str]:
        """The first limit this run has reached, as a reason a human can read; None while within budget."""
        if passes_used >= self.max_passes:
            return f"pass budget: {passes_used} of {self.max_passes} passes used"
        return self.overspent(spend)

    def overspent(self, spend: Spend) -> Optional[str]:
        """Money, time or patience gone: the limits that can run out in the middle of a pass."""
        if spend.cost_usd >= self.max_cost_usd:
            return f"cost budget: ${spend.cost_usd:.4f} of ${self.max_cost_usd:.2f}"
        if spend.minutes >= self.max_minutes:
            return f"time budget: {spend.minutes:.1f} of {self.max_minutes:g} minutes"
        if spend.rejections >= self.max_rejections:
            return f"rejection budget: {spend.rejections} reviews rejected, the actor isn't converging"
        return None
