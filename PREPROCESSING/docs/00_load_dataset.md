# 00. 데이터 다운로드 및 정리 문서

이 문서는 `PREPROCESSING/osj/00_load_dataset.ipynb`의 목적과 실행 기준을 정리한다.

00번 노트북은 HeatGrid Agent의 ML 파트에서 사용할 외부 공개 데이터를 로컬 `data/raw_data` 아래에 준비하는 단계다.
Git 저장소에는 원천 데이터 파일을 올리지 않고, 실행 시 필요한 사람이 직접 내려받도록 한다.

## 프로젝트 관점의 목적

HeatGrid Agent의 ML 파트는 PreDist v2 운영 시계열과 고장/정상/정비 이력을 기준으로 위험 가능성, lead time, 주요 이상 센서 후보를 만든다.
따라서 00번 단계는 모델링이 아니라 재현 가능한 데이터 확보 단계다.

## 다루는 데이터

- PreDist v2
  - 원본: `https://zenodo.org/records/19496480`
  - 저장 위치: `data/raw_data/predist_v2`
  - 현재 01~02 단계에서 직접 사용한다.
- XAI4HEAT SCADA
  - 원본: `https://data.mendeley.com/datasets/2mwc6x6kwb/1`
  - 저장 위치: `data/raw_data/xai4heat_scada_dataset`
  - 현재 01~02 단계에서는 직접 사용하지 않는다. 이후 비교 실험 또는 추가 검증용 데이터로 남긴다.

## 실행 순서

1. `PREPROCESSING/osj/00_load_dataset.ipynb`를 연다.
2. 프로젝트 루트와 데이터 저장 경로를 만든다.
3. PreDist zip을 내려받고 `data/raw_data/predist_v2`에 압축 해제한다.
4. Mendeley 공개 API에서 XAI4HEAT 파일 목록을 읽고 CSV를 저장한다.
5. 저장된 파일 목록을 확인한다.

## 디렉터리 규칙

- `data/raw_data/`는 Git에 올리지 않는다.
- `data/_downloads/`는 다운로드 중간 파일 보관용이며 Git에 올리지 않는다.
- `data/processed/`는 노트북 실행으로 다시 만들 수 있는 중간 산출물이므로 Git에 올리지 않는다.
