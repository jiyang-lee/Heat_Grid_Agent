from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


ReportJson = dict[str, Any]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_SRC = PROJECT_ROOT / "src"


def enrich_anomaly_input_with_rag(
    input_data: ReportJson,
    *,
    rag_url: str | None = None,
    top_k: int = 5,
    force: bool = False,
) -> ReportJson:
    enriched = dict(input_data)
    ops_evidence = _infer_ops_evidence(enriched)
    card_id = _infer_card_id(enriched, ops_evidence)

    if not ops_evidence or not card_id:
        enriched.setdefault(
            "external_context",
            {
                "status": "missing_required_context",
                "message": "card_id and ops_evidence are required for RAG enrichment.",
            },
        )
        enriched.setdefault("rag_evidence", [])
        return enriched

    if force or not _has_configured_external_context(enriched.get("external_context")):
        enriched["external_context"] = fetch_external_context(
            card_id=card_id,
            ops_evidence=ops_evidence,
            rag_url=rag_url,
            top_k=top_k,
        )

    if force or not enriched.get("rag_evidence"):
        enriched["rag_evidence"] = build_rag_evidence(enriched.get("external_context"))

    if "ops_evidence" not in enriched:
        enriched["ops_evidence"] = ops_evidence
    return enriched


def enrich_daily_input_with_rag(
    input_data: ReportJson,
    *,
    rag_url: str | None = None,
    top_k: int = 5,
    force: bool = False,
) -> ReportJson:
    enriched = dict(input_data)
    priority_cards = _as_list(enriched.get("priority_cards"))
    ops_evidence_list = _as_list(enriched.get("ops_evidence_list"))

    if not ops_evidence_list and _infer_ops_evidence(enriched):
        ops_evidence_list = [_infer_ops_evidence(enriched)]
        enriched["ops_evidence_list"] = ops_evidence_list

    existing_contexts = _as_list(enriched.get("external_context_list"))
    should_fetch = force or not existing_contexts

    if should_fetch:
        external_contexts: list[ReportJson] = []
        for index, ops_evidence in enumerate(ops_evidence_list):
            if not isinstance(ops_evidence, dict):
                continue
            priority_card = priority_cards[index] if index < len(priority_cards) else {}
            card_id = _infer_card_id({"priority_card": priority_card}, ops_evidence)
            if not card_id:
                external_contexts.append(
                    {
                        "status": "missing_card_id",
                        "message": "card_id is required for RAG enrichment.",
                    }
                )
                continue
            external_contexts.append(
                fetch_external_context(
                    card_id=card_id,
                    ops_evidence=ops_evidence,
                    rag_url=rag_url,
                    top_k=top_k,
                )
            )
        enriched["external_context_list"] = external_contexts
    else:
        external_contexts = existing_contexts

    if force or not enriched.get("rag_evidence"):
        enriched["rag_evidence"] = _dedupe_rag_evidence(
            item
            for external_context in external_contexts
            for item in build_rag_evidence(external_context)
        )

    return enriched


def fetch_external_context(
    *,
    card_id: str,
    ops_evidence: ReportJson,
    rag_url: str | None = None,
    top_k: int = 5,
) -> ReportJson:
    _load_project_env()
    effective_url = (rag_url or os.getenv("HEATGRID_RAG_URL") or "").strip().rstrip("/")
    if effective_url:
        return _fetch_external_context_http(
            rag_url=effective_url,
            card_id=card_id,
            ops_evidence=ops_evidence,
            top_k=top_k,
        )
    return _fetch_external_context_local(card_id=card_id, ops_evidence=ops_evidence, top_k=top_k)


def _load_project_env() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key.removeprefix("export ").strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def build_rag_evidence(external_context: Any) -> list[ReportJson]:
    if not isinstance(external_context, dict):
        return []
    retrieval = external_context.get("retrieval")
    if not isinstance(retrieval, dict):
        return []
    chunks = retrieval.get("chunks")
    if not isinstance(chunks, list):
        return []

    evidence: list[ReportJson] = []
    for index, chunk in enumerate(chunks, start=1):
        if not isinstance(chunk, dict):
            continue
        chunk_id = str(chunk.get("chunk_id") or f"chunk-{index}")
        evidence.append(
            {
                "ref_id": f"rag-{chunk_id}",
                "source_type": "rag_document",
                "title": chunk.get("document_title") or chunk.get("section_title") or chunk_id,
                "source_id": chunk_id,
                "uri": chunk.get("download_url") or chunk.get("source_file") or chunk.get("curated_file"),
                "excerpt": chunk.get("text"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "rag_role": chunk.get("rag_role"),
                "score": chunk.get("score"),
                "matched_terms": chunk.get("matched_terms") or [],
            }
        )
    return evidence


def _fetch_external_context_http(
    *,
    rag_url: str,
    card_id: str,
    ops_evidence: ReportJson,
    top_k: int,
) -> ReportJson:
    payload = json.dumps(
        {"card_id": card_id, "ops_evidence": ops_evidence, "top_k": top_k},
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{rag_url}/external-context",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
        result = json.loads(body)
    except (OSError, URLError, json.JSONDecodeError) as exc:
        fallback = _fetch_external_context_local(card_id=card_id, ops_evidence=ops_evidence, top_k=top_k)
        fallback["http_fallback"] = {
            "status": "unavailable",
            "source": "rag_http_server",
            "message": str(exc),
        }
        return fallback
    if isinstance(result, dict):
        return result
    return {
        "card_id": card_id,
        "status": "invalid_response",
        "source": "rag_http_server",
    }


def _fetch_external_context_local(*, card_id: str, ops_evidence: ReportJson, top_k: int) -> ReportJson:
    if str(PROJECT_SRC) not in sys.path:
        sys.path.insert(0, str(PROJECT_SRC))
    try:
        from heatgrid_rag.search import RagSearcher

        return RagSearcher().external_context(card_id=card_id, evidence=ops_evidence, top_k=top_k)
    except Exception as exc:
        return {
            "card_id": card_id,
            "status": "unavailable",
            "source": "local_rag_searcher",
            "message": str(exc),
        }


def _infer_ops_evidence(input_data: ReportJson) -> ReportJson:
    ops_evidence = input_data.get("ops_evidence")
    if isinstance(ops_evidence, dict):
        return ops_evidence
    if "raw_context" in input_data and "priority_context" in input_data:
        return {
            "raw_context": input_data.get("raw_context") or {},
            "priority_context": input_data.get("priority_context") or {},
            "internal_context": input_data.get("internal_context") or {},
        }
    return {}


def _infer_card_id(input_data: ReportJson, ops_evidence: ReportJson) -> str | None:
    candidates = [
        input_data.get("card_id"),
        _get_path(input_data, "priority_card.card_id"),
        _get_path(input_data, "report_context.source_card_id"),
        _get_path(ops_evidence, "priority_context.card.card_id"),
        _get_path(ops_evidence, "raw_context.card.card_id"),
        _get_path(ops_evidence, "card_id"),
    ]
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _get_path(data: Any, dotted_path: str) -> Any:
    current = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _has_configured_external_context(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    status = str(value.get("status") or "").strip()
    return bool(status and status not in {"external_context_not_configured", "not_configured"})


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe_rag_evidence(items: Any) -> list[ReportJson]:
    seen: set[str] = set()
    result: list[ReportJson] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("source_id") or item.get("ref_id") or "")
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
