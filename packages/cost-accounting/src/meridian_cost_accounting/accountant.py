"""CostAccountant — translates ModelResponse.usage into USD.

Rates in USD per 1M tokens, mirroring the provider docs.

Section 19 D4 cost targets:
  small (Haiku / 4.1-mini)  ~$0.001/request
  mid   (Sonnet / 4.1)      ~$0.01/request
  frontier (Opus / GPT-5)   ~$0.05/request

These rates are snapshots; Phase 7 wires a dynamic config source (env var,
LiteLLM /model_group_info, or a Postgres table) so finance can update
without a code deploy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from meridian_contracts import ModelResponse


@dataclass(frozen=True)
class ModelRate:
    model: str
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    cache_read_usd_per_million: Decimal | None = None


def default_rates() -> dict[str, ModelRate]:
    """Built-in USD/M-token rates for the models in infra/litellm/config.yaml."""
    return {
        # --- Anthropic ---
        "meridian-small": ModelRate(
            "meridian-small", Decimal("0.80"), Decimal("4.00"), Decimal("0.08")
        ),
        "meridian-mid": ModelRate(
            "meridian-mid", Decimal("3.00"), Decimal("15.00"), Decimal("0.30")
        ),
        "meridian-frontier": ModelRate(
            "meridian-frontier", Decimal("15.00"), Decimal("75.00"), Decimal("1.50")
        ),
        # --- Canonical provider IDs — LiteLLM sometimes exposes the underlying alias ---
        "claude-haiku-4-5-20251001": ModelRate(
            "claude-haiku-4-5-20251001", Decimal("0.80"), Decimal("4.00"), Decimal("0.08")
        ),
        "claude-sonnet-4-6": ModelRate(
            "claude-sonnet-4-6", Decimal("3.00"), Decimal("15.00"), Decimal("0.30")
        ),
        "claude-opus-4-7": ModelRate(
            "claude-opus-4-7", Decimal("15.00"), Decimal("75.00"), Decimal("1.50")
        ),
        "gpt-4o-mini": ModelRate("gpt-4o-mini", Decimal("0.15"), Decimal("0.60")),
        "gpt-4o": ModelRate("gpt-4o", Decimal("2.50"), Decimal("10.00")),
    }


@dataclass
class CostBreakdown:
    model: str
    input_usd: Decimal
    output_usd: Decimal
    cache_read_usd: Decimal
    total_usd: Decimal


@dataclass
class CostAccountant:
    """Stateless. Looks up a rate and multiplies through the usage counts."""

    rates: dict[str, ModelRate] = field(default_factory=default_rates)

    def cost_of(self, response: ModelResponse) -> CostBreakdown:
        rate = self.rates.get(response.model)
        if rate is None:
            # Unknown model — zero cost but a non-failing fallback so the
            # orchestrator doesn't crash if someone adds a new provider alias
            # without updating the table.
            return CostBreakdown(
                model=response.model,
                input_usd=Decimal("0"),
                output_usd=Decimal("0"),
                cache_read_usd=Decimal("0"),
                total_usd=Decimal("0"),
            )
        million = Decimal("1000000")
        input_tokens = Decimal(response.usage.input_tokens)
        output_tokens = Decimal(response.usage.output_tokens)
        cache_read = Decimal(response.usage.cache_read_input_tokens)

        input_usd = (input_tokens / million) * rate.input_usd_per_million
        output_usd = (output_tokens / million) * rate.output_usd_per_million
        cache_rate = rate.cache_read_usd_per_million or rate.input_usd_per_million
        cache_read_usd = (cache_read / million) * cache_rate

        total = input_usd + output_usd + cache_read_usd
        return CostBreakdown(
            model=response.model,
            input_usd=input_usd,
            output_usd=output_usd,
            cache_read_usd=cache_read_usd,
            total_usd=total,
        )
