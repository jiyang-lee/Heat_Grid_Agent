from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
sys.path.insert(0, str(BACKEND))


def test_determine_work_order_kind_defaults_to_site_check() -> None:
    from work_order_generation import determine_work_order_kind

    assert determine_work_order_kind(priority_level=None, has_evidence=False) == "site_check"
    assert determine_work_order_kind(priority_level="urgent", has_evidence=False) == "site_check"
    assert determine_work_order_kind(priority_level="medium", has_evidence=True) == "site_check"


def test_determine_work_order_kind_routes_confirmed_asset_to_maintenance() -> None:
    from work_order_generation import determine_work_order_kind

    assert determine_work_order_kind(priority_level="urgent", has_evidence=True) == "maintenance"
    assert determine_work_order_kind(priority_level="high", has_evidence=True) == "maintenance"


def test_equipment_type_from_text_detects_known_keywords() -> None:
    from work_order_generation import _equipment_type_from_text

    assert _equipment_type_from_text("순환펌프 이상 소음 발생") == "순환펌프"
    assert _equipment_type_from_text("열교환기 온도차 이상") == "열교환기"
    assert _equipment_type_from_text("알 수 없는 설비") == "순환펌프"


def test_forbidden_internal_terms_are_stripped() -> None:
    from work_order_generation import _strip_forbidden_terms

    assert _strip_forbidden_terms("RAG 검색 결과가 부족합니다") == "상황 정보가 확보되지 않았습니다."
    assert _strip_forbidden_terms("공급 온도가 기준보다 낮습니다") == "공급 온도가 기준보다 낮습니다"


def test_render_work_order_markdown_includes_expected_headings() -> None:
    from incident_document_api_models import (
        BooleanChecklistItem,
        SafetyPermitPrecheck,
        SafetyPermitQuestion,
        WorkOrderChecklistItem,
        WorkOrderHeader,
        WorkOrderStructuredContent,
        SAFETY_PERMIT_QUESTIONS,
    )
    from work_order_generation import render_work_order_markdown

    content = WorkOrderStructuredContent(
        work_order_kind="site_check",
        header=WorkOrderHeader(
            document_number="WO-TEST-1",
            issued_at="2026-01-01T00:00:00Z",
            priority="high",
            target_building="테스트 단지",
            equipment_type="순환펌프",
            work_type="현장 확인",
        ),
        purpose="순환펌프 이상 신호가 확인되어 현장 확인이 필요합니다.",
        risk_and_evidence="최근 6시간 공급 온도가 기준 대비 3도 낮게 유지되고 있습니다.",
        restriction_or_prep_checklist=(
            BooleanChecklistItem(label="설비 분해를 하지 않는다"),
        ),
        checklist=(
            WorkOrderChecklistItem(
                seq=1,
                instrument_or_target="공급·환수 온도",
                check_or_task_action="온도계 표시값 확인",
                pass_fail_criteria="표시 온도가 시스템 데이터와 일치",
                result="pending",
            ),
        ),
        outcome_and_followup="정상이면 모니터링을 유지합니다.",
        safety_permit_precheck=SafetyPermitPrecheck(
            questions=tuple(
                SafetyPermitQuestion(question=question, applicable=False)
                for question in SAFETY_PERMIT_QUESTIONS
            ),
            permit_required=False,
        ),
    )

    markdown = render_work_order_markdown(content)

    assert "작업 목적" in markdown
    assert "위험성 및 근거" in markdown
    assert "최근 6시간 공급 온도가 기준 대비 3도 낮게" in markdown
    assert "작업 절차" in markdown
    assert "안전 확인" in markdown
    assert "판정 및 후속 조치" in markdown
    assert "공급·환수 온도" in markdown


def test_safety_permit_precheck_requires_exactly_six_questions() -> None:
    from incident_document_api_models import SafetyPermitPrecheck, SafetyPermitQuestion

    with pytest.raises(Exception):
        SafetyPermitPrecheck(
            questions=(SafetyPermitQuestion(question="q1", applicable=False),),
            permit_required=False,
        )


def test_work_order_structured_content_disclaimer_has_a_default() -> None:
    from incident_document_api_models import (
        PROTOTYPE_DISCLAIMER,
        SafetyPermitPrecheck,
        SafetyPermitQuestion,
        WorkOrderHeader,
        WorkOrderStructuredContent,
        SAFETY_PERMIT_QUESTIONS,
    )

    content = WorkOrderStructuredContent(
        work_order_kind="site_check",
        header=WorkOrderHeader(
            document_number="WO-TEST-2",
            issued_at="2026-01-01T00:00:00Z",
            priority="high",
            target_building="테스트 단지",
            equipment_type="순환펌프",
            work_type="현장 확인",
        ),
        purpose="테스트",
        risk_and_evidence="테스트 근거",
        outcome_and_followup="테스트",
        safety_permit_precheck=SafetyPermitPrecheck(
            questions=tuple(
                SafetyPermitQuestion(question=question, applicable=False)
                for question in SAFETY_PERMIT_QUESTIONS
            ),
            permit_required=False,
        ),
    )

    assert content.disclaimer == PROTOTYPE_DISCLAIMER


def test_content_from_row_dispatches_by_document_type() -> None:
    from incident_document_api_models import IncidentDocumentContent
    from incident_document_content import content_from_row

    legacy_row = {
        "document_type": "incident_report",
        "content": {
            "title": "테스트",
            "body": "본문",
            "actions": (),
            "evidence": (),
            "safety_notes": "",
        },
    }
    assert isinstance(content_from_row(legacy_row), IncidentDocumentContent)

    legacy_work_order_row = {
        "document_type": "work_order",
        "content": {
            "title": "테스트",
            "body": "본문",
            "actions": (),
            "evidence": (),
            "safety_notes": "",
        },
    }
    assert isinstance(content_from_row(legacy_work_order_row), IncidentDocumentContent)
