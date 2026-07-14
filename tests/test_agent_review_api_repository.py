from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys
from typing import Final

import pytest


ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))


def test_agent_run_cursor_round_trips_created_at_and_run_id() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.agent_run_listing_repository import (
        AgentRunCursor,
    )

    cursor = AgentRunCursor(
        created_at=datetime(2026, 7, 14, 3, 4, 5, tzinfo=UTC),
        run_id="00000000-0000-0000-0000-000000000002",
    )

    encoded = cursor.encode()
    decoded = AgentRunCursor.decode(encoded)

    assert decoded == cursor
    assert "+" not in encoded
    assert "/" not in encoded


@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64!",
        "e30",
        "eyJjcmVhdGVkX2F0IjoieCIsInJ1bl9pZCI6InkifQ",
    ],
)
def test_agent_run_cursor_rejects_malformed_payload(cursor: str) -> None:
    from simulator.versions.v2_postgres_react_ops.backend.agent_run_listing_repository import (
        AgentRunCursor,
        AgentRunCursorError,
    )

    with pytest.raises(AgentRunCursorError):
        AgentRunCursor.decode(cursor)


def test_rag_pg_query_selects_review_provenance() -> None:
    source = (ROOT / "src" / "heatgrid_rag" / "pgstore.py").read_text(
        encoding="utf-8"
    )

    assert "join rag_documents" in source.lower()
    assert "document_type" in source
    assert "source_owner" in source
    assert '"provenance"' in source


def test_agent_review_migration_adds_run_list_indexes_conditionally() -> None:
    source = (
        ROOT / "docker" / "postgres" / "init" / "005_agent_review.sql"
    ).read_text(encoding="utf-8").lower()

    assert "agent_runs_v3_list_idx" in source
    assert "agent_run_tasks_v3_worker_idx" in source
    assert "agent_run_events_v3_snapshot_idx" in source
    assert "to_regclass('public.agent_runs') is not null" in source


def test_operations_metrics_query_qualifies_worker_status_filters() -> None:
    source = (
        ROOT
        / "simulator"
        / "versions"
        / "v2_postgres_react_ops"
        / "backend"
        / "agent_operations_metrics_repository.py"
    ).read_text(encoding="utf-8")

    assert "WHERE worker.worker_status = 'completed'" in source
    assert "WHERE worker.worker_status = 'timeout'" in source
    assert "WHERE worker.worker_status = 'invalid'" in source
    assert "WHERE worker.worker_status = 'budget_exceeded'" in source
    assert "WHERE worker_status =" not in source
