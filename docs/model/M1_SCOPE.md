# M1 Scope

이 저장소는 `manufacturer 1`만 대상으로 한다.

## 포함 범위

```text
manufacturer == manufacturer 1
```

M2 row는 canonical window import 단계에서 제외된다. anomaly 학습, current-best score bridge, M1 specialist gate scoring, hybrid priority, validation report는 모두 M1 기준이다.

## 포함 단계

```text
raw inventory 확인
canonical window import
M1 anomaly baseline
current-best risk/leadtime/priority score bridge
operational agent card
M1 specialist gate scoring
M1 hybrid priority
validation 및 ablation
```

## 해석 제한

- 결과는 M1 특화 운영 우선순위 산출 결과다.
- M2 또는 전체 제조사 공통 성능으로 주장하지 않는다.
- M2 적용은 별도 calibration, feature coverage 확인, threshold 재검증이 필요하다.
- leadtime은 정확한 고장 시각 예측값이 아니라 priority 참고 신호다.
- priority는 현장 조치 순서를 정하는 ranking 신호이며 자동 정비 지시가 아니다.
