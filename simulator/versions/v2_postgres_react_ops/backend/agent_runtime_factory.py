from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from agent_input_model_adapter import PostgresAgentInputModelAdapter
from agent_persistence_adapter import PostgresAgentPersistenceAdapter
from agent_review_adapter import PostgresAgentReviewAdapter
from heatgrid_ops.agent.config import AgentRuntimeConfig
from heatgrid_ops.agent.contracts import SimulateCard
from heatgrid_ops.agent.graph import AgentGraphContext
from heatgrid_ops.agent.models import JsonObject, JsonValue
from heatgrid_ops.agent.run_models import EvidenceContextSnapshot
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_rag.search import RagSearcher
from settings import (
    GPT_5_4_MINI_CACHED_INPUT_USD_PER_1M,
    GPT_5_4_MINI_INPUT_USD_PER_1M,
    GPT_5_4_MINI_OUTPUT_USD_PER_1M,
    GPT_5_4_MINI_PRICING_SOURCE,
    Settings,
)


@dataclass(frozen=True, slots=True)
class RagEvidenceContextAdapter:
    searcher: RagSearcher

    def collect(
        self,
        card_id: str,
        source_input: JsonObject,
        top_k: int,
    ) -> EvidenceContextSnapshot:
        context = self.searcher.external_context(card_id, source_input, top_k=top_k)
        return EvidenceContextSnapshot(
            status=str(context.get("status") or "unavailable"),
            rag_evidence=_json_object(context.get("retrieval")),
            external_data={
                "site": _json_value(context.get("site")),
                "weather": _json_value(context.get("weather")),
                "references": _json_value(context.get("references")),
            },
        )


def create_agent_runtime(
    settings: Settings,
    rag_searcher: RagSearcher | None = None,
) -> AgentRuntime:
    return AgentRuntime(
        config=agent_runtime_config(settings),
        evidence_context=RagEvidenceContextAdapter(rag_searcher or RagSearcher()),
    )


def create_agent_graph_context(
    engine: AsyncEngine,
    runtime: AgentRuntime,
    simulate_card: SimulateCard | None = None,
) -> AgentGraphContext:
    persistence = PostgresAgentPersistenceAdapter(engine)
    input_model = PostgresAgentInputModelAdapter(engine)
    return AgentGraphContext(
        runtime=runtime,
        inputs=input_model,
        lifecycle=persistence,
        audit=persistence,
        model_data=input_model,
        reviews=PostgresAgentReviewAdapter(engine),
        artifacts=persistence,
        legacy_simulate_card=simulate_card,
    )


def agent_runtime_config(settings: Settings) -> AgentRuntimeConfig:
    key = settings.openai_api_key
    return AgentRuntimeConfig(
        openai_model=settings.openai_model,
        openai_api_key=None if key is None else key.get_secret_value(),
        rag_top_k=settings.rag_top_k,
        agent_max_iterations=settings.agent_max_iterations,
        agent_evidence_threshold=settings.agent_evidence_threshold,
        model_score_tolerance=settings.model_score_tolerance,
        external_search_enabled=settings.external_search_enabled,
        external_search_model=settings.external_search_model,
        external_search_max_results=settings.external_search_max_results,
        external_search_allowed_domains=settings.external_search_allowed_domains,
        external_search_max_calls_per_run=settings.external_search_max_calls_per_run,
        external_search_estimated_cost_usd=settings.external_search_estimated_cost_usd,
        external_search_budget_per_run_usd=settings.external_search_budget_per_run_usd,
        input_usd_per_1m=GPT_5_4_MINI_INPUT_USD_PER_1M,
        cached_input_usd_per_1m=GPT_5_4_MINI_CACHED_INPUT_USD_PER_1M,
        output_usd_per_1m=GPT_5_4_MINI_OUTPUT_USD_PER_1M,
        pricing_source=GPT_5_4_MINI_PRICING_SOURCE,
    )


def _json_object(value: object) -> JsonObject:
    return value if isinstance(value, dict) else {}


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)
