from __future__ import annotations

from schemas import (
    AgentRunResponse,
    OpsAgentActionItem,
    OpsAgentEvidenceItem,
    OpsAgentReport,
    OpsAgentResultV4,
)


def build_ops_agent_result_v4(run: AgentRunResponse) -> OpsAgentResultV4 | None:
    output = run.ops_output
    if output is None:
        return None
    return OpsAgentResultV4(
        run_id=run.run_id,
        card_id=run.card_id,
        headline=output.summary,
        situation=output.summary,
        evidence=[
            OpsAgentEvidenceItem(
                label="운영 근거",
                content="우선순위 카드, 분석 구간, 모델 산출 근거를 함께 참고했습니다.",
                source="postgres",
            ),
            OpsAgentEvidenceItem(
                label="외부 참고자료",
                content="단지 매핑, 기상, 운영 참고자료는 검색 계층에서 제공된 경우 최종 문장에 반영됩니다.",
                source="manual",
            ),
        ],
        actions=[
            OpsAgentActionItem(
                priority=1,
                title="권장 조치",
                detail=output.action_plan,
            ),
        ],
        cautions=[output.caution],
        report=OpsAgentReport(
            title="작업 지시 보고서",
            content=(
                f"# 작업 지시 보고서\n\n"
                f"## 상황 요약\n{output.summary}\n\n"
                f"## 권장 조치\n{output.action_plan}\n\n"
                f"## 주의 사항\n{output.caution}\n"
            ),
        ),
    )
