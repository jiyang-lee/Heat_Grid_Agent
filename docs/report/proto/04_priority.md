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
| score min | 10.61 |
| score max | 31.98 |
| score mean | 20.11 |
| urgent | 0 |
| high | 0 |
| medium | 180 |
| low | 120 |
| model_version | `priority_v3_lgbm_reg` |
| training_basis | `data/processed/ml_model_chain/model_chain_output.csv` |
| holdout verdict | baseline 미달, 모델 보류 |

| Top 5 | 대상 | 점수 | 사유 |
|---:|---|---:|---|
| 1 | manufacturer 2 / substation 50 / 2019-11-16 12:00 | 31.98 | risk=medium, leadtime=1-3d, anomaly=0.58 |
| 2 | manufacturer 1 / substation 27 / 2020-01-17 18:00 | 31.98 | risk=high, leadtime=1-3d, anomaly=0.47 |
| 3 | manufacturer 1 / substation 27 / 2020-01-16 06:00 | 31.98 | risk=high, leadtime=1-3d, anomaly=0.45 |
| 4 | manufacturer 2 / substation 52 / 2019-02-18 06:00 | 31.98 | risk=medium, leadtime=1-3d, anomaly=0.20 |
| 5 | manufacturer 1 / substation 15 / 2018-10-04 06:00 | 31.98 | risk=medium, leadtime=1-3d, anomaly=0.21 |

## 정성 해석

priority는 모델 체인의 여러 신호를 운영자가 행동할 수 있는 단일 큐로 압축한다. 현재 모델은 mock 학습을 제거하고 실제 `model_chain_output.csv`로 재학습했지만, holdout 평가에서 rule baseline보다 낮다. 따라서 구조 검증은 완료됐지만, 운영 채택 관점에서는 모델을 보류하고 재학습/튜닝이 필요하다.

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

- priority 모델은 실제 중간 모델 출력으로 재학습됐지만, holdout에서 baseline 미달이다.
- 새 모델 출력은 `medium/low`에만 분포해 즉시 운영용 긴급 큐로 쓰기에는 보수적이다.
- `priority_scores.csv`는 목록용 핵심 컬럼만 갖고 있고, 상세 화면의 risk/leadtime/anomaly 근거는 서버에서 `model_chain_output.csv`와 병합한다.
