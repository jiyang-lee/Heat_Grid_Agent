# `00_load_dataset.ipynb` 설명

이 노트북은 외부 데이터셋을 내려받아 `data/raw_data` 아래에 정리하는 초기 전처리 단계입니다.

## 목적

- Git 저장소에는 데이터 파일을 넣지 않는다.
- 실행 시 Zenodo와 Mendeley Data에서 원본 파일을 가져온다.
- 가져온 파일을 로컬의 `data/raw_data` 아래에 분리해서 저장한다.
- 한글 설명과 실행 절차를 노트북 안에서 바로 읽을 수 있게 한다.

## 다루는 데이터

- PreDist
  - 원본: `https://zenodo.org/records/19496480`
  - 저장 위치: `data/raw_data/predist_v2`
- XAI4HEAT SCADA
  - 원본: `https://data.mendeley.com/datasets/2mwc6x6kwb/1`
  - 저장 위치: `data/raw_data/xai4heat_scada_dataset`

## 실행 순서

1. `PREPROCESSING/00_load_dataset.ipynb`를 연다.
2. 첫 번째 셀에서 프로젝트 루트와 저장 경로를 만든다.
3. PreDist zip 다운로드 및 압축 해제를 실행한다.
4. Mendeley Data 공개 API에서 파일 목록을 읽고 각 CSV를 다운로드한다.
5. 마지막 셀에서 저장된 파일 목록을 확인한다.

## 디렉터리 규칙

- `data/raw_data/`는 Git에 올리지 않는다.
- `data/_downloads/`는 다운로드 중간 파일 보관용이다.
- `PREPROCESSING/docs/`는 전처리 노트북 설명용 문서만 둔다.

## 주의사항

- Zenodo는 세션이 없는 요청에서 403을 줄 수 있으므로 노트북은 세션 기반 다운로드를 사용한다.
- 실행 환경의 네트워크가 막혀 있으면 다운로드 단계에서 실패할 수 있다.
- 한글이 깨지면 노트북 파일 인코딩 문제가 아니라 실행 환경의 표시 문제일 가능성이 크다.
