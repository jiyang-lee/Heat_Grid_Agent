# HeatGrid Agent ML 인수 인덱스

이 문서는 `HeatGrid Agent` 프로젝트에서 ML 파트를 시작할 때 먼저 읽는 인덱스다.

ML 관련 기준은 아래 문서로 나누어 관리한다.

- `ML_NOTEBOOK_PLAN.md`
  - 노트북 진행 순서
  - 단계별 분석 방안
  - 시각화 방안
- `ML_PAPER_GUIDELINE.md`
  - 참고 논문을 구현 기준으로 바꾸는 방법
  - 모델 선택 방향
  - 평가 원칙
- `ML_OUTPUT_CONTRACT.md`
  - ML 결과를 Agent에게 어떤 형식으로 넘길지
  - 필수 필드와 권장 필드

## 현재 합의된 기준

- 프로젝트명은 `HeatGrid Agent`다.
- ML은 최종 우선순위를 직접 정하지 않는다.
- ML은 Agent가 판단할 수 있도록 이상점수, 위험도, 리드타임, 근거 센서를 제공한다.
- 모델 구조는 `Isolation Forest + LightGBM`의 2단계 구조를 기본으로 둔다.
- `Isolation Forest`는 정상 운전 패턴과 다른 이상징후를 찾고 `anomaly_score`를 산출한다.
- `LightGBM`은 Isolation Forest가 산출한 이상점수와 센서 feature, 고장신고 전 위험구간 라벨, 정비/작업 이력을 함께 사용해 `risk_score` 또는 `risk_probability`를 산출한다.
- 두 모델의 결과는 모두 고장 확정이 아니라 Agent와 Priority Engine이 참고할 위험 정보다.

## 현재 작업 범위

ML 담당자는 다음까지만 책임진다.

1. raw data 로딩
2. 전처리
3. feature 생성
4. baseline 학습
5. inference
6. 결과 export
7. Agent 전달용 계약 정리

Agent 판단, 작업지시서, 메일 발송은 ML 범위가 아니다.
