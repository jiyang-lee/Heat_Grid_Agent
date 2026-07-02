# PreDist supervised label ratio audit

## 기준

- window_size: `6h`
- horizon_hours: `168`
- fault: `efd_possible=True` and report date 이전 7일 윈도우
- normal: `normal_events.csv` event range 안의 윈도우
- unlabeled operational row/window는 supervised 비율에서 제외

## 이벤트 행 수

| 구분 | 건수 |
|---|---:|
| fault_events | 73 |
| efd_possible_fault_events | 55 |
| normal_events | 65 |

## 6시간 윈도우 비율

| label | windows | ratio |
|---|---:|---:|
| normal | 1818 | 0.5433 |
| pre_fault | 1528 | 0.4567 |
| total | 3346 | 1.0000 |

## pre_fault lead bucket

| bucket | windows | ratio_in_pre_fault |
|---|---:|---:|
| `0-24h` | 217 | 0.1420 |
| `1-3d` | 436 | 0.2853 |
| `3-7d` | 875 | 0.5726 |

## 해석

- full PreDist supervised 후보 윈도우는 1:1이 아니다.
- fixture는 이 관측 비율을 따라야 하며 임의로 normal/pre_fault를 1:1로 맞추지 않는다.
