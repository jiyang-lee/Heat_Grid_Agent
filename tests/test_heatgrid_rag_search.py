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
