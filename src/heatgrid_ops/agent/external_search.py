from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, Field


class ExternalEvidenceHit(BaseModel):
    title: str
    url: str | None = None
    content: str
    trust_score: float = Field(default=0.55, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalEvidenceSearchResult(BaseModel):
    status: str
    query: str
    hits: list[ExternalEvidenceHit] = Field(default_factory=list)
    message: str | None = None


@dataclass(frozen=True, slots=True)
class OpenAIWebEvidenceProvider:
    api_key: str | None
    model: str
    max_results: int = 5
    allowed_domains: tuple[str, ...] = ()

    async def search(self, query: str) -> ExternalEvidenceSearchResult:
        if not self.api_key:
            return ExternalEvidenceSearchResult(
                status="not_configured",
                query=query,
                message="OPENAI_API_KEY가 없어 외부 검색을 실행하지 않았습니다.",
            )
        domain_instruction = ""
        if self.allowed_domains:
            domain_instruction = (
                " 허용된 도메인만 사용하세요: " + ", ".join(self.allowed_domains) + "."
            )
        prompt = (
            "지역난방 운영 검수에 필요한 근거를 검색하세요. 원문에서 확인되는 사실만 "
            "간결하게 정리하고 출처 URL과 제목을 반드시 남기세요." + domain_instruction
        )
        try:
            response = await AsyncOpenAI(api_key=self.api_key).responses.create(
                model=self.model,
                tools=[{"type": "web_search"}],
                include=["web_search_call.action.sources"],
                input=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": query},
                ],
            )
        except (OpenAIError, OSError, ValueError) as exc:
            return ExternalEvidenceSearchResult(
                status="unavailable",
                query=query,
                message=str(exc),
            )
        payload = response.model_dump(mode="json")
        hits = _hits_from_response(payload, response.output_text, self.max_results)
        return ExternalEvidenceSearchResult(
            status="available" if hits else "no_match",
            query=query,
            hits=hits,
        )


def _hits_from_response(
    payload: dict[str, Any],
    output_text: str,
    max_results: int,
) -> list[ExternalEvidenceHit]:
    sources: list[tuple[str | None, str | None]] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        action = item.get("action")
        if isinstance(action, dict):
            for source in action.get("sources", []) or []:
                if isinstance(source, dict):
                    sources.append((source.get("title"), source.get("url")))
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            for annotation in content.get("annotations", []) or []:
                if isinstance(annotation, dict) and annotation.get("url"):
                    sources.append((annotation.get("title"), annotation.get("url")))

    unique: list[tuple[str | None, str | None]] = []
    seen: set[str] = set()
    for title, url in sources:
        key = str(url or title or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append((title, url))

    summary = output_text.strip()[:4000]
    if not unique and summary:
        return [
            ExternalEvidenceHit(
                title="외부 검색 요약",
                content=summary,
                trust_score=0.45,
                metadata={"citation_missing": True},
            )
        ]
    return [
        ExternalEvidenceHit(
            title=str(title or url or "외부 근거"),
            url=str(url) if url else None,
            content=summary,
            trust_score=0.6,
        )
        for title, url in unique[:max_results]
    ]
