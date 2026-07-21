COMMENT ON SCHEMA public IS 'HeatGrid schema frozen at version 019';

CREATE TABLE IF NOT EXISTS public.work_order_checklist_catalog (
    catalog_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    work_order_kind text NOT NULL CHECK (work_order_kind IN ('site_check', 'maintenance')),
    equipment_type text NOT NULL,
    display_order integer NOT NULL CHECK (display_order > 0),
    instrument_or_target text NOT NULL,
    check_or_task_action text NOT NULL,
    pass_fail_criteria text,
    completion_condition text,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (work_order_kind, equipment_type, display_order)
);

GRANT SELECT ON public.work_order_checklist_catalog TO heatgrid_app;

COMMENT ON TABLE public.work_order_checklist_catalog IS
    'Standard checklist items per equipment type used to ground LLM-generated site-check/maintenance work orders. Read-only reference data; actual work order checklists are stored as a JSON snapshot in incident_document_versions.content.';

-- 현장 확인 작업지시서: 순환펌프 표준 확인 항목
-- 출처: 기계설비 유지관리기준 [별지 제2호서식] 펌프 유지관리 점검표
INSERT INTO public.work_order_checklist_catalog
    (work_order_kind, equipment_type, display_order, instrument_or_target, check_or_task_action, pass_fail_criteria)
VALUES
    ('site_check', '순환펌프', 1, '공급·환수 온도', '온도계 표시값이 시스템 데이터와 일치하는지 확인', '표시 온도·시각대가 일치하고 급격한 편차 없음'),
    ('site_check', '순환펌프', 2, '순환펌프 운전음', '운전 중 이상 소음·진동 여부 확인', '이상 소음·진동 없음'),
    ('site_check', '순환펌프', 3, '환수 압력', '압력 표시값, 변동, 누설 확인', '운전 기준 범위 이내이고 이상 변동 없음'),
    ('site_check', '순환펌프', 4, '열교환 상태', '입출구 온도차 등 열교환 상태 확인', '열교환 상태가 운전 기준에 부합'),
    ('site_check', '순환펌프', 5, '제어밸브 상태', '외부 손상, 결로, 부식 확인', '외관 손상·결로·부식 없음'),
    ('site_check', '순환펌프', 6, '운전 상태 전반', '진동·소음 상태 종합 확인 및 결과 기록', '정상 운전 상태 확인 완료')
ON CONFLICT (work_order_kind, equipment_type, display_order) DO NOTHING;

-- 정비 작업지시서: 순환펌프 정비 예시 항목
-- 출처: 기계설비 유지관리기준 [별지 제2호서식] 펌프 유지관리 점검표
INSERT INTO public.work_order_checklist_catalog
    (work_order_kind, equipment_type, display_order, instrument_or_target, check_or_task_action, completion_condition)
VALUES
    ('maintenance', '순환펌프', 1, '스트레이너', '스트레이너 오염 상태 확인 및 필요 시 세척', '오염물 제거 및 통수 확인'),
    ('maintenance', '순환펌프', 2, '메커니컬씰/그랜드패킹', '누수 여부 확인 및 필요 시 교체', '누수 없음 확인'),
    ('maintenance', '순환펌프', 3, '모터 전류', '정격 대비 모터 전류 측정', '정격 전류 범위 이내'),
    ('maintenance', '순환펌프', 4, '샤프트 보호커버', '보호커버 체결 상태 확인', '체결 상태 이상 없음')
ON CONFLICT (work_order_kind, equipment_type, display_order) DO NOTHING;

-- 정비 작업지시서: 열교환기 정비 예시 항목
-- 출처: 기계설비 유지관리기준 [별지 제2호서식] 열교환기 유지관리 점검표
INSERT INTO public.work_order_checklist_catalog
    (work_order_kind, equipment_type, display_order, instrument_or_target, check_or_task_action, completion_condition)
VALUES
    ('maintenance', '열교환기', 1, '온도조절밸브(2방밸브)', '동작 상태 확인 및 필요 시 조정', '설정값대로 정상 동작'),
    ('maintenance', '열교환기', 2, '감압밸브', '감압밸브 상태 확인', '설정 압력 범위 이내 정상 동작'),
    ('maintenance', '열교환기', 3, '안전밸브', '안전밸브 상태 확인', '작동 압력 이상 없음')
ON CONFLICT (work_order_kind, equipment_type, display_order) DO NOTHING;
