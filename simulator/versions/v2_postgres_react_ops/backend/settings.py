from typing import Final

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SYSTEM_PROMPT: Final = (
    "You are a Korean district-heating operations assistant. "
    "You receive only a card_id. Use get_ops_evidence when evidence is needed. "
    "Evidence comes from PostgreSQL. External context is not configured. "
    "Final output must contain only summary, action_plan, and caution."
)
GPT_5_4_MINI_INPUT_USD_PER_1M: Final = 0.75
GPT_5_4_MINI_CACHED_INPUT_USD_PER_1M: Final = 0.075
GPT_5_4_MINI_OUTPUT_USD_PER_1M: Final = 4.50
GPT_5_4_MINI_PRICING_SOURCE: Final = (
    "https://developers.openai.com/api/docs/models/gpt-5.4-mini"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HEATGRID_")

    database_url: str = (
        "postgresql+asyncpg://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops"
    )
    openai_model: str = "gpt-5.4-mini"
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
