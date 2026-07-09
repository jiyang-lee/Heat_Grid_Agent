# 이상 징후 보고서 양식 기준

## 목적

이 문서는 `report_generator_hsj`의 이상 징후 보고서가 어떤 흐름으로 구성되어야 하는지 정리한 기준 문서입니다.
현재 보고서는 고장 확정 보고서가 아니라, 모델과 운영 근거를 바탕으로 운영자가 우선 확인할 항목을 정리하는 "이상 탐지 기반 운영 검토 보고서"로 둡니다.

## 참고한 보고서 구조

운영 보고서 양식은 장애 사후보고서와 설비 점검 보고서의 구조를 섞어 사용합니다.

- Google SRE Postmortem Culture: 사고 기록에는 영향, 조치, 원인, 재발 방지 조치가 포함되어야 하며, 비난보다 시스템 개선에 초점을 둡니다.
- Google SRE Workbook Postmortem Culture: 좋은 사후보고서는 잘 작성되고, 실제 조치로 이어지며, 공유되어야 합니다.
- Atlassian Incident Postmortem Template: summary, impact, detection, response, root cause, lessons learned, corrective actions처럼 같은 구조를 반복 사용하면 누락을 줄이고 나중에 비교하기 쉽습니다.

출처:

- https://sre.google/sre-book/postmortem-culture/
- https://sre.google/workbook/postmortem-culture/
- https://www.atlassian.com/incident-management/postmortem/templates

## HeatGrid 적용 양식

HeatGrid에서는 실제 고장 확정 전 단계가 많기 때문에 `root cause`를 그대로 쓰지 않고 `추정 원인`과 `확인/배제 방법`으로 낮춰 씁니다.

권장 흐름:

1. 요약: 무엇이 어디서 언제 감지되었는지
2. 대상/시점: 열수급 지점, 설비 구성, 분석 구간
3. 영향 평가: 공급 안정성, 민원 가능성, 에너지 효율, 운영 부담
4. 탐지 근거: 위험도, 주요 센서 변화, 진단 근거, 기상/부하 맥락
5. 운영 맥락: 계절, 외기 조건, 부하 변동, 자료 한계
6. 추정 원인: 단정이 아닌 후보와 확인/배제 방법
7. 즉시 조치: 운영자가 바로 확인할 항목
8. 후속 모니터링: 다음 교대까지 추적할 항목
9. 근거 추적: 내부 데이터, 외부 데이터, 문헌 근거의 연결

## 사용자 문장 규칙

보고서 본문에는 개발자가 쓰는 내부 용어를 그대로 노출하지 않습니다.

- `RAG`, `pgvector`, `chunk`, `retrieval` 대신 "운영 기준 근거", "문헌 근거", "과거 사례 근거"처럼 씁니다.
- `current_best`, `m1_specialist`, `fault_group` 같은 필드명은 쓰지 않습니다.
- `Urgent`, `High`, `Medium`, `Low`는 schema enum에는 남기되 사용자 문장에서는 `긴급`, `높음`, `보통`, `낮음`으로 씁니다.
- 고장 확정 전에는 "고장입니다", "원인은 ...입니다"처럼 단정하지 않습니다.
- 점수는 사용자에게 보이는 곳에서 소수점 둘째 자리까지만 표시합니다.
- 화면에서 번호가 붙을 수 있으므로 조치 문장에는 `1.`, `-`, `*` 같은 접두어를 붙이지 않습니다.

## 현재 구현 반영 위치

- 프롬프트: `report_generator_hsj/report_generator/prompts/anomaly_report_prompt.md`
- 공통 LLM 시스템 지시: `report_generator_hsj/report_generator/src/report_utils.py`
- 출력 후처리: `report_generator_hsj/report_generator/src/generate_anomaly_report.py`
