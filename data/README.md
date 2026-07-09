# HeatGrid Data Folder Boundaries

프로젝트 데이터가 섞이지 않도록 아래 경계를 유지합니다.

## `data/external/`

세종 아파트, K-APT, 지역난방 공급현황, PreDist substation 가상 매핑처럼 정적인 외부 결합 데이터를 둡니다.

예:

- `substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv`
- `predist_virtual_substation_sensor_metadata_m1.csv`

## `data/rag_sources/`

RAG 원본 PDF, 선별 markdown, chunk metadata만 둡니다.

원본 PDF 전체는 보존만 하고, ingestion은 `curated/`와 `metadata/rag_chunks.jsonl`만 사용합니다.

## `data/weather/`

기상청 ASOS API 응답, 샘플 weather context, 운영 캐시만 둡니다.

기상 데이터는 RAG 문서가 아니며, LangGraph의 `get_weather_context` tool에서 날짜/시간 기준으로 조회하는 정형 외부 데이터입니다.

## `data/processed/`, `data/interim/`

모델 학습/검증 파이프라인의 중간 산출물과 처리 결과를 둡니다.

외부 서비스 연동 결과를 임의로 넣지 않습니다.
