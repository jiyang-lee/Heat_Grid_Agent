from pathlib import Path
from typing import Final

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SYSTEM_PROMPT: Final = (
    "당신은 한국어로 답하는 지역난방 운영 보조 에이전트입니다. "
    "우선 운영 근거를 확인하고 필요할 때 설비 위치, 기상, 운영 참고자료를 확인하세요. "
    "운영자에게 자연스러운 한국어로 작성하고 내부 변수명, 모델명, 데이터베이스, "
    "검색 도구 이름은 노출하지 마세요. 기상은 운전 부하 맥락일 뿐 고장 원인의 "
    "확정 근거가 아닙니다. 승인되지 않은 외부 근거 후보는 결정적 사실로 표현하지 말고 "
    "추가 검수가 필요하다고 명시하세요. 모델 재검증 결과가 기존 결과와 다르면 그 "
    "불확실성을 주의 사항에 포함하세요. 최종 출력은 summary, action_plan, caution만 포함하세요."
)
GPT_5_4_MINI_INPUT_USD_PER_1M: Final = 0.75
GPT_5_4_MINI_CACHED_INPUT_USD_PER_1M: Final = 0.075
GPT_5_4_MINI_OUTPUT_USD_PER_1M: Final = 4.50
GPT_5_4_MINI_PRICING_SOURCE: Final = (
    "https://developers.openai.com/api/docs/models/gpt-5.4-mini"
)
PROJECT_ROOT: Final = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HEATGRID_",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+asyncpg://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops"
    )
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8003, ge=1, le=65535)
    openai_model: str = "gpt-5.4-mini"
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    rag_top_k: int = 5
    agent_max_iterations: int = Field(default=4, ge=1, le=8)
    agent_evidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    model_score_tolerance: float = Field(default=0.12, ge=0.0, le=1.0)
    retrain_auto_execute_enabled: bool = False
    priority_expected_substations: int = Field(default=31, ge=1)
    priority_stale_after_hours: int = Field(default=720, ge=1)
    priority_model_version: str = "active-priority-contract-v1"
    replay_enabled: bool = True
    replay_dataset_root: Path = PROJECT_ROOT / "data" / "demo_replay" / "current"
    replay_tick_seconds: float | None = Field(default=None, gt=0.0)
