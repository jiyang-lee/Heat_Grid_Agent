from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


class AgentCoreError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AgentInputNotFoundError(AgentCoreError):
    entity: Literal["alert_id", "card_id"]
    identifier: str

    def __str__(self) -> str:
        return f"{self.entity}를 찾을 수 없습니다."


@dataclass(frozen=True, slots=True)
class AgentInputContractError(AgentCoreError):
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(slots=True)
class AgentDependencyError(AgentCoreError):
    service: Literal["llm", "model", "persistence", "rag", "report"]
    detail: str

    def __str__(self) -> str:
        return self.detail


@dataclass(slots=True)
class MissingApiKeyError(AgentDependencyError):
    service: Literal["llm"] = "llm"
    detail: str = "OPENAI_API_KEY가 필요합니다."
