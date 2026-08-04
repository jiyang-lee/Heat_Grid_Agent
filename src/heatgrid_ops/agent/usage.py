from __future__ import annotations

from heatgrid_ops.agent.config import AgentRuntimeConfig, ModelPricing
from heatgrid_ops.agent.models import CostEstimate, TokenCall, TokenUsage


def usage_with_totals(usage: TokenUsage, config: AgentRuntimeConfig) -> TokenUsage:
    usage.model_calls = len(usage.calls)
    usage.input_tokens = sum(call.input_tokens for call in usage.calls)
    usage.cached_input_tokens = sum(call.cached_input_tokens for call in usage.calls)
    usage.output_tokens = sum(call.output_tokens for call in usage.calls)
    usage.total_tokens = sum(call.total_tokens for call in usage.calls)
    usage.cost_estimate = cost_for_usage(usage, config)
    return usage


def cost_for_usage(usage: TokenUsage, config: AgentRuntimeConfig) -> CostEstimate:
    default_pricing = ModelPricing(
        model=config.openai_model,
        input_usd_per_1m=config.input_usd_per_1m,
        cached_input_usd_per_1m=config.cached_input_usd_per_1m,
        output_usd_per_1m=config.output_usd_per_1m,
        pricing_source=config.pricing_source,
    )
    pricing_by_model = {
        pricing.model: pricing
        for pricing in (default_pricing, *config.model_pricing_overrides)
    }
    input_cost = 0.0
    cached_input_cost = 0.0
    output_cost = 0.0
    models: list[str] = []
    sources: list[str] = []
    calls = usage.calls or [
        TokenCall(
            model=config.openai_model,
            input_tokens=usage.input_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
        )
    ]
    for call in calls:
        pricing = _pricing_for_call(call, default_pricing, pricing_by_model)
        regular_input_tokens = max(call.input_tokens - call.cached_input_tokens, 0)
        input_cost += regular_input_tokens * pricing.input_usd_per_1m / 1_000_000
        cached_input_cost += (
            call.cached_input_tokens * pricing.cached_input_usd_per_1m / 1_000_000
        )
        output_cost += call.output_tokens * pricing.output_usd_per_1m / 1_000_000
        if pricing.model not in models:
            models.append(pricing.model)
        if pricing.pricing_source not in sources:
            sources.append(pricing.pricing_source)

    regular_input_tokens = max(usage.input_tokens - usage.cached_input_tokens, 0)
    return CostEstimate(
        model="+".join(models) or config.openai_model,
        input_usd_per_1m=_effective_rate(input_cost, regular_input_tokens),
        cached_input_usd_per_1m=_effective_rate(
            cached_input_cost,
            usage.cached_input_tokens,
        ),
        output_usd_per_1m=_effective_rate(output_cost, usage.output_tokens),
        input_cost_usd=input_cost,
        cached_input_cost_usd=cached_input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=input_cost + cached_input_cost + output_cost,
        pricing_source=" | ".join(sources) or config.pricing_source,
    )


def _pricing_for_call(
    call: TokenCall,
    default: ModelPricing,
    pricing_by_model: dict[str, ModelPricing],
) -> ModelPricing:
    if call.model is None:
        return default
    return pricing_by_model.get(call.model, default)


def _effective_rate(cost_usd: float, tokens: int) -> float:
    return cost_usd * 1_000_000 / tokens if tokens else 0.0
