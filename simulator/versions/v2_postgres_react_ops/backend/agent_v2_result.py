from __future__ import annotations

import orjson
from pydantic import TypeAdapter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.agent.lineage import canonical_json_hash
from heatgrid_ops.agent.models import OpsAgentOutput, TokenUsage
from heatgrid_ops.agent.run_models import AgentLoopSummary, AgentRunResult
from heatgrid_ops.agent.review_models import (
    AgentRunReviewCaptureSource,
    ReviewCaptureSourceCardSnapshot,
    ReviewDiagnosticSnapshot,
    ReviewFinalResultSnapshot,
    ReviewOpsAgentOutput,
)
from heatgrid_ops.agent.state import AgentGraphOutput, ResultState
from heatgrid_ops.agent.v2_state import AgentV2State


def build_v2_graph_output(
    result: object,
    *,
    execution_duration_ms: int,
) -> AgentGraphOutput:
    state = TypeAdapter(dict[str, object]).validate_python(result)
    raw_state = v2_state_from_graph_result(result)
    report = raw_state.report_draft
    summary = report.get("summary")
    action_plan = report.get("action_plan")
    caution = report.get("caution")
    output = (
        OpsAgentOutput(summary=summary, action_plan=action_plan, caution=caution)
        if isinstance(summary, str)
        and isinstance(action_plan, str)
        and isinstance(caution, str)
        else OpsAgentOutput(
            summary="Graph v2 stage execution completed.",
            action_plan="Review the persisted stage evidence and disposition.",
            caution="Stage quality and external evaluator availability are recorded in snapshots.",
        )
    )
    usage = report.get("token_usage")
    completed_stages = state.get("completed_stages")
    iteration_count = len(completed_stages) if isinstance(completed_stages, (tuple, list)) else 0
    loop_summary = AgentLoopSummary(
        iterations=iteration_count,
        max_iterations=4,
        decision="finalize",
        confidence=1.0,
        evidence_score=100.0,
        review_required=raw_state.parent_disposition.force_review,
        disposition=raw_state.parent_disposition.disposition,
        blocking_retry_exhausted=list(raw_state.parent_disposition.blocking_retry_exhausted),
        graph_contract_version="agent_graph_v2.v3",
        execution_duration_ms=execution_duration_ms,
    )
    result_model = AgentRunResult(
        run_id=raw_state.request.run_id,
        status="completed",
        input_source="alert",
        alert_id=raw_state.request.alert_id,
        card_id=raw_state.request.card_id,
        agent_mode="fallback",
        ops_output=output,
        token_usage=TokenUsage.model_validate(usage) if isinstance(usage, dict) else TokenUsage(),
        loop_summary=loop_summary,
        review_status="pending",
    )
    capture = AgentRunReviewCaptureSource(
        run_id=raw_state.request.run_id,
        result=ReviewFinalResultSnapshot(
            status="completed",
            agent_mode="fallback",
            ops_output=ReviewOpsAgentOutput(
                summary=output.summary,
                action_plan=output.action_plan,
                caution=output.caution,
            ),
        ),
        loop_count=iteration_count,
        handling_reason="explicit graph v2 completed",
        diagnostic=ReviewDiagnosticSnapshot(status="not_triggered"),
        source_card=_source_card(raw_state),
    )
    return {"result": ResultState(value=result_model, review_capture_source=capture)}


def _source_card(state: AgentV2State) -> ReviewCaptureSourceCardSnapshot:
    source = state.request.source_input
    priority_context = _mapping(source.get("priority_context"))
    card = _mapping(priority_context.get("card"))
    priority = _mapping(priority_context.get("priority"))
    explanation = _mapping(priority_context.get("explanation"))
    window = _mapping(_mapping(source.get("raw_context")).get("window"))
    priority_level = _bounded(_string(priority.get("priority_level")), 120)
    return ReviewCaptureSourceCardSnapshot(
        card_id=state.request.card_id,
        substation_id=_integer(window.get("substation_id")),
        manufacturer_id=_bounded(_string(window.get("manufacturer_id")), 200),
        priority_level=priority_level,
        status=_bounded(_string(card.get("status")), 120),
        review_required=state.parent_disposition.force_review,
        reason=_bounded(
            _string(
                explanation.get("why_reason")
                or card.get("why_reason")
                or card.get("reason")
                or (f"priority_level={priority_level}" if priority_level else None)
            ),
            1000,
        ),
    )


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _string(value: object) -> str:
    return value if isinstance(value, str) else ""


def _integer(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _bounded(value: str, limit: int) -> str | None:
    return value[:limit] if value else None


def v2_state_from_graph_result(result: object) -> AgentV2State:
    state = TypeAdapter(dict[str, object]).validate_python(result)
    raw_state = state.get("state")
    if isinstance(raw_state, AgentV2State):
        return raw_state
    return AgentV2State.model_validate(raw_state)


async def persist_completed_v2_run(
    engine: AsyncEngine,
    output: AgentGraphOutput,
    *,
    state: AgentV2State,
) -> None:
    result = output["result"].value
    if result is None:
        raise RuntimeError("v2 graph completed without result")
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE agent_runs SET status = 'completed', agent_mode = :agent_mode, "
                "ops_output = CAST(:ops_output AS jsonb), "
                "token_usage = CAST(:token_usage AS jsonb), "
                "loop_summary = CAST(:loop_summary AS jsonb), error = NULL, "
                "updated_at = now() WHERE run_id = :run_id"
            ),
            {
                "run_id": result.run_id,
                "agent_mode": result.agent_mode,
                "ops_output": orjson.dumps(
                    result.ops_output.model_dump(mode="json")
                    if result.ops_output is not None
                    else None
                ).decode("utf-8"),
                "token_usage": orjson.dumps(
                    result.token_usage.model_dump(mode="json")
                    if result.token_usage is not None
                    else None
                ).decode("utf-8"),
                "loop_summary": orjson.dumps(
                    result.loop_summary.model_dump(mode="json")
                    if result.loop_summary is not None
                    else None
                ).decode("utf-8"),
            },
        )
        await _persist_report_model_call(connection, result.run_id, state)


async def _persist_report_model_call(connection, run_id: str, state: AgentV2State) -> None:
    report = state.report_draft
    usage = TokenUsage.model_validate(report.get("token_usage", {}))
    bundle_hash = report.get("snapshot_bundle_hash")
    if not isinstance(bundle_hash, str):
        bundle_hash = None
    output_hash = canonical_json_hash(
        {
            "summary": report.get("summary"),
            "action_plan": report.get("action_plan"),
            "caution": report.get("caution"),
        }
    )
    stage_attempt = state.attempts.get("report_draft", 1)
    operation_key = (
        f"model-call:{run_id}:report_draft:{stage_attempt}:report_snapshot_only:"
        f"{bundle_hash or state.request.input_hash}"
    )
    snapshot = await connection.execute(
        text(
            "SELECT stage_snapshot_id FROM agent_stage_snapshots "
            "WHERE run_id = :run_id AND stage_name = 'report_draft' "
            "AND attempt = :attempt"
        ),
        {"run_id": run_id, "attempt": stage_attempt},
    )
    snapshot_id = snapshot.scalar_one_or_none()
    status = "completed" if usage.model_calls == 1 else "failed"
    await connection.execute(
        text(
            "INSERT INTO agent_model_calls ("
            "run_id, stage_snapshot_id, stage_name, stage_attempt, execution_profile, "
            "purpose, model_name, status, input_hash, snapshot_bundle_hash, output_hash, "
            "allowed_tools, max_total_tool_calls, max_model_turns, actual_tool_calls, "
            "actual_model_turns, input_tokens, cached_input_tokens, output_tokens, "
            "total_tokens, operation_key, completed_at"
            ") VALUES ("
            ":run_id, :stage_snapshot_id, 'report_draft', :stage_attempt, "
            "'report_snapshot_only', 'report_draft', 'configured', :status, "
            ":input_hash, :bundle_hash, :output_hash, '[]'::jsonb, 0, 1, 0, "
            ":model_turns, :input_tokens, :cached_input_tokens, :output_tokens, "
            ":total_tokens, :operation_key, now()"
            ") ON CONFLICT (operation_key) DO NOTHING"
        ),
        {
            "run_id": run_id,
            "stage_snapshot_id": snapshot_id,
            "stage_attempt": stage_attempt,
            "status": status,
            "input_hash": bundle_hash or state.request.input_hash,
            "bundle_hash": bundle_hash,
            "output_hash": output_hash,
            "model_turns": min(usage.model_calls, 1),
            "input_tokens": usage.input_tokens,
            "cached_input_tokens": usage.cached_input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": usage.total_tokens,
            "operation_key": operation_key,
        },
    )
    await connection.execute(
        text(
            "INSERT INTO agent_run_events (run_id, event_type, message, payload, operation_key) "
            "VALUES (:run_id, 'model_call_completed', 'report model call recorded', "
            "CAST(:payload AS jsonb), :operation_key) "
            "ON CONFLICT (operation_key) WHERE operation_key IS NOT NULL DO NOTHING"
        ),
        {
            "run_id": run_id,
            "payload": orjson.dumps(
                {
                    "stage_name": "report_draft",
                    "stage_attempt": stage_attempt,
                    "execution_profile": "report_snapshot_only",
                    "snapshot_bundle_hash": bundle_hash,
                    "actual_tool_calls": 0,
                    "actual_model_turns": min(usage.model_calls, 1),
                }
            ).decode("utf-8"),
            "operation_key": f"event:{operation_key}",
        },
    )
