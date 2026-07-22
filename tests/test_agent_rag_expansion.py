from __future__ import annotations

import importlib
from pathlib import Path
from typing import cast

import pytest

from heatgrid_ops.agent.config import AgentRuntimeConfig
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.rag_quality import evaluate_retrieval_quality
from heatgrid_ops.agent.rag_quality import rerank_retrieval
from heatgrid_ops.agent.run_models import RagEvidenceSnapshot
from heatgrid_ops.agent.v2_state import AgentV2State, V2RequestState


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"


def runtime_config() -> AgentRuntimeConfig:
    return AgentRuntimeConfig(
        openai_model="test",
        rag_top_k=5,
        agent_max_iterations=4,
        agent_evidence_threshold=0.75,
        model_score_tolerance=0.12,
        input_usd_per_1m=0.0,
        cached_input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        pricing_source="test",
    )


def state(*, broaden: bool) -> AgentV2State:
    return AgentV2State(
        request=V2RequestState(
            run_id="run-1",
            alert_id="alert-1",
            card_id="card-1",
            source_input={},
            input_hash="a" * 64,
            target_stage="rag_retrieval" if broaden else None,
            broaden=broaden,
        )
    )


def retrieval(top_k: int, *, strong: bool) -> RagEvidenceSnapshot:
    chunks = [
        {
            "chunk_id": f"chunk-{index}",
            "score": 6 if strong else 4,
            "matched_terms": ["pump", "pressure"] if strong else [],
        }
        for index in range(top_k)
    ]
    return RagEvidenceSnapshot(
        status="available",
        retrieval=cast(
            JsonObject,
            {"backend": "jsonl", "top_k": top_k, "chunks": chunks},
        ),
        references={"technical_standards": []},
    )


class FakeRag:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def search(self, request):
        self.calls.append(request.top_k)
        return retrieval(request.top_k, strong=request.top_k == 20)


class FakeRuntime:
    def __init__(self) -> None:
        self.config = runtime_config()
        self.rag = FakeRag()


def test_jsonl_quality_proxy_uses_calibrated_signals() -> None:
    quality, reasons = evaluate_retrieval_quality(
        retrieval(5, strong=True).retrieval,
        quality_enabled=True,
    )
    assert quality.quality_status == "passed"
    assert quality.score == 100.0
    assert reasons == ()


def test_reranker_promotes_low_rank_operational_match() -> None:
    chunks = [
        {
            "chunk_id": f"generic-{index:02d}",
            "rag_role": "domestic_inspection_standard",
            "text": "generic meter installation standard",
        }
        for index in range(1, 20)
    ]
    chunks.append(
        {
            "chunk_id": "pressure-valve-relevant",
            "rag_role": "troubleshooting_manual",
            "text": "differential pressure drop requires control valve inspection",
        }
    )

    reranked, metadata = rerank_retrieval(
        {"backend": "pgvector", "top_k": 20, "chunks": chunks},
        {
            "priority_context": {
                "model_signals": {
                    "fault_group": "differential pressure drop control valve"
                }
            }
        },
        limit=5,
    )

    selected_ids = [item["chunk_id"] for item in reranked["chunks"]]
    assert "pressure-valve-relevant" in selected_ids
    assert reranked["chunks"][0]["chunk_id"] == "pressure-valve-relevant"
    assert reranked["chunks"][0]["original_rank"] == 20
    assert metadata["candidate_count"] == 20
    assert metadata["selected_count"] == 5


@pytest.mark.anyio
async def test_normal_run_uses_only_top_five(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(BACKEND_DIR))
    adapters = importlib.import_module("agent_v2_adapters")
    runtime = FakeRuntime()

    envelope = await adapters._rag_retrieval(runtime, True)(state(broaden=False))

    assert runtime.rag.calls == [5]
    rag = envelope.data["rag_retrieval"]
    assert rag["quality_status"] == "partial"
    assert rag["broadened"] is False
    assert envelope.control.force_review is True


@pytest.mark.anyio
async def test_insufficient_evidence_rerun_expands_to_twenty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(BACKEND_DIR))
    adapters = importlib.import_module("agent_v2_adapters")
    runtime = FakeRuntime()

    envelope = await adapters._rag_retrieval(runtime, True)(state(broaden=True))

    assert runtime.rag.calls == [10, 20]
    rag = envelope.data["rag_retrieval"]
    assert rag["quality_status"] == "passed"
    assert rag["retrieval"]["top_k"] == 20
    assert [item["top_k"] for item in rag["retrieval_attempts"]] == [10, 20]
    assert rag["broadened"] is True
    assert envelope.control.force_review is False
