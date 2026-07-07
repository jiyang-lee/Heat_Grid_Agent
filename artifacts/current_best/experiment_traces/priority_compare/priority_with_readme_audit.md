# priority_with_readme 재검토 결과

## 결론

현재 프로젝트의 공식 운영 기준으로는 `rule-based priority_engine_v2_threshold48`이 `LGBM priority regression`보다 우세하다.

단, 팀원 `priority_with_readme` 코드가 기록한 자체 metadata 기준에서는 LGBM이 rule baseline을 이겼다고 되어 있다. 이 차이는 평가 데이터와 split 기준이 다르기 때문에 발생한다.

## priority_with_readme 구조

`priority_with_readme`는 모델 파일이 아니라 priority LGBM을 만들기 위한 코드 패키지다.

주요 흐름:

```text
model_chain_output.csv
-> build_dataset.py
-> train_priority_model.py
-> lightgbm_priority_model.joblib
-> run_priority.py
-> priority_scores.csv
```

LGBM 입력 feature는 7개다.

```text
anomaly_score
risk_probability
risk_score
leadtime_prob_0-24h
leadtime_prob_1-3d
leadtime_prob_3-7d
predicted_lead_time_confidence
```

Target은 다음 mapping이다.

```text
normal = 0
3-7d   = 33
1-3d   = 66
0-24h  = 100
```

Split은 `substation_id % 3 == 0`을 holdout으로 두는 방식이다.

## 중요한 제한

현재 repo에는 `priority_with_readme`가 학습 기준으로 삼은 파일이 없다.

```text
data/processed/ml_model_chain/model_chain_output.csv
```

따라서 팀원 metadata의 원래 학습/평가 결과는 현재 repo에서 그대로 재현할 수 없다.

## 팀원 metadata 기준 결과

팀원 metadata에는 아래처럼 기록되어 있다.

```text
holdout rows: 837
positive R: 528

LGBM:
  precision@10 = 1.0000
  ndcg@10      = 0.7131
  precision@R  = 0.7879
  ndcg@R       = 0.7553

rule baseline:
  precision@10 = 0.5000
  ndcg@10      = 0.3755
  precision@R  = 0.7102
  ndcg@R       = 0.6631
```

이 기준만 보면 LGBM이 rule baseline보다 좋다.

하지만 이 결과는 현재 공식 pipeline 데이터와 행 수, holdout 수, positive 수가 다르다.

## 현재 공식 데이터 기준 재평가

현재 공식 데이터:

```text
data/processed/ml_priority/priority_engine_scores_tuned.csv
data/processed/ml_features/trainable_windows.csv
```

비교 모델:

```text
rule = 현재 공식 priority_score
lgbm = 팀원 lightgbm_priority_model.joblib 재예측 score
```

### current split_time_based holdout

```text
rows = 366
pre_fault positives = 115
within_3d positives = 107
```

| metric | rule | LGBM |
|---|---:|---:|
| MAE | 20.5625 | 26.1631 |
| Spearman | 0.6854 | 0.4302 |
| NDCG@10 | 1.0000 | 0.9444 |
| Precision@R | 0.7304 | 0.5130 |
| NDCG@R | 0.7805 | 0.5976 |
| Top-100 pre_fault recall | 0.7304 | 0.4957 |
| high/urgent precision | 0.8837 | 0.8333 |
| high/urgent recall | 0.7103 | 0.3271 |
| high/urgent F1 | 0.7876 | 0.4698 |

판정: rule-base 우세.

### team style `substation_id % 3 == 0` holdout on current rows

```text
rows = 500
pre_fault positives = 195
within_3d positives = 192
```

| metric | rule | LGBM |
|---|---:|---:|
| MAE | 13.8574 | 13.6533 |
| Spearman | 0.8199 | 0.7805 |
| NDCG@10 | 1.0000 | 1.0000 |
| Precision@R | 0.9128 | 0.8821 |
| NDCG@R | 0.9243 | 0.9007 |
| Top-100 pre_fault recall | 0.5128 | 0.4974 |
| high/urgent precision | 0.9682 | 0.9520 |
| high/urgent recall | 0.7917 | 0.6198 |
| high/urgent F1 | 0.8711 | 0.7508 |

판정: MAE만 LGBM이 근소하게 좋고, ranking/action 기준은 rule-base 우세.

## 최종 판정

LGBM regression이 이긴다는 주장은 `priority_with_readme`의 원래 `model_chain_output.csv` 기준 metadata 안에서는 맞다.

하지만 현재 프로젝트의 공식 산출물과 운영 평가 기준에서는 rule-base가 더 낫다.

따라서 운영 모델 판정은 다음과 같다.

```text
공식 운영 priority: rule-based 유지
LGBM regression: shadow score 또는 재학습 후보
```

LGBM을 공식 교체 후보로 보려면 다음 조건이 필요하다.

```text
1. model_chain_output.csv 원본을 확보한다.
2. 현재 공식 pipeline 기준으로 동일 split을 다시 만든다.
3. current holdout, event holdout, substation holdout을 모두 평가한다.
4. high/urgent recall, Top-K recall, NDCG@K에서 rule-base를 이겨야 한다.
```

현재 상태에서 확실한 결론:

```text
현재 프로젝트 기준: rule-base > LGBM regression
팀원 proto metadata 기준: LGBM regression > rule baseline
운영 채택 기준: rule-base 유지
```
