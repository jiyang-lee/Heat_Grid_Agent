# mlmodel2 시작 가이드

이 브랜치는 **전처리(00~03)까지만 만들어둔 베이스**다.
너는 03이 만든 결과물을 입력으로 **04 feature engineering부터 새로 짜면 된다.**

```
[고정] 00 → 01 → 02 → 03  →  ml_window_dataset.csv
                                     │
[네 작업]                            └→ 04 FE → 05 → 06 ...
```

---

## 1. 환경 준비

```bash
git clone https://github.com/jiyang-lee/Heat_Grid_Agent.git
cd Heat_Grid_Agent
git checkout mlmodel2
uv sync          # uv 없으면: pip install uv
```

> 예전에 mlmodel2를 받아둔 적 있으면: `git fetch origin && git reset --hard origin/mlmodel2`

---

## 2. raw 데이터 넣기

받아둔 PreDist v2 데이터를 아래 위치에 그대로 넣는다. (git에는 안 올라감)

```
data/raw_data/predist_v2/
├── manufacturer 1/
│   ├── operational_data/substation_*.csv
│   ├── configuration_types.csv
│   ├── faults.csv
│   ├── normal_events.csv
│   └── disturbances.csv
└── manufacturer 2/   (구조 동일)
```

폴더 이름 공백(`manufacturer 1`)까지 그대로 둔다. 노트북이 이 경로를 그대로 읽는다.

---

## 3. 노트북 실행 (00 → 03)

`PREPROCESSING/osj/` 안의 노트북을 순서대로 실행한다.

1. `00_load_dataset.ipynb` — 데이터 확인 (raw 이미 있으면 다운로드는 건너뜀)
2. `01_raw_inspection.ipynb` — 컬럼/결측 점검
3. `02_label_alignment.ipynb` — 라벨 정렬
4. `03_preprocess_windows.ipynb` — 윈도우 생성

실행이 끝나고 이 파일이 생기면 준비 완료:

```
data/processed/ml_windows/ml_window_dataset.csv   ← 04의 입력
```

**03까지는 고정이다. 건드리지 말 것.**

---

## 4. 여기서부터 네 작업 (Feature Engineering)

`ml_window_dataset.csv`를 입력으로 04를 새로 만든다.

- 학습 행: `use_for_supervised_training == True`, `label`이 `normal`/`pre_fault`인 행
- 누수 방지: 결측 대체·스케일 통계는 **train split에서만** 계산 (split 컬럼은 03이 이미 줌)
- 피처 아이디어: 추세(`last-first`, 기울기), 물리 관계(공급-환수 온도차, 설정값 대비 편차), 정규화(외기온 잔차·그룹 z-score), 시간은 sin/cos
- 평가: 정확도 말고 **PR-AUC / ROC-AUC / recall** 위주로 본다
- 최종 출력 형식은 `PREPROCESSING/docs/ML_OUTPUT_CONTRACT.md`를 맞춘다

---

## 한 줄 요약
raw를 `data/raw_data/predist_v2/`에 넣고 → 00~03 실행 → `ml_window_dataset.csv` 생성 →
그걸 입력으로 **04 feature engineering부터 새로 설계**.

자세한 컬럼 설명: `PREPROCESSING/docs/03_preprocess_windows.md`, `agent_preprocessed_input_columns.md`
