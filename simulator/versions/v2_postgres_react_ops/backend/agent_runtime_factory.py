from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine

from agent_budget_adapter import PostgresAgentBudgetAdapter
from agent_chat_model_adapter import OpenAIChatModelAdapter
from agent_evidence_adapters import (
    InternalRagEvidenceAdapter,
    StructuredExternalDataAdapter,
)
from agent_input_model_adapter import PostgresAgentInputModelAdapter
from agent_model_verification_adapter import ActiveModelVerificationAdapter
from agent_persistence_adapter import PostgresAgentPersistenceAdapter
from agent_report_writer_adapter import (
    LocalReportWriterAdapter,
    default_report_output_root,
)
from agent_review_adapter import PostgresAgentReviewAdapter
from heatgrid_ops.agent.config import AgentRuntimeConfig, ModelPricing
from heatgrid_ops.agent.contracts import SimulateCard
from heatgrid_ops.agent.graph import AgentGraphContext
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_rag.search import RagSearcher
from settings import (
    GPT_5_4_CACHED_INPUT_USD_PER_1M,
    GPT_5_4_INPUT_USD_PER_1M,
    GPT_5_4_MINI_CACHED_INPUT_USD_PER_1M,
    GPT_5_4_MINI_INPUT_USD_PER_1M,
    GPT_5_4_MINI_OUTPUT_USD_PER_1M,
    GPT_5_4_MINI_PRICING_SOURCE,
    GPT_5_4_OUTPUT_USD_PER_1M,
    GPT_5_4_PRICING_SOURCE,
    Settings,
)


def create_agent_runtime(
    settings: Settings,
    engine: AsyncEngine,
    rag_searcher: RagSearcher | None = None,
) -> AgentRuntime:
    searcher = rag_searcher or RagSearcher()
    input_model = PostgresAgentInputModelAdapter(engine)
    key = settings.openai_api_key
    key_value = None if key is None else key.get_secret_value().strip()
    api_key = key_value or None
    integrated_model = OpenAIChatModelAdapter(
        api_key=api_key,
        model=settings.integrated_agent_model,
    )
    work_order_model = OpenAIChatModelAdapter(
        api_key=api_key,
        model=settings.work_order_model,
    )
    independent_model = OpenAIChatModelAdapter(
        api_key=api_key,
        model=settings.independent_agent_model,
    )
    rejudge_model = OpenAIChatModelAdapter(
        api_key=api_key,
        model=settings.rejudge_model,
    )
    return AgentRuntime(
        config=agent_runtime_config(settings),
        rag=InternalRagEvidenceAdapter(searcher),
        external_data=StructuredExternalDataAdapter(searcher),
        chat_model=integrated_model,
        work_order_model=work_order_model,
        rejudge_model=rejudge_model,
        answer_quality_model=rejudge_model,
        model_verification=ActiveModelVerificationAdapter(
            model_data=input_model,
            tolerance=settings.model_score_tolerance,
        ),
        report_writer=LocalReportWriterAdapter(
            api_key=api_key,
            model=settings.report_model,
            output_root=default_report_output_root(),
        ),
        diagnostic_model=independent_model,
    )


def create_agent_graph_context(
    engine: AsyncEngine,
    runtime: AgentRuntime,
    simulate_card: SimulateCard | None = None,
) -> AgentGraphContext:
    persistence = PostgresAgentPersistenceAdapter(engine)
    return AgentGraphContext(
        runtime=runtime,
        inputs=PostgresAgentInputModelAdapter(engine),
        lifecycle=persistence,
        audit=persistence,
        reviews=PostgresAgentReviewAdapter(engine),
        artifacts=persistence,
        legacy_simulate_card=simulate_card,
        budget=PostgresAgentBudgetAdapter(engine),
    )


def agent_runtime_config(settings: Settings) -> AgentRuntimeConfig:
    return AgentRuntimeConfig(
        openai_model=settings.integrated_agent_model,
        rag_top_k=settings.rag_top_k,
        rag_expanded_top_k=settings.rag_expanded_top_k,
        rag_max_top_k=settings.rag_max_top_k,
        rag_jsonl_min_top_score=settings.rag_jsonl_min_top_score,
        rag_jsonl_min_unique_matches=settings.rag_jsonl_min_unique_matches,
        agent_max_iterations=settings.agent_max_iterations,
        agent_evidence_threshold=settings.agent_evidence_threshold,
        model_score_tolerance=settings.model_score_tolerance,
        input_usd_per_1m=GPT_5_4_MINI_INPUT_USD_PER_1M,
        cached_input_usd_per_1m=GPT_5_4_MINI_CACHED_INPUT_USD_PER_1M,
        output_usd_per_1m=GPT_5_4_MINI_OUTPUT_USD_PER_1M,
        pricing_source=GPT_5_4_MINI_PRICING_SOURCE,
        answer_quality_enabled=settings.answer_quality_enabled,
        answer_quality_threshold=settings.answer_quality_threshold,
        answer_quality_baseline_version=settings.answer_quality_baseline_version,
        model_pricing_overrides=(
            ModelPricing(
                model=settings.rejudge_model,
                input_usd_per_1m=GPT_5_4_INPUT_USD_PER_1M,
                cached_input_usd_per_1m=GPT_5_4_CACHED_INPUT_USD_PER_1M,
                output_usd_per_1m=GPT_5_4_OUTPUT_USD_PER_1M,
                pricing_source=GPT_5_4_PRICING_SOURCE,
            ),
        ),
    )
