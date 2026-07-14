from __future__ import annotations

import os
from typing import Final

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from heatgrid_rag.embedding import hash_embedding, vector_literal
from heatgrid_rag.pgstore import PgVectorStore


DATABASE_URL: Final = os.getenv("HEATGRID_V3_REVIEW_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="HEATGRID_V3_REVIEW_TEST_DATABASE_URL is required",
)


@pytest.mark.anyio
async def test_pgvector_result_preserves_manual_evidence_provenance() -> None:
    engine = create_async_engine(str(DATABASE_URL))
    try:
        embedding = vector_literal(hash_embedding("operator manual"))
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO rag_documents ("
                    "document_id, title, document_type, source_path, source_owner"
                    ") VALUES ("
                    "'review-manual-doc', 'Operator manual', "
                    "'operator_manual_evidence', 'manual.pdf', 'operations'"
                    ") ON CONFLICT (document_id) DO NOTHING"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO rag_chunks ("
                    "chunk_id, document_id, chunk_text, section_title, embedding"
                    ") VALUES ("
                    "'review-manual-chunk', 'review-manual-doc', "
                    "'operator manual evidence', 'Inspection', CAST(:embedding AS vector)"
                    ") ON CONFLICT (chunk_id) DO NOTHING"
                ),
                {"embedding": embedding},
            )

        result = PgVectorStore(str(DATABASE_URL)).search_chunks(
            "operator manual", top_k=1
        )
        chunk = result["chunks"][0]

        assert chunk["document_type"] == "operator_manual_evidence"
        assert chunk["source_owner"] == "operations"
        assert chunk["document_title"] == "Operator manual"
        assert chunk["provenance"]["document_id"] == "review-manual-doc"
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM rag_documents WHERE document_id = 'review-manual-doc'")
            )
        await engine.dispose()


@pytest.mark.anyio
async def test_pgvector_search_excludes_historical_external_evidence() -> None:
    engine = create_async_engine(str(DATABASE_URL))
    document_ids = (
        "review-internal-doc",
        "review-manual-filter-doc",
        "review-external-type-doc",
        "review-web-type-doc",
        "review-external-origin-doc",
        "review-external-source-doc",
        "review-external-query-doc",
    )
    try:
        embedding = vector_literal(hash_embedding("review filter marker"))
        documents = (
            (document_ids[0], "internal_rag", "{}"),
            (document_ids[1], "operator_manual_evidence", "{}"),
            (document_ids[2], "external_search", "{}"),
            (document_ids[3], "web", "{}"),
            (document_ids[4], "internal_rag", '{"origin":"external_search"}'),
            (document_ids[5], "internal_rag", '{"source_type":"web"}'),
            (document_ids[6], "internal_rag", '{"query":"review filter marker"}'),
        )
        async with engine.begin() as connection:
            for document_id, document_type, metadata in documents:
                await connection.execute(
                    text(
                        "INSERT INTO rag_documents ("
                        "document_id, title, document_type, metadata"
                        ") VALUES ("
                        ":document_id, :document_id, :document_type, "
                        "CAST(:metadata AS jsonb)"
                        ") ON CONFLICT (document_id) DO UPDATE SET "
                        "document_type = EXCLUDED.document_type, "
                        "metadata = EXCLUDED.metadata, is_active = true"
                    ),
                    {
                        "document_id": document_id,
                        "document_type": document_type,
                        "metadata": metadata,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO rag_chunks ("
                        "chunk_id, document_id, chunk_text, embedding"
                        ") VALUES ("
                        ":chunk_id, :document_id, 'review filter marker', "
                        "CAST(:embedding AS vector)"
                        ") ON CONFLICT (chunk_id) DO UPDATE SET "
                        "chunk_text = EXCLUDED.chunk_text, "
                        "embedding = EXCLUDED.embedding, is_active = true"
                    ),
                    {
                        "chunk_id": f"{document_id}-chunk",
                        "document_id": document_id,
                        "embedding": embedding,
                    },
                )

        result = PgVectorStore(str(DATABASE_URL)).search_chunks(
            "review filter marker",
            top_k=20,
        )

        returned_ids = {
            chunk["document_id"]
            for chunk in result["chunks"]
            if str(chunk["document_id"]).startswith("review-")
        }
        assert returned_ids == {document_ids[0], document_ids[1]}
    finally:
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM rag_documents WHERE document_id = ANY(:document_ids)"),
                {"document_ids": list(document_ids)},
            )
        await engine.dispose()
