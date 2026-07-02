# 05 Isolation Forest Threshold Quantile Experiment

## 목적

Isolation Forest의 `threshold_quantile`을 조절했을 때 이상치 라벨, pre_fault 포착률, normal 오탐률이 어떻게 바뀌는지 확인했다.

## 핵심 결과

### 현재 공식 기준

- 공식 quantile: `0.99`
- threshold: `0.535778`
- holdout F1/Recall/Precision: `0.2267` / `0.1278` / `1.0000`
- holdout FPR: `0.0000`
- TP/FP/FN/TN: `17` / `0` / `116` / `261`

### F1 기준 최고 후보

- quantile: `0.85`
- threshold: `0.478249`
- holdout F1/Recall/Precision: `0.4778` / `0.3233` / `0.9149`
- holdout FPR: `0.0153`
- TP/FP/FN/TN: `43` / `4` / `90` / `257`

### holdout FP 0 유지 가능 하한

- quantile: `0.92`
- threshold: `0.500080`
- holdout F1/Recall: `0.3270` / `0.1955`

## Quantile별 holdout 요약

- q `0.85`: F1 `0.4778`, Recall `0.3233`, Precision `0.9149`, FPR `0.0153`, TP `43`, FP `4`
- q `0.9`: F1 `0.3855`, Recall `0.2406`, Precision `0.9697`, FPR `0.0038`, TP `32`, FP `1`
- q `0.92`: F1 `0.3270`, Recall `0.1955`, Precision `1.0000`, FPR `0.0000`, TP `26`, FP `0`
- q `0.94`: F1 `0.2614`, Recall `0.1504`, Precision `1.0000`, FPR `0.0000`, TP `20`, FP `0`
- q `0.95`: F1 `0.2614`, Recall `0.1504`, Precision `1.0000`, FPR `0.0000`, TP `20`, FP `0`
- q `0.96`: F1 `0.2614`, Recall `0.1504`, Precision `1.0000`, FPR `0.0000`, TP `20`, FP `0`
- q `0.975`: F1 `0.2384`, Recall `0.1353`, Precision `1.0000`, FPR `0.0000`, TP `18`, FP `0`
- q `0.98`: F1 `0.2384`, Recall `0.1353`, Precision `1.0000`, FPR `0.0000`, TP `18`, FP `0`
- q `0.99`: F1 `0.2267`, Recall `0.1278`, Precision `1.0000`, FPR `0.0000`, TP `17`, FP `0`
- q `0.995`: F1 `0.2148`, Recall `0.1203`, Precision `1.0000`, FPR `0.0000`, TP `16`, FP `0`

## Priority 영향

- 현재 `priority_engine_v2_threshold48`은 `anomaly_label`이 아니라 연속값 `anomaly_score`를 사용한다.
- 따라서 threshold quantile만 바꿔도 priority_score와 priority_level은 직접 바뀌지 않는다.
- quantile 변경은 anomaly_label, 이상치 개수, main abnormal 판단 기준, 보고용 이상 감지 민감도에 영향을 준다.

- priority 매칭 holdout rows: `366`
- quantile-only priority score delta: `0.0`

## 해석

- quantile을 낮추면 더 많은 window를 anomaly로 찍어서 recall은 올라가지만 normal 오탐도 증가한다.
- quantile을 높이면 강한 이상만 잡아서 오탐은 줄지만 pre_fault 선행 이상을 놓칠 가능성이 커진다.
- 현재 공식 q=0.99는 매우 보수적이며 holdout FP는 0이지만 recall이 낮다.
- 운영에서 anomaly_label을 직접 경보로 쓸 거면 q=0.98 또는 q=0.99 같은 보수 구간을 검토하고, risk/priority는 연속 anomaly_score를 유지하는 것이 안전하다.
