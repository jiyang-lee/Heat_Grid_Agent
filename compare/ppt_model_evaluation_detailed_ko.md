# HeatGrid 모델 성능·운영 우선순위·Agent 평가표 — PPT 삽입용 상세 문안

작성 기준일: 2026-07-22
대상: `Heat_Grid_Beta` 복원 모델 산출물과 `artifacts/current_best` 비교 자료
중요: 이 문서는 PPT 파일이 아니라, PPT 제작 GPT에 그대로 전달할 수 있는 문안·수치·표 구성안이다.

## 0. 한 문장 결론

> 검증된 handoff Risk·Leadtime artifact를 복원해 임시 내부 재학습의 과적합을 제거했다. 복원 Risk는 holdout 정밀도 85.7%, FPR 4.7%, 복원 Leadtime은 Macro-F1 69.3%, Top-2 98.5%다. 이를 결합한 공식 Priority v4 `Risk ≥0.78 OR pre-event ≥0.99`는 holdout 정밀도 83.6%, 재현율 72.7%, F1 77.8%, 이벤트 7/8로 현재 비교 정책 중 균형 성능이 가장 높다.

## 1. PPT 구성 권고

발표 본문은 아래 3장으로 압축하고, 질문 대응용 상세 수치는 부록 6장으로 분리한다.

1. 본문 1 — 현재 ML 모델별 성능과 일반화 판정
2. 본문 2 — 운영 우선순위 Rule/LGBM/Hybrid 비교
3. 본문 3 — Agent 구성, 호출량, 시간, 비용과 재생성 영향
4. 부록 A — 이상탐지 상세
5. 부록 B — Risk 상세 및 확률 보정
6. 부록 C — Leadtime 상세 및 구간별 성능
7. 부록 D — Priority Top-K·NDCG·이벤트 성능
8. 부록 E — 분포 이동과 95% 신뢰구간
9. 부록 F — 승격 평가기준과 추가 검증 로드맵

---

# 본문 1. 현재 ML 모델별 성능과 일반화 판정

## 슬라이드 제목

**검증된 Risk·Leadtime artifact 복원으로 저오경보·구간분류 성능을 회복했다**

## 상단 핵심 메시지

- 이상탐지 결합 정책은 holdout F1 61.8%지만 validation F1 7.9%로 분포 이동에 매우 민감하다.
- 복원 Risk는 holdout 정밀도 85.7%, F1 51.1%, FPR 4.7%, ROC-AUC 67.2%, AP 71.3%로 낮은 오경보율을 재현했다.
- 복원 Leadtime은 holdout 정확도 71.2%, Macro-F1 69.3%, Weighted-F1 70.8%, Top-2 98.5%, Bucket MAE 0.288이다.
- Risk 재현율은 36.4%로 단독 탐지에는 부족하므로, 공식 Priority v4에서 pre-event 근거를 결합해 재현율을 72.7%로 보완한다.

## PPT 중앙 요약표

| 모델 | 현재 버전/정책 | 평가 계약 | 핵심 수치 | 판정 |
|---|---|---|---|---|
| 이상탐지 | IF·Mahalanobis 결합 | time holdout 183행, 양성 77 | Precision 82.6%, Recall 49.4%, F1 61.8%, FPR 7.5%, AP 73.8% | holdout 참고 가능, validation 붕괴로 단독 경보 금지 |
| Risk | `best_risk_lgbm_anomaly_ensemble_v1_restored_fpr05_v2` | event-regime holdout 152행, 양성 66 | Precision 85.7%, Recall 36.4%, F1 51.1%, FPR 4.7%, ROC-AUC 67.2%, AP 71.3% | 저오경보 핵심 신호; recall 보완 필요 |
| Leadtime | `best_leadtime_lgbm_risk_anomaly_v2_restored` | pre-fault holdout 66행 | Accuracy 71.2%, Macro-F1 69.3%, Top-2 98.5%, Bucket MAE 0.288 | 현재 승격 후보; 외부검증 필요 |
| Priority v4 | `m1_risk_pre_event_priority_v4` | time holdout 183행, 양성 77 | Precision 83.6%, Recall 72.7%, F1 77.8%, FPR 10.4%, Event 7/8 | 현재 공식 균형 정책 |

## 우측 강조 카드

**일반화 경고**

- Risk F1: 53.7% → 45.5% → 51.1% `(train → validation → holdout)`
- Leadtime Macro-F1: 38.5% → 43.1% → 69.3%
- train 대비 holdout PSI: 이상탐지 4.36, Risk probability 4.39, Risk score 4.51, Leadtime confidence 0.36
- 일반 참고상 PSI 0.25 이상은 큰 이동으로 보므로 네 점수 모두 강한 분포 이동 신호다.

## 하단 결론 문구

> 복원 artifact의 재현 수치를 현재 기준으로 사용하되, Risk recall과 작은 이벤트 표본은 untouched event holdout·rolling split·확률 보정으로 추가 검증한다.

## 추천 시각화

- 왼쪽 2/3: 모델별 `train-validation-holdout` 성능 막대그래프
- 오른쪽 1/3: Traffic light 판정 카드
  - 이상탐지: 주의
  - Risk: 저오경보 통과 / recall 보완
  - Leadtime: 승격 후보
  - Priority v4: 공식 / 신규 이벤트 감시
- 데이터: `13_risk_extended_metrics_ko.csv`, `15_leadtime_extended_metrics_ko.csv`

---

# 본문 2. 운영 우선순위 검증

## 슬라이드 제목

**공식 Priority v4가 현재 비교 정책 중 가장 높은 균형 F1을 기록했다**

## PPT 중앙 성능표 — 현재 M1 183행 holdout

| 설정 | Precision | Recall | F1 | FPR | MCC | 알람률 | 이벤트 탐지 | 판정 |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| 현재 Rule body | 77.0% | 61.0% | 68.1% | 13.2% | 0.501 | 33.3% | 7/8 | 기준 비교 |
| M1 specialist 단독 | 56.9% | 37.7% | 45.3% | 20.8% | 0.186 | 27.9% | 5/8 | 보조 모델 |
| Legacy Hybrid v1 `0.65/0.35·82.5/95.0` | 100.0% | 27.3% | 42.9% | 0.0% | 0.422 | 11.5% | 5/8 | 롤백 기준선 |
| 요청 Hybrid v2 `0.72/0.28·67.5/82.5` | 100.0% | 53.2% | 69.5% | 0.0% | 0.630 | 22.4% | 7/8 | 보수적 비교값 |
| 이전 Evidence Gate v3 `pre≥0.99 OR lead≥0.97` | 78.6% | 42.9% | 55.5% | 8.5% | 0.403 | 23.0% | 6/8 | 이전 정책 비교 |
| **공식 v4 `Risk≥0.78 OR pre≥0.99`** | **83.6%** | **72.7%** | **77.8%** | 10.4% | **0.639** | 36.6% | **7/8** | **현재 공식 정책** |

## Rule-based와 LGBM의 동일 366행 계약 비교

| Priority 본체 | Level Accuracy | Level Macro-F1 | Action Precision | Action Recall | Action F1 | FPR |
|---|---:|---:|---:|---:|---:|---:|
| Rule-based `v2_threshold48` | 69.1% | 41.8% | 88.4% | 71.0% | **78.8%** | 3.9% |
| LGBM priority-only | 36.9% | 30.8% | 83.3% | 32.7% | **47.0%** | 2.7% |

## Top-K 순위 품질 — 동일 366행 holdout

| K | Rule Precision@K | LGBM Precision@K | Rule NDCG@K | LGBM NDCG@K |
|---:|---:|---:|---:|---:|
| 10 | 100.0% | 100.0% | **1.000** | 0.944 |
| 20 | **100.0%** | 90.0% | **0.901** | 0.798 |
| 50 | **100.0%** | 82.0% | **0.845** | 0.728 |
| 100 | **84.0%** | 57.0% | **0.828** | 0.620 |

## 반드시 함께 적을 불확실성

- 공식 v4 이벤트 재현율 87.5%는 7/8건이고 Wilson 95% 신뢰구간은 52.9~97.8%로 넓다.
- FPR 10.4%의 Wilson 95% 신뢰구간은 5.9~17.6%다. 균형 F1은 가장 높지만 장기 목표 5%에는 아직 도달하지 못했다.
- validation 이벤트가 3건뿐이므로 신규 event/rolling 검증 없이 절대 최적이라고 표현하지 않는다.

## 하단 결론 문구

> 공식 v4는 validation에서 고정한 label-free Gate다. 보수적 v2 대비 Recall +19.5%p, F1 +8.3%p를 확보하는 대신 FPR이 +10.4%p 증가하므로, 운영 목적에 따라 v4와 v2를 함께 감시한다.

## 추천 시각화

- 왼쪽: 네 설정의 F1·FPR 묶음 막대
- 오른쪽 위: 이벤트 탐지 `7/8, 5/8, 5/8, 7/8, 6/8, 7/8`
- 오른쪽 아래: “공식 v4” 배지와 FPR·Event Recall 95% CI 에러바
- 데이터: `17_priority_extended_metrics_ko.csv`, `20_uncertainty_key_metrics_ko.csv`

---

# 본문 3. Agent 구성·호출량·시간·비용

## 슬라이드 제목

**Agent는 단계별 모델을 분리했지만, 현재 실측은 V1 7건뿐이며 품질 성공률 개선이 우선이다**

## 현재 모델 역할

| 역할 | 모델 | 현재 용도 | 호출 조건 |
|---|---|---|---|
| 일반 대화·통합 Agent | GPT-5.4 mini | 운영 질문, evidence loop, 기본 답변 | 기본 실행 |
| 독립 분석 Agent | GPT-5.4 mini | 독립 분석/진단 worker 설정 | V2 fault 단계에는 아직 미연결 |
| 작업지시서·보고서 | GPT-5.4 nano | 짧은 구조화 초안·보고서 JSON | 보고서 단계 1회 계획 |
| 상위 재판정·Quality Judge | GPT-5.4 | ML 저품질 재판정, 답변 품질 평가 | 조건부, 기본 기능 비활성 |

## 현재 V1 실측 — 7사이클

| KPI | 실측 |
|---|---:|
| GPT-5.4 mini 기록 호출 | 3~7회, 평균 5.14회 |
| nano 보고서 포함 API 호출 추정 | 4~8회, 평균 6.14회 |
| 기록 토큰 | 5,999~7,915, 평균 6,981토큰 — nano 사용량 누락 |
| 전체 시간 | 44.6~93.7초, 평균 60.9초 |
| 보고서 단계 | 평균 33.3초 |
| 보고서 성공 | 5/7 = 71.4%, 95% CI 35.9~91.8% |
| DB 기록 mini 비용 | $0.00685~$0.01164, 평균 $0.00940 |
| nano 계획값 포함 1사이클 기준 | 약 **$0.01475** — 추정 |

## 재생성·재실행 비용

| 시나리오 | 추가 호출 | 추가 시간 | 예상/실측 비용 | 상태 |
|---|---:|---:|---:|---|
| 출력 파싱 재생성 1회 | mini 1회 | 실측 +3.6~6.4초, 평균 +4.7초 | 실측 귀속 평균 **+$0.00512** | 3/7건 발생 |
| Child 전체 수동 재실행 | V1 전체 반복 | 평균 약 +59.4초 | nano 추정 포함 **+$0.01449** | 실측 기반 |
| V2 보고서 단계만 재실행 | nano 1회 | 계약 예산 30초 | **약 $0.00240** | 계획값, 실측 없음 |
| V2 ML+상위 재판정 | GPT-5.4 1회 중심 | 조건부 | **약 $0.03190** | 계획값, 실측 없음 |
| Answer-quality 자동 재생성 | Judge+재생성+Judge | 조건부 | **약 $0.04880** | 기능 비활성, 실측 없음 |
| 작업지시서 수정 초안 | mini 1회 | 미계측 | **약 $0.00375** | 계획값 |
| 수정안 확정 | LLM 0회 | DB 처리 | **$0** | 결정론적 처리 |

## 공식 단가 — 2026-07-22 확인, 1M tokens당

| 모델 | 입력 | 캐시 입력 | 출력 |
|---|---:|---:|---:|
| GPT-5.4 mini | $0.75 | $0.075 | $4.50 |
| GPT-5.4 nano | $0.20 | $0.02 | $1.25 |
| GPT-5.4 | $2.50 | $0.25 | $15.00 |

가격 출처: OpenAI 공식 모델 문서
`https://developers.openai.com/api/docs/models/gpt-5.4-mini`
`https://developers.openai.com/api/docs/models/gpt-5.4-nano`
`https://developers.openai.com/api/docs/models/gpt-5.4`

## 하단 결론 문구

> 비용보다 먼저 보고서 성공률 71.4%와 재생성 발생률 42.9%를 개선해야 한다. V2의 핵심 경제성은 전체 사이클을 반복하지 않고 실패 단계의 snapshot만 재실행하는 데 있으며, 실제 V2 로그가 쌓이기 전에는 계획비용으로만 표시한다.

## 추천 시각화

- 왼쪽: 9단계 Agent pipeline
  - ML 검증 → 날씨 → RAG 검색 → RAG 해석 → 고장분석 → 상위 재판정 → 부모 판정 → 보고서 초안 → 충실도 검증
- 오른쪽: 기본·재생성·전체재실행·V2 단계재실행 비용 비교
- 각 비용 막대에 `실측`, `추정`, `계획` 배지를 붙인다.

---

# 부록 A. 이상탐지 모델 상세 성능

평가 계약: `split_time_based`, validation 169행 `(정상 143, 사전고장 26)`, holdout 183행 `(정상 106, 사전고장 77)`.

## Holdout 비교

| 정책 | Accuracy | Balanced Acc. | Precision | Recall | Specificity | F1 | MCC | FPR | ROC-AUC | AP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Isolation Forest | 72.1% | 69.0% | 76.0% | 49.4% | 88.7% | 59.8% | 0.421 | 11.3% | 0.637 | 0.701 |
| Mahalanobis | 67.2% | 66.2% | 61.3% | 59.7% | 72.6% | 60.5% | 0.325 | 27.4% | 0.657 | 0.723 |
| IF·Mahalanobis 결합 | **74.3%** | **70.9%** | **82.6%** | 49.4% | **92.5%** | **61.8%** | **0.476** | **7.5%** | **0.667** | **0.738** |
| 강한 q99 결합 | 69.9% | 64.3% | 100.0% | 28.6% | 100.0% | 44.4% | 0.434 | 0% | 0.667 | 0.738 |
| 지속성 criticality | 69.4% | 63.6% | 100.0% | 27.3% | 100.0% | 42.9% | 0.422 | 0% | 0.667 | 0.738 |

## Validation 붕괴

- IF·Mahalanobis 결합: Precision 6.0%, Recall 11.5%, F1 7.9%, FPR 32.9%, MCC -0.169
- 지속성 criticality: Precision/Recall/F1 모두 0%, FPR 28.7%, MCC -0.241
- holdout 결합 정책의 Precision 82.6%도 95% CI 69.3~90.9%, Recall 49.4%는 38.5~60.3%다.

## 평가기준

- 필수: Recall, FPR, Event recall, false-positive episodes/site-month, 첫 탐지 lead time
- 보조: Balanced Accuracy, MCC, AP, threshold sensitivity
- 강건성: 계절·설비·고장유형, 결측 주입, spike/noise, train-holdout PSI/KS

## 판정

> 결합 정책은 증거 보강용으로는 유효하지만 validation 성능이 반전되므로 독립 자동경보 모델로 승격할 수 없다.

---

# 부록 B. Risk 모델 상세 및 확률 보정

현재 모델: `best_risk_lgbm_anomaly_ensemble_v1_restored_fpr05_v2`

| Split | N/양성 | Accuracy | Balanced Acc. | Precision | Recall | Specificity | F1 | MCC | FPR | ROC-AUC | AP | Brier | ECE-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Train | 896/229 | 83.8% | 68.3% | 100.0% | 36.7% | 100.0% | 53.7% | 0.549 | 0% | 0.994 | 0.988 | 0.117 | 0.137 |
| Validation | 204/26 | 88.2% | 67.0% | 55.6% | 38.5% | 95.5% | 45.5% | 0.399 | 4.5% | 0.711 | 0.407 | 0.146 | 0.154 |
| Holdout | 152/66 | 69.7% | 65.9% | **85.7%** | 36.4% | **95.3%** | 51.1% | 0.405 | **4.7%** | 0.672 | **0.713** | 0.242 | 0.204 |

## 핵심 해석

- validation과 holdout 모두 FPR 5% cap을 통과했다.
- Holdout 정밀도 85.7%의 Wilson 95% CI는 68.5~94.3%, FPR 4.7%의 CI는 1.8~11.4%다.
- Recall 36.4%는 단독 탐지 기준으로 부족하다. 이 한계를 숨기지 않고 pre-event와 결합한 Priority v4에서 72.7%로 보완한다.
- Base probability Brier 0.242, ECE-10 0.204이므로 `risk_probability`를 실제 고장 확률로 단정하지 않는다.

## 평가기준

- 분류: Precision, Recall, F1, Specificity, MCC, ROC-AUC, AP
- 보정: Brier, Log-loss, ECE, reliability diagram
- 운영: event recall, false episodes/site-month, first-alarm lead time
- 일반화: 계절·설비구성·기계실·고장유형, leave-one-substation-out, rolling split

## 판정

> 복원 모델은 오경보 억제와 정밀도 측면에서 운영 후보로 사용할 수 있다. 다만 recall과 확률 보정은 부족하므로 `Risk≥0.78` 단독 알람이 아니라 pre-event 결합 및 사람 검토 구조로 사용한다.

---

# 부록 C. Leadtime 모델 상세

현재 모델: `best_leadtime_lgbm_risk_anomaly_v2_restored`

| Split | N | Exact Accuracy | Balanced Acc. | Macro-F1 | Weighted-F1 | Top-2 | Bucket MAE | 지연예측률 | Brier | ECE-10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Train | 229 | 55.0% | 41.9% | 38.5% | 50.6% | 85.2% | 0.524 | 15.7% | 0.632 | 0.177 |
| Validation | 26 | 46.2% | 43.8% | 43.1% | 48.2% | 100.0% | 0.538 | 19.2% | 0.818 | 0.413 |
| Holdout | 66 | **71.2%** | **67.2%** | **69.3%** | **70.8%** | **98.5%** | **0.288** | 18.2% | **0.393** | **0.150** |

## Holdout 구간별 성능

| 실제 구간 | Support | Precision | Recall | F1 | 판정 |
|---|---:|---:|---:|---:|---|
| 0–24h | 27 | 76.2% | 59.3% | 66.7% | 긴급구간 성능 개선, 추가 검증 필요 |
| 1–3d | 34 | 68.3% | 82.4% | 74.7% | 가장 안정적인 구간 |
| 3–7d | 5 | 75.0% | 60.0% | 66.7% | 표본 5건이라 CI 필수 |

## 평가기준

- 필수: Exact Accuracy, Macro-F1, 구간별 Recall, Top-2, Bucket MAE
- 안전: 지연예측률과 평균 부호오차 — 실제보다 여유 있다고 판단한 비율
- 보정: multiclass Brier, Log-loss, confidence ECE
- 일반화: lead-time horizon별 event split, 계절/설비/고장유형, rolling split

## 판정

> Holdout Macro-F1 69.3%와 Top-2 98.5%는 승격 후보 수준이지만, validation 26건과 3–7d 5건은 작다. 신규 event·rolling split에서 구간별 recall을 다시 확인한다.

---

# 부록 D. Priority 운영 평가

## 운영 holdout 300행·10이벤트 계약

`priority_high_or_urgent` 정책:

- 이벤트 탐지 10/10 = 100%
- 정상 오경보율 9.35%
- false rows/site-month 11.38
- false episodes/site-month 3.41
- 첫 알람 중앙 lead time 25.59h, 평균 38.55h

## Priority score Top-K

| K | Precision@K | Row Recall@K | Event Recall@K | Urgent Recall@K | NDCG@K |
|---:|---:|---:|---:|---:|---:|
| 10 | 100.0% | 11.6% | 20.0% | 8.6% | 0.601 |
| 20 | 100.0% | 23.3% | 60.0% | 28.6% | 0.656 |
| 50 | 82.0% | 47.7% | 90.0% | 57.1% | 0.657 |
| 86 | 75.6% | 75.6% | 100.0% | 97.1% | 0.761 |
| 100 | 71.0% | 82.6% | 100.0% | 100.0% | 0.796 |

## 평가기준

- 행 분류: Precision, Recall, F1, FPR, MCC
- 이벤트: Event recall, 24h/3d/7d recall, median/p10 lead time
- 알람 부하: Alarm rate, false rows/site-month, false episodes/site-month
- 순위: Precision@K, Recall@K, Event Recall@K, NDCG@K
- 승격: validation에서 가중치·임계값 고정 후 untouched event holdout과 rolling split 모두 통과

---

# 부록 E. 불확실성·분포 이동

## 핵심 95% 신뢰구간

| 대상 | 지표 | 점추정 | 95% CI | 의미 |
|---|---|---:|---:|---|
| 이상탐지 결합 | Precision | 82.6% | 69.3~90.9% | 표본 확대 필요 |
| 이상탐지 결합 | Recall | 49.4% | 38.5~60.3% | 미탐 불확실성 큼 |
| 복원 Risk | Precision | 85.7% | 68.5~94.3% | 고정밀이나 recall과 함께 해석 |
| 복원 Risk | FPR | 4.7% | 1.8~11.4% | 점추정은 5% cap 통과, 상한은 초과 |
| 복원 Leadtime | Exact Accuracy | 71.2% | 59.4~80.7% | 외부검증 전 확정 금지 |
| 복원 Leadtime | Top-2 | 98.5% | 91.9~99.7% | 인접 구간 포함 성능 우수 |
| Priority 공식 v4 | FPR | 10.4% | 5.9~17.6% | 균형 F1 최상, 장기 목표 5%는 미달 |
| Priority 공식 v4 | Event Recall | 87.5% | 52.9~97.8% | 이벤트 8건이라 여전히 넓음 |
| Agent V1 | Report Success | 71.4% | 35.9~91.8% | 7건 표본으로 SLO 판단 불가 |

## 점수 분포 이동

| 점수 | PSI | KS statistic | p-value | 판정 |
|---|---:|---:|---:|---|
| 이상탐지 score | 4.357 | 0.523 | <0.001 | 큰 이동 |
| Risk probability | 4.391 | 0.540 | <0.001 | 큰 이동 |
| Risk 운영 score | 4.508 | 0.570 | <0.001 | 큰 이동 |
| Leadtime confidence | 0.358 | 0.242 | 0.004 | 큰 이동 |

## 해석 주의

- PSI·KS는 이동 경보지 원인 설명이 아니다.
- 작은 이벤트 표본에서는 점추정만 제시하지 않고 성공건/전체건과 CI를 함께 적는다.
- 후보 선택에 사용한 holdout은 최종 성능을 증명하는 untouched holdout이 아니다.

---

# 부록 F. 평가기준과 승격 Gate

아래 권고 기준은 PPT/PoC 의사결정을 위한 제안이며 현재 프로젝트의 확정 계약값이 아니다.

| 대상 | 권고 Gate | 이유 |
|---|---|---|
| Risk | Recall ≥80%, FPR ≤5%, ROC-AUC ≥0.70, AP가 기존 대비 +0.05 이상 | 미탐·오경보·순위품질 동시 통제 |
| Risk probability | Brier ≤0.20, ECE ≤0.05 | 확률을 실제 위험도로 해석하기 위한 조건 |
| Leadtime | Macro-F1 ≥0.60, Top-2 ≥0.90, Bucket MAE ≤0.40 | 희소 구간과 인접구간 품질 보장 |
| Leadtime safety | 0–24h Recall ≥0.80, 지연예측률 ≤0.10 | 긴급 대응 지연 방지 |
| Priority | Event Recall ≥0.90, FPR ≤0.05, Precision ≥0.80 | 고장 탐지와 출동부하 균형 |
| Priority operations | False episodes/site-month ≤1, median lead ≥24h | 현장 알람 피로와 대응시간 관리 |
| Agent | Report success ≥0.95, Task completion ≥0.90 | 운영 안정성 |
| Agent quality | Groundedness ≥0.90, unsupported claim ≤0.02 | LLM 근거성·안전성 |
| Agent SLO | p95 latency ≤90s, p95 cost ≤$0.05 | 성능·비용 상한 |

## 현재 코드에 실제 존재하는 기준

- Agent evidence threshold: 0.75
- UI/API 모델 점수 tolerance: 0.12
- Answer quality threshold: 75/100 — 기능 기본 비활성
- RAG JSONL top score: 6.0, unique matches: 2 — 품질 기능 기본 비활성
- Risk/pre-event gate 공식 v4 재현 실적: Precision 0.8358, Recall 0.7273, F1 0.7778, Event Recall 0.875, FPR 0.1038

## 추가 검증 우선순위

### 최우선

1. 임계값 선택에 사용하지 않은 untouched fault-event holdout
2. 월별 walk-forward/rolling split
3. V2 Agent 실제 30건 이상 계측: 호출량·토큰·비용·단계별 p50/p95
4. 한글 운영 대화 평가셋: 수정·확정·취소 의도 적중률
5. 문장별 groundedness·unsupported claim 사람평가

### 높음

1. Leave-one-substation-out
2. 계절·설비구성·고장유형별 성능과 95% CI
3. 센서 결측 5/10/20/30% block injection
4. noise·spike·outlier 강건성
5. false episodes/site-month와 first-alarm lead time의 공식 v4 재산출
6. 작업지시서 first-pass acceptance와 초안-최종본 편집거리 계측

### 현재 데이터로 불가능

- 제조사 간 일반화: 현재 `manufacturer 1`만 존재
- V2 실측 성능: DB에 V2 완료 실행 표본 없음
- RAG/answer quality의 실제 효과: 기본 기능이 비활성이고 평가 로그 없음

---

# 발표에서 사용할 표현과 피해야 할 표현

## 사용할 표현

- “동일 holdout에서 비교 정책 중 균형 F1이 가장 높은 label-free 공식 v4 정책”
- “서로 다른 평가 계약의 결과는 분리해 제시했다”
- “운영 우선순위는 Rule 기반 본체와 ML 보조 신호를 결합한다”
- “V2 재실행 비용은 구조 기반 계획값이며 실측 전이다”
- “점추정과 함께 표본수·신뢰구간을 표시했다”

## 피해야 할 표현

- “현재 모든 모델이 최적값이다”
- “Risk 84%는 실제 고장 확률 84%다”
- “Priority 83점의 정확도는 83%다”
- “이벤트 재현율 87.5%가 안정적으로 검증됐다”
- “V2 Agent가 실제로 매번 9단계와 고장진단 모델을 모두 호출한다”
- “DB 비용이 완전한 전체 비용이다” — nano 보고서 토큰이 누락돼 있다.

---

# 파일 사용 안내

- 실행형 한글 노트북: `compare/ml_ops_agent_validation_ko.ipynb`
- 노트북 생성기: `compare/generate_ml_ops_agent_validation_notebook.py`
- PPT 표 CSV: `compare/ppt_tables/`
- 지표 정의: `11_model_evaluation_metric_definitions_ko.csv`
- 모델별 확장 성능: `12`~`17` CSV
- Top-K: `18`, `18b` CSV
- Drift·신뢰구간: `19`, `20` CSV
- Gate·추가 검증·Agent KPI: `21`~`23` CSV

PPT 제작 GPT에는 이 문서와 필요한 CSV만 전달하면 된다. 핵심 3장만 만들 때는 “본문 1~3”을 사용하고, 질의응답 대비용으로는 “부록 A~F”를 추가한다.
