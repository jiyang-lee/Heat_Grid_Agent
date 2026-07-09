from __future__ import annotations

from typing import Literal, TypedDict

from schemas import AgentRunResponse, JsonValue, OpsAgentOutput, TokenUsage


class AgentState(TypedDict, total=False):
    run_id: str
    alert_id: str
    card_id: str
    source_input: dict[str, JsonValue]
    ops_evidence: dict[str, JsonValue]
    external_context: dict[str, JsonValue]
    used_tools: list[str]
    report_artifacts: list[dict[str, JsonValue]]
    report_errors: list[str]
    ops_output: OpsAgentOutput
    token_usage: TokenUsage
    agent_mode: Literal["llm", "fallback"]
    error: str
    result: AgentRunResponse
