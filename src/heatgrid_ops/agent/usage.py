from __future__ import annotations

from heatgrid_ops.agent.config import AgentRuntimeConfig
from heatgrid_ops.agent.models import CostEstimate, TokenUsage


def usage_with_totals(usage: TokenUsage, config: AgentRuntimeConfig) -> TokenUsage:
    usage.model_calls = len(usage.calls)
    usage.input_tokens = sum(call.input_tokens for call in usage.calls)
    usage.cached_input_tokens = sum(call.cached_input_tokens for call in usage.calls)
    usage.output_tokens = sum(call.output_tokens for call in usage.calls)
    usage.total_tokens = sum(call.total_tokens for call in usage.calls)
    usage.cost_estimate = cost_for_usage(usage, config)
    return usage


def cost_for_usage(usage: TokenUsage, config: AgentRuntimeConfig) -> CostEstimate:
    regular_input_tokens = max(usage.input_tokens - usage.cached_input_tokens, 0)
    input_cost = regular_input_tokens * config.input_usd_per_1m / 1_000_000
    cached_input_cost = (
        usage.cached_input_tokens * config.cached_input_usd_per_1m / 1_000_000
    )
    output_cost = usage.output_tokens * config.output_usd_per_1m / 1_000_000
    return CostEstimate(
        model=config.openai_model,
        input_usd_per_1m=config.input_usd_per_1m,
        cached_input_usd_per_1m=config.cached_input_usd_per_1m,
        output_usd_per_1m=config.output_usd_per_1m,
        input_cost_usd=input_cost,
        cached_input_cost_usd=cached_input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=input_cost + cached_input_cost + output_cost,
        pricing_source=config.pricing_source,
    )
