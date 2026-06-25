"""시스템 프롬프트 + 보고서/메일 markdown 템플릿.

운영 원칙: 고장 확정 금지, 근거·원인후보·점검항목·한계 포함, 운영자 검토 전제, 자동 발송 없음.
"""

from __future__ import annotations

SYSTEM_PROMPT = """당신은 HeatGrid 지역난방 기계실 운영 보조 에이전트입니다.

역할:
- 우선순위 점수 상위 대상에 대해 운영자가 검토할 점검 보고서와 작업자 메일 '초안'을 만듭니다.

규칙(반드시 준수):
- 고장을 단정하지 않습니다. "위험 가능성", "점검 필요"로만 표현합니다.
- 보고서에는 근거(센서/점수), 원인 후보(확정 아님), 권고 점검 항목, 한계를 반드시 포함합니다.
- 모든 산출물은 운영자 검토 전제이며 자동 발송하지 않습니다.

작업 절차:
1. get_top_priority(n) 으로 상위 n개 점검 대상 목록을 얻습니다.
2. 각 대상마다 get_substation_context, get_sensor_evidence 로 근거를 모읍니다.
3. draft_work_order 로 보고서 초안을, draft_email 로 메일 초안을 저장합니다.
4. 저장된 파일 경로를 보고합니다.
"""

WORK_ORDER_TEMPLATE = """# 점검 작업지시 초안 — Substation {substation_id} (검토 필요, 자동발송 아님)

- 대상: {manufacturer} / substation {substation_id}
- 윈도우: {window_start} ~ {window_end}
- 우선순위: {priority_score} ({priority_level}) · 위험등급 {risk_level} · 예상 리드타임 {lead_time_bucket}

## 근거 (센서/점수)
{evidence}

## 원인 후보 (확정 아님)
{causes}

## 권고 점검 항목
{checklist}

## 설비 컨텍스트
{context}

## 한계
- 단일 6시간 윈도우 추론 결과입니다. 현장 확인 전 고장으로 단정할 수 없습니다.
- 본 문서는 운영자 검토용 초안이며 자동 발송되지 않습니다.
"""

EMAIL_TEMPLATE = """제목: [점검요청·검토필요] Substation {substation_id} 우선 점검 대상 안내

안녕하세요,

아래 대상에 대한 우선 점검을 요청드립니다(운영자 검토용 초안).

- 대상: {manufacturer} / substation {substation_id}
- 점검 윈도우: {window_start} ~ {window_end}
- 우선순위: {priority_score} ({priority_level}) — 위험 가능성 높음(고장 확정 아님)
- 주요 근거: {evidence_short}

상세 근거와 권고 점검 항목은 첨부 보고서를 참고해 주세요:
{work_order_path}

※ 본 메일은 자동 발송되지 않으며, 운영자 확인 후 전달 바랍니다.
"""

DEFAULT_CAUSES = "- 순환펌프/열교환기 이상 가능성, 밸브 제어 이상 가능성 (현장 점검으로 확인 필요)"
DEFAULT_CHECKLIST = (
    "1. 주요 이상 센서 계측값 현장 확인\n"
    "2. 순환펌프 흡입측 압력·기포 점검\n"
    "3. 1차측 차압 및 스트레이너 점검\n"
    "4. 제어 모드/밸브 동작 상태 확인"
)
