# 08. Agent / Priority Engine 전달용 Export

이 문서는 `PREPROCESSING/hsj/08_export_for_agent.ipynb`의 목적, 입력 데이터, 생성 방식, 산출물을 정리한다.

## 1. 목적

08 단계의 목적은 05, 06, 07에서 만든 모델 결과를 다음 단계의 Priority Engine 또는 Agent가 읽기 쉬운 형태로 합치는 것이다.

중요한 점은 08이 최종 점검 우선순위를 결정하는 단계가 아니라는 것이다. 현재 단계의 산출물은 다음 질문에 답하기 위한 입력값 묶음이다.

```text
어떤 설비를 먼저 점검해야 하는가
왜 해당 설비의 우선순위가 높은가
이상 징후의 주요 원인은 무엇인가
운영자가 어떤 조치를 취해야 하는가
현재 상태가 관찰, 주의, 경고, 긴급 중 어디에 해당하는가
```

따라서 08에서는 `priority_input_score`와 `status_candidate`를 만들지만, 이 값들은 최종 운영 판단이 아니라 후속 우선순위 회귀/스코어링 모델의 baseline 입력 후보로 해석해야 한다.

## 2. 입력 데이터

08은 모델을 새로 학습하지 않고 기존 산출물을 읽는다.

```text
data/processed/ml_supervised/agent_model_outputs.csv
data/processed/ml_explainability/decision_feature_evidence.csv
data/processed/ml_explainability/false_positive_group_diagnostics.csv
data/processed/ml_supervised/risk_leadtime_model_metadata.json
data/processed/ml_explainability/explainability_metadata.json
```

각 파일의 역할은 다음과 같다.

- `agent_model_outputs.csv`: 06에서 만든 이상 점수, 위험 확률, 리드타임 3중분류 결과를 담은 기준 테이블이다.
- `decision_feature_evidence.csv`: 07에서 만든 window별 주요 센서, 센서 점수, 근거 설명을 담은 테이블이다.
- `false_positive_group_diagnostics.csv`: 위험도 모델이 특정 group에서 과대위험 입력값을 만들 수 있는지 진단한 결과다.
- metadata JSON 파일: 어떤 06/07 run을 기준으로 export했는지 추적하기 위한 버전 정보다.

병합 기준은 다음 5개 컬럼이다.

```text
manufacturer
substation_id
source_file
window_start
window_end
```

## 3. 처리 방식

08은 06의 `agent_model_outputs.csv`를 기준으로 left join을 수행한다. 07의 근거 테이블은 고위험 또는 진단 대상 window 중심으로 생성되어 전체 window보다 행 수가 적기 때문이다.

근거가 없는 window는 삭제하지 않는다. 실제 우선순위 모델에서는 근거가 없는 낮은 위험 window도 정상적인 비교 대상이 되기 때문에 전체 window를 보존하는 것이 더 안전하다.

추가로 생성하는 주요 입력 후보는 다음과 같다.

- `risk_margin`: `risk_probability - risk_threshold`로 계산한 위험도 임계값 대비 여유다.
- `anomaly_margin`: `anomaly_score - anomaly_threshold`로 계산한 이상 점수 임계값 대비 여유다.
- `leadtime_urgency_score`: 리드타임 3중분류를 우선순위 입력용 긴급도 점수로 변환한 값이다.
- `priority_input_score`: 위험 확률, 리드타임 긴급도, 이상 label, 리드타임 confidence를 조합한 baseline 입력 점수다.
- `status_candidate`: `관찰`, `주의`, `경고`, `긴급` 중 하나로 만든 후보 상태 등급이다.
- `overestimated_risk_group_flag`: 07에서 확인한 과대위험 가능 group에 해당하는지 표시한 진단 flag다.

`priority_input_score`는 다음 규칙으로 계산한다.

```text
0.40 * risk_probability
+ 0.25 * leadtime_urgency_score
+ 0.20 * anomaly_label
+ 0.15 * lead_time_confidence
```

이 규칙은 최종 우선순위 공식이 아니다. 08 단계에서는 downstream 모델과 Agent가 사용할 수 있도록 신호를 한 곳에 모으는 것이 목적이며, 실제 우선순위 산정 방식은 후속 단계에서 별도로 학습하거나 조정해야 한다.

## 4. 리드타임 3중분류 유지

프로젝트 목적에 맞춰 리드타임은 계속 3중분류로 유지한다.

```text
short_0_24h
mid_24_72h
long_72h_plus
```

08에서는 hard label인 `lead_time_bucket`뿐 아니라 다음 확률값도 함께 보존한다.

```text
leadtime_prob_short_0_24h
leadtime_prob_mid_24_72h
leadtime_prob_long_72h_plus
lead_time_confidence
```

이렇게 보존하는 이유는 Agent 또는 Priority Engine이 "짧은 리드타임으로 분류되었는가"만 보는 것이 아니라 "그 판단의 확신도가 얼마나 높은가"까지 함께 해석할 수 있어야 하기 때문이다.

## 5. 산출물

08을 실행하면 다음 위치에 산출물이 저장된다.

```text
data/processed/ml_decision/
data/processed/ml_decision/runs/run_YYYYMMDD_HHMMSS/
```

최신본은 `data/processed/ml_decision/`에 덮어쓰고, 실행별 기록은 `runs/run_YYYYMMDD_HHMMSS/`에 별도로 저장한다.

생성 파일은 다음과 같다.

- `decision_features.csv`: 06/07 결과를 병합하고 priority 입력 후보 신호를 붙인 전체 상세 테이블이다.
- `priority_input_table.csv`: 우선순위 입력 점수 기준으로 정렬한 전체 window 테이블이다.
- `agent_summary_export.csv`: 설비별 최신 window만 추린 요약 테이블이다.
- `agent_detail_export.csv`: 센서 점수, 근거 세부 내용, 진단 flag까지 포함한 상세 export 테이블이다.
- `agent_records.json`: Agent가 읽기 쉬운 nested JSON 구조의 요약 record다.
- `export_metadata.json`: 입력 파일, source run id, export row 수, 상태 후보 분포를 기록한 메타데이터다.

## 6. 왜 이렇게 설계했는가

현재 모델 구조에서 가장 중요한 점은 분류 모델 결과를 최종 알림으로 직접 사용하지 않는 것이다.

05 Isolation Forest는 정상 패턴 대비 벗어남 정도를 `anomaly_score`로 제공한다. 06 Risk LightGBM은 고장 전 위험 패턴과의 유사도를 `risk_probability`로 제공한다. 06 Leadtime LightGBM은 문제가 가까운 시점에 나타날 가능성을 3중분류 확률로 제공한다. 07은 이 판단을 설명할 수 있는 센서 근거를 제공한다.

이 값들은 서로 역할이 다르기 때문에 하나의 label로 먼저 눌러버리면 정보 손실이 생긴다. 그래서 08에서는 hard label보다 연속값과 근거 문자열을 최대한 보존한다.

특히 다음 단계에서 우선순위 회귀 또는 스코어링 모델을 만들려면 아래 신호들이 함께 필요하다.

- 이상 정도: `anomaly_score`, `anomaly_margin`
- 고장 전 위험 유사도: `risk_probability`, `risk_margin`
- 시간 긴급도: `lead_time_bucket`, `leadtime_urgency_score`, `lead_time_confidence`
- 판단 근거: `top_sensors`, `sensor_scores`, `evidence_details`, `pattern_notes`
- 과대평가 진단: `overestimated_risk_group_flag`, `overestimated_risk_group_notes`

따라서 08은 최종 판단을 내리는 단계라기보다, Agent와 Priority Engine이 같은 언어로 ML 결과를 읽게 만드는 계약 계층에 가깝다.

## 7. 다음 단계 제안

08 실행 후에는 두 가지 방향으로 이어갈 수 있다.

- Priority Engine baseline을 만든다. `priority_input_table.csv`를 사용해 점검 우선순위 회귀 또는 rule-based scoring을 설계한다.
- 05 Isolation Forest 성능 개선으로 돌아간다. 현재 08 구조가 `anomaly_score`를 그대로 보존하므로, 05의 feature subset을 개선하면 06/07/08 체인에 더 좋은 이상 신호를 다시 주입할 수 있다.

추천 순서는 먼저 08을 한 번 실행해 end-to-end 산출물 구조를 확인한 뒤, 05 Isolation Forest feature ablation으로 돌아가 성능을 개선하는 것이다.
