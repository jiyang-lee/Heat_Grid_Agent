"""Run one production-shaped RAG answer-quality smoke test."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
for path in (ROOT / "src", BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from agent_runtime_factory import create_agent_runtime  # noqa: E402
from agent_v2_adapters import _rag_retrieval  # noqa: E402
from agent_v2_reporting import _report  # noqa: E402
from heatgrid_ops.agent.errors import AgentDependencyError  # noqa: E402
from heatgrid_ops.agent.lineage import canonical_json_hash  # noqa: E402
from heatgrid_ops.agent.v2_state import AgentV2State, V2RequestState  # noqa: E402
from heatgrid_rag.search import RagSearcher  # noqa: E402
from repository import fetch_ops_input, list_cards, make_engine  # noqa: E402
from settings import Settings  # noqa: E402


class _CapturingModel:
    def __init__(self, delegate: Any, errors: list[dict[str, str]]) -> None:
        self.delegate = delegate
        self.errors = errors

    async def generate(self, request: Any) -> Any:
        try:
            return await self.delegate.generate(request)
        except AgentDependencyError as exc:
            self.errors.append(
                {
                    "operation": "generate",
                    "service": exc.service,
                    "detail": exc.detail[:500],
                }
            )
            raise

    async def evaluate_answer_quality(self, request: Any) -> Any:
        try:
            return await self.delegate.evaluate_answer_quality(request)
        except AgentDependencyError as exc:
            self.errors.append(
                {
                    "operation": "evaluate_answer_quality",
                    "service": exc.service,
                    "detail": exc.detail[:500],
                }
            )
            raise


def _synthetic_state() -> AgentV2State:
    source_input = {
        "card_id": "synthetic-answer-quality-smoke",
        "priority_context": {
            "priority": {"priority_level": "HIGH"},
            "explanation": {
                "why_reason": "가상 공급 온도 편차가 반복되어 점검이 필요합니다.",
                "recommended_action": "가상 센서와 제어 밸브 상태를 확인합니다.",
            },
        },
    }
    return AgentV2State(
        request=V2RequestState(
            run_id="answer-quality-runtime-smoke",
            alert_id="synthetic-runtime-smoke",
            card_id="synthetic-answer-quality-smoke",
            source_input=source_input,
            input_hash=canonical_json_hash(source_input),
        ),
        rag_retrieval={
            "execution_status": "passed",
            "quality_status": "passed",
            "score": 100.0,
            "status": "available",
            "retrieval": {
                "status": "available",
                "backend": "synthetic",
                "top_k": 1,
                "chunks": [
                    {
                        "chunk_id": "synthetic-check-001",
                        "document_title": "가상 설비 점검 기준",
                        "section_title": "공급 온도 편차",
                        "text": (
                            "가상 공급 온도 편차가 반복되면 센서 교차 확인, "
                            "제어 밸브 개도 확인, 설정값 변경 이력 확인 순으로 점검한다. "
                            "현장 계측 전에는 밸브 고장으로 확정하지 않는다."
                        ),
                    }
                ],
            },
            "references": {
                "technical_standards": [
                    {
                        "chunk_id": "synthetic-check-001",
                        "document_title": "가상 설비 점검 기준",
                    }
                ]
            },
            "quality_reasons": [],
            "retrieval_attempts": [
                {
                    "top_k": 1,
                    "result_count": 1,
                    "quality_status": "passed",
                    "score": 100.0,
                    "reasons": [],
                }
            ],
            "broadened": False,
        },
    )


async def run_smoke(
    card_id: str | None,
    *,
    synthetic: bool = False,
    exercise_regeneration: bool = False,
) -> dict[str, object]:
    load_dotenv(ROOT / ".env", override=False)
    os.environ["HEATGRID_RAG_BACKEND"] = "pgvector"
    settings = Settings()
    searcher = RagSearcher()
    health = searcher.health()
    if health.get("active_backend") != "pgvector":
        raise RuntimeError(f"pgvector is unavailable: {health.get('pgvector')}")

    engine = make_engine(settings.database_url)
    try:
        runtime = create_agent_runtime(settings, engine, rag_searcher=searcher)
        if exercise_regeneration:
            runtime = replace(
                runtime,
                config=replace(runtime.config, answer_quality_threshold=101.0),
            )
        captured_errors: list[dict[str, str]] = []
        runtime = replace(
            runtime,
            work_order_model=_CapturingModel(
                runtime.work_order_model,
                captured_errors,
            ),
            answer_quality_model=_CapturingModel(
                runtime.answer_quality_model,
                captured_errors,
            ),
        )
        if synthetic:
            state = _synthetic_state()
            selected_card_id = state.request.card_id
            priority_level = "HIGH"
        else:
            cards = await list_cards(engine, priority_level="HIGH")
            if not cards:
                cards = await list_cards(engine)
            if not cards:
                raise RuntimeError("no priority card is available for the smoke test")
            selected_card_id = card_id or str(cards[0]["card_id"])
            source_input = await fetch_ops_input(engine, selected_card_id)
            if source_input is None:
                raise RuntimeError(f"card not found: {selected_card_id}")
            state = AgentV2State(
                request=V2RequestState(
                    run_id="answer-quality-runtime-smoke",
                    alert_id="runtime-smoke",
                    card_id=selected_card_id,
                    source_input=source_input,
                    input_hash=canonical_json_hash(source_input),
                )
            )
            rag_envelope = await _rag_retrieval(runtime, True)(state)
            state = AgentV2State.model_validate(rag_envelope.data)
            priority_level = str(cards[0].get("priority_level"))
        report_envelope = await _report(runtime)(state)
        report = report_envelope.data["report_draft"]
        comparison = report["answer_quality_comparison"]
        retrieval = state.rag_retrieval["retrieval"]

        regenerated = comparison["regeneration_triggered"] is True
        expected_calls = 4 if regenerated else 2
        initial_judged = comparison["initial"]["evaluation"] is not None
        regenerated_judged = (
            not regenerated or comparison["regenerated"]["evaluation"] is not None
        )
        smoke_passed = (
            not captured_errors
            and report["model_call_count"] == expected_calls
            and initial_judged
            and regenerated_judged
        )

        return {
            "smoke_passed": smoke_passed,
            "input_mode": "synthetic" if synthetic else "live_card",
            "regeneration_test_override": exercise_regeneration,
            "card_id": selected_card_id,
            "priority_level": priority_level,
            "local_rag_backend": health.get("active_backend"),
            "rag_backend": retrieval.get("backend"),
            "rag_top_k": retrieval.get("top_k"),
            "rag_quality_status": state.rag_retrieval.get("quality_status"),
            "answer_model": settings.work_order_model,
            "judge_model": settings.rejudge_model,
            "threshold": comparison["threshold"],
            "initial_score": comparison["initial"]["score"],
            "regeneration_triggered": regenerated,
            "regenerated_score": (
                None
                if comparison["regenerated"] is None
                else comparison["regenerated"]["score"]
            ),
            "selected_variant": comparison["selected_variant"],
            "selected_score": report["score"],
            "quality_status": report["quality_status"],
            "force_review": report_envelope.control.force_review,
            "model_call_count": report["model_call_count"],
            "evaluation_error": comparison["evaluation_error"],
            "captured_errors": captured_errors,
        }
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card-id")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--exercise-regeneration", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(
        run_smoke(
            args.card_id,
            synthetic=args.synthetic,
            exercise_regeneration=args.exercise_regeneration,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["smoke_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
