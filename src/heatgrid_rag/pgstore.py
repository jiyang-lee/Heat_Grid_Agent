from __future__ import annotations

import json
import os
import uuid
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


def _to_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_usage(usage: dict[str, Any] | None) -> dict[str, int | None]:
    if not isinstance(usage, dict):
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    return {
        "input_tokens": _to_int(usage.get("input_tokens")),
        "output_tokens": _to_int(usage.get("output_tokens")),
        "total_tokens": _to_int(usage.get("total_tokens")),
    }


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
                    rag_chunks, site_context = cur.fetchone()
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
                    chunk_count = int(cur.fetchone()[0])
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
                    site_count = int(cur.fetchone()[0])
                    cur.execute("select count(*) from ops_agent_runs")
                    run_count = int(cur.fetchone()[0])
            return {
                "status": "ok",
                "chunk_count": chunk_count,
                "site_count": site_count,
                "run_count": run_count,
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
                        chunk_id,
                        document_id,
                        chunk_text,
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
                        1 - (embedding <=> %s::vector) as similarity
                    from rag_chunks
                    where is_active
                    order by embedding <=> %s::vector
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
                similarity,
            ) = row
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "document_title": document_id,
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

    def insert_agent_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._psycopg is None:
            return {"status": "missing_dependency", "message": "psycopg is not installed"}

        output = payload.get("output") if isinstance(payload.get("output"), dict) else {}
        external_context = payload.get("external_context") if isinstance(payload.get("external_context"), dict) else {}
        evidence = payload.get("ops_evidence") if isinstance(payload.get("ops_evidence"), dict) else {}
        row_identifier = payload.get("row_identifier") if isinstance(payload.get("row_identifier"), dict) else {}
        usage_payload = payload.get("openai_usage") if isinstance(payload.get("openai_usage"), dict) else {}
        usage = _parse_usage(usage_payload.get("usage") if isinstance(usage_payload.get("usage"), dict) else None)
        site = external_context.get("site") if isinstance(external_context.get("site"), dict) else {}
        decision = output.get("decision") if isinstance(output.get("decision"), dict) else {}
        output_evidence = output.get("evidence") if isinstance(output.get("evidence"), dict) else {}
        validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
        run_id = str(payload.get("run_id") or uuid.uuid4())
        substation_id = _to_int(row_identifier.get("substation_id") or site.get("substation_id"))

        with self._psycopg.connect(self.database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into ops_agent_runs (
                        run_id, card_id, window_id, substation_id, apartment_name,
                        window_start, window_end, priority, suspected_type, summary,
                        action_plan, caution, model_name, prompt_version,
                        input_tokens, output_tokens, total_tokens, latency_ms,
                        validation_ok, status, output_json, external_context_json, validation_json
                    )
                    values (
                        %s::uuid, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s::jsonb, %s::jsonb, %s::jsonb
                    )
                    on conflict (run_id) do update set
                        summary = excluded.summary,
                        action_plan = excluded.action_plan,
                        caution = excluded.caution,
                        output_json = excluded.output_json,
                        external_context_json = excluded.external_context_json,
                        validation_json = excluded.validation_json
                    """,
                    (
                        run_id,
                        payload.get("card_id"),
                        payload.get("window_id"),
                        substation_id,
                        site.get("apartment_name"),
                        row_identifier.get("window_start"),
                        row_identifier.get("window_end"),
                        decision.get("priority"),
                        output_evidence.get("m1_specialist"),
                        output.get("summary"),
                        json.dumps(output.get("action_plan") or [], ensure_ascii=False),
                        json.dumps(output.get("caution") or [], ensure_ascii=False),
                        usage_payload.get("model"),
                        payload.get("prompt_version"),
                        usage["input_tokens"],
                        usage["output_tokens"],
                        usage["total_tokens"],
                        _to_int(payload.get("latency_ms")),
                        bool(validation.get("valid")) if "valid" in validation else None,
                        "ok",
                        json.dumps(output, ensure_ascii=False),
                        json.dumps(external_context, ensure_ascii=False),
                        json.dumps(validation, ensure_ascii=False),
                    ),
                )

                for rank, chunk in enumerate(external_context.get("retrieval", {}).get("chunks", []) or [], start=1):
                    cur.execute(
                        """
                        insert into ops_retrieval_hits (
                            run_id, chunk_id, rank, score, document_type,
                            rag_role, equipment_type, fault_type
                        )
                        values (%s::uuid, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            run_id,
                            chunk.get("chunk_id"),
                            rank,
                            chunk.get("score"),
                            chunk.get("document_title"),
                            chunk.get("rag_role"),
                            chunk.get("equipment_type"),
                            chunk.get("fault_type"),
                        ),
                    )

                for tool_name in output_evidence.get("used_tools") or []:
                    cur.execute(
                        """
                        insert into ops_tool_calls (
                            run_id, tool_name, tool_input, tool_output_summary, success
                        )
                        values (%s::uuid, %s, '{}'::jsonb, %s::jsonb, true)
                        """,
                        (
                            run_id,
                            tool_name,
                            json.dumps({"card_id": payload.get("card_id")}, ensure_ascii=False),
                        ),
                    )
            conn.commit()

        return {"status": "ok", "run_id": run_id, "backend": "pgvector"}

    def recent_runs(self, limit: int = 20) -> dict[str, Any]:
        if self._psycopg is None:
            return {"status": "missing_dependency", "runs": []}
        with self._psycopg.connect(self.database_url, connect_timeout=5) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select run_id::text, card_id, substation_id, apartment_name, priority,
                           suspected_type, summary, total_tokens, latency_ms, created_at
                    from ops_agent_runs
                    order by created_at desc
                    limit %s
                    """,
                    (max(1, min(int(limit or 20), 100)),),
                )
                rows = cur.fetchall()
        return {
            "status": "ok",
            "runs": [
                {
                    "run_id": row[0],
                    "card_id": row[1],
                    "substation_id": row[2],
                    "apartment_name": row[3],
                    "priority": row[4],
                    "suspected_type": row[5],
                    "summary": row[6],
                    "total_tokens": row[7],
                    "latency_ms": row[8],
                    "created_at": row[9].isoformat() if row[9] else None,
                }
                for row in rows
            ],
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
