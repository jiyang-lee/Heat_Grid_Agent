"""상위 N 자동 처리 드라이버 → docs/send/ 에 보고서+메일 초안.

기본은 동일 tool 을 결정적 순서로 직접 호출(_run_offline)한다.
--llm 을 명시하고 OPENAI_API_KEY 가 있을 때만 langgraph(ChatOpenAI)로 구동한다.

실행: ``uv run python -m agent.llm.run_agent --top-n 5``
"""

from __future__ import annotations

import argparse
import json
import os

from agent.llm import prompts
from agent.llm import tools as t


def _run_offline(top_n: int) -> list[dict]:
    top = json.loads(t.get_top_priority.invoke({"n": top_n}))
    results = []
    for item in top:
        sid = int(item["substation_id"])
        ws, we = item["window_start"], item["window_end"]
        ctx = json.loads(
            t.get_substation_context.invoke(
                {
                    "manufacturer": item["manufacturer"],
                    "substation_id": sid,
                    "window_start": ws,
                    "window_end": we,
                }
            )
        )
        ev = json.loads(
            t.get_sensor_evidence.invoke(
                {"substation_id": sid, "window_start": ws, "window_end": we}
            )
        )
        findings = json.dumps(
            {"evidence": ev, "context": ctx, "priority": item}, ensure_ascii=False
        )
        wo_path = t.draft_work_order.invoke(
            {
                "manufacturer": item["manufacturer"],
                "substation_id": sid,
                "window_start": ws,
                "window_end": we,
                "findings": findings,
            }
        )
        sensors = ev.get("main_abnormal_sensors") or []
        email_path = t.draft_email.invoke(
            {
                "manufacturer": item["manufacturer"],
                "substation_id": sid,
                "window_start": ws,
                "window_end": we,
                "work_order_path": wo_path,
                "priority_score": item["priority_score"],
                "priority_level": item["priority_level"],
                "evidence_short": ", ".join(sensors) if sensors else "위험 점수 상승",
            }
        )
        results.append({"substation_id": sid, "work_order": wo_path, "email": email_path})
    return results


def _run_with_llm(top_n: int) -> list[dict]:
    from langchain_core.messages import HumanMessage, SystemMessage

    from agent.llm.graph import build_graph

    app = build_graph()
    seed = (
        f"우선순위 상위 {top_n}개 점검 대상 각각에 대해 운영 보고서와 작업자 메일 초안을 "
        f"작성하고 저장된 파일 경로를 보고하세요."
    )
    state = app.invoke(
        {"messages": [SystemMessage(prompts.SYSTEM_PROMPT), HumanMessage(seed)]}
    )
    # tool 메시지에서 생성된 파일 경로 수집
    paths_found = []
    for m in state["messages"]:
        content = getattr(m, "content", "")
        if isinstance(content, str) and ("work_order_" in content or "email_" in content):
            paths_found.append(content)
    return [{"raw_tool_outputs": paths_found}]


def run(top_n: int = 5, *, use_llm: bool = False) -> list[dict]:
    if use_llm and os.getenv("OPENAI_API_KEY"):
        print(f"[run_agent] LLM 모드(ChatOpenAI), top_n={top_n}")
        return _run_with_llm(top_n)
    if use_llm and not os.getenv("OPENAI_API_KEY"):
        print("[run_agent] OPENAI_API_KEY 없음 — 오프라인 결정적 모드로 전환")
    print(f"[run_agent] 오프라인 결정적 모드, top_n={top_n}")
    return _run_offline(top_n)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--offline", action="store_true", help="deterministic tool-only mode; this is the default")
    ap.add_argument("--llm", action="store_true", help="use LangGraph/OpenAI when OPENAI_API_KEY exists")
    args = ap.parse_args()
    results = run(args.top_n, use_llm=args.llm and not args.offline)
    print(f"[run_agent] 생성 {len(results)}건:")
    for r in results:
        print("  " + json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
