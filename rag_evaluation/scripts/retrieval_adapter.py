"""Adapter between production RagSearcher and retrieval evaluation."""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@contextmanager
def temporary_backend(backend: str) -> Iterator[None]:
    previous = os.environ.get("HEATGRID_RAG_BACKEND")
    if backend:
        os.environ["HEATGRID_RAG_BACKEND"] = backend
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("HEATGRID_RAG_BACKEND", None)
        else:
            os.environ["HEATGRID_RAG_BACKEND"] = previous


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_evidence(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "evaluation_metadata": {
            "case_id": case.get("case_id"),
            "category": case.get("category"),
            "query_intent": case.get("query_intent"),
            "fault_group": case.get("fault_group"),
            "substation_context": case.get("substation_context"),
        },
        "priority_context": {
            "model_signals": {
                "m1_specialist_fault_group": case.get("fault_group"),
            }
        },
    }


def normalize_chunks(raw_result: dict[str, Any]) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_result.get("chunks") or [], 1):
        if not isinstance(item, dict):
            warnings.append(f"non_dict_chunk_skipped:{index}")
            continue
        chunk_id = item.get("chunk_id")
        if not chunk_id:
            warnings.append(f"missing_chunk_id_skipped:{index}")
            continue
        chunk_id = str(chunk_id)
        if chunk_id in seen:
            warnings.append(f"duplicate_chunk_id_deduped:{chunk_id}")
            continue
        seen.add(chunk_id)
        normalized.append(chunk_id)
    return normalized, warnings


class RagSearcherAdapter:
    def __init__(self, requested_backend: str = "jsonl", top_k: int = 5) -> None:
        self.requested_backend = requested_backend
        self.top_k = top_k

    def _create_searcher(self) -> Any:
        from heatgrid_rag.search import RagSearcher

        with temporary_backend(self.requested_backend):
            return RagSearcher()

    def health(self) -> dict[str, Any]:
        try:
            searcher = self._create_searcher()
            return searcher.health()
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def search_case(self, case: dict[str, Any]) -> dict[str, Any]:
        started_at = utc_now_iso()
        start = time.monotonic()
        raw_result: dict[str, Any] | None = None
        normalized: list[str] = []
        warnings: list[str] = []
        error: str | None = None
        actual_backend: str | None = None
        try:
            searcher = self._create_searcher()
            health = searcher.health()
            active_backend = health.get("active_backend")
            if self.requested_backend == "pgvector" and active_backend != "pgvector":
                raise RuntimeError("requested pgvector backend is unavailable; active backend is not pgvector")
            raw_result = searcher.search(
                query=str(case.get("query") or ""),
                top_k=self.top_k,
                evidence=build_evidence(case),
            )
            actual_backend = str(raw_result.get("backend") or active_backend or "unknown")
            normalized, warnings = normalize_chunks(raw_result)
            if self.requested_backend != "auto" and actual_backend != self.requested_backend:
                warnings.append(f"requested_backend_differs_from_actual:{self.requested_backend}->{actual_backend}")
        except Exception as exc:
            error = str(exc)
            raw_result = None
            actual_backend = None
        finished_at = utc_now_iso()
        latency_ms = (time.monotonic() - start) * 1000
        return {
            "case_id": case.get("case_id"),
            "query": case.get("query"),
            "requested_backend": self.requested_backend,
            "actual_backend": actual_backend,
            "top_k": self.top_k,
            "raw_results": raw_result,
            "normalized_retrieved_chunk_ids": normalized,
            "warnings": warnings,
            "retrieval_started_at": started_at,
            "retrieval_finished_at": finished_at,
            "retrieval_latency_ms": latency_ms,
            "error": error,
        }
