# 12. Priority 규칙 기반 엔진 전환 결과

## 무엇을 변경했는가

`IF + LGBM risk + LGBM leadtime`까지의 중간 예측 체인은 그대로 두고, `model_chain_output.csv -> priority_scores.csv` 변환 단계만 LGBM 회귀에서 규칙 기반 엔진으로 바꿨다.

| 구분 | 변경 전 | 변경 후 |
|---|---|---|
| priority runtime | `lightgbm_priority_model.joblib` 예측 | `priority_engine_v2_rule_based_tuned` 규칙 계산 |
| 입력 | `model_chain_output.csv` | 동일 |
| 출력 | `priority_scores.csv` 9개 컬럼 | 동일 |
| version 값 | `priority_v3_lgbm_reg` | `priority_engine_v2_rule_based_tuned` |
| legacy LGBM 파일 | runtime 사용 | 보존만 하고 runtime 미사용 |

## 왜 이렇게 했는가

우선순위 단계는 고장 확정 모델이 아니라 운영자가 "무엇을 먼저 점검할지" 정하는 정책 계층이다. 이 단계는 학습 모델보다 규칙 기반이 더 설명하기 쉽고, risk/leadtime/anomaly/history의 반영 이유를 운영 정책으로 조정하기 쉽다.

기존 IF, risk LGBM, leadtime LGBM은 중간 신호 생성 역할이므로 변경하지 않았다. 변경 범위를 priority 단계로 제한해 기존 모델 체인과 API/프론트 컬럼 계약의 위험을 줄였다.

## 규칙 기준

| 항목 | 값 |
|---|---|
| engine | `priority_engine_v2_rule_based_tuned` |
| risk base | critical 38 / high 28 / medium 15 / low 4 |
| risk probability | `risk_probability * 18` |
| leadtime | 0-24h 18 / 1-3d 10 / 3-7d 4 |
| confidence multiplier | >=0.8: 1.0 / >=0.6: 0.8 / <0.6: 0.6 |
| anomaly | `anomaly_score * 6` |
| history | 최근 작업/이벤트 감점, high/critical 장기 fault gap +2 |
| level | urgent >= 70 / high >= 52 / medium >= 34 / low < 34 |

## 정량 결과

현재 `data/processed/ml_model_chain/model_chain_output.csv` 300행을 입력으로 재생성했다.

| 항목 | 값 |
|---|---:|
| output rows | 300 |
| output columns | 9 |
| score min | 8.76 |
| score max | 78.31 |
| score mean | 39.74 |
| urgent | 28 |
| high | 89 |
| medium | 50 |
| low | 133 |

| Top 5 | 대상 | 점수 | 사유 |
|---:|---|---:|---|
| 1 | manufacturer 1 / substation 21 / 2019-01-21 00:00 | 78.31 | risk=critical, leadtime=0-24h, anomaly=0.47 |
| 2 | manufacturer 1 / substation 6 / 2020-06-04 06:00 | 77.20 | risk=critical, leadtime=0-24h, anomaly=0.45 |
| 3 | manufacturer 1 / substation 24 / 2016-10-24 00:00 | 75.92 | risk=critical, leadtime=0-24h, anomaly=0.39 |
| 4 | manufacturer 1 / substation 6 / 2019-04-15 06:00 | 75.04 | risk=critical, leadtime=0-24h, anomaly=0.41 |
| 5 | manufacturer 1 / substation 6 / 2020-06-08 18:00 | 74.27 | risk=critical, leadtime=0-24h, anomaly=0.59 |

## 검증

| 검증 | 결과 |
|---|---|
| `uv run python -m agent.priority.run_priority` | 통과, 300행 재생성 |
| `uv run python -m agent.priority.validate_contracts` | 통과 |
| `uv run pytest tests/test_priority_rule_engine.py -q` | 3 passed |
| `uv run pytest tests -q` | 17 passed |
| `C:/Users/Admin/Downloads/07_priority_engine.ipynb` 코드 셀 순차 실행 | 통과 |

## 남은 한계

- priority는 이제 학습 모델 성능 지표가 아니라 운영 정책으로 해석해야 한다.
- 현재 규칙은 fixture와 현재 model chain output 기준으로 검증했다.
- 현장 적용 전에는 운영자 피드백으로 threshold와 history 감점 정책을 조정해야 한다.
