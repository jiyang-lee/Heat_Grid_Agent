from __future__ import annotations

import argparse
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

import asyncpg
import pandas as pd

try:
    from ops_alert_queue import collect_source_diagnostics, enqueue_priority_alerts
    from predictor_db_schema import ensure_target_schema
except ModuleNotFoundError:
    from scripts.ops_alert_queue import collect_source_diagnostics, enqueue_priority_alerts
    from scripts.predictor_db_schema import ensure_target_schema


DEFAULT_DATABASE_URL = "postgresql://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops"
CURRENT_BEST_FLOW = "flow1_anomaly_current_best"
M1_SPECIALIST_FLOW = "flow2_m1_specialist"
NAMESPACE = uuid.UUID("8b4f9f4a-6d84-45b8-b0df-4a1dff1b6d4f")
MODEL_FAMILY = "priority_engine"
MODEL_NAME = "offline_priority_simulator"
MODEL_RUN_TYPE = "offline_simulation"
MODEL_SOURCE_ARTIFACT = "output/agent_priority_card.csv"

CURRENT_BEST_FEATURES = (
    "anomaly_ensemble_score",
    "anomaly_policy_score",
    "iforest_score_ratio",
    "mahalanobis_score_ratio",
    "anomaly_consensus_count",
    "risk_probability",
    "risk_score",
    "leadtime_urgency_score",
    "current_best_priority_score",
)
M1_SPECIALIST_FEATURES = (
    "m1_specialist_priority_score",
    "m1_specialist_fault_probability",
    "m1_specialist_task_probability",
    "m1_specialist_activity_probability",
    "m1_specialist_pre_event_probability",
    "m1_specialist_group_weight",
    "m1_specialist_gate_review_required",
)


@dataclass(frozen=True)
class LoadPaths:
    agent_card: Path
    windows_csv: Path
    database_url: str
    append: bool
    model_run_id: str | None
    enqueue_alerts: bool


def parse_args() -> LoadPaths:
    parser = argparse.ArgumentParser(description="Load predictor simulation input into PostgreSQL.")
    parser.add_argument(
        "--agent-card",
        default="output/agent_priority_card.csv",
        help="Path to output/agent_priority_card.csv",
    )
    parser.add_argument(
        "--windows-csv",
        default="data/processed/trainable_windows.csv",
        help="Path to data/processed/trainable_windows.csv",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("HEATGRID_DATABASE_URL", DEFAULT_DATABASE_URL),
        help="PostgreSQL URL (default: HEATGRID_DATABASE_URL or local heatgrid_ops)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing DB instead of resetting tables.",
    )
    parser.add_argument(
        "--model-run-id",
        default=None,
        help="Optional model_run_id(UUID) for model_outputs rows.",
    )
    parser.add_argument(
        "--enqueue-alerts",
        action="store_true",
        help="Enqueue urgent/high priority cards into ops_alert_queue.",
    )
    args = parser.parse_args()
    return LoadPaths(
        agent_card=Path(args.agent_card),
        windows_csv=Path(args.windows_csv),
        database_url=args.database_url,
        append=args.append,
        model_run_id=args.model_run_id,
        enqueue_alerts=args.enqueue_alerts,
    )


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def normalize_key_value(value: object) -> str:
    return str(value).strip()


def normalize_database_url(url: str) -> str:
    return url.replace("+asyncpg://", "://", 1) if "+asyncpg://" in url else url


def to_utc_iso(value: object) -> str:
    ts = pd.to_datetime(value)
    if pd.isna(ts):
        raise ValueError(f"invalid datetime: {value!r}")
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.isoformat()


def to_utc_datetime(value: object):
    ts = pd.to_datetime(value)
    if pd.isna(ts):
        raise ValueError(f"invalid datetime: {value!r}")
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


def to_optional_datetime(value: object):
    if value is None or pd.isna(value):
        return None
    try:
        return to_utc_datetime(value)
    except (TypeError, ValueError):
        return None


def to_optional_int(value: object) -> int | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool):
        return int(value)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_optional_bool(value: object) -> bool | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y"}:
        return True
    if text in {"0", "false", "f", "no", "n"}:
        return False
    return None


def to_optional_str(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return None if text == "" else text


def build_id(*parts: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, "|".join(parts))


def split_reasons(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    text = str(value).strip()
    if not text:
        return []
    return [item.strip() for item in text.split("|") if item.strip()]


def build_feature_records(row: pd.Series | dict[str, object]) -> list[tuple[str, str]]:
    records: list[tuple[str, str]] = []
    for name in CURRENT_BEST_FEATURES:
        value = to_optional_float(row.get(name))
        if value is not None:
            records.append((CURRENT_BEST_FLOW, str(name)))
    for name in M1_SPECIALIST_FEATURES:
        value = to_optional_float(row.get(name))
        if value is not None:
            records.append((M1_SPECIALIST_FLOW, str(name)))
    return records


async def count_rows(conn: asyncpg.Connection, table: str) -> int:
    return int(await conn.fetchval(f"SELECT count(*) FROM {table}"))


def validate_and_merge(agent: pd.DataFrame, windows: pd.DataFrame) -> pd.DataFrame:
    required_key_cols = ("manufacturer", "substation_id", "window_start", "window_end")
    for col in required_key_cols:
        if col not in agent.columns or col not in windows.columns:
            raise KeyError(f"키 컬럼 누락: {col}")

    agent = agent.copy()
    windows = windows.copy()
    for col in required_key_cols:
        if col == "substation_id":
            agent[col] = pd.to_numeric(agent[col], errors="coerce")
            windows[col] = pd.to_numeric(windows[col], errors="coerce")
        else:
            agent[col] = agent[col].astype(str).str.strip()
            windows[col] = windows[col].astype(str).str.strip()

    merged = agent.merge(
        windows[
            [
                *required_key_cols,
                "label",
                "fault_event_id",
                "season_bucket",
                "source_file",
                "configuration_type",
            ]
        ],
        on=list(required_key_cols),
        how="left",
        indicator=True,
        validate="many_to_one",
        suffixes=("_agent", ""),
    )
    missing = merged["_merge"].eq("left_only")
    if missing.any():
        sample = merged.loc[missing, required_key_cols].head(3)
        raise ValueError(
            f"windows/csv 키 매칭 실패 샘플: {sample.to_dict(orient='records')}"
        )
    return merged.drop(columns="_merge")


async def table_exists(conn: asyncpg.Connection, table: str) -> bool:
    value = await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table}")
    return bool(value)


async def reset_tables(conn: asyncpg.Connection) -> None:
    tables = (
        "agent_run_artifacts",
        "agent_runs",
        "model_runs",
        "model_outputs",
        "sensor_summaries",
        "priority_card_review_reasons",
        "llm_ops_notes",
        "ops_alert_queue",
        "priority_cards",
        "priority_decisions",
        "windows",
    )
    existing = [table for table in tables if await table_exists(conn, table)]
    if not existing:
        return
    await conn.execute(
        f"TRUNCATE TABLE {', '.join(existing)} RESTART IDENTITY CASCADE"
    )


async def load(paths: LoadPaths) -> dict[str, object]:
    agent = read_csv(paths.agent_card)
    windows = read_csv(paths.windows_csv)
    merged = validate_and_merge(agent, windows)

    key_cols = ["manufacturer", "substation_id", "window_start", "window_end"]
    if len(agent) != len(windows) or len(agent) != len(merged):
        raise ValueError(
            f"행 수 불일치: agent={len(agent)}, windows={len(windows)}, merged={len(merged)}"
        )

    duplicates = merged.duplicated(subset=key_cols)
    if duplicates.any():
        raise ValueError(f"중복 키 존재: {int(duplicates.sum())}건")

    if paths.model_run_id:
        try:
            model_run_id = uuid.UUID(paths.model_run_id)
        except ValueError as exc:
            raise ValueError("--model-run-id는 UUID 형식이어야 합니다.") from exc
    else:
        model_run_id = None

    conn = await asyncpg.connect(normalize_database_url(paths.database_url))
    try:
        await ensure_target_schema(conn)
        source_diagnostics = await collect_source_diagnostics(
            conn,
            agent_rows=len(agent),
            windows_rows=len(windows),
        )
        if not paths.append:
            await reset_tables(conn)

        expected_feature_count = 0
        expected_reason_count = 0
        rows = merged.to_dict(orient="records")
        for row in rows:
            expected_feature_count += len(build_feature_records(row))
            reasons: list[str] = []
            reasons.extend(split_reasons(row.get("review_reasons")))
            reasons.extend(split_reasons(row.get("m1_specialist_gate_review_reasons")))
            expected_reason_count += len(dict.fromkeys(reasons))

        expected_counts = {
            "windows": len(rows),
            "priority_decisions": len(rows),
            "priority_cards": len(rows),
            "sensor_summaries": expected_feature_count,
            "review_reasons": expected_reason_count,
            "model_outputs": len(rows) if model_run_id is not None else 0,
            "model_runs": 1 if model_run_id is not None else 0,
        }

        before_counts = {}
        if paths.append:
            before_counts = {
                "windows": await count_rows(conn, "windows"),
                "priority_decisions": await count_rows(conn, "priority_decisions"),
                "priority_cards": await count_rows(conn, "priority_cards"),
                "sensor_summaries": await count_rows(conn, "sensor_summaries"),
                "review_reasons": await count_rows(conn, "priority_card_review_reasons"),
                "model_runs": await count_rows(conn, "model_runs"),
                "model_outputs": await count_rows(conn, "model_outputs"),
            }

        upsert_windows = (
            "INSERT INTO windows ("
            "window_id, manufacturer_id, substation_id, window_start, window_end,"
            " source_file, season_bucket, label, fault_event_id"
            ") VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)"
            " ON CONFLICT (window_id) DO NOTHING"
        )
        upsert_substation = (
            "INSERT INTO substations ("
            "manufacturer_id, substation_id, configuration_type"
            ") VALUES ($1,$2,$3)"
            " ON CONFLICT (manufacturer_id, substation_id) DO UPDATE "
            "SET configuration_type = EXCLUDED.configuration_type"
        )
        upsert_priority_decisions = (
            "INSERT INTO priority_decisions ("
            "priority_decision_id, window_id, current_best_priority_score, current_best_priority_level,"
            " m1_specialist_priority_score, m1_specialist_priority_level, priority_score, priority_level,"
            " priority_source, m1_priority_agreement, policy_version,"
            " current_best_weight, m1_specialist_weight, decision_basis,"
            " m1_specialist_primary_state, m1_specialist_fault_group"
            ") VALUES ("
            "$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16"
            ") ON CONFLICT (priority_decision_id) DO NOTHING"
        )
        upsert_priority_cards = (
            "INSERT INTO priority_cards ("
            "card_id, priority_decision_id, operational_label, primary_state, review_required,"
            " trust_level, why_reason, recommended_action, first_crossing_time, stable_crossing_time,"
            " stable_crossing_lead_hours, raw_card"
            ") VALUES ("
            "$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12"
            ") ON CONFLICT (card_id) DO NOTHING"
        )
        upsert_sensor_summary = (
            "INSERT INTO sensor_summaries ("
            "sensor_summary_id, card_id, window_id, flow_source, model_id, model_version,"
            " source_artifact, selection_rule, feature_name, source_sensor, source_column,"
            " meaning, unit, calculation, feature_value, display_rank, summary_text"
            ") VALUES ("
            "$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17"
            ") ON CONFLICT DO NOTHING"
        )
        upsert_review_reason = (
            "INSERT INTO priority_card_review_reasons (card_id, reason_code, display_rank)"
            " VALUES ($1,$2,$3)"
            " ON CONFLICT (card_id, reason_code) DO NOTHING"
        )
        upsert_model_run = (
            "INSERT INTO model_runs ("
            "model_run_id, model_family, model_name, model_version, run_type, source_artifact"
            ") VALUES ($1,$2,$3,$4,$5,$6)"
            " ON CONFLICT (model_run_id) DO NOTHING"
        )
        upsert_model_output = (
            "INSERT INTO model_outputs ("
            "model_output_id, window_id, model_run_id, model_family, score_name, score_value,"
            " label_name, label_value, display_rank"
            ") VALUES ("
            "$1,$2,$3,$4,$5,$6,$7,$8,$9"
            ") ON CONFLICT (model_output_id) DO NOTHING"
        )

        counters = {
            "windows": 0,
            "priority_decisions": 0,
            "priority_cards": 0,
            "sensor_summaries": 0,
            "review_reasons": 0,
            "model_runs": 0,
            "model_outputs": 0,
        }

        for row in rows:
            window_id = build_id(
                "window",
                normalize_key_value(row["manufacturer"]),
                normalize_key_value(row["substation_id"]),
                to_utc_iso(row["window_start"]),
                to_utc_iso(row["window_end"]),
            )
            feature_records = build_feature_records(row)
            decision_id = build_id("decision", str(window_id), to_utc_iso(row["window_start"]))
            card_id = build_id(
                "card",
                str(decision_id),
                normalize_key_value(row["priority_level"]),
            )

            window_start = to_utc_datetime(row["window_start"])
            window_end = to_utc_datetime(row["window_end"])
            manufacturer_id = normalize_key_value(row["manufacturer"])
            substation_id = to_optional_int(row["substation_id"])
            if substation_id is not None:
                await conn.execute(
                    upsert_substation,
                    manufacturer_id,
                    substation_id,
                    to_optional_str(row.get("configuration_type")),
                )
            await conn.execute(
                upsert_windows,
                window_id,
                manufacturer_id,
                substation_id,
                window_start,
                window_end,
                to_optional_str(row["source_file"]),
                to_optional_str(row["season_bucket"]),
                to_optional_str(row["label"]),
                to_optional_str(row["fault_event_id"]),
            )
            counters["windows"] += 1

            await conn.execute(
                upsert_priority_decisions,
                decision_id,
                window_id,
                to_optional_float(row.get("current_best_priority_score")),
                to_optional_str(row.get("current_best_priority_level")),
                to_optional_float(row.get("m1_specialist_priority_score")),
                to_optional_str(row.get("m1_specialist_priority_level")),
                to_optional_float(row.get("priority_score")),
                to_optional_str(row.get("priority_level")),
                to_optional_str(row.get("priority_source")),
                to_optional_str(row.get("m1_priority_agreement")),
                to_optional_str(row.get("policy_version")) or to_optional_str(row.get("priority_source")),
                to_optional_float(row.get("current_best_weight")),
                to_optional_float(row.get("m1_specialist_weight")),
                to_optional_str(row.get("decision_basis")),
                to_optional_str(row.get("m1_specialist_primary_state")),
                to_optional_str(row.get("m1_specialist_fault_group")),
            )
            counters["priority_decisions"] += 1

            raw_card = {
                "manufacturer": row["manufacturer"],
                "substation_id": row["substation_id"],
                "window_start": row["window_start"],
                "window_end": row["window_end"],
                "configuration_type": to_optional_str(row.get("configuration_type")),
                "label": to_optional_str(row.get("label")),
                "fault_label": to_optional_str(
                    row.get("fault_label_agent", row.get("fault_label"))
                ),
                "fault_event_id": to_optional_str(row.get("fault_event_id")),
                "priority_score": row.get("priority_score"),
                "priority_level": row.get("priority_level"),
            }

            await conn.execute(
                upsert_priority_cards,
                card_id,
                decision_id,
                to_optional_str(row.get("operational_label")),
                to_optional_str(row.get("primary_state")),
                to_optional_bool(row.get("review_required")),
                to_optional_str(row.get("trust_level")),
                to_optional_str(row.get("why_reason")),
                to_optional_str(row.get("recommended_action")),
                to_optional_datetime(row.get("first_crossing_time")),
                to_optional_datetime(row.get("stable_crossing_time")),
                to_optional_float(row.get("stable_crossing_lead_hours")),
                json.dumps(raw_card, ensure_ascii=False),
            )
            counters["priority_cards"] += 1

            feature_values: list[tuple[str, str, float]] = []
            for feature_flow, feature_name in feature_records:
                numeric = to_optional_float(row.get(feature_name))
                if numeric is None:
                    continue
                feature_values.append((feature_flow, feature_name, numeric))

            rank = 1
            for feature_flow, feature_name, numeric in feature_values:
                source_sensor = (
                    "current_best"
                    if feature_flow == CURRENT_BEST_FLOW
                    else "m1_specialist"
                )

                await conn.execute(
                    upsert_sensor_summary,
                    build_id(
                        "sensor_summary",
                        str(card_id),
                        str(feature_flow),
                        feature_name,
                        str(numeric),
                    ),
                    card_id,
                    window_id,
                    feature_flow,
                    source_sensor,
                    None,
                    "agent_priority_card",
                    "numeric_feature_bundle",
                    feature_name,
                    source_sensor,
                    feature_name,
                    "card feature",
                    None,
                    "from agent_priority_card.csv",
                    numeric,
                    rank,
                    f"{feature_flow}:{feature_name}",
                )
                counters["sensor_summaries"] += 1
                rank += 1

            reasons: list[str] = []
            reasons.extend(split_reasons(row.get("review_reasons")))
            reasons.extend(split_reasons(row.get("m1_specialist_gate_review_reasons")))
            for i, reason in enumerate(dict.fromkeys(reasons), start=1):
                await conn.execute(upsert_review_reason, card_id, reason, i)
                counters["review_reasons"] += 1

            if model_run_id is not None:
                if counters["model_runs"] == 0:
                    await conn.execute(
                        upsert_model_run,
                        model_run_id,
                        MODEL_FAMILY,
                        MODEL_NAME,
                        None,
                        MODEL_RUN_TYPE,
                        MODEL_SOURCE_ARTIFACT,
                    )
                    counters["model_runs"] += 1

                await conn.execute(
                    upsert_model_output,
                    build_id(
                        "model_output",
                        str(window_id),
                        str(model_run_id),
                        MODEL_FAMILY,
                    ),
                    window_id,
                    model_run_id,
                    MODEL_FAMILY,
                    "priority_score",
                    to_optional_float(row.get("priority_score")),
                    "priority_level",
                    to_optional_str(row.get("priority_level")),
                    1,
                )
                counters["model_outputs"] += 1

        after_counts = {
            "windows": await count_rows(conn, "windows"),
            "priority_decisions": await count_rows(conn, "priority_decisions"),
            "priority_cards": await count_rows(conn, "priority_cards"),
            "sensor_summaries": await count_rows(conn, "sensor_summaries"),
            "review_reasons": await count_rows(conn, "priority_card_review_reasons"),
            "model_runs": await count_rows(conn, "model_runs"),
            "model_outputs": await count_rows(conn, "model_outputs"),
        }
        alert_summary = None
        if paths.enqueue_alerts:
            alert_summary = await enqueue_priority_alerts(conn)
        actual_counts = {
            "windows": after_counts["windows"],
            "priority_decisions": after_counts["priority_decisions"],
            "priority_cards": after_counts["priority_cards"],
            "sensor_summaries": after_counts["sensor_summaries"],
            "review_reasons": after_counts["review_reasons"],
            "model_runs": after_counts["model_runs"],
            "model_outputs": after_counts["model_outputs"],
        }

        if not paths.append:
            for key, expected in expected_counts.items():
                if actual_counts[key] != expected:
                    raise RuntimeError(
                        f"{key} 실제 건수 불일치: expected={expected}, actual={actual_counts[key]}"
                    )

        summary = {
            "source_diagnostics": source_diagnostics,
            "counters": counters,
            "expected": expected_counts,
            "actual": actual_counts,
        }
        if alert_summary is not None:
            summary["alerts"] = alert_summary
        if paths.append:
            summary["before"] = before_counts
            summary["added"] = {
                "windows": actual_counts["windows"] - before_counts["windows"],
                "priority_decisions": actual_counts["priority_decisions"] - before_counts["priority_decisions"],
                "priority_cards": actual_counts["priority_cards"] - before_counts["priority_cards"],
                "sensor_summaries": actual_counts["sensor_summaries"] - before_counts["sensor_summaries"],
                "review_reasons": actual_counts["review_reasons"] - before_counts["review_reasons"],
                "model_runs": actual_counts["model_runs"] - before_counts["model_runs"],
                "model_outputs": actual_counts["model_outputs"] - before_counts["model_outputs"],
            }
        return summary
    finally:
        await conn.close()


async def main() -> None:
    paths = parse_args()
    summary = await load(paths)
    print("Load complete:", summary)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
