COMMENT ON SCHEMA public IS 'HeatGrid schema frozen at version 020';

-- 현장 확인 작업지시서: 열교환기 표준 확인 항목
-- 출처: 기계설비 유지관리기준 [별지 제2호서식] 열교환기 유지관리 점검표
INSERT INTO public.work_order_checklist_catalog
    (work_order_kind, equipment_type, display_order, instrument_or_target, check_or_task_action, pass_fail_criteria)
VALUES
    ('site_check', '열교환기', 1, '환수온도', '현장 온도계 표시값과 시스템 기록값을 비교 확인', '표시 시각과 온도가 일치하고 급격한 편차 없음'),
    ('site_check', '열교환기', 2, '입·출구 온도', '열교환기 입·출구 온도와 온도차 확인', '운전 기준 온도 범위와 온도차에 부합'),
    ('site_check', '열교환기', 3, '온도조절밸브', '밸브 개도와 동작 상태 확인', '설정값에 따라 걸림 없이 동작'),
    ('site_check', '열교환기', 4, '열교환기 외관', '누수, 결로, 부식과 보온재 손상 여부 확인', '누수·결로·부식·보온재 손상 없음'),
    ('site_check', '열교환기', 5, '압력 상태', '1·2차측 압력 표시값과 변동 확인', '운전 기준 범위 이내이고 급격한 변동 없음'),
    ('site_check', '열교환기', 6, '운전 상태 전반', '이상 소음과 진동 여부를 확인하고 결과 기록', '이상 소음·진동 없음')
ON CONFLICT (work_order_kind, equipment_type, display_order) DO NOTHING;
