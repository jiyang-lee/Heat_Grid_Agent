from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HEATGRID_")

    database_url: str = (
        "postgresql+asyncpg://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops"
    )
    openai_model: str = "gpt-5.5"
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
