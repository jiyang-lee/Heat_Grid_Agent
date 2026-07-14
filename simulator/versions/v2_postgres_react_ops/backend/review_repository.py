from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Final
from uuid import uuid4

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from agent_operator_review_repository import ReviewRecordInput, record_review
from heatgrid_rag.embedding import hash_embedding, vector_literal
from schemas import (
    AutomationPolicy,
    AutomationPolicyUpdateRequest,
    EvidenceCandidate,
    EvidenceCandidateCreateRequest,
    EvidenceCandidateReviewRequest,
    HumanReviewTask,
    ReviewSubmitResponse,
    ReviewTaskSubmitRequest,
    TrainingFeedback,
)

EVIDENCE_CANDIDATES_DDL: Final = """
CREATE TABLE IF NOT EXISTS evidence_candidates (
    candidate_id uuid PRIMARY KEY,
    run_id uuid,
    source_type text NOT NULL,
    source_uri text,
    title text NOT NULL,
    content text NOT NULL,
    query text,
    risk_level text NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    trust_score double precision NOT NULL CHECK (trust_score >= 0 AND trust_score <= 1),
    status text NOT NULL CHECK (
        status IN ('pending', 'auto_approved', 'approved', 'rejected', 'ingest_failed')
    ),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    requested_by text NOT NULL,
    reviewed_by text,
    review_reason text,
    rag_document_id text,
    rag_chunk_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz
)
"""

HUMAN_REVIEW_TASKS_DDL: Final = """
CREATE TABLE IF NOT EXISTS human_review_tasks (
    task_id uuid PRIMARY KEY,
    task_type text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('pending', 'auto_approved', 'approved', 'rejected', 'corrected', 'cancelled')
    ),
    risk_level text NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    title text NOT NULL,
    run_id uuid,
    candidate_id uuid REFERENCES evidence_candidates(candidate_id) ON DELETE SET NULL,
    retrain_job_id uuid,
    model_candidate_id uuid,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    resolution jsonb NOT NULL DEFAULT '{}'::jsonb,
    assigned_to text,
    reviewed_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz
)
"""

TRAINING_FEEDBACK_DDL: Final = """
CREATE TABLE IF NOT EXISTS training_feedback (
    feedback_id uuid PRIMARY KEY,
    task_id uuid NOT NULL REFERENCES human_review_tasks(task_id) ON DELETE CASCADE,
    run_id uuid,
    card_id uuid,
    reviewer text NOT NULL,
    decision text NOT NULL,
    original_output jsonb NOT NULL DEFAULT '{}'::jsonb,
    corrected_output jsonb NOT NULL DEFAULT '{}'::jsonb,
    corrected_label text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (task_id)
)
"""

AUTOMATION_POLICY_DDL: Final = """
CREATE TABLE IF NOT EXISTS automation_policy (
    policy_id text PRIMARY KEY,
    mode text NOT NULL CHECK (mode IN ('human_only', 'assisted', 'guarded_auto')),
    auto_transition_enabled boolean NOT NULL DEFAULT false,
    minimum_review_count integer NOT NULL DEFAULT 100,
    minimum_approval_rate double precision NOT NULL DEFAULT 0.95,
    minimum_confidence double precision NOT NULL DEFAULT 0.90,
    minimum_source_trust double precision NOT NULL DEFAULT 0.85,
    maximum_drift_score double precision NOT NULL DEFAULT 0.10,
    final_review_required boolean NOT NULL DEFAULT true,
    updated_by text NOT NULL DEFAULT 'system',
    updated_at timestamptz NOT NULL DEFAULT now()
)
"""

AUTOMATION_POLICY_SEED_DDL: Final = """
INSERT INTO automation_policy (policy_id, mode)
VALUES ('default', 'human_only')
ON CONFLICT (policy_id) DO NOTHING
"""

AUTOMATION_INDEX_DDL: Final = (
    "CREATE INDEX IF NOT EXISTS evidence_candidates_status_idx ON evidence_candidates(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS review_tasks_status_idx ON human_review_tasks(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS training_feedback_created_idx ON training_feedback(created_at DESC)",
)


async def ensure_review_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(EVIDENCE_CANDIDATES_DDL))
        await connection.execute(text(HUMAN_REVIEW_TASKS_DDL))
        await connection.execute(text(TRAINING_FEEDBACK_DDL))
        await connection.execute(text(AUTOMATION_POLICY_DDL))
        await connection.execute(text(AUTOMATION_POLICY_SEED_DDL))
        for statement in AUTOMATION_INDEX_DDL:
            await connection.execute(text(statement))


async def create_evidence_candidate(
    engine: AsyncEngine,
    payload: EvidenceCandidateCreateRequest,
    *,
    status: str = "pending",
    candidate_id: str | None = None,
    reviewed_by: str | None = None,
    review_reason: str | None = None,
) -> EvidenceCandidate:
    await ensure_review_tables(engine)
    candidate_id = candidate_id or str(uuid4())
    query = text(
        "INSERT INTO evidence_candidates ("
        "candidate_id, run_id, source_type, source_uri, title, content, query, risk_level, "
        "trust_score, status, metadata, requested_by, reviewed_by, review_reason, reviewed_at"
        ") VALUES ("
        ":candidate_id, :run_id, :source_type, :source_uri, :title, :content, :query, "
        ":risk_level, :trust_score, :status, CAST(:metadata AS jsonb), :requested_by, "
        ":reviewed_by, :review_reason, :reviewed_at"
        ") RETURNING " + _candidate_select_columns()
    )
    params = {
        **payload.model_dump(mode="json"),
        "candidate_id": candidate_id,
        "query": None,
        "status": status,
        "metadata": _json(payload.metadata),
        "reviewed_by": reviewed_by,
        "review_reason": review_reason,
        "reviewed_at": None if reviewed_by is None else datetime.now(timezone.utc),
    }
    async with engine.begin() as connection:
        result = await connection.execute(query, params)
    candidate = _candidate_from_row(result.mappings().one())
    if status == "auto_approved":
        return await ingest_evidence_candidate(engine, candidate.candidate_id)
    return candidate


async def list_evidence_candidates(
    engine: AsyncEngine,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[EvidenceCandidate]:
    await ensure_review_tables(engine)
    where = "WHERE status = :status" if status else ""
    query = text(
        f"SELECT {_candidate_select_columns()} FROM evidence_candidates {where} "
        "ORDER BY created_at DESC LIMIT :limit"
    )
    async with engine.connect() as connection:
        result = await connection.execute(
            query,
            {"status": status, "limit": max(1, min(limit, 500))},
        )
    return [_candidate_from_row(row) for row in result.mappings().all()]


async def get_evidence_candidate(
    engine: AsyncEngine,
    candidate_id: str,
) -> EvidenceCandidate | None:
    await ensure_review_tables(engine)
    query = text(
        f"SELECT {_candidate_select_columns()} FROM evidence_candidates "
        "WHERE candidate_id = :candidate_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"candidate_id": candidate_id})
    row = result.mappings().one_or_none()
    return None if row is None else _candidate_from_row(row)


async def review_evidence_candidate(
    engine: AsyncEngine,
    candidate_id: str,
    payload: EvidenceCandidateReviewRequest,
) -> EvidenceCandidate | None:
    await ensure_review_tables(engine)
    existing = await get_evidence_candidate(engine, candidate_id)
    if existing is not None and _is_historical_external_candidate(existing):
        raise ValueError("외부 검색 근거는 과거 기록 조회만 허용됩니다.")
    status = "approved" if payload.decision == "approve" else "rejected"
    query = text(
        "UPDATE evidence_candidates SET status = :status, reviewed_by = :reviewer, "
        "review_reason = :reason, trust_score = COALESCE(:trust_score, trust_score), "
        "reviewed_at = now() WHERE candidate_id = :candidate_id "
        "RETURNING " + _candidate_select_columns()
    )
    async with engine.begin() as connection:
        result = await connection.execute(
            query,
            {
                "candidate_id": candidate_id,
                "status": status,
                "reviewer": payload.reviewer,
                "reason": payload.reason,
                "trust_score": payload.trust_score,
            },
        )
        row = result.mappings().one_or_none()
        if row is not None:
            await connection.execute(
                text(
                    "UPDATE human_review_tasks SET status = :task_status, "
                    "reviewed_by = :reviewer, reviewed_at = now(), "
                    "resolution = CAST(:resolution AS jsonb) "
                    "WHERE candidate_id = :candidate_id AND status = 'pending'"
                ),
                {
                    "candidate_id": candidate_id,
                    "task_status": status,
                    "reviewer": payload.reviewer,
                    "resolution": _json(payload.model_dump(mode="json")),
                },
            )
    if row is None:
        return None
    if status == "approved":
        return await ingest_evidence_candidate(engine, candidate_id)
    return _candidate_from_row(row)


async def ingest_evidence_candidate(
    engine: AsyncEngine,
    candidate_id: str,
) -> EvidenceCandidate:
    candidate = await get_evidence_candidate(engine, candidate_id)
    if candidate is None:
        raise ValueError("candidate_id를 찾을 수 없습니다.")
    if _is_historical_external_candidate(candidate):
        raise ValueError("외부 검색 근거는 RAG에 적재할 수 없습니다.")
    document_id = f"approved-evidence-{candidate.candidate_id}"
    chunk_id = f"approved-evidence-{candidate.candidate_id}-001"
    embedding = vector_literal(
        hash_embedding(f"{candidate.title}\n{candidate.content}")
    )
    metadata = {
        **candidate.metadata,
        "candidate_id": candidate.candidate_id,
        "approved_by": candidate.reviewed_by,
        "approval_status": candidate.status,
    }
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO rag_documents ("
                    "document_id, title, document_type, source_path, source_owner, "
                    "trust_level, metadata"
                    ") VALUES ("
                    ":document_id, :title, 'operator_manual_evidence', :source_path, "
                    ":source_owner, :trust_level, CAST(:metadata AS jsonb)"
                    ") ON CONFLICT (document_id) DO UPDATE SET "
                    "title = EXCLUDED.title, source_path = EXCLUDED.source_path, "
                    "source_owner = EXCLUDED.source_owner, trust_level = EXCLUDED.trust_level, "
                    "metadata = EXCLUDED.metadata, is_active = true, updated_at = now()"
                ),
                {
                    "document_id": document_id,
                    "title": candidate.title,
                    "source_path": candidate.source_uri,
                    "source_owner": candidate.reviewed_by,
                    "trust_level": _trust_level(candidate.trust_score),
                    "metadata": _json(metadata),
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO rag_chunks ("
                    "chunk_id, document_id, chunk_text, chunk_order, section_title, rag_role, "
                    "language, source_file, curated_file, download_url, embedding, "
                    "embedding_source, metadata"
                    ") VALUES ("
                    ":chunk_id, :document_id, :content, 1, :title, 'fault_case_history', "
                    "'ko', :source_file, :curated_file, :download_url, CAST(:embedding AS vector), "
                    "'hash-v1', CAST(:metadata AS jsonb)"
                    ") ON CONFLICT (chunk_id) DO UPDATE SET "
                    "chunk_text = EXCLUDED.chunk_text, embedding = EXCLUDED.embedding, "
                    "metadata = EXCLUDED.metadata, is_active = true, updated_at = now()"
                ),
                {
                    "chunk_id": chunk_id,
                    "document_id": document_id,
                    "content": candidate.content,
                    "title": candidate.title,
                    "source_file": candidate.source_uri,
                    "curated_file": f"db/manual_evidence/{candidate.candidate_id}.json",
                    "download_url": candidate.source_uri,
                    "embedding": embedding,
                    "metadata": _json(metadata),
                },
            )
            await connection.execute(
                text(
                    "UPDATE evidence_candidates SET rag_document_id = :document_id, "
                    "rag_chunk_id = :chunk_id WHERE candidate_id = :candidate_id"
                ),
                {
                    "candidate_id": candidate_id,
                    "document_id": document_id,
                    "chunk_id": chunk_id,
                },
            )
    except (SQLAlchemyError, OSError, ValueError):
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE evidence_candidates SET status = 'ingest_failed' "
                    "WHERE candidate_id = :candidate_id"
                ),
                {"candidate_id": candidate_id},
            )
    updated = await get_evidence_candidate(engine, candidate_id)
    if updated is None:
        raise RuntimeError("근거 후보 상태를 다시 읽을 수 없습니다.")
    return updated


async def create_review_task(
    engine: AsyncEngine,
    *,
    task_type: str,
    risk_level: str,
    title: str,
    payload: dict[str, object],
    status: str = "pending",
    run_id: str | None = None,
    candidate_id: str | None = None,
    retrain_job_id: str | None = None,
    model_candidate_id: str | None = None,
    assigned_to: str | None = None,
    reviewed_by: str | None = None,
    task_id: str | None = None,
    operation_key: str | None = None,
) -> HumanReviewTask:
    if task_type == "external_search":
        raise ValueError("외부 검색 승인 작업은 새로 만들 수 없습니다.")
    await ensure_review_tables(engine)
    task_id = task_id or str(uuid4())
    query = text(
        "INSERT INTO human_review_tasks ("
        "task_id, task_type, status, risk_level, title, run_id, candidate_id, "
        "retrain_job_id, model_candidate_id, payload, assigned_to, reviewed_by, reviewed_at, "
        "operation_key"
        ") VALUES ("
        ":task_id, :task_type, :status, :risk_level, :title, :run_id, :candidate_id, "
        ":retrain_job_id, :model_candidate_id, CAST(:payload AS jsonb), :assigned_to, "
        ":reviewed_by, :reviewed_at, :operation_key"
        ") ON CONFLICT (operation_key) WHERE operation_key IS NOT NULL DO UPDATE SET "
        "operation_key = EXCLUDED.operation_key RETURNING " + _review_select_columns()
    )
    async with engine.begin() as connection:
        result = await connection.execute(
            query,
            {
                "task_id": task_id,
                "task_type": task_type,
                "status": status,
                "risk_level": risk_level,
                "title": title,
                "run_id": run_id,
                "candidate_id": candidate_id,
                "retrain_job_id": retrain_job_id,
                "model_candidate_id": model_candidate_id,
                "payload": _json(payload),
                "assigned_to": assigned_to,
                "reviewed_by": reviewed_by,
                "reviewed_at": None
                if reviewed_by is None
                else datetime.now(timezone.utc),
                "operation_key": operation_key,
            },
        )
    return _review_from_row(result.mappings().one())


async def list_review_tasks(
    engine: AsyncEngine,
    *,
    status: str | None = None,
    task_type: str | None = None,
    limit: int = 100,
) -> list[HumanReviewTask]:
    await ensure_review_tables(engine)
    filters: list[str] = []
    params: dict[str, object] = {"limit": max(1, min(limit, 500))}
    if status:
        filters.append("status = :status")
        params["status"] = status
    if task_type:
        filters.append("task_type = :task_type")
        params["task_type"] = task_type
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    query = text(
        f"SELECT {_review_select_columns()} FROM human_review_tasks {where} "
        "ORDER BY created_at DESC LIMIT :limit"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, params)
    return [_review_from_row(row) for row in result.mappings().all()]


async def get_review_task(
    engine: AsyncEngine,
    task_id: str,
) -> HumanReviewTask | None:
    await ensure_review_tables(engine)
    async with engine.connect() as connection:
        return await _get_review_task(connection, task_id)


async def _get_review_task(
    connection: AsyncConnection,
    task_id: str,
) -> HumanReviewTask | None:
    query = text(
        f"SELECT {_review_select_columns()} FROM human_review_tasks WHERE task_id = :task_id"
    )
    result = await connection.execute(query, {"task_id": task_id})
    row = result.mappings().one_or_none()
    return None if row is None else _review_from_row(row)


async def submit_review_task(
    engine: AsyncEngine,
    task_id: str,
    payload: ReviewTaskSubmitRequest,
) -> ReviewSubmitResponse | None:
    await ensure_review_tables(engine)
    task = await get_review_task(engine, task_id)
    if task is None:
        return None
    if task.task_type == "external_search":
        raise ValueError("외부 검색 승인 작업은 과거 기록 조회만 허용됩니다.")
    if task.status != "pending":
        raise ValueError("이미 처리된 검수 작업입니다.")
    status = {
        "approve": "approved",
        "reject": "rejected",
        "correct": "corrected",
    }[payload.decision]
    resolution = payload.model_dump(mode="json")
    query = text(
        "UPDATE human_review_tasks SET status = :status, reviewed_by = :reviewer, "
        "resolution = CAST(:resolution AS jsonb), reviewed_at = now() "
        "WHERE task_id = :task_id RETURNING " + _review_select_columns()
    )
    async with engine.begin() as connection:
        task = await _get_review_task(connection, task_id)
        if task is None:
            return None
        if task.task_type == "external_search":
            raise ValueError("?몃? 寃???뱀씤 ?묒뾽? 怨쇨굅 湲곕줉 議고쉶留??덉슜?⑸땲??")
        if task.status != "pending":
            raise ValueError("?대? 泥섎━??寃???묒뾽?낅땲??")
        result = await connection.execute(
            query,
            {
                "task_id": task_id,
                "status": status,
                "reviewer": payload.reviewer,
                "resolution": _json(resolution),
            },
        )
        updated = _review_from_row(result.mappings().one())
        feedback = await _insert_feedback(connection, updated, payload)
        if updated.run_id and updated.task_type == "final_output":
            corrected_output = (
                {
                    "summary": payload.corrected_output.summary,
                    "action_plan": payload.corrected_output.action_plan,
                    "caution": payload.corrected_output.caution,
                }
                if payload.corrected_output is not None
                else None
            )
            await connection.execute(
                text(
                    "UPDATE agent_runs SET "
                    "ops_output = COALESCE(CAST(:corrected_output AS jsonb), ops_output), "
                    "updated_at = now() "
                    "WHERE run_id = :run_id"
                ),
                {
                    "run_id": updated.run_id,
                    "corrected_output": None
                    if corrected_output is None
                    else _json(corrected_output),
                },
            )
            await record_review(
                connection,
                _legacy_review_record_input(
                    task=updated,
                    payload=payload,
                    corrected_output=corrected_output,
                ),
            )
    return ReviewSubmitResponse(task=updated, feedback=feedback)


def _legacy_review_record_input(
    *,
    task: HumanReviewTask,
    payload: ReviewTaskSubmitRequest,
    corrected_output: dict[str, str] | None,
) -> ReviewRecordInput:
    match payload.decision:
        case "approve":
            decision = "approve"
            legacy_status_override = None
            operator_labels: tuple[str, ...] = ()
        case "correct":
            decision = "correct"
            legacy_status_override = None
            operator_labels = ()
        case "reject":
            decision = "keep_human_review"
            legacy_status_override = "rejected"
            operator_labels = ("legacy_reject",)
    return ReviewRecordInput(
        run_id=task.run_id or "",
        decision=decision,
        reviewer=payload.reviewer,
        reason=payload.reason or "legacy review task submission",
        idempotency_key=f"legacy-task:{task.task_id}",
        request_hash=_legacy_request_hash(payload),
        disposition=None,
        correction=corrected_output,
        evidence_annotations=(),
        operator_labels=operator_labels,
        legacy_status_override=legacy_status_override,
    )


def _legacy_request_hash(payload: ReviewTaskSubmitRequest) -> str:
    canonical_payload = orjson.dumps(
        payload.model_dump(mode="json"),
        option=orjson.OPT_SORT_KEYS,
    )
    return sha256(canonical_payload).hexdigest()


async def list_training_feedback(
    engine: AsyncEngine,
    *,
    limit: int = 100,
) -> list[TrainingFeedback]:
    await ensure_review_tables(engine)
    query = text(
        f"SELECT {_feedback_select_columns()} FROM training_feedback "
        "ORDER BY created_at DESC LIMIT :limit"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"limit": max(1, min(limit, 500))})
    return [_feedback_from_row(row) for row in result.mappings().all()]


async def get_automation_policy(engine: AsyncEngine) -> AutomationPolicy:
    await ensure_review_tables(engine)
    async with engine.begin() as connection:
        reviewed_count, approved_count = await _feedback_stats(connection)
        result = await connection.execute(
            text(
                "SELECT policy_id, mode, auto_transition_enabled, minimum_review_count, "
                "minimum_approval_rate, minimum_confidence, minimum_source_trust, "
                "maximum_drift_score, final_review_required, updated_by, updated_at "
                "FROM automation_policy WHERE policy_id = 'default'"
            )
        )
        row = result.mappings().one()
        policy = _policy_from_row(row, reviewed_count, approved_count)
        if (
            policy.auto_transition_enabled
            and policy.mode != "guarded_auto"
            and policy.eligible_for_guarded_auto
        ):
            await connection.execute(
                text(
                    "UPDATE automation_policy SET mode = 'guarded_auto', "
                    "updated_by = 'automatic-transition', updated_at = now() "
                    "WHERE policy_id = 'default'"
                )
            )
            result = await connection.execute(
                text(
                    "SELECT policy_id, mode, auto_transition_enabled, minimum_review_count, "
                    "minimum_approval_rate, minimum_confidence, minimum_source_trust, "
                    "maximum_drift_score, final_review_required, updated_by, updated_at "
                    "FROM automation_policy WHERE policy_id = 'default'"
                )
            )
            policy = _policy_from_row(
                result.mappings().one(), reviewed_count, approved_count
            )
    return policy


async def update_automation_policy(
    engine: AsyncEngine,
    payload: AutomationPolicyUpdateRequest,
) -> AutomationPolicy:
    await ensure_review_tables(engine)
    fields = payload.model_dump(exclude_none=True, mode="json")
    updated_by = str(fields.pop("updated_by"))
    assignments = [f"{name} = :{name}" for name in fields]
    assignments.extend(["updated_by = :updated_by", "updated_at = now()"])
    async with engine.begin() as connection:
        await connection.execute(
            text(
                f"UPDATE automation_policy SET {', '.join(assignments)} "
                "WHERE policy_id = 'default'"
            ),
            {**fields, "updated_by": updated_by},
        )
    return await get_automation_policy(engine)


async def resolve_linked_review_tasks(
    engine: AsyncEngine,
    *,
    status: str,
    reviewer: str,
    resolution: dict[str, object],
    retrain_job_id: str | None = None,
    model_candidate_id: str | None = None,
) -> None:
    await ensure_review_tables(engine)
    filters: list[str] = ["status = 'pending'"]
    params: dict[str, object] = {
        "status": status,
        "reviewer": reviewer,
        "resolution": _json(resolution),
    }
    if retrain_job_id:
        filters.append("retrain_job_id = :retrain_job_id")
        params["retrain_job_id"] = retrain_job_id
    if model_candidate_id:
        filters.append("model_candidate_id = :model_candidate_id")
        params["model_candidate_id"] = model_candidate_id
    if len(filters) == 1:
        return
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE human_review_tasks SET status = :status, reviewed_by = :reviewer, "
                "resolution = CAST(:resolution AS jsonb), reviewed_at = now() "
                f"WHERE {' AND '.join(filters)}"
            ),
            params,
        )


async def _insert_feedback(
    connection: AsyncConnection,
    task: HumanReviewTask,
    payload: ReviewTaskSubmitRequest,
) -> TrainingFeedback | None:
    if task.task_type not in {"final_output", "model_disagreement", "label_correction"}:
        return None
    feedback_id = str(uuid4())
    original = task.payload.get("ops_output")
    if not isinstance(original, dict):
        original = task.payload
    corrected = (
        payload.corrected_output.model_dump(mode="json")
        if payload.corrected_output is not None
        else {}
    )
    card_id = None
    if task.run_id:
        run_result = await connection.execute(
            text("SELECT card_id FROM agent_runs WHERE run_id = :run_id"),
            {"run_id": task.run_id},
        )
        row = run_result.mappings().one_or_none()
        if row is not None:
            card_id = str(row["card_id"])
    query = text(
        "INSERT INTO training_feedback ("
        "feedback_id, task_id, run_id, card_id, reviewer, decision, original_output, "
        "corrected_output, corrected_label, metadata"
        ") VALUES ("
        ":feedback_id, :task_id, :run_id, :card_id, :reviewer, :decision, "
        "CAST(:original_output AS jsonb), CAST(:corrected_output AS jsonb), "
        ":corrected_label, CAST(:metadata AS jsonb)"
        ") RETURNING " + _feedback_select_columns()
    )
    result = await connection.execute(
        query,
        {
            "feedback_id": feedback_id,
            "task_id": task.task_id,
            "run_id": task.run_id,
            "card_id": card_id,
            "reviewer": payload.reviewer,
            "decision": payload.decision,
            "original_output": _json(original),
            "corrected_output": _json(corrected),
            "corrected_label": payload.corrected_label,
            "metadata": _json(payload.metadata),
        },
    )
    return _feedback_from_row(result.mappings().one())


async def _feedback_stats(connection: AsyncConnection) -> tuple[int, int]:
    result = await connection.execute(
        text(
            "SELECT count(*) AS reviewed_count, "
            "count(*) FILTER (WHERE decision = 'approve') AS approved_count "
            "FROM training_feedback"
        )
    )
    row = result.mappings().one()
    return int(row["reviewed_count"]), int(row["approved_count"])


def _candidate_select_columns() -> str:
    return (
        "candidate_id, run_id, source_type, source_uri, title, content, query, "
        "risk_level, trust_score, status, CAST(metadata AS text) AS metadata, "
        "requested_by, reviewed_by, review_reason, rag_document_id, rag_chunk_id, "
        "created_at, reviewed_at"
    )


def _review_select_columns() -> str:
    return (
        "task_id, task_type, status, risk_level, title, run_id, candidate_id, "
        "retrain_job_id, model_candidate_id, CAST(payload AS text) AS payload, "
        "CAST(resolution AS text) AS resolution, assigned_to, reviewed_by, "
        "created_at, reviewed_at"
    )


def _feedback_select_columns() -> str:
    return (
        "feedback_id, task_id, run_id, card_id, reviewer, decision, "
        "CAST(original_output AS text) AS original_output, "
        "CAST(corrected_output AS text) AS corrected_output, corrected_label, "
        "CAST(metadata AS text) AS metadata, created_at"
    )


def _candidate_from_row(row: RowMapping) -> EvidenceCandidate:
    return EvidenceCandidate.model_validate(
        {
            "candidate_id": str(row["candidate_id"]),
            "run_id": None if row["run_id"] is None else str(row["run_id"]),
            "source_type": str(row["source_type"]),
            "source_uri": row["source_uri"],
            "title": str(row["title"]),
            "content": str(row["content"]),
            "query": row["query"],
            "risk_level": str(row["risk_level"]),
            "trust_score": float(row["trust_score"]),
            "status": str(row["status"]),
            "metadata": orjson.loads(row["metadata"]),
            "requested_by": str(row["requested_by"]),
            "reviewed_by": row["reviewed_by"],
            "review_reason": row["review_reason"],
            "rag_document_id": row["rag_document_id"],
            "rag_chunk_id": row["rag_chunk_id"],
            "created_at": row["created_at"].isoformat(),
            "reviewed_at": None
            if row["reviewed_at"] is None
            else row["reviewed_at"].isoformat(),
        }
    )


def _review_from_row(row: RowMapping) -> HumanReviewTask:
    return HumanReviewTask.model_validate(
        {
            "task_id": str(row["task_id"]),
            "task_type": str(row["task_type"]),
            "status": str(row["status"]),
            "risk_level": str(row["risk_level"]),
            "title": str(row["title"]),
            "run_id": None if row["run_id"] is None else str(row["run_id"]),
            "candidate_id": None
            if row["candidate_id"] is None
            else str(row["candidate_id"]),
            "retrain_job_id": None
            if row["retrain_job_id"] is None
            else str(row["retrain_job_id"]),
            "model_candidate_id": None
            if row["model_candidate_id"] is None
            else str(row["model_candidate_id"]),
            "payload": orjson.loads(row["payload"]),
            "resolution": orjson.loads(row["resolution"]),
            "assigned_to": row["assigned_to"],
            "reviewed_by": row["reviewed_by"],
            "created_at": row["created_at"].isoformat(),
            "reviewed_at": None
            if row["reviewed_at"] is None
            else row["reviewed_at"].isoformat(),
        }
    )


def _feedback_from_row(row: RowMapping) -> TrainingFeedback:
    return TrainingFeedback(
        feedback_id=str(row["feedback_id"]),
        task_id=str(row["task_id"]),
        run_id=None if row["run_id"] is None else str(row["run_id"]),
        card_id=None if row["card_id"] is None else str(row["card_id"]),
        reviewer=str(row["reviewer"]),
        decision=str(row["decision"]),
        original_output=orjson.loads(row["original_output"]),
        corrected_output=orjson.loads(row["corrected_output"]),
        corrected_label=row["corrected_label"],
        metadata=orjson.loads(row["metadata"]),
        created_at=row["created_at"].isoformat(),
    )


def _policy_from_row(
    row: RowMapping,
    reviewed_count: int,
    approved_count: int,
) -> AutomationPolicy:
    approval_rate = approved_count / max(1, reviewed_count)
    eligible = bool(
        reviewed_count >= int(row["minimum_review_count"])
        and approval_rate >= float(row["minimum_approval_rate"])
    )
    return AutomationPolicy.model_validate(
        {
            "policy_id": "default",
            "mode": str(row["mode"]),
            "auto_transition_enabled": bool(row["auto_transition_enabled"]),
            "minimum_review_count": int(row["minimum_review_count"]),
            "minimum_approval_rate": float(row["minimum_approval_rate"]),
            "minimum_confidence": float(row["minimum_confidence"]),
            "minimum_source_trust": float(row["minimum_source_trust"]),
            "maximum_drift_score": float(row["maximum_drift_score"]),
            "final_review_required": bool(row["final_review_required"]),
            "reviewed_count": reviewed_count,
            "approval_rate": round(approval_rate, 4),
            "eligible_for_guarded_auto": eligible,
            "updated_by": str(row["updated_by"]),
            "updated_at": row["updated_at"].isoformat(),
        }
    )


def _trust_level(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.6:
        return "medium"
    return "low"


def _is_historical_external_candidate(candidate: EvidenceCandidate) -> bool:
    origin = candidate.metadata.get("origin")
    return bool(
        candidate.source_type in {"web", "external_search"}
        or candidate.query is not None
        or origin == "external_search"
    )


def _json(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")
