from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine

from retrain_repository import (
    complete_retrain_job,
    create_model_candidate,
    fail_retrain_job,
    get_retrain_job,
    mark_retrain_running,
    reviewed_feedback_rows,
)
from review_repository import create_review_task

ROOT = Path(__file__).resolve().parents[4]
MODEL_GROUPS = ("risk", "leadtime", "priority", "anomaly", "m1_specialist")


async def execute_retrain_job(engine: AsyncEngine, job_id: str) -> None:
    job = await get_retrain_job(engine, job_id)
    if job is None or job.status != "approved":
        return
    await mark_retrain_running(engine, job_id)
    feedback_rows = await reviewed_feedback_rows(engine, job.feedback_ids)
    candidate_id = str(uuid4())
    try:
        execution = await asyncio.to_thread(
            _train_and_snapshot,
            job_id,
            candidate_id,
            feedback_rows,
        )
        candidate = await create_model_candidate(
            engine,
            job_id=job_id,
            candidate_id=candidate_id,
            version=str(execution["version"]),
            artifact_uri=str(execution["artifact_uri"]),
            baseline_metrics=execution["baseline_metrics"],
            candidate_metrics=execution["candidate_metrics"],
            validation_summary=execution["validation_summary"],
        )
        await complete_retrain_job(
            engine,
            job_id,
            execution_metadata=execution,
            candidate_id=candidate.candidate_id,
        )
        await create_review_task(
            engine,
            task_type="model_promotion",
            risk_level="critical",
            title=f"모델 후보 {candidate.version} 최종 승격 검수",
            model_candidate_id=candidate.candidate_id,
            retrain_job_id=job_id,
            payload=candidate.model_dump(mode="json"),
        )
    except Exception as exc:  # background job boundary
        await fail_retrain_job(engine, job_id, str(exc))


def activate_model_candidate(artifact_uri: str, deployment_payload: dict[str, object]) -> None:
    source_root = _resolve_artifact_root(artifact_uri) / "models"
    if not source_root.exists():
        raise FileNotFoundError(f"모델 후보 디렉터리를 찾을 수 없습니다: {source_root}")
    target_root = ROOT / "models"
    for group in MODEL_GROUPS:
        source = source_root / group
        if source.exists():
            shutil.copytree(source, target_root / group, dirs_exist_ok=True)
    pointer = {
        **deployment_payload,
        "activated_at": datetime.now(timezone.utc).isoformat(),
    }
    (target_root / "active_model.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _train_and_snapshot(
    job_id: str,
    candidate_id: str,
    feedback_rows: list[dict[str, object]],
) -> dict[str, object]:
    from third_model.pipeline import run_steps

    job_root = ROOT / "output" / "retrain_jobs" / job_id
    baseline_root = job_root / "baseline_models"
    candidate_root = ROOT / "output" / "model_candidates" / candidate_id
    feedback_path = job_root / "approved_feedback.jsonl"
    job_root.mkdir(parents=True, exist_ok=True)
    candidate_root.mkdir(parents=True, exist_ok=True)
    feedback_path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in feedback_rows
            if row.get("corrected_label")
        ),
        encoding="utf-8",
    )
    _copy_model_groups(ROOT / "models", baseline_root)
    baseline_metrics = _model_manifest(baseline_root)
    previous_feedback_path = os.environ.get("HEATGRID_TRAINING_FEEDBACK_PATH")
    os.environ["HEATGRID_TRAINING_FEEDBACK_PATH"] = str(feedback_path)
    try:
        run_steps(["full_retrain"])
        _copy_model_groups(ROOT / "models", candidate_root / "models")
        candidate_metrics = _model_manifest(candidate_root / "models")
        validation_summary = _validation_summary(feedback_rows)
    finally:
        _copy_model_groups(baseline_root, ROOT / "models")
        if previous_feedback_path is None:
            os.environ.pop("HEATGRID_TRAINING_FEEDBACK_PATH", None)
        else:
            os.environ["HEATGRID_TRAINING_FEEDBACK_PATH"] = previous_feedback_path

    version = datetime.now(timezone.utc).strftime("heatgrid-%Y%m%dT%H%M%SZ")
    manifest = {
        "job_id": job_id,
        "candidate_id": candidate_id,
        "version": version,
        "feedback_count": len(feedback_rows),
        "baseline_metrics": baseline_metrics,
        "candidate_metrics": candidate_metrics,
        "validation_summary": validation_summary,
    }
    (candidate_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        **manifest,
        "artifact_uri": candidate_root.relative_to(ROOT).as_posix(),
        "feedback_path": feedback_path.relative_to(ROOT).as_posix(),
    }


def _copy_model_groups(source_root: Path, target_root: Path) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    for group in MODEL_GROUPS:
        source = source_root / group
        if source.exists():
            shutil.copytree(source, target_root / group, dirs_exist_ok=True)


def _model_manifest(root: Path) -> dict[str, object]:
    files: list[dict[str, object]] = []
    if root.exists():
        for path in sorted(root.rglob("*")):
            if path.is_file():
                files.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "sha256": _sha256(path),
                        "size_bytes": path.stat().st_size,
                    }
                )
    return {"artifact_count": len(files), "artifacts": files}


def _validation_summary(feedback_rows: list[dict[str, object]]) -> dict[str, object]:
    corrected = [row for row in feedback_rows if row.get("corrected_label")]
    return {
        "status": "awaiting_human_promotion_review",
        "reviewed_feedback_count": len(feedback_rows),
        "corrected_label_count": len(corrected),
        "final_promotion_requires_human": True,
    }


def _resolve_artifact_root(artifact_uri: str) -> Path:
    path = Path(artifact_uri)
    return path if path.is_absolute() else ROOT / path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
