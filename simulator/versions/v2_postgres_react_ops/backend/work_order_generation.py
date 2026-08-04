from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast

import orjson
from openai import AsyncOpenAI, OpenAIError
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from incident_document_api_models import (
    PROTOTYPE_DISCLAIMER,
    SAFETY_PERMIT_QUESTIONS,
    BooleanChecklistItem,
    ChecklistResult,
    SafetyPermitPrecheck,
    SafetyPermitQuestion,
    WorkOrderChecklistItem,
    WorkOrderFieldPatchRequest,
    WorkOrderHeader,
    WorkOrderKind,
    WorkOrderStructuredContent,
)

LOGGER = logging.getLogger(__name__)

WORK_ORDER_MARKDOWN_HEADINGS = (
    "상황 요약",
    "위험성 및 근거",
    "작업 절차",
    "안전 확인",
)

_UNKNOWN_EQUIPMENT_TYPE = "대상 계통"
_EQUIPMENT_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("열교환", "열교환기"),
    ("펌프", "순환펌프"),
    ("순환 유량", "순환펌프"),
    ("공급·순환 계통", "순환펌프"),
)

_SITE_CHECK_PREP_ITEMS: tuple[str, ...] = (
    "설비 정지·분해 금지",
    "밸브 및 제어 설정값 임의 변경 금지",
    "센서 탈거·전기반 개방 금지",
    "고온 배관·회전체 직접 접촉 금지",
    "누수·이상음·과도한 진동 발견 시 즉시 작업 중지",
    "이상 발견 시 현장 관리자에게 보고",
)
_MAINTENANCE_PREP_ITEMS: tuple[str, ...] = (
    "도면·정비 매뉴얼을 확인했다",
    "필요한 작업허가를 확인했다",
    "관련 밸브·전원을 차단했다",
    "보호구를 준비했다",
    "필요 자재·부품을 준비했다",
    "주변 통제를 실시했다",
)

# 개발자용 내부 진단 정보(모델 스냅샷, 검색 계층 오류 등)는 작업 절차 본문에
# 노출하지 않는다 (참고 자료의 "중요한 제한" 원칙).
_FORBIDDEN_INTERNAL_TERMS: tuple[str, ...] = (
    "rag", "pgvector", "priority card", "priority_card",
    "검색 계층", "모델 스냅샷", "fallback", "임베딩", "캘리브레이션",
    "신뢰도", "모델 간", "전문가 모델", "예측 스냅샷", "재검증",
    "m1_priority", "partial",
)


class WorkOrderGenerationError(RuntimeError):
    pass


class WorkOrderPatchError(ValueError):
    pass


_CHECKLIST_FIELD_ALLOWLIST = frozenset(
    {"result", "measured_before", "measured_after", "checked_by", "signature", "note"}
)
_CHECKLIST_RESULTS: frozenset[str] = frozenset({"pass", "fail", "not_applicable", "pending"})
_BOOLEAN_TRUE_VALUES = frozenset({"true", "1", "checked", "yes", "y"})
_BOOLEAN_FALSE_VALUES = frozenset({"false", "0", "unchecked", "no", "n"})


def _parse_bool(raw: str) -> bool:
    normalized = raw.strip().lower()
    if normalized in _BOOLEAN_TRUE_VALUES:
        return True
    if normalized in _BOOLEAN_FALSE_VALUES:
        return False
    raise WorkOrderPatchError(f"invalid boolean value: {raw!r}")


def _patch_checklist_item(
    item: WorkOrderChecklistItem,
    *,
    target_field: str,
    new_value: str,
) -> WorkOrderChecklistItem:
    if target_field not in _CHECKLIST_FIELD_ALLOWLIST:
        raise WorkOrderPatchError(f"field not editable on checklist rows: {target_field}")
    if target_field == "result":
        if new_value not in _CHECKLIST_RESULTS:
            raise WorkOrderPatchError(f"invalid checklist result: {new_value!r}")
        return item.model_copy(update={"result": cast(ChecklistResult, new_value)})
    value = new_value.strip() or None
    return item.model_copy(update={target_field: value})


def _patch_checklist(
    checklist: tuple[WorkOrderChecklistItem, ...],
    *,
    target_seq: int,
    target_field: str,
    new_value: str,
) -> tuple[WorkOrderChecklistItem, ...]:
    if not (1 <= target_seq <= len(checklist)):
        raise WorkOrderPatchError(f"target_seq out of range: {target_seq}")
    index = target_seq - 1
    patched = _patch_checklist_item(checklist[index], target_field=target_field, new_value=new_value)
    return checklist[:index] + (patched,) + checklist[index + 1 :]


def _patch_boolean_checklist(
    items: tuple[BooleanChecklistItem, ...],
    *,
    target_seq: int,
    target_field: str,
    new_value: str,
) -> tuple[BooleanChecklistItem, ...]:
    if target_field != "checked":
        raise WorkOrderPatchError(f"field not editable on this checklist: {target_field}")
    if not (1 <= target_seq <= len(items)):
        raise WorkOrderPatchError(f"target_seq out of range: {target_seq}")
    index = target_seq - 1
    patched = items[index].model_copy(update={"checked": _parse_bool(new_value)})
    return items[:index] + (patched,) + items[index + 1 :]


def _patch_safety_permit_precheck(
    precheck: SafetyPermitPrecheck,
    *,
    target_seq: int,
    target_field: str,
    new_value: str,
) -> SafetyPermitPrecheck:
    if target_field not in {"applicable", "required_action"}:
        raise WorkOrderPatchError(f"field not editable on safety permit precheck: {target_field}")
    if not (1 <= target_seq <= len(precheck.questions)):
        raise WorkOrderPatchError(f"target_seq out of range: {target_seq}")
    index = target_seq - 1
    if target_field == "applicable":
        update: dict[str, object] = {"applicable": _parse_bool(new_value)}
    else:
        update = {"required_action": new_value.strip() or None}
    patched_question = precheck.questions[index].model_copy(update=update)
    questions = precheck.questions[:index] + (patched_question,) + precheck.questions[index + 1 :]
    return SafetyPermitPrecheck(
        questions=questions,
        permit_required=any(question.applicable for question in questions),
    )


_TOP_LEVEL_TEXT_SECTIONS = frozenset({"purpose", "risk_and_evidence", "outcome_and_followup"})


def apply_work_order_patch(
    content: WorkOrderStructuredContent,
    patch: WorkOrderFieldPatchRequest,
) -> WorkOrderStructuredContent:
    if patch.target_section in _TOP_LEVEL_TEXT_SECTIONS:
        if patch.target_field != "text":
            raise WorkOrderPatchError(f"field not editable on {patch.target_section}: {patch.target_field}")
        value = patch.new_value.strip()
        if not value:
            raise WorkOrderPatchError(f"{patch.target_section} cannot be empty")
        return content.model_copy(update={patch.target_section: value})
    if patch.target_section == "checklist":
        return content.model_copy(
            update={
                "checklist": _patch_checklist(
                    content.checklist,
                    target_seq=patch.target_seq,
                    target_field=patch.target_field,
                    new_value=patch.new_value,
                )
            }
        )
    if patch.target_section == "commissioning_checklist":
        return content.model_copy(
            update={
                "commissioning_checklist": _patch_checklist(
                    content.commissioning_checklist,
                    target_seq=patch.target_seq,
                    target_field=patch.target_field,
                    new_value=patch.new_value,
                )
            }
        )
    if patch.target_section == "restriction_or_prep_checklist":
        return content.model_copy(
            update={
                "restriction_or_prep_checklist": _patch_boolean_checklist(
                    content.restriction_or_prep_checklist,
                    target_seq=patch.target_seq,
                    target_field=patch.target_field,
                    new_value=patch.new_value,
                )
            }
        )
    return content.model_copy(
        update={
            "safety_permit_precheck": _patch_safety_permit_precheck(
                content.safety_permit_precheck,
                target_seq=patch.target_seq,
                target_field=patch.target_field,
                new_value=patch.new_value,
            )
        }
    )


def determine_work_order_kind(
    *,
    priority_level: str | None,
    has_evidence: bool,
) -> WorkOrderKind:
    # 문서선택 규칙(참고 자료): 대상 설비와 정비 필요성이 확인된 경우에만
    # 정비 작업지시서로 분류하고, 그 외(고장 미확정·모델 불일치·신뢰도 낮음 등)는
    # 현장 확인 작업지시서로 보낸다. "정밀점검요청서" 분기는 아직 구현하지 않았으므로
    # 안전한 기본값인 site_check로 폴백한다 (TODO: 정밀점검요청서 지원).
    if has_evidence and priority_level in {"urgent", "high"}:
        return "maintenance"
    return "site_check"


def _equipment_type_from_text(*texts: str) -> str:
    joined = " ".join(texts)
    for keyword, equipment_type in _EQUIPMENT_TYPE_KEYWORDS:
        if keyword in joined:
            return equipment_type
    return _UNKNOWN_EQUIPMENT_TYPE


async def _catalog_items(
    connection: AsyncConnection,
    *,
    work_order_kind: WorkOrderKind,
    equipment_type: str,
) -> list[dict[str, Any]]:
    result = await connection.execute(
        text(
            "SELECT instrument_or_target, check_or_task_action, pass_fail_criteria, "
            "completion_condition FROM work_order_checklist_catalog "
            "WHERE work_order_kind = :work_order_kind AND equipment_type = :equipment_type "
            "AND active ORDER BY display_order"
        ),
        {"work_order_kind": work_order_kind, "equipment_type": equipment_type},
    )
    return [dict(row) for row in result.mappings().all()]


def _checklist_from_catalog(
    rows: list[dict[str, Any]],
) -> tuple[WorkOrderChecklistItem, ...]:
    return tuple(
        WorkOrderChecklistItem(
            seq=index,
            instrument_or_target=str(row["instrument_or_target"]),
            check_or_task_action=str(row["check_or_task_action"]),
            pass_fail_criteria=row.get("pass_fail_criteria"),
            completion_condition=row.get("completion_condition"),
            result="pending",
        )
        for index, row in enumerate(rows, start=1)
    )


def _default_safety_permit_precheck() -> SafetyPermitPrecheck:
    return SafetyPermitPrecheck(
        questions=tuple(
            SafetyPermitQuestion(question=question, applicable=False)
            for question in SAFETY_PERMIT_QUESTIONS
        ),
        permit_required=False,
    )


def _prep_checklist(work_order_kind: WorkOrderKind) -> tuple[BooleanChecklistItem, ...]:
    items = _SITE_CHECK_PREP_ITEMS if work_order_kind == "site_check" else _MAINTENANCE_PREP_ITEMS
    return tuple(BooleanChecklistItem(label=label, checked=False) for label in items)


def _situation_text(ops_output: dict[str, object]) -> str:
    report_value = ops_output.get("report")
    report = cast(dict[str, object], report_value) if isinstance(report_value, dict) else {}
    return str(
        ops_output.get("situation")
        or ops_output.get("summary")
        or report.get("title")
        or "상황 정보가 확보되지 않았습니다."
    ).strip()


def _evidence_lines(ops_output: dict[str, object]) -> list[str]:
    evidence_value = ops_output.get("evidence")
    evidence_values = cast(list[object], evidence_value) if isinstance(evidence_value, list) else []
    return [
        f"{item.get('label', '근거')}: {item.get('content', '')}".strip()
        for item in evidence_values
        if isinstance(item, dict)
    ]


def _default_risk_and_evidence(evidence_lines: list[str]) -> str:
    if not evidence_lines:
        return "현장에서 대상 계기의 표시값과 설비 운전 상태를 확인하고 결과를 기록합니다."
    return " ".join(f"{line}." for line in evidence_lines)


def _default_outcome_and_followup(work_order_kind: WorkOrderKind) -> str:
    if work_order_kind == "site_check":
        return (
            "확인 결과가 모두 정상이면 정상 운전으로 간주하고 추가 모니터링을 유지합니다. "
            "이상이 확인되면 현장 관리자에게 즉시 보고하고 정비 작업지시서 발행 여부를 판단합니다."
        )
    return (
        "시운전 및 최종 확인 결과가 기준을 만족하면 정비를 완료 처리합니다. "
        "기준을 만족하지 못하면 재작업 또는 추가 정비 계획을 수립합니다."
    )


def _default_purpose(
    *,
    equipment_type: str,
    situation: str,
    checklist: tuple[WorkOrderChecklistItem, ...],
) -> str:
    target = equipment_type if equipment_type != _UNKNOWN_EQUIPMENT_TYPE else "대상 설비"
    actions = " ".join(item.check_or_task_action.rstrip(".。") + "." for item in checklist[:3])
    instruction = actions or "관련 계기 표시값과 설비 외관, 운전 상태를 확인합니다."
    return (
        f"{situation.rstrip('.。')}에 따라 {target}의 현재 운전 상태와 관련 측정값을 현장에서 확인해 주십시오. "
        f"{instruction} 알림에 포함된 현상이 현장에서도 지속되는지 확인하고, 각 점검 결과에 측정값과 이상 여부를 함께 기록해 주십시오. "
        "확인한 내용은 현재 운전 상태와 후속 정비 필요 여부를 판단할 수 있도록 구체적으로 남겨 주십시오."
    )


async def _target_building(connection: AsyncConnection | None, substation_id: int | None) -> str:
    if connection is None or substation_id is None:
        return "미확인 건물"
    building = await connection.scalar(
        text(
            "SELECT apartment_name FROM public.substation_building_context "
            "WHERE substation_id = :substation_id"
        ),
        {"substation_id": substation_id},
    )
    return str(building).strip() if building is not None and str(building).strip() else "미확인 건물"


def _strip_forbidden_terms(text_value: str) -> str:
    lowered = text_value.lower()
    if any(term in lowered for term in _FORBIDDEN_INTERNAL_TERMS):
        return "상황 정보가 확보되지 않았습니다."
    return text_value


def _field_facing_source(text_value: str, *, fallback: str) -> str:
    normalized = text_value.strip()
    if not normalized or _strip_forbidden_terms(normalized) != normalized:
        return fallback
    return normalized


class _NarrativeFields(BaseModel):
    purpose: str = Field(min_length=1, max_length=2000)
    risk_and_evidence: str = Field(min_length=1, max_length=3000)
    outcome_and_followup: str = Field(min_length=1, max_length=2000)


async def _llm_narrative(
    *,
    api_key: str | None,
    model: str,
    work_order_kind: WorkOrderKind,
    equipment_type: str,
    situation: str,
    evidence_lines: list[str],
    has_approved_procedure: bool,
) -> _NarrativeFields | None:
    if api_key is None:
        return None
    prompt = orjson.dumps(
        {
            "work_order_kind": work_order_kind,
            "equipment_type": equipment_type,
            "situation": situation,
            "evidence": evidence_lines,
            "has_approved_procedure": has_approved_procedure,
        }
    ).decode("utf-8")
    instructions = (
        "Write three Korean fields for a field-technician work order, grounded strictly "
        "in the supplied situation/evidence (do not invent numbers or facts not present):\n"
        "'purpose' (3-4 detailed field-facing sentences — describe the predicted fault situation, "
        "why this work order is issued, which equipment/readings must be checked, the exact field "
        "actions to take, and what must be recorded).\n"
        "'risk_and_evidence' (5-7 sentences, the most detailed field — explain concretely "
        "which readings/conditions triggered this work order, how they deviate from normal, "
        "and why that matters operationally. Use the specific evidence items given; if an "
        "evidence item has a metric or trend, state it plainly. This is the field technician's "
        "main justification for why the check is needed, so it must be substantive, not generic.).\n"
        "'outcome_and_followup' (3-4 sentences — what to record, report, or hand off based "
        "on the check/maintenance result).\n"
        "Never mention AI internals, model names, confidence/agreement scores, search/retrieval "
        "systems, or developer diagnostics (e.g. do not say things like 'unknown', 'partial', "
        "'snapshot', 'RAG', 'fallback'). Never write as if revising or critiquing a previous "
        "answer (no phrases like '재작성합니다', '표현을 완화해', '기존 답변'); write directly "
        "as the final field instruction itself. Write each instruction as a natural Korean "
        "sentence that makes the target, action, decision criterion, and result clear where "
        "relevant. Do not print labels or formula-like phrases such as '대상 + 행동 + "
        "판정기준 + 결과'. "
        "Only include detailed teardown/adjustment/replacement steps if "
        "has_approved_procedure is true; otherwise keep it observation-only. "
        "Return only the three fields as JSON matching the schema.\n\n" + prompt
    )
    try:
        async with AsyncOpenAI(api_key=api_key) as client:
            response = await client.responses.create(
                model=model,
                input=instructions,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "work_order_narrative",
                        "schema": _NarrativeFields.model_json_schema(),
                        "strict": False,
                    }
                },
            )
    except OpenAIError:
        LOGGER.warning("work order narrative generation failed; using deterministic fallback", exc_info=True)
        return None
    try:
        payload = orjson.loads(response.output_text)
        return _NarrativeFields.model_validate(payload)
    except (orjson.JSONDecodeError, ValidationError):
        LOGGER.warning("work order narrative response failed validation; using deterministic fallback")
        return None


async def generate_structured_work_order(
    connection: AsyncConnection,
    *,
    episode_id: str,
    ops_output: dict[str, object],
    manufacturer_id: str | None,
    substation_id: int | None,
    priority_level: str | None,
    api_key: str | None,
    model: str = "gpt-5.4-mini",
    alert_reason: str | None = None,
) -> WorkOrderStructuredContent:
    safe_source_fallback = "대상 설비의 운전 상태와 계기 표시값을 현장에서 확인합니다."
    analysis_situation = _field_facing_source(
        _situation_text(ops_output),
        fallback=safe_source_fallback,
    )
    safe_alert_reason = _field_facing_source(
        alert_reason or "",
        fallback="",
    )
    situation = safe_alert_reason or analysis_situation
    evidence_lines = [
        line for line in _evidence_lines(ops_output)
        if _strip_forbidden_terms(line) == line
    ]
    if safe_alert_reason:
        evidence_lines = [f"알림 사유: {safe_alert_reason}", *evidence_lines]
    action_plan = str(ops_output.get("action_plan") or "")
    equipment_type = _equipment_type_from_text(
        alert_reason or "",
        situation,
        action_plan,
        *evidence_lines,
    )
    suggested_work_order_kind = determine_work_order_kind(
        priority_level=priority_level,
        has_evidence=bool(evidence_lines),
    )
    has_approved_procedure = False  # RAG 승인 절차서 연결은 향후 단계에서 배선한다.
    work_order_kind: WorkOrderKind = (
        suggested_work_order_kind if has_approved_procedure else "site_check"
    )
    catalog_rows = (
        []
        if equipment_type == _UNKNOWN_EQUIPMENT_TYPE
        else await _catalog_items(
            connection,
            work_order_kind=work_order_kind,
            equipment_type=equipment_type,
        )
    )
    checklist = _checklist_from_catalog(catalog_rows)
    if not checklist and equipment_type != _UNKNOWN_EQUIPMENT_TYPE:
        raise WorkOrderGenerationError(
            f"no checklist catalog entries for {work_order_kind}/{equipment_type}"
        )
    narrative = await _llm_narrative(
        api_key=api_key,
        model=model,
        work_order_kind=work_order_kind,
        equipment_type=equipment_type,
        situation=situation,
        evidence_lines=evidence_lines,
        has_approved_procedure=has_approved_procedure,
    )
    purpose_fallback = _default_purpose(
        equipment_type=equipment_type,
        situation=situation,
        checklist=checklist,
    )
    risk_fallback = _default_risk_and_evidence(evidence_lines)
    outcome_fallback = _default_outcome_and_followup(work_order_kind)
    # 작업 목적은 같은 분석을 재생성해도 화면과 다운로드 문서가 바뀌지 않도록
    # 분석 상황·점검 항목에서 결정적으로 만들고, LLM은 위험성·후속 조치 문장에만 사용한다.
    purpose = purpose_fallback
    risk_and_evidence = _strip_forbidden_terms(
        narrative.risk_and_evidence if narrative else risk_fallback
    )
    outcome_and_followup = _strip_forbidden_terms(
        narrative.outcome_and_followup if narrative else outcome_fallback
    )
    if purpose == "상황 정보가 확보되지 않았습니다.":
        purpose = purpose_fallback
    if risk_and_evidence == "상황 정보가 확보되지 않았습니다.":
        risk_and_evidence = risk_fallback
    if outcome_and_followup == "상황 정보가 확보되지 않았습니다.":
        outcome_and_followup = outcome_fallback
    header = WorkOrderHeader(
        document_number=f"WO-{episode_id[:8]}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        issued_at=datetime.now(UTC),
        priority=priority_level or "medium",
        assignee=None,
        target_building=await _target_building(connection, substation_id),
        mechanical_room=str(substation_id) if substation_id is not None else None,
        equipment_type=equipment_type,
        work_type="현장 확인" if work_order_kind == "site_check" else "정비",
        issue_reason=safe_alert_reason or situation,
        status="검토 중",
    )
    return WorkOrderStructuredContent(
        work_order_kind=work_order_kind,
        header=header,
        purpose=purpose[:2000] or "상황 정보가 확보되지 않았습니다.",
        risk_and_evidence=risk_and_evidence[:3000] or "구체적인 근거 데이터가 확보되지 않았습니다.",
        restriction_or_prep_checklist=_prep_checklist(work_order_kind),
        checklist=checklist if work_order_kind == "site_check" else (),
        commissioning_checklist=checklist if work_order_kind == "maintenance" else (),
        outcome_and_followup=outcome_and_followup[:2000],
        safety_permit_precheck=_default_safety_permit_precheck(),
        disclaimer=PROTOTYPE_DISCLAIMER,
    )


def render_work_order_markdown(content: WorkOrderStructuredContent) -> str:
    checklist = content.checklist or content.commissioning_checklist
    evidence_detail_lines = tuple(
        f"- {item.instrument_or_target}: {item.pass_fail_criteria or item.completion_condition or ''}".strip(": ")
        for item in checklist
    )
    action_lines = tuple(
        f"{index}. {item.check_or_task_action}"
        f"{f' (판정기준: {item.pass_fail_criteria})' if item.pass_fail_criteria else ''}"
        for index, item in enumerate(checklist, start=1)
    ) or ("1. 현장 확인이 필요합니다.",)
    safety_lines = tuple(
        f"{index}. {item.label}"
        for index, item in enumerate(content.restriction_or_prep_checklist, start=1)
    ) or ("1. 현장 안전 절차를 준수합니다.",)
    title = f"{content.header.work_type} 작업지시서 · {content.header.equipment_type}"
    body = "\n".join(
        (
            title,
            "",
            "작업 목적",
            content.purpose,
            "",
            "위험성 및 근거",
            content.risk_and_evidence,
            *(("", *evidence_detail_lines) if evidence_detail_lines else ()),
            "",
            "작업 절차",
            *action_lines,
            "",
            "안전 확인",
            *safety_lines,
            "",
            "판정 및 후속 조치",
            content.outcome_and_followup,
        )
    ).strip()
    return body[:8000]
