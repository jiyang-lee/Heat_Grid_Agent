ALTER TABLE public.final_test_demo_packages
    ADD COLUMN IF NOT EXISTS work_order_versions jsonb NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS report_versions jsonb NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
    ALTER TABLE public.final_test_demo_packages
        ADD CONSTRAINT final_test_demo_packages_versions_array_check CHECK (
            jsonb_typeof(work_order_versions) = 'array'
            AND jsonb_typeof(report_versions) = 'array'
        );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

WITH base AS (
    SELECT
        demo_id,
        substation_id,
        fault_label,
        fault_payload,
        work_order_document,
        report_document,
        chat_script,
        jsonb_set(
            jsonb_set(
                jsonb_set(
                    work_order_document,
                    '{document_id}',
                    to_jsonb(demo_id || '-work-order-v2'),
                    true
                ),
                '{status}',
                '"draft"'::jsonb,
                true
            ),
            '{summary}',
            to_jsonb(
                fault_label || '에 대응하여 고장 원인을 확인하고, 현장 안전 확보와 부하 안정화 후 센서 정상 복귀를 검증하는 것을 작업 목적으로 한다.'
            ),
            true
        ) AS work_order_v2,
        jsonb_set(
            jsonb_set(
                jsonb_set(
                    report_document,
                    '{document_id}',
                    to_jsonb(demo_id || '-report-v2'),
                    true
                ),
                '{status}',
                '"draft"'::jsonb,
                true
            ),
            '{sections}',
            COALESCE(report_document -> 'sections', '[]'::jsonb) || jsonb_build_array(
                jsonb_build_object(
                    'heading', '조치 결과 상세',
                    'body',
                    '변압기 온도 ' || COALESCE(fault_payload #>> '{sensors,0,value}', '-') || COALESCE(fault_payload #>> '{sensors,0,unit}', '')
                    || ', 부하율 ' || COALESCE(fault_payload #>> '{sensors,1,value}', '-') || COALESCE(fault_payload #>> '{sensors,1,unit}', '')
                    || ', 진동 ' || COALESCE(fault_payload #>> '{sensors,2,value}', '-') || COALESCE(fault_payload #>> '{sensors,2,unit}', '')
                    || '를 기준으로 현장 점검, 부하 분산, 복구 추세 확인 결과를 기록한다.'
                )
            ),
            true
        ) AS report_v2
    FROM public.final_test_demo_packages
    WHERE scenario_id = 'final_test'
),
revisions AS (
    SELECT
        base.*,
        jsonb_set(
            jsonb_set(
                jsonb_set(
                    work_order_v2,
                    '{document_id}',
                    to_jsonb(demo_id || '-work-order-v3'),
                    true
                ),
                '{safety}',
                COALESCE(work_order_v2 -> 'safety', '[]'::jsonb) || jsonb_build_array(
                    '차단기별 LOTO 번호와 무전압 측정값을 작업표에 기록',
                    '복전 전 현장 책임자와 관제 담당자의 교차 승인 확인'
                ),
                true
            ),
            '{completion_criteria}',
            COALESCE(work_order_v2 -> 'completion_criteria', '[]'::jsonb) || jsonb_build_array(
                '작업 목적·담당자·작업 범위 브리핑 기록 완료',
                'LOTO·무전압 측정·복전 승인 기록 완료'
            ),
            true
        ) AS work_order_v3,
        jsonb_set(
            jsonb_set(
                jsonb_set(
                    report_v2,
                    '{document_id}',
                    to_jsonb(demo_id || '-report-v3'),
                    true
                ),
                '{sections}',
                COALESCE(report_v2 -> 'sections', '[]'::jsonb) || jsonb_build_array(
                    jsonb_build_object(
                        'heading', '후속 점검 계획',
                        'body', '복구 후 15분, 1시간, 24시간 시점의 온도·부하·진동 추세를 재확인하고 기준 이탈 시 긴급 상태로 재분류한다.'
                    )
                ),
                true
            ),
            '{conclusion}',
            to_jsonb('현장 조치와 센서 복구 검증을 완료한 뒤 운영자가 결과를 확인하고 관제 책임자가 승인한 경우에만 정상 상태로 전환한다.'::text),
            true
        ) AS report_v3
    FROM base
)
UPDATE public.final_test_demo_packages AS package
SET
    work_order_versions = jsonb_build_array(
        jsonb_build_object('version', 1, 'change_summary', '최초 사전 승인본', 'document', revisions.work_order_document),
        jsonb_build_object('version', 2, 'change_summary', '작업 목적 상세화', 'document', revisions.work_order_v2),
        jsonb_build_object('version', 3, 'change_summary', '안전 확인 및 완료 기준 보강', 'document', revisions.work_order_v3)
    ),
    report_versions = jsonb_build_array(
        jsonb_build_object('version', 1, 'change_summary', '최초 사전 승인본', 'document', revisions.report_document),
        jsonb_build_object('version', 2, 'change_summary', '조치 결과와 센서 수치 상세화', 'document', revisions.report_v2),
        jsonb_build_object('version', 3, 'change_summary', '결론과 후속 점검 계획 보강', 'document', revisions.report_v3)
    ),
    chat_script = jsonb_build_object(
        'greeting', '안녕하세요. 이 대화는 ' || revisions.substation_id || '번 기계실 관련 대화만 답변합니다.',
        'suggested_prompts', jsonb_build_array(
            '현재 가장 큰 위험은 무엇인가요?',
            '작업목적의 내용을 세부적으로 바꿔줘',
            '안전확인 내용을 현장 기준으로 보강해줘',
            '조치 결과를 세부적으로 작성해줘',
            '결론과 후속 점검 내용을 구체적으로 바꿔줘'
        ),
        'responses', jsonb_build_array(
            jsonb_build_object(
                'intent', 'risk',
                'patterns', jsonb_build_array('현재 가장 큰 위험은 무엇인가요?', '가장 큰 위험', '위험', '주의'),
                'response', '가장 큰 위험은 과열 지속에 따른 절연 수명 저하와 정전 가능성입니다. 작업 전 LOTO, 무전압 확인, 아크 등급 보호구가 필수입니다.'
            ),
            jsonb_build_object(
                'intent', 'revise_work_purpose',
                'patterns', jsonb_build_array('작업목적의 내용을 세부적으로 바꿔줘', '작업 목적을 상세하게 수정해줘'),
                'response', '작업 목적에 고장 원인 확인, 현장 안전 확보, 부하 안정화, 센서 정상 복귀 검증을 추가한 v2 변경안을 불러왔습니다.',
                'action', jsonb_build_object(
                    'type', 'preview_document_version',
                    'document_type', 'work_order',
                    'source_version', 1,
                    'target_version', 2,
                    'confirmation_message', '작업지시서를 v2로 수정하시겠습니까?',
                    'applied_response', '작업지시서가 v2로 변경되었습니다. 기존 v1도 버전 목록에서 확인할 수 있습니다.',
                    'cancelled_response', 'v2 변경을 취소했습니다. 작업지시서 v1을 유지합니다.'
                )
            ),
            jsonb_build_object(
                'intent', 'reinforce_safety',
                'patterns', jsonb_build_array('안전확인 내용을 현장 기준으로 보강해줘', '안전 확인을 더 구체적으로 바꿔줘'),
                'response', 'LOTO 번호, 무전압 측정값, 복전 전 교차 승인 절차를 보강한 v3 변경안을 불러왔습니다.',
                'action', jsonb_build_object(
                    'type', 'preview_document_version',
                    'document_type', 'work_order',
                    'source_version', 2,
                    'target_version', 3,
                    'confirmation_message', '작업지시서를 v3로 수정하시겠습니까?',
                    'applied_response', '작업지시서가 v3로 변경되었습니다. v1·v2·v3를 버전 목록에서 비교할 수 있습니다.',
                    'cancelled_response', 'v3 변경을 취소했습니다. 현재 작업지시서 버전을 유지합니다.'
                )
            ),
            jsonb_build_object(
                'intent', 'detail_report_actions',
                'patterns', jsonb_build_array('조치 결과를 세부적으로 작성해줘', '보고서 조치 결과를 상세하게 바꿔줘'),
                'response', '센서 수치와 현장 점검·부하 분산·복구 확인 결과를 추가한 보고서 v2 변경안을 불러왔습니다.',
                'action', jsonb_build_object(
                    'type', 'preview_document_version',
                    'document_type', 'report',
                    'source_version', 1,
                    'target_version', 2,
                    'confirmation_message', '보고서를 v2로 수정하시겠습니까?',
                    'applied_response', '보고서가 v2로 변경되었습니다. 기존 v1도 버전 목록에서 확인할 수 있습니다.',
                    'cancelled_response', '보고서 v2 변경을 취소했습니다. v1을 유지합니다.'
                )
            ),
            jsonb_build_object(
                'intent', 'reinforce_report_conclusion',
                'patterns', jsonb_build_array('결론과 후속 점검 내용을 구체적으로 바꿔줘', '보고서 결론을 최종본으로 바꿔줘'),
                'response', '정상 전환 조건과 15분·1시간·24시간 후속 점검 계획을 추가한 보고서 v3 변경안을 불러왔습니다.',
                'action', jsonb_build_object(
                    'type', 'preview_document_version',
                    'document_type', 'report',
                    'source_version', 2,
                    'target_version', 3,
                    'confirmation_message', '보고서를 v3로 수정하시겠습니까?',
                    'applied_response', '보고서가 v3로 변경되었습니다. v1·v2·v3를 버전 목록에서 비교할 수 있습니다.',
                    'cancelled_response', '보고서 v3 변경을 취소했습니다. 현재 보고서 버전을 유지합니다.'
                )
            ),
            jsonb_build_object(
                'intent', 'steps',
                'patterns', jsonb_build_array('작업 순서', '조치 순서', '요약'),
                'response', '현장 안전 확보 → 센서·외관 점검 → 관제 승인 후 부하 안정화 → 15분 복구 검증 순서입니다.'
            ),
            jsonb_build_object(
                'intent', 'evidence',
                'patterns', jsonb_build_array('판단 근거', '근거', '왜 긴급'),
                'response', '동일 시점의 온도·부하율·진동 임계치 초과와 우선순위 점수, 순위를 함께 근거로 사용했습니다.'
            ),
            jsonb_build_object(
                'intent', 'status',
                'patterns', jsonb_build_array('현재 상태', '고장 상태'),
                'response', revisions.fault_label || ' 상태이며 완료 기준 확인 전까지 긴급으로 유지합니다.'
            )
        ),
        'guardrails', revisions.chat_script -> 'guardrails',
        'fallback_response', '이 시연 챗봇은 현재 기계실의 센서, 위험, 작업지시서, 보고서에 관한 질문만 답변합니다. 추천 질문을 선택하면 준비된 문서 변경안을 확인할 수 있습니다.'
    )
FROM revisions
WHERE package.demo_id = revisions.demo_id;
