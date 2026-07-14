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
