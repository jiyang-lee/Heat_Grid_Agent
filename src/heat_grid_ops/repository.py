from pathlib import Path

import orjson
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from heat_grid_ops.schemas import (
    CardContext,
    ExplanationContext,
    FeatureContext,
    ModelSignals,
    OpsAgentInput,
    OpsAgentOutput,
    PriorityContext,
    PriorityContextBlock,
    RawContext,
    WindowContext,
)

ROOT_DIR = Path(__file__).resolve().parents[2]
VERSION_DIR = ROOT_DIR / "05_시뮬레이션" / "versions" / "v0_minimal_ops"
EXAMPLE_INPUT = VERSION_DIR / "examples" / "ops_agent_input.example.json"
SCHEMA_SQL = VERSION_DIR / "db" / "schema.sql"
SEED_SQL = VERSION_DIR / "db" / "seed.sql"

FEATURE_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "missing_rate": ("data_quality", "window 내 결측률"),
    "p_return_gap__last_minus_first": ("p_return_gap", "window 내 return gap 변화"),
}


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
            feature_result = await connection.execute(
                text(
                    "select feature_name, feature_value "
                    "from window_features "
                    "where window_id = :window_id "
                    "order by display_rank, feature_name"
                ),
                {"window_id": card_row["window_id"]},
            )
    except OSError:
        return None
    return _ops_input_from_rows(card_row, feature_result.mappings().all())


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


def _ops_input_from_rows(card_row, feature_rows) -> OpsAgentInput:
    features = [
        FeatureContext(
            feature_name=str(row["feature_name"]),
            source_sensor=FEATURE_DESCRIPTIONS.get(str(row["feature_name"]), ("unknown", ""))[0],
            meaning=FEATURE_DESCRIPTIONS.get(str(row["feature_name"]), ("unknown", ""))[1],
            feature_value=row["feature_value"],
        )
        for row in feature_rows
    ]
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
            features=features,
        ),
        priority_context=PriorityContext(
            card=CardContext(
                card_id=str(card_row["card_id"]),
                operational_label=card_row["operational_label"],
                primary_state=card_row["primary_state"],
                review_required=card_row["review_required"],
                trust_level=card_row["trust_level"],
            ),
            priority=PriorityContextBlock(
                priority_decision_id=str(card_row["priority_decision_id"]),
                priority_score=card_row["priority_score"],
                priority_level=card_row["priority_level"],
                priority_source=card_row["priority_source"],
                m1_priority_agreement=card_row["m1_priority_agreement"],
            ),
            model_signals=ModelSignals(
                current_best_priority_score=card_row["current_best_priority_score"],
                current_best_priority_level=card_row["current_best_priority_level"],
                m1_specialist_priority_score=card_row["m1_specialist_priority_score"],
                m1_specialist_priority_level=card_row["m1_specialist_priority_level"],
            ),
            explanation=ExplanationContext(
                why_reason=card_row["why_reason"],
                recommended_action=card_row["recommended_action"],
            ),
        ),
    )
