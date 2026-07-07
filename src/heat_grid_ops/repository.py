from collections.abc import Sequence
from pathlib import Path

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from heat_grid_ops.schemas import (
    CardContext,
    CurrentBestSensorValues,
    ExplanationContext,
    M1SpecialistFeatures,
    ModelSignals,
    OpsAgentInput,
    OpsAgentOutput,
    PriorityCalculation,
    PriorityContext,
    PriorityContextBlock,
    RawContext,
    SensorValueContext,
    WindowContext,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
VERSION_DIR = ROOT_DIR / "05_시뮬레이션" / "versions" / "v0_minimal_ops"
EXAMPLE_INPUT = VERSION_DIR / "examples" / "ops_agent_input.example.json"
SCHEMA_SQL = VERSION_DIR / "db" / "schema.sql"
SEED_SQL = VERSION_DIR / "db" / "seed.sql"

CURRENT_BEST_FLOW = "flow1_anomaly_current_best"
M1_SPECIALIST_FLOW = "flow2_m1_specialist"
PRIORITY_CALCULATION_EXPRESSION = (
    "priority_score = current_best_weight * current_best_priority_score + "
    "m1_specialist_weight * m1_specialist_priority_score"
)


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def load_example_input() -> OpsAgentInput:
    payload = orjson.loads(EXAMPLE_INPUT.read_bytes())
    return OpsAgentInput.model_validate(payload)


async def check_database(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("select 1"))
    except (SQLAlchemyError, OSError):
        return False
    return True


async def setup_database(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        for statement in _sql_statements(SCHEMA_SQL):
            await connection.execute(text(statement))
        for statement in _sql_statements(SEED_SQL):
            await connection.execute(text(statement))


async def list_card_ids(engine: AsyncEngine) -> list[str]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text("select card_id from priority_cards order by created_at, card_id")
        )
    return [str(row[0]) for row in result.all()]


async def fetch_ops_input(engine: AsyncEngine, card_id: str) -> OpsAgentInput | None:
    try:
        async with engine.connect() as connection:
            card_result = await connection.execute(_card_query(), {"card_id": card_id})
            card_row = card_result.mappings().one_or_none()
            if card_row is None:
                return None
            current_best_result = await connection.execute(
                _sensor_summary_query(),
                {"card_id": card_id, "flow_source": CURRENT_BEST_FLOW},
            )
            m1_result = await connection.execute(
                _sensor_summary_query(),
                {"card_id": card_id, "flow_source": M1_SPECIALIST_FLOW},
            )
            review_reason_result = await connection.execute(
                text(
                    "select reason_code "
                    "from priority_card_review_reasons "
                    "where card_id = :card_id "
                    "order by display_rank, reason_code"
                ),
                {"card_id": card_id},
            )
    except OSError:
        return None
    return _ops_input_from_rows(
        card_row,
        current_best_result.mappings().all(),
        m1_result.mappings().all(),
        review_reason_result.mappings().all(),
    )


async def save_ops_note(
    engine: AsyncEngine,
    card_id: str,
    ops_input: OpsAgentInput,
    ops_output: OpsAgentOutput,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "insert into llm_ops_notes ("
                "card_id, summary, action_plan, caution, prompt_input, llm_output"
                ") values ("
                ":card_id, :summary, :action_plan, :caution, "
                "cast(:prompt_input as jsonb), cast(:llm_output as jsonb)"
                ")"
            ),
            {
                "card_id": card_id,
                "summary": ops_output.summary,
                "action_plan": ops_output.action_plan,
                "caution": ops_output.caution,
                "prompt_input": ops_input.model_dump_json(),
                "llm_output": ops_output.model_dump_json(),
            },
        )


def _sql_statements(path: Path) -> list[str]:
    return [part.strip() for part in path.read_text(encoding="utf-8").split(";") if part.strip()]


def _card_query():
    return text(
        "select "
        "pc.card_id, pc.operational_label, pc.primary_state, pc.review_required, "
        "pc.trust_level, pc.why_reason, pc.recommended_action, "
        "pd.priority_decision_id, pd.priority_score, pd.priority_level, "
        "pd.priority_source, pd.m1_priority_agreement, "
        "pd.current_best_priority_score, pd.current_best_priority_level, "
        "pd.m1_specialist_priority_score, pd.m1_specialist_priority_level, "
        "pd.current_best_weight, pd.m1_specialist_weight, "
        "pd.m1_specialist_primary_state, pd.m1_specialist_fault_group, "
        "w.window_id, w.manufacturer_id, w.substation_id, "
        "w.window_start, w.window_end, s.configuration_type "
        "from priority_cards pc "
        "join priority_decisions pd on pd.priority_decision_id = pc.priority_decision_id "
        "join windows w on w.window_id = pd.window_id "
        "left join substations s "
        "on s.manufacturer_id = w.manufacturer_id "
        "and s.substation_id = w.substation_id "
        "where pc.card_id = :card_id"
    )


def _sensor_summary_query():
    return text(
        "select model_id, model_version, source_artifact, selection_rule, "
        "feature_name, source_sensor, source_column, meaning, unit, calculation, "
        "feature_value, display_rank "
        "from sensor_summaries "
        "where card_id = :card_id and flow_source = :flow_source "
        "order by display_rank, feature_name"
    )


def _ops_input_from_rows(
    card_row: RowMapping,
    current_best_rows: Sequence[RowMapping],
    m1_rows: Sequence[RowMapping],
    review_reason_rows: Sequence[RowMapping],
) -> OpsAgentInput:
    current_best_values = [_sensor_value_from_row(row) for row in current_best_rows]
    m1_values = [_sensor_value_from_row(row) for row in m1_rows]
    return OpsAgentInput(
        raw_context=RawContext(
            window=WindowContext(
                window_id=str(card_row["window_id"]),
                manufacturer_id=str(card_row["manufacturer_id"]),
                substation_id=card_row["substation_id"],
                configuration_type=card_row["configuration_type"],
                window_start=card_row["window_start"].isoformat(),
                window_end=card_row["window_end"].isoformat(),
            ),
            current_best_sensor_values=CurrentBestSensorValues(
                model_id=_group_text(current_best_rows, "model_id", "current-best"),
                model_version=_row_optional_text(current_best_rows[0], "model_version")
                if current_best_rows
                else None,
                source_artifact=_group_text(
                    current_best_rows,
                    "source_artifact",
                    "m1_specialist_handoff/data_contract/trainable_windows.csv",
                ),
                selection_rule=_group_text(
                    current_best_rows,
                    "selection_rule",
                    "current-best 입력 feature 중 화면 확인용 raw sensor 집계값 top N",
                ),
                top_n=len(current_best_values),
                values=current_best_values,
            ),
            m1_specialist_features=M1SpecialistFeatures(
                model_id=_group_text(m1_rows, "model_id", "m1-specialist"),
                model_version=_row_optional_text(m1_rows[0], "model_version")
                if m1_rows
                else None,
                source_artifact=_group_text(
                    m1_rows,
                    "source_artifact",
                    "m1_specialist_handoff/scores/m1_specialist_compact13_features.csv",
                ),
                feature_count=len(m1_values),
                features=m1_values,
            ),
        ),
        priority_context=PriorityContext(
            card=CardContext(
                card_id=str(card_row["card_id"]),
                operational_label=card_row["operational_label"],
                primary_state=card_row["primary_state"],
                trust_level=card_row["trust_level"],
            ),
            priority=PriorityContextBlock(
                priority_decision_id=str(card_row["priority_decision_id"]),
                priority_score=card_row["priority_score"],
                priority_level=card_row["priority_level"],
                priority_source=card_row["priority_source"],
                m1_priority_agreement=card_row["m1_priority_agreement"],
                calculation=PriorityCalculation(
                    current_best_weight=card_row["current_best_weight"],
                    m1_specialist_weight=card_row["m1_specialist_weight"],
                    expression=PRIORITY_CALCULATION_EXPRESSION,
                ),
            ),
            model_signals=ModelSignals(
                current_best_priority_score=card_row["current_best_priority_score"],
                current_best_priority_level=card_row["current_best_priority_level"],
                m1_specialist_priority_score=card_row["m1_specialist_priority_score"],
                m1_specialist_priority_level=card_row["m1_specialist_priority_level"],
                m1_specialist_primary_state=card_row["m1_specialist_primary_state"],
                m1_specialist_fault_group=card_row["m1_specialist_fault_group"],
            ),
            explanation=ExplanationContext(
                why_reason=card_row["why_reason"],
                recommended_action=card_row["recommended_action"],
                review_required=card_row["review_required"],
                review_reasons=[str(row["reason_code"]) for row in review_reason_rows],
            ),
        ),
    )


def _sensor_value_from_row(row: RowMapping) -> SensorValueContext:
    return SensorValueContext(
        rank=int(row["display_rank"]),
        feature_name=str(row["feature_name"]),
        source_sensor=str(row["source_sensor"]),
        source_column=_row_text(row, "source_column", str(row["feature_name"])),
        feature_value=row["feature_value"],
        unit=_row_optional_text(row, "unit"),
        calculation=_row_text(row, "calculation", "unknown"),
        meaning=_row_text(row, "meaning", ""),
    )


def _group_text(rows: Sequence[RowMapping], key: str, fallback: str) -> str:
    return fallback if len(rows) == 0 else _row_text(rows[0], key, fallback)


def _row_text(row: RowMapping, key: str, fallback: str) -> str:
    value = row[key]
    return fallback if value is None else str(value)


def _row_optional_text(row: RowMapping, key: str) -> str | None:
    value = row[key]
    return None if value is None else str(value)
