# 04. 우선순위 회귀

## 목적

우선순위 단계는 중간 모델 체인의 anomaly, risk, leadtime 신호를 운영자가 볼 수 있는 점수와 등급으로 바꾼다. 이 출력이 서버 목록과 대시보드 큐의 기준이다.

## 입력과 출력

| 구분 | 경로 | 설명 |
|---|---|---|
| 입력 | `data/processed/ml_model_chain/model_chain_output.csv` | 중간 모델 출력 |
| 모델 | `agent/priority/models/lightgbm_priority_model.joblib` | LGBM 회귀 모델 |
| metadata | `agent/priority/models/priority_model_metadata.json` | 모델 버전과 feature 정의 |
| 출력 | `data/processed/ml_priority/priority_scores.csv` | 운영 우선순위 점수 |

## 구현 위치

| 역할 | 파일 |
|---|---|
| priority 실행 | `agent/priority/run_priority.py` |
| 학습 데이터 구성 | `agent/priority/build_dataset.py` |
| 계약/등급 기준 | `agent/priority/contracts.py` |
| baseline 비교 | `agent/priority/rule_baseline.py` |

## 정량 수치

| 항목 | 값 |
|---|---:|
| priority output rows | 300 |
| priority output columns | 9 |
| score min | 2.06 |
| score max | 99.83 |
| score mean | 57.62 |
| urgent | 25 |
| high | 168 |
| medium | 103 |
| low | 4 |
| model_version | `priority_v3_lgbm_reg` |

| Top 5 | 대상 | 점수 | 사유 |
|---:|---|---:|---|
| 1 | manufacturer 1 / substation 16 / 2018-03-04 06:00 | 99.83 | risk=high, leadtime=0-24h, anomaly=0.74 |
| 2 | manufacturer 1 / substation 22 / 2020-03-18 18:00 | 98.55 | risk=critical, leadtime=0-24h, anomaly=0.91 |
| 3 | manufacturer 1 / substation 22 / 2019-02-05 12:00 | 96.72 | risk=critical, leadtime=0-24h, anomaly=0.90 |
| 4 | manufacturer 2 / substation 45 / 2020-03-09 12:00 | 96.67 | risk=critical, leadtime=0-24h, anomaly=0.77 |
| 5 | manufacturer 1 / substation 22 / 2020-03-14 18:00 | 94.93 | risk=critical, leadtime=0-24h, anomaly=0.89 |

## 정성 해석

priority는 모델 체인의 여러 신호를 운영자가 행동할 수 있는 단일 큐로 압축한다. 점수 자체보다 중요한 것은 점수와 함께 남는 `priority_reason`이다. 이 사유가 있어야 운영자가 왜 이 설비가 상위에 있는지 빠르게 검토할 수 있다.

## 다이어그램

```mermaid
flowchart LR
  CHAIN["model_chain_output.csv"] --> F7["priority input signals<br/>anomaly, risk, leadtime, recency"]
  F7 --> LGBM["LGBM priority regression"]
  LGBM --> SCORE["priority_score<br/>0 to 100"]
  SCORE --> LEVEL["priority_level<br/>urgent / high / medium / low"]
  SCORE --> REASON["priority_reason<br/>risk, leadtime, anomaly summary"]
  LEVEL --> CSV["priority_scores.csv<br/>300 x 9"]
  REASON --> CSV
```

## 수정 가이드

우선순위 정책을 바꾸려면 먼저 `contracts.py`의 등급 기준과 `run_priority.py`의 입력 feature 구성을 확인한다. 점수 산출 모델을 재학습하면 metadata의 `model_version`을 올리고, 보고서의 score 분포와 Top 5를 다시 계산해야 한다.

대시보드는 `priority_scores.csv`를 점수순으로 읽기 때문에 점수 범위나 등급명이 바뀌면 프론트 표시 규칙도 같이 확인한다.

## 한계

- priority 모델은 현재 실제 중간 모델 출력으로 실행되지만, 모델 자체는 향후 운영 라벨과 새 chain output으로 재학습하는 것이 좋다.
- `priority_scores.csv`는 목록용 핵심 컬럼만 갖고 있고, 상세 화면의 risk/leadtime/anomaly 근거는 서버에서 `model_chain_output.csv`와 병합한다.
