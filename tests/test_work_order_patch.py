from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
sys.path.insert(0, str(BACKEND))


def _content():
    from incident_document_api_models import (
        BooleanChecklistItem,
        SafetyPermitPrecheck,
        SafetyPermitQuestion,
        WorkOrderChecklistItem,
        WorkOrderHeader,
        WorkOrderStructuredContent,
        SAFETY_PERMIT_QUESTIONS,
    )

    return WorkOrderStructuredContent(
        work_order_kind="site_check",
        header=WorkOrderHeader(
            document_number="WO-TEST-1",
            issued_at="2026-01-01T00:00:00Z",
            priority="high",
            target_building="테스트 단지",
            equipment_type="순환펌프",
            work_type="현장 확인",
        ),
        purpose="테스트 목적",
        risk_and_evidence="테스트 근거",
        restriction_or_prep_checklist=(
            BooleanChecklistItem(label="설비 분해를 하지 않는다", checked=False),
        ),
        checklist=(
            WorkOrderChecklistItem(
                seq=1,
                instrument_or_target="공급·환수 온도",
                check_or_task_action="온도계 표시값 확인",
                pass_fail_criteria="표시 온도가 일치",
                result="pending",
            ),
            WorkOrderChecklistItem(
                seq=2,
                instrument_or_target="순환펌프 운전음",
                check_or_task_action="이상 소음 확인",
                pass_fail_criteria="이상 소음 없음",
                result="pending",
            ),
        ),
        outcome_and_followup="테스트 결과",
        safety_permit_precheck=SafetyPermitPrecheck(
            questions=tuple(
                SafetyPermitQuestion(question=question, applicable=False)
                for question in SAFETY_PERMIT_QUESTIONS
            ),
            permit_required=False,
        ),
    )


def _patch(**overrides):
    from incident_document_api_models import WorkOrderFieldPatchRequest

    defaults = dict(
        expected_version=1,
        edited_by="tester",
        idempotency_key="patch-1",
        target_section="checklist",
        target_seq=1,
        target_field="measured_after",
        new_value="42",
    )
    defaults.update(overrides)
    return WorkOrderFieldPatchRequest(**defaults)


def test_patch_updates_top_level_risk_and_evidence_text() -> None:
    from work_order_generation import apply_work_order_patch

    content = _content()
    patch = _patch(
        target_section="risk_and_evidence",
        target_seq=1,
        target_field="text",
        new_value="최근 6시간 공급 온도가 기준 대비 3도 낮게 유지되고 있습니다.",
    )

    result = apply_work_order_patch(content, patch)

    assert result.risk_and_evidence == "최근 6시간 공급 온도가 기준 대비 3도 낮게 유지되고 있습니다."
    assert result.purpose == content.purpose
    assert result.checklist == content.checklist


def test_patch_rejects_empty_top_level_text() -> None:
    from work_order_generation import WorkOrderPatchError, apply_work_order_patch

    content = _content()
    patch = _patch(target_section="purpose", target_seq=1, target_field="text", new_value="   ")

    with pytest.raises(WorkOrderPatchError):
        apply_work_order_patch(content, patch)


def test_patch_rejects_wrong_field_name_for_top_level_text() -> None:
    from work_order_generation import WorkOrderPatchError, apply_work_order_patch

    content = _content()
    patch = _patch(target_section="outcome_and_followup", target_seq=1, target_field="body", new_value="변경")

    with pytest.raises(WorkOrderPatchError):
        apply_work_order_patch(content, patch)


def test_patch_updates_checklist_measured_value() -> None:
    from work_order_generation import apply_work_order_patch

    content = _content()
    patch = _patch(target_seq=2, target_field="measured_after", new_value="이상 없음")

    result = apply_work_order_patch(content, patch)

    assert result.checklist[1].measured_after == "이상 없음"
    assert result.checklist[0] == content.checklist[0]
    assert result.header == content.header
    assert result.purpose == content.purpose


def test_patch_updates_checklist_result_enum() -> None:
    from work_order_generation import apply_work_order_patch

    content = _content()
    patch = _patch(target_seq=1, target_field="result", new_value="pass")

    result = apply_work_order_patch(content, patch)

    assert result.checklist[0].result == "pass"


def test_patch_rejects_invalid_result_value() -> None:
    from work_order_generation import WorkOrderPatchError, apply_work_order_patch

    content = _content()
    patch = _patch(target_seq=1, target_field="result", new_value="not-a-real-result")

    with pytest.raises(WorkOrderPatchError):
        apply_work_order_patch(content, patch)


def test_patch_rejects_field_not_in_allowlist() -> None:
    from work_order_generation import WorkOrderPatchError, apply_work_order_patch

    content = _content()
    patch = _patch(target_seq=1, target_field="instrument_or_target", new_value="변조 시도")

    with pytest.raises(WorkOrderPatchError):
        apply_work_order_patch(content, patch)


def test_patch_rejects_out_of_range_seq() -> None:
    from work_order_generation import WorkOrderPatchError, apply_work_order_patch

    content = _content()
    patch = _patch(target_seq=99, target_field="result", new_value="pass")

    with pytest.raises(WorkOrderPatchError):
        apply_work_order_patch(content, patch)


def test_patch_toggles_boolean_checklist() -> None:
    from work_order_generation import apply_work_order_patch

    content = _content()
    patch = _patch(
        target_section="restriction_or_prep_checklist",
        target_seq=1,
        target_field="checked",
        new_value="true",
    )

    result = apply_work_order_patch(content, patch)

    assert result.restriction_or_prep_checklist[0].checked is True


def test_patch_recomputes_permit_required_from_questions() -> None:
    from work_order_generation import apply_work_order_patch

    content = _content()
    assert content.safety_permit_precheck.permit_required is False

    patch = _patch(
        target_section="safety_permit_precheck",
        target_seq=3,
        target_field="applicable",
        new_value="true",
    )

    result = apply_work_order_patch(content, patch)

    assert result.safety_permit_precheck.questions[2].applicable is True
    assert result.safety_permit_precheck.permit_required is True


def test_patch_ignores_client_supplied_permit_required_and_recomputes() -> None:
    from work_order_generation import apply_work_order_patch

    content = _content()
    # Even if a caller tried to directly flip permit_required without any
    # applicable question, only the questions-derived value is trusted.
    patch = _patch(
        target_section="safety_permit_precheck",
        target_seq=1,
        target_field="applicable",
        new_value="false",
    )

    result = apply_work_order_patch(content, patch)

    assert result.safety_permit_precheck.permit_required is False
