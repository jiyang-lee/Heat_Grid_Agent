from typing import Final

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SYSTEM_PROMPT: Final = (
    "You are a Korean district-heating operations assistant. "
    "You receive only a card_id. First use get_ops_evidence for PostgreSQL evidence. "
    "When location, weather, or operating-reference context is needed, use get_external_context. "
    "Write for an operator in natural Korean. Do not expose internal variable names, model names, "
    "RAG, chunk, retrieval, pgvector, PostgreSQL, KMA API, or tool names. "
    "Use terms such as 위험도, 의심 유형, 판단 근거, 점검 항목, 문제 발생 위치, 기상 요인, 운영 참고자료. "
    "Weather is only operating-load context, not proof of a fault cause. "
    "Final output must contain only summary, action_plan, and caution."
)
GPT_5_4_MINI_INPUT_USD_PER_1M: Final = 0.75
GPT_5_4_MINI_CACHED_INPUT_USD_PER_1M: Final = 0.075
GPT_5_4_MINI_OUTPUT_USD_PER_1M: Final = 4.50
GPT_5_4_MINI_PRICING_SOURCE: Final = (
    "https://developers.openai.com/api/docs/models/gpt-5.4-mini"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HEATGRID_",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+asyncpg://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops"
    )
    openai_model: str = "gpt-5.4-mini"
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    rag_top_k: int = 5
