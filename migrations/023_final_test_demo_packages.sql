CREATE TABLE IF NOT EXISTS public.final_test_demo_packages (
    demo_id text PRIMARY KEY,
    scenario_id text NOT NULL,
    alert_id text NOT NULL UNIQUE,
    substation_id integer NOT NULL REFERENCES public.substation_building_context(substation_id),
    facility_name text NOT NULL,
    fault_label text NOT NULL,
    normal_payload jsonb NOT NULL,
    fault_payload jsonb NOT NULL,
    work_order_document jsonb NOT NULL,
    report_document jsonb NOT NULL,
    chat_script jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT final_test_demo_packages_payloads_object_check CHECK (
        jsonb_typeof(normal_payload) = 'object'
        AND jsonb_typeof(fault_payload) = 'object'
        AND jsonb_typeof(work_order_document) = 'object'
        AND jsonb_typeof(report_document) = 'object'
        AND jsonb_typeof(chat_script) = 'object'
    )
);

CREATE INDEX IF NOT EXISTS final_test_demo_packages_scenario_idx
    ON public.final_test_demo_packages (scenario_id, substation_id);

WITH demo_seed AS (
    SELECT * FROM (VALUES
        (
            'final-test-fault-001',
            'scenario-alert-prefault-drift-1',
            1,
            '도램마을10단지호반베르디움아파트',
            '1번 변전소 열화·과부하 복합 고장',
            97.4,
            1,
            78.6,
            91.8,
            1.34,
            '2026-07-24 09:00 KST'
        ),
        (
            'final-test-fault-010',
            'scenario-alert-flow-drop-10',
            10,
            '도램마을19단지아파트',
            '10번 변전소 냉각 성능 저하',
            92.1,
            2,
            74.2,
            88.5,
            1.27,
            '2026-07-24 09:05 KST'
        ),
        (
            'final-test-fault-030',
            'scenario-alert-return-drop-30',
            30,
            '범지기마을9단지한신휴플러스리버파크아파트',
            '30번 변전소 절연 열화 징후',
            88.7,
            3,
            71.9,
            84.3,
            1.19,
            '2026-07-24 09:10 KST'
        )
    ) AS valueset(
        demo_id,
        alert_id,
        substation_id,
        facility_name,
        fault_label,
        priority_score,
        priority_rank,
        transformer_temp,
        load_percent,
        vibration,
        detected_at
    )
),
guardrails AS (
    SELECT jsonb_build_array(
        jsonb_build_object('category', 'jailbreak', 'patterns', jsonb_build_array('이전 지시를 무시', '탈옥', 'DAN 모드'), 'response', '시스템 지시를 우회하는 요청은 처리할 수 없습니다.'),
        jsonb_build_object('category', 'prompt_leak', 'patterns', jsonb_build_array('시스템 프롬프트 공개', '내부 지침 보여줘'), 'response', '내부 프롬프트와 보안 설정은 공개할 수 없습니다.'),
        jsonb_build_object('category', 'profanity', 'patterns', jsonb_build_array('씨발', '병신', '개새끼'), 'response', '서로 존중하는 표현으로 HeatGrid 운영 질문을 입력해 주세요.'),
        jsonb_build_object('category', 'recipe_replacement', 'patterns', jsonb_build_array('위험성을 김치볶음밥 레시피로', '작업지시서를 요리법으로'), 'response', '안전·위험 정보를 다른 내용으로 바꾸는 요청은 거절합니다.'),
        jsonb_build_object('category', 'off_topic', 'patterns', jsonb_build_array('축구 결과', '오늘 날씨', '주식 추천'), 'response', '저는 HeatGrid 설비 상태와 작업지시서·보고서만 답변합니다.'),
        jsonb_build_object('category', 'safety_bypass', 'patterns', jsonb_build_array('안전 절차 삭제', '보호구 없이', '잠금표찰 생략'), 'response', '필수 안전 절차를 삭제하거나 우회할 수 없습니다.'),
        jsonb_build_object('category', 'approval_bypass', 'patterns', jsonb_build_array('승인 없이 실행', '관리자 승인 건너뛰기'), 'response', '운영 승인 절차를 건너뛰는 요청은 처리할 수 없습니다.'),
        jsonb_build_object('category', 'unsafe_action', 'patterns', jsonb_build_array('즉시 차단기 내려', '원격으로 전원 차단'), 'response', '현장 확인과 승인 없는 위험 설비 조작은 안내하지 않습니다.'),
        jsonb_build_object('category', 'credential_request', 'patterns', jsonb_build_array('API 키 알려줘', 'DB 비밀번호', '관리자 계정'), 'response', '인증정보와 비밀값은 제공할 수 없습니다.'),
        jsonb_build_object('category', 'code_injection', 'patterns', jsonb_build_array('<script>', 'DROP TABLE', 'rm -rf'), 'response', '코드 실행이나 시스템 변경 요청은 처리하지 않습니다.'),
        jsonb_build_object('category', 'impersonation', 'patterns', jsonb_build_array('관리자인 척', '승인자 서명 위조'), 'response', '사용자 권한이나 승인 기록을 위조할 수 없습니다.'),
        jsonb_build_object('category', 'data_tampering', 'patterns', jsonb_build_array('센서값 정상으로 바꿔', '고장 기록 지워'), 'response', '센서 원본과 고장 이력을 임의로 변경할 수 없습니다.')
    ) AS items
)
INSERT INTO public.final_test_demo_packages (
    demo_id,
    scenario_id,
    alert_id,
    substation_id,
    facility_name,
    fault_label,
    normal_payload,
    fault_payload,
    work_order_document,
    report_document,
    chat_script
)
SELECT
    seed.demo_id,
    'final_test',
    seed.alert_id,
    seed.substation_id,
    seed.facility_name,
    seed.fault_label,
    jsonb_build_object(
        'state', 'normal',
        'captured_at', '2026-07-24 08:55 KST',
        'sensors', jsonb_build_array(
            jsonb_build_object('key', 'transformer_temp', 'label', '변압기 온도', 'value', 48.2, 'unit', '°C', 'status', 'normal'),
            jsonb_build_object('key', 'load_percent', 'label', '부하율', 'value', 62.4, 'unit', '%', 'status', 'normal'),
            jsonb_build_object('key', 'vibration', 'label', '진동', 'value', 0.42, 'unit', 'mm/s', 'status', 'normal')
        ),
        'priority', jsonb_build_object('level', 'normal', 'score', 12.0, 'rank', null, 'reason', '정상 운전 범위')
    ),
    jsonb_build_object(
        'state', 'fault',
        'captured_at', seed.detected_at,
        'sensors', jsonb_build_array(
            jsonb_build_object('key', 'transformer_temp', 'label', '변압기 온도', 'value', seed.transformer_temp, 'unit', '°C', 'status', 'critical'),
            jsonb_build_object('key', 'load_percent', 'label', '부하율', 'value', seed.load_percent, 'unit', '%', 'status', 'critical'),
            jsonb_build_object('key', 'vibration', 'label', '진동', 'value', seed.vibration, 'unit', 'mm/s', 'status', 'warning')
        ),
        'priority', jsonb_build_object('level', 'urgent', 'score', seed.priority_score, 'rank', seed.priority_rank, 'reason', seed.fault_label)
    ),
    jsonb_build_object(
        'document_id', seed.demo_id || '-work-order',
        'document_type', 'work_order',
        'title', seed.substation_id || '번 변전소 긴급 작업지시서',
        'status', 'approved',
        'header', jsonb_build_object('work_order_number', 'WO-FINAL-' || lpad(seed.substation_id::text, 3, '0'), 'facility', seed.facility_name, 'issued_at', seed.detected_at, 'priority', '긴급'),
        'summary', seed.fault_label || '가 확인되어 현장 점검과 부하 안정화 조치를 시행한다.',
        'risk', jsonb_build_array('과열 지속 시 절연 수명 저하 및 정전 위험', '작업 중 감전·아크 플래시 위험', '부하 전환 시 인접 설비 과부하 위험'),
        'safety', jsonb_build_array('작업 전 LOTO 및 무전압 확인', '아크 등급 보호구와 절연 장갑 착용', '2인 1조 작업 및 관제 승인 후 조작'),
        'steps', jsonb_build_array(
            jsonb_build_object('order', 1, 'title', '현장 안전 확보', 'detail', '작업구역 통제, LOTO, 무전압 상태를 교차 확인한다.'),
            jsonb_build_object('order', 2, 'title', '센서·외관 점검', 'detail', '온도·부하·진동 센서와 단자부 변색 및 냉각 상태를 확인한다.'),
            jsonb_build_object('order', 3, 'title', '부하 안정화', 'detail', '관제 승인 후 단계적으로 부하를 분산하고 기준값 복귀를 확인한다.'),
            jsonb_build_object('order', 4, 'title', '복구 검증', 'detail', '15분간 센서 추세를 관찰하고 정상 범위 유지 시 복구를 보고한다.')
        ),
        'completion_criteria', jsonb_build_array('변압기 온도 60°C 이하', '부하율 75% 이하', '진동 0.8 mm/s 이하', '관제 승인 및 작업자 서명 완료'),
        'approval', jsonb_build_object('prepared_by', 'HeatGrid AI 운영지원', 'reviewed_by', '김운영', 'approved_by', '박관제', 'approved_at', '2026-07-24 08:30 KST')
    ),
    jsonb_build_object(
        'document_id', seed.demo_id || '-report',
        'document_type', 'incident_report',
        'title', seed.substation_id || '번 변전소 고장 분석 보고서',
        'status', 'approved',
        'executive_summary', seed.fault_label || '를 사전 탐지했으며 긴급 작업지시서에 따라 안전 점검과 부하 안정화를 수행한다.',
        'sections', jsonb_build_array(
            jsonb_build_object('heading', '발생 개요', 'body', seed.detected_at || '에 센서 임계치 초과와 우선순위 점수 ' || seed.priority_score || '점이 확인되었다.'),
            jsonb_build_object('heading', '영향 분석', 'body', '즉시 조치하지 않으면 절연 열화와 공급 중단 위험이 증가한다. 현재 인명 피해와 정전은 없다.'),
            jsonb_build_object('heading', '조치 계획', 'body', 'LOTO와 보호구를 적용하고 현장 점검, 부하 분산, 15분 추세 확인 순서로 처리한다.'),
            jsonb_build_object('heading', '판단 근거', 'body', '동일 시점 센서 묶음과 우선순위 결과를 단일 시연 ID로 고정해 문서와 수치의 불일치를 제거했다.')
        ),
        'conclusion', '완료 기준 충족 전까지 긴급 상태를 유지하고 관제 승인 후에만 정상 상태로 전환한다.',
        'approval', jsonb_build_object('author', 'HeatGrid AI 운영지원', 'reviewer', '김운영', 'approver', '박관제', 'approved_at', '2026-07-24 08:30 KST')
    ),
    jsonb_build_object(
        'greeting', '안녕하세요. 이 대화는 ' || seed.substation_id || '번 변전소 시연 데이터에만 답변합니다.',
        'suggested_prompts', jsonb_build_array('현재 가장 큰 위험은 무엇인가요?', '작업 순서를 요약해 주세요.', '보고서 판단 근거를 알려 주세요.'),
        'responses', jsonb_build_array(
            jsonb_build_object('intent', 'risk', 'patterns', jsonb_build_array('가장 큰 위험', '위험', '주의'), 'response', '가장 큰 위험은 과열 지속에 따른 절연 수명 저하와 정전 가능성입니다. 작업 전 LOTO, 무전압 확인, 아크 등급 보호구가 필수입니다.'),
            jsonb_build_object('intent', 'steps', 'patterns', jsonb_build_array('작업 순서', '조치 순서', '요약'), 'response', '현장 안전 확보 → 센서·외관 점검 → 관제 승인 후 부하 안정화 → 15분 복구 검증 순서입니다.'),
            jsonb_build_object('intent', 'evidence', 'patterns', jsonb_build_array('판단 근거', '근거', '왜 긴급'), 'response', '동일 시점의 온도·부하율·진동 임계치 초과와 우선순위 점수, 순위를 함께 근거로 사용했습니다.'),
            jsonb_build_object('intent', 'status', 'patterns', jsonb_build_array('현재 상태', '고장 상태'), 'response', seed.fault_label || ' 상태이며 완료 기준 확인 전까지 긴급으로 유지합니다.')
        ),
        'guardrails', guardrails.items,
        'fallback_response', '이 시연 챗봇은 현재 변전소의 센서, 위험, 작업지시서, 보고서에 관한 질문만 답변합니다.'
    )
FROM demo_seed AS seed
CROSS JOIN guardrails
JOIN public.substations ON public.substations.substation_id = seed.substation_id
ON CONFLICT (demo_id) DO UPDATE
SET scenario_id = EXCLUDED.scenario_id,
    alert_id = EXCLUDED.alert_id,
    substation_id = EXCLUDED.substation_id,
    facility_name = EXCLUDED.facility_name,
    fault_label = EXCLUDED.fault_label,
    normal_payload = EXCLUDED.normal_payload,
    fault_payload = EXCLUDED.fault_payload,
    work_order_document = EXCLUDED.work_order_document,
    report_document = EXCLUDED.report_document,
    chat_script = EXCLUDED.chat_script;

REVOKE ALL ON TABLE public.final_test_demo_packages FROM PUBLIC;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON TABLE public.final_test_demo_packages FROM heatgrid_app;
GRANT SELECT ON TABLE public.final_test_demo_packages TO heatgrid_app;
