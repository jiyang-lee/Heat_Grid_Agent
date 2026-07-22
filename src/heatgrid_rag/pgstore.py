from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .embedding import hash_embedding, vector_literal


ROOT = Path(__file__).resolve().parents[2]


def truncate_text(value: Any, max_length: int = 1200) -> str:
    text = str(value or "").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1].rstrip()}..."


DEFAULT_DATABASE_URL = "postgresql://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops"


def normalize_database_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def database_url_from_env() -> str:
    raw_url = os.getenv("HEATGRID_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
    return normalize_database_url(raw_url)


def _psycopg():
    try:
        import psycopg  # type: ignore
    except ImportError:
        return None
    return psycopg


class PgVectorStore:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = normalize_database_url(database_url) if database_url else database_url_from_env()
        self._psycopg = _psycopg()

    @property
    def available(self) -> bool:
        if self._psycopg is None:
            return False
        try:
            with self._psycopg.connect(self.database_url, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("select 1")
                    cur.fetchone()
                    cur.execute(
                        "select to_regclass('public.rag_chunks'), "
                        "to_regclass('public.substation_building_context')"
                    )
                    schema_row = cur.fetchone()
                    if schema_row is None:
                        return False
                    rag_chunks, site_context = schema_row
                    return rag_chunks is not None and site_context is not None
        except Exception:
            return False

    def health(self) -> dict[str, Any]:
        if self._psycopg is None:
            return {
                "status": "missing_dependency",
                "message": "psycopg is not installed",
            }
        try:
            with self._psycopg.connect(self.database_url, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("select count(*) from rag_chunks where is_active")
                    chunk_row = cur.fetchone()
                    chunk_count = 0 if chunk_row is None else int(chunk_row[0])
                    cur.execute(
                        """
                        select coalesce(rag_role, 'unknown'), count(*)
                        from rag_chunks
                        where is_active
                        group by 1
                        order by 1
                        """
                    )
                    roles = {str(role): int(count) for role, count in cur.fetchall()}
                    cur.execute("select count(*) from substation_building_context")
                    site_row = cur.fetchone()
                    site_count = 0 if site_row is None else int(site_row[0])
            return {
                "status": "ok",
                "chunk_count": chunk_count,
                "site_count": site_count,
                "roles": roles,
            }
        except Exception as exc:
            return {
                "status": "unavailable",
                "message": str(exc),
            }

    def search_chunks(self, query: str, top_k: int = 5) -> dict[str, Any]:
        if self._psycopg is None:
            raise RuntimeError("psycopg is not installed")
        embedding = vector_literal(hash_embedding(query))
        with self._psycopg.connect(self.database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                        chunks.chunk_id,
                        chunks.document_id,
                        chunks.chunk_text,
                        chunks.section_title,
                        chunks.rag_role,
                        chunks.language,
                        chunks.source_file,
                        chunks.curated_file,
                        chunks.page_start,
                        chunks.page_end,
                        chunks.download_url,
                        chunks.equipment_type,
                        chunks.fault_type,
                        chunks.risk_level,
                        documents.title,
                        documents.document_type,
                        documents.source_path,
                        documents.source_owner,
                        documents.version,
                        documents.trust_level,
                        1 - (chunks.embedding <=> %s::vector) as similarity
                    from rag_chunks chunks
                    join rag_documents documents
                      on documents.document_id = chunks.document_id
                    where chunks.is_active and documents.is_active
                      and lower(coalesce(documents.document_type, ''))
                          not in ('external_search', 'web')
                      and lower(coalesce(documents.metadata->>'source_type', ''))
                          not in ('external_search', 'web')
                      and lower(coalesce(documents.metadata->>'origin', ''))
                          <> 'external_search'
                      and not (
                          documents.metadata ? 'query'
                          and documents.metadata->'query' <> 'null'::jsonb
                      )
                      and lower(coalesce(chunks.metadata->>'source_type', ''))
                          not in ('external_search', 'web')
                      and lower(coalesce(chunks.metadata->>'origin', ''))
                          <> 'external_search'
                      and not (
                          chunks.metadata ? 'query'
                          and chunks.metadata->'query' <> 'null'::jsonb
                      )
                    order by chunks.embedding <=> %s::vector
                    limit %s
                    """,
                    (embedding, embedding, max(1, min(int(top_k or 5), 20))),
                )
                rows = cur.fetchall()

        chunks = []
        for row in rows:
            (
                chunk_id,
                document_id,
                text,
                section_title,
                rag_role,
                language,
                source_file,
                curated_file,
                page_start,
                page_end,
                download_url,
                equipment_type,
                fault_type,
                risk_level,
                document_title,
                source_document_type,
                source_path,
                source_owner,
                document_version,
                trust_level,
                similarity,
            ) = row
            document_type = (
                "operator_manual_evidence"
                if source_document_type == "operator_manual_evidence"
                else "internal_rag"
            )
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "document_title": document_title,
                    "document_type": document_type,
                    "source_owner": source_owner,
                    "source_file": source_file,
                    "curated_file": curated_file,
                    "rag_role": rag_role,
                    "language": language,
                    "page_start": page_start,
                    "page_end": page_end,
                    "section_title": section_title,
                    "download_url": download_url,
                    "equipment_type": equipment_type,
                    "fault_type": fault_type,
                    "risk_level": risk_level,
                    "score": round(float(similarity or 0) * 1000, 3),
                    "matched_terms": [],
                    "text": truncate_text(text),
                    "provenance": {
                        "backend": "pgvector",
                        "document_id": document_id,
                        "chunk_id": chunk_id,
                        "document_type": source_document_type,
                        "source_path": source_path,
                        "source_owner": source_owner,
                        "document_version": document_version,
                        "trust_level": trust_level,
                    },
                }
            )
        return {
            "status": "available" if chunks else "no_match",
            "source": "rag_http_server",
            "backend": "pgvector",
            "query": query,
            "top_k": len(chunks),
            "chunks": chunks,
        }

def append_local_run_log(payload: dict[str, Any]) -> dict[str, Any]:
    log_dir = ROOT / "output" / "ops_agent" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "ops_agent_runs.jsonl"
    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return {
        "status": "local_logged",
        "path": str(log_path.relative_to(ROOT)),
    }


def recent_local_run_logs(limit: int = 20) -> dict[str, Any]:
    log_path = ROOT / "output" / "ops_agent" / "logs" / "ops_agent_runs.jsonl"
    if not log_path.exists():
        return {"status": "local_logged", "runs": []}

    runs: list[dict[str, Any]] = []
    for line in reversed(log_path.read_text(encoding="utf-8").splitlines()):
        if len(runs) >= max(1, min(int(limit or 20), 100)):
            break
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            runs.append(payload)
    return {"status": "local_logged", "runs": runs}
