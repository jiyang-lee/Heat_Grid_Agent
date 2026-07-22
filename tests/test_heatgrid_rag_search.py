import json
from pathlib import Path
from typing import Any

import pytest

from heatgrid_rag.pgstore import PgVectorStore
from heatgrid_rag.search import RagSearcher


class FakeCursor:
    def __init__(self) -> None:
        self.query_count = 0

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def execute(self, query: str) -> None:
        self.query_count += 1

    def fetchone(self) -> tuple[int] | tuple[None, None]:
        if self.query_count == 1:
            return (1,)
        return (None, None)


class FakeConnection:
    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor()


class FakePsycopg:
    def connect(self, database_url: str, connect_timeout: int) -> FakeConnection:
        return FakeConnection()


def test_pgvector_store_is_unavailable_when_required_tables_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = PgVectorStore(database_url="postgresql://example")
    monkeypatch.setattr(store, "_psycopg", FakePsycopg())

    assert store.available is False


def test_pgvector_health_does_not_query_legacy_run_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries: list[str] = []

    class HealthCursor(FakeCursor):
        def execute(self, query: str) -> None:
            queries.append(query)
            super().execute(query)

        def fetchall(self) -> list[tuple[str, int]]:
            return [("internal", 1)]

        def fetchone(self) -> tuple[int] | tuple[None, None]:
            if self.query_count in {1, 3}:
                return (1,)
            return (None, None)

    class HealthConnection(FakeConnection):
        def cursor(self) -> HealthCursor:
            return HealthCursor()

    class HealthPsycopg(FakePsycopg):
        def connect(self, database_url: str, connect_timeout: int) -> HealthConnection:
            return HealthConnection()

    store = PgVectorStore(database_url="postgresql://example")
    monkeypatch.setattr(store, "_psycopg", HealthPsycopg())

    result = store.health()

    assert result["status"] == "ok"
    assert "ops_agent_runs" not in " ".join(queries)
    assert "run_count" not in result


def test_rag_run_logging_uses_jsonl_after_legacy_tables_are_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEATGRID_RAG_BACKEND", "jsonl")
    monkeypatch.setattr("heatgrid_rag.pgstore.ROOT", tmp_path)
    searcher = RagSearcher(
        chunks_path=tmp_path / "chunks.jsonl",
        site_context_path=tmp_path / "missing.csv",
    )

    logged = searcher.log_agent_run({"run_id": "legacy-free-run"})
    listed = searcher.recent_runs()

    assert logged["status"] == "local_logged"
    assert listed["status"] == "local_logged"
    assert listed["runs"] == [{"run_id": "legacy-free-run"}]


def test_jsonl_search_excludes_historical_external_evidence_before_ranking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    site_context_path = tmp_path / "missing.csv"
    chunks = [
        {
            "chunk_id": "internal",
            "document_id": "internal-doc",
            "document_title": "Internal procedure",
            "document_type": "internal_rag",
            "source_type": "internal_manual",
            "text": "pressure inspection procedure",
        },
        {
            "chunk_id": "manual",
            "document_id": "manual-doc",
            "document_title": "Operator manual",
            "document_type": "operator_manual_evidence",
            "text": "pressure inspection procedure",
        },
        {
            "chunk_id": "external-type",
            "document_id": "external-type-doc",
            "document_title": "External search result",
            "document_type": "external_search",
            "text": "pressure inspection procedure",
        },
        {
            "chunk_id": "web-source",
            "document_id": "web-source-doc",
            "document_title": "Web result",
            "source_type": "web",
            "text": "pressure inspection procedure",
        },
        {
            "chunk_id": "external-origin",
            "document_id": "external-origin-doc",
            "document_title": "Historical result",
            "metadata": {"origin": "external_search"},
            "text": "pressure inspection procedure",
        },
        {
            "chunk_id": "external-query",
            "document_id": "external-query-doc",
            "document_title": "Queried result",
            "query": "pressure inspection",
            "text": "pressure inspection procedure",
        },
    ]
    chunks_path.write_text(
        "\n".join(json.dumps(chunk) for chunk in chunks),
        encoding="utf-8",
    )
    monkeypatch.setenv("HEATGRID_RAG_BACKEND", "jsonl")
    monkeypatch.setattr("heatgrid_rag.search.ROOT", tmp_path)

    result = RagSearcher(
        chunks_path=chunks_path,
        site_context_path=site_context_path,
    ).search("pressure inspection", top_k=20)

    assert {chunk["chunk_id"] for chunk in result["chunks"]} == {
        "internal",
        "manual",
    }
    assert {chunk["document_type"] for chunk in result["chunks"]} == {
        "internal_rag",
        "operator_manual_evidence",
    }
