"""Deterministic runtime quality proxy for RAG retrieval results."""

from __future__ import annotations

import re
from typing import Any

from heatgrid_ops.agent.quality import StageQualityResult, rag_quality_result


_TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
_SOURCE_SIGNAL_KEYS = (
    "action",
    "equipment",
    "fault",
    "label",
    "reason",
    "review",
    "state",
    "symptom",
)
_STOPWORDS = {
    "and",
    "for",
    "the",
    "with",
    "검토",
    "권장",
    "상태",
    "설비",
    "점검",
    "확인",
}
_ROLE_BOOST = {
    "symptom_cause_action_table": 10.0,
    "troubleshooting_manual": 8.0,
    "domestic_inspection_standard": 5.0,
    "fault_priority_research": 4.0,
}


def evaluate_retrieval_quality(
    retrieval: dict[str, Any],
    *,
    quality_enabled: bool,
    jsonl_min_top_score: float = 6.0,
    jsonl_min_unique_matches: int = 2,
) -> tuple[StageQualityResult, tuple[str, ...]]:
    chunks = [item for item in retrieval.get("chunks") or [] if isinstance(item, dict)]
    count_quality = rag_quality_result(
        result_count=len(chunks),
        quality_enabled=quality_enabled,
    )
    if not quality_enabled:
        return count_quality, ("quality_check_disabled",)
    if not chunks:
        return count_quality, ("no_retrieval_results",)

    backend = str(retrieval.get("backend") or "unknown").lower()
    if backend != "jsonl":
        return count_quality, (f"{backend}_count_proxy",)

    scores = [
        float(item["score"])
        for item in chunks
        if isinstance(item.get("score"), (int, float))
    ]
    top_score = max(scores, default=0.0)
    unique_matches = {
        str(term).strip().lower()
        for item in chunks
        for term in item.get("matched_terms") or []
        if str(term).strip()
    }
    match_count = len(unique_matches)
    score_strength = min(top_score / max(jsonl_min_top_score, 1.0), 1.0)
    match_strength = min(match_count / max(jsonl_min_unique_matches, 1), 1.0)
    proxy_score = round((score_strength * 0.55 + match_strength * 0.45) * 100.0, 2)

    reasons: list[str] = []
    if top_score < jsonl_min_top_score:
        reasons.append(f"top_score_below_threshold:{top_score:g}<{jsonl_min_top_score:g}")
    if match_count < jsonl_min_unique_matches:
        reasons.append(
            f"unique_matches_below_threshold:{match_count}<{jsonl_min_unique_matches}"
        )
    if not reasons:
        return StageQualityResult("passed", "passed", proxy_score), ()
    if top_score > 0 or match_count > 0:
        return StageQualityResult("passed", "partial", proxy_score), tuple(reasons)
    return StageQualityResult("passed", "insufficient", 0.0), tuple(reasons)


def rerank_retrieval(
    retrieval: dict[str, Any],
    source_input: dict[str, Any],
    *,
    limit: int = 5,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Rerank expanded candidates with deterministic operational signals."""
    raw_candidates = retrieval.get("chunks")
    candidates: list[dict[str, Any]] = (
        [item for item in raw_candidates if isinstance(item, dict)]
        if isinstance(raw_candidates, list)
        else []
    )
    selected_limit = max(1, min(limit, 8, len(candidates)))
    source_tokens = _source_tokens(source_input)
    candidate_count = len(candidates)
    scored: list[tuple[float, str, dict[str, Any]]] = []
    for original_rank, candidate in enumerate(candidates, start=1):
        chunk_id = str(candidate.get("chunk_id") or f"rank-{original_rank}")
        chunk_tokens = _chunk_tokens(candidate)
        overlap = _matching_signals(source_tokens, chunk_tokens)
        overlap_ratio = len(overlap) / max(len(source_tokens), 1)
        original_rank_score = (
            (candidate_count - original_rank + 1) / max(candidate_count, 1) * 40.0
        )
        lexical_score = min(overlap_ratio * 45.0, 45.0)
        matched_terms = candidate.get("matched_terms")
        matched_terms = matched_terms if isinstance(matched_terms, list) else []
        matched_term_score = min(
            len(
                {
                    token
                    for value in matched_terms
                    for token in _tokens(value)
                    if token in source_tokens
                }
            )
            * 2.5,
            10.0,
        )
        role_score = _ROLE_BOOST.get(str(candidate.get("rag_role") or ""), 0.0)
        provenance = candidate.get("provenance")
        provenance = provenance if isinstance(provenance, dict) else {}
        trust_level = str(provenance.get("trust_level") or "").lower()
        trust_score = 5.0 if trust_level in {"approved", "high", "trusted"} else 0.0
        rerank_score = round(
            original_rank_score
            + lexical_score
            + matched_term_score
            + role_score
            + trust_score,
            4,
        )
        enriched: dict[str, Any] = {
            **candidate,
            "original_rank": original_rank,
            "rerank_score": rerank_score,
            "rerank_matched_signals": sorted(overlap)[:12],
        }
        scored.append((rerank_score, chunk_id, enriched))

    ranked = sorted(scored, key=lambda item: (-item[0], item[1]))
    selected = [item[2] for item in ranked[:selected_limit]]
    reranked: dict[str, Any] = {
        **retrieval,
        "top_k": len(selected),
        "chunks": selected,
        "candidate_top_k": candidate_count,
        "reranking": {
            "method": "deterministic_operational_v1",
            "candidate_count": candidate_count,
            "selected_count": len(selected),
            "source_signal_count": len(source_tokens),
        },
    }
    metadata: dict[str, Any] = {
        "method": "deterministic_operational_v1",
        "candidate_count": candidate_count,
        "selected_count": len(selected),
        "selected_chunk_ids": [item.get("chunk_id") for item in selected],
        "original_ranks": [item.get("original_rank") for item in selected],
    }
    return reranked, metadata


def _source_tokens(source_input: dict[str, Any]) -> set[str]:
    values: list[str] = []

    def visit(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, str(child_key).lower())
            return
        if isinstance(value, list):
            for child in value:
                visit(child, key)
            return
        if isinstance(value, str) and any(signal in key for signal in _SOURCE_SIGNAL_KEYS):
            values.append(value)

    visit(source_input)
    return {
        token
        for value in values
        for token in _tokens(value)
        if token not in _STOPWORDS
    }


def _chunk_tokens(chunk: dict[str, Any]) -> set[str]:
    values = [
        chunk.get("document_title"),
        chunk.get("equipment_type"),
        chunk.get("fault_type"),
        chunk.get("rag_role"),
        chunk.get("section_title"),
        chunk.get("text"),
    ]
    return {
        token
        for value in values
        for token in _tokens(value)
        if token not in _STOPWORDS
    }


def _tokens(value: Any) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_PATTERN.findall(str(value or ""))
        if len(token) >= 2
    }


def _matching_signals(
    source_tokens: set[str],
    chunk_tokens: set[str],
) -> set[str]:
    return {
        source
        for source in source_tokens
        if any(
            source == chunk
            or (min(len(source), len(chunk)) >= 3 and source in chunk)
            or (min(len(source), len(chunk)) >= 3 and chunk in source)
            for chunk in chunk_tokens
        )
    }
