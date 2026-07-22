from __future__ import annotations

import asyncio

import orjson
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, Field

from review_chat_guardrail import check_operator_message, check_output_text
from report_docx import render_anomaly_report_docx
from settings import Settings


class ReportReviewHistoryItem(BaseModel):
    role: str = Field(pattern="^(operator|assistant)$")
    content: str = Field(min_length=1, max_length=8000)


class ReportReviewRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    report_context: dict[str, object] | str
    history: tuple[ReportReviewHistoryItem, ...] = Field(default=(), max_length=20)


class ReportReviewResponse(BaseModel):
    answer: str


class ReportDocumentRequest(BaseModel):
    report_context: dict[str, object]
    alert_id: str | None = None
    building_name: str = Field(min_length=1, max_length=300)
    machine_room: str = Field(min_length=1, max_length=120)
    status_label: str = Field(default="검토 대기", min_length=1, max_length=80)
    document_version: int = Field(default=1, ge=1)


def make_report_review_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post("/report-documents/docx")
    async def create_report_document(payload: ReportDocumentRequest) -> StreamingResponse:
        document = await asyncio.to_thread(
            render_anomaly_report_docx,
            payload.report_context,
            alert_id=payload.alert_id,
            building_name=payload.building_name,
            machine_room=payload.machine_room,
            status_label=payload.status_label,
            document_version=payload.document_version,
        )
        return StreamingResponse(
            iter((document,)),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": 'attachment; filename="heatgrid-anomaly-report.docx"'},
        )

    @router.post("/report-review/chat", response_model=ReportReviewResponse)
    async def review_report(payload: ReportReviewRequest) -> ReportReviewResponse:
        api_key = None if settings.openai_api_key is None else settings.openai_api_key.get_secret_value()
        verdict = await check_operator_message(payload.message, api_key=api_key)
        if not verdict.allowed:
            raise HTTPException(status_code=422, detail="검토 요청을 처리할 수 없습니다.")
        if api_key is None:
            raise HTTPException(status_code=503, detail="보고서 검토 모델이 설정되지 않았습니다.")
        prompt = orjson.dumps(
            {
                "report": payload.report_context,
                "recent_conversation": [item.model_dump() for item in payload.history[-12:]],
                "operator_question": payload.message,
            }
        ).decode("utf-8")
        try:
            async with AsyncOpenAI(api_key=api_key) as client:
                response = await client.responses.create(
                    model=settings.natural_chat_model,
                    input=(
                        "당신은 지역난방 운영 보고서 검토자입니다. 제공된 보고서 내용만 근거로 한국어로 답하세요. "
                        "작업지시서 수정 대화와 섞지 말고, 보고서의 사실관계·누락·표현·근거 연결만 검토하세요. "
                        "수정을 요청받으면 적용했다고 말하지 말고 교체할 문안을 제안하세요. 없는 수치나 사실은 만들지 마세요. "
                        "Markdown 기호나 제목 없이 간결한 일반 문장으로 답하세요.\n\n" + prompt
                    ),
                )
        except OpenAIError as error:
            raise HTTPException(status_code=502, detail="보고서 검토 응답을 생성하지 못했습니다.") from error
        answer = await check_output_text(response.output_text.strip(), api_key=api_key)
        return ReportReviewResponse(answer=answer[:8000])

    return router
