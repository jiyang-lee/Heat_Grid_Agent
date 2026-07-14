from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Protocol

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Checkpointer, Durability
from pydantic import TypeAdapter

from heatgrid_ops.agent.contracts import AgentRunRequest, SimulateCard
from heatgrid_ops.agent.nodes import (
    assess_collected_evidence,
    complete_run,
    create_final_review,
    expand_internal_evidence,
    generate_fallback_output,
    generate_operational_answer,
    get_external_context,
    get_ops_evidence,
    load_ops_input,
    mark_running,
    prepare_output_retry,
    rerun_model_verification,
    run_diagnostic_worker,
    route_after_assessment,
    route_after_llm,
    route_after_output_validation,
    validate_output,
    verify_model_output,
)
from heatgrid_ops.agent.ports import (
    AgentBudgetPort,
    ArtifactPort,
    AgentInputPort,
    ReviewPort,
    RunAuditPort,
    RunLifecyclePort,
)
from heatgrid_ops.agent.report_nodes import write_anomaly_report
from heatgrid_ops.agent.run_models import AgentRunResult
from heatgrid_ops.agent.review_models import (
    AgentRunReviewCaptureSource,
    ReviewCaptureFailure,
)
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_ops.agent.state import (
    AgentGraphInput,
    AgentGraphOutput,
    AgentState,
    AuditState,
    EvidenceState,
    LoopState,
    OutputState,
    RequestState,
    ResultState,
)


@dataclass(frozen=True, slots=True)
class AgentGraphContext:
    runtime: AgentRuntime
    inputs: AgentInputPort
    lifecycle: RunLifecyclePort
    audit: RunAuditPort
    reviews: ReviewPort
    artifacts: ArtifactPort
    legacy_simulate_card: SimulateCard | None = None
    budget: AgentBudgetPort | None = None


class AgentGraphInvoker(Protocol):
    @property
    def checkpointer_enabled(self) -> bool: ...

    @property
    def max_iterations(self) -> int: ...

    async def ainvoke(
        self,
        input: AgentGraphInput | None,
        config: RunnableConfig,
        *,
        durability: Durability | None,
    ) -> AgentGraphOutput: ...


@dataclass(frozen=True, slots=True)
class CompiledAgentGraph:
    compiled: CompiledStateGraph[
        AgentState,
        None,
        AgentGraphInput,
        AgentGraphOutput,
    ]
    max_iterations: int

    @property
    def checkpointer_enabled(self) -> bool:
        return self.compiled.checkpointer is not None

    async def ainvoke(
        self,
        input: AgentGraphInput | None,
        config: RunnableConfig,
        *,
        durability: Durability | None,
    ) -> AgentGraphOutput:
        output = await self.compiled.ainvoke(
            input,
            config,
            durability=durability,
        )
        return TypeAdapter(AgentGraphOutput).validate_python(output)


@dataclass(frozen=True, slots=True)
class AgentGraphExecution:
    result: AgentRunResult
    review_capture_source: AgentRunReviewCaptureSource | None
    review_capture_failure: ReviewCaptureFailure | None = None


async def execute_agent_graph(
    context: AgentGraphContext | None,
    request: AgentRunRequest,
    *,
    graph: AgentGraphInvoker | None = None,
    resume: bool = False,
) -> AgentRunResult:
    execution = await execute_agent_graph_with_capture(
        context,
        request,
        graph=graph,
        resume=resume,
    )
    return execution.result


async def execute_agent_graph_with_capture(
    context: AgentGraphContext | None,
    request: AgentRunRequest,
    *,
    graph: AgentGraphInvoker | None = None,
    resume: bool = False,
) -> AgentGraphExecution:
    if graph is None:
        if context is None:
            raise ValueError("context is required when graph is not precompiled")
        active_graph = build_agent_graph(context)
    else:
        active_graph = graph
    initial: AgentGraphInput | None = (
        None
        if resume
        else {
            "request": RequestState(
                run_id=request.run_id,
                alert_id=request.alert_id,
                card_id=request.card_id,
            ),
            "evidence": EvidenceState(),
            "loop": LoopState(
                max_iterations=active_graph.max_iterations,
            ),
            "output": OutputState(),
            "audit": AuditState(),
            "result": ResultState(),
        }
    )
    config: RunnableConfig = {
        "configurable": {"thread_id": request.run_id},
        "recursion_limit": 64,
    }
    state = await active_graph.ainvoke(
        initial,
        config,
        durability="sync" if active_graph.checkpointer_enabled else None,
    )
    result = ResultState.model_validate(state["result"])
    if result.value is None:
        raise RuntimeError("agent graph completed without a result")
    return AgentGraphExecution(
        result=result.value,
        review_capture_source=result.review_capture_source,
        review_capture_failure=result.review_capture_failure,
    )


def build_agent_graph(
    context: AgentGraphContext,
    checkpointer: Checkpointer = None,
) -> AgentGraphInvoker:
    graph = StateGraph(
        AgentState,
        input_schema=AgentGraphInput,
        output_schema=AgentGraphOutput,
    )
    graph.add_node("mark_running", partial(mark_running, context))
    graph.add_node("load_ops_input", partial(load_ops_input, context))
    graph.add_node("get_ops_evidence", partial(get_ops_evidence, context))
    graph.add_node("get_external_context", partial(get_external_context, context))
    graph.add_node("verify_model_output", partial(verify_model_output, context))
    graph.add_node(
        "assess_collected_evidence", partial(assess_collected_evidence, context)
    )
    graph.add_node(
        "expand_internal_evidence", partial(expand_internal_evidence, context)
    )
    graph.add_node(
        "rerun_model_verification", partial(rerun_model_verification, context)
    )
    graph.add_node("run_diagnostic_worker", partial(run_diagnostic_worker, context))
    graph.add_node(
        "generate_operational_answer", partial(generate_operational_answer, context)
    )
    graph.add_node(
        "generate_fallback_output", partial(generate_fallback_output, context)
    )
    graph.add_node("validate_output", partial(validate_output, context))
    graph.add_node("prepare_output_retry", partial(prepare_output_retry, context))
    graph.add_node("create_final_review", partial(create_final_review, context))
    graph.add_node("complete_run", partial(complete_run, context))
    graph.add_node("write_anomaly_report", partial(write_anomaly_report, context))
    graph.add_edge(START, "mark_running")
    graph.add_edge("mark_running", "load_ops_input")
    graph.add_edge("load_ops_input", "get_ops_evidence")
    graph.add_edge("get_ops_evidence", "get_external_context")
    graph.add_edge("get_external_context", "verify_model_output")
    graph.add_edge("verify_model_output", "assess_collected_evidence")
    graph.add_conditional_edges(
        "assess_collected_evidence",
        route_after_assessment,
        {
            "expand_internal_evidence": "expand_internal_evidence",
            "rerun_model_verification": "rerun_model_verification",
            "run_diagnostic_worker": "run_diagnostic_worker",
            "generate_operational_answer": "generate_operational_answer",
        },
    )
    graph.add_edge("expand_internal_evidence", "assess_collected_evidence")
    graph.add_edge("rerun_model_verification", "assess_collected_evidence")
    graph.add_edge("run_diagnostic_worker", "assess_collected_evidence")
    graph.add_conditional_edges(
        "generate_operational_answer",
        route_after_llm,
        {
            "generate_fallback_output": "generate_fallback_output",
            "validate_output": "validate_output",
        },
    )
    graph.add_edge("generate_fallback_output", "validate_output")
    graph.add_conditional_edges(
        "validate_output",
        route_after_output_validation,
        {
            "prepare_output_retry": "prepare_output_retry",
            "create_final_review": "create_final_review",
        },
    )
    graph.add_edge("prepare_output_retry", "generate_operational_answer")
    graph.add_edge("create_final_review", "write_anomaly_report")
    graph.add_edge("write_anomaly_report", "complete_run")
    graph.add_edge("complete_run", END)
    return CompiledAgentGraph(
        compiled=graph.compile(checkpointer=checkpointer),
        max_iterations=context.runtime.config.agent_max_iterations,
    )
