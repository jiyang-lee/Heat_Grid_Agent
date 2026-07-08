from schemas import CostEstimate, TokenUsage
from settings import (
    GPT_5_4_MINI_CACHED_INPUT_USD_PER_1M,
    GPT_5_4_MINI_INPUT_USD_PER_1M,
    GPT_5_4_MINI_OUTPUT_USD_PER_1M,
    GPT_5_4_MINI_PRICING_SOURCE,
    Settings,
)


def usage_with_totals(usage: TokenUsage, settings: Settings) -> TokenUsage:
    usage.model_calls = len(usage.calls)
    usage.input_tokens = sum(call.input_tokens for call in usage.calls)
    usage.cached_input_tokens = sum(call.cached_input_tokens for call in usage.calls)
    usage.output_tokens = sum(call.output_tokens for call in usage.calls)
    usage.total_tokens = sum(call.total_tokens for call in usage.calls)
    usage.cost_estimate = cost_for_usage(usage, settings)
    return usage


def cost_for_usage(usage: TokenUsage, settings: Settings) -> CostEstimate:
    regular_input_tokens = max(usage.input_tokens - usage.cached_input_tokens, 0)
    input_cost = regular_input_tokens * GPT_5_4_MINI_INPUT_USD_PER_1M / 1_000_000
    cached_input_cost = (
        usage.cached_input_tokens * GPT_5_4_MINI_CACHED_INPUT_USD_PER_1M / 1_000_000
    )
    output_cost = usage.output_tokens * GPT_5_4_MINI_OUTPUT_USD_PER_1M / 1_000_000
    return CostEstimate(
        model=settings.openai_model,
        input_usd_per_1m=GPT_5_4_MINI_INPUT_USD_PER_1M,
        cached_input_usd_per_1m=GPT_5_4_MINI_CACHED_INPUT_USD_PER_1M,
        output_usd_per_1m=GPT_5_4_MINI_OUTPUT_USD_PER_1M,
        input_cost_usd=input_cost,
        cached_input_cost_usd=cached_input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=input_cost + cached_input_cost + output_cost,
        pricing_source=GPT_5_4_MINI_PRICING_SOURCE,
    )
