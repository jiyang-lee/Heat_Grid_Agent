# HeatGrid RAG curated corpus

이 폴더는 원본 PDF 전체를 그대로 색인하지 않고, HeatGrid Agent의 위험 설명/원인 추정/조치안 생성에 필요한 부분만 선별한 RAG 입력 자료입니다.

## 사용 원칙

- `raw/`에는 원본 PDF를 보존합니다.
- 실제 RAG ingestion은 `curated/`의 markdown과 `metadata/rag_chunks.jsonl`만 사용합니다.
- 표지, 목차, 회사 소개, 광고성 페이지, 반복 안전문구, 프로젝트와 무관한 설치 세부사항은 제외했습니다.
- 최종 답변 생성 시 모델 수치 근거와 RAG 문서 근거를 분리해서 설명해야 합니다.

## Curated files

| file | rag_role | included pages | chunks |
|---|---|---:|---:|
| `danfoss_troubleshooting_table.md` | `symptom_cause_action_table` | 23-24 | 12 |
| `danfoss_substation_operation_extract.md` | `troubleshooting_manual` | 5, 10, 14, 16, 18, 20-24 | 10 |
| `fault_priority_extract.md` | `fault_priority_research` | 1, 4-9 | 7 |
| `kdhc_inspection_extract.md` | `domestic_inspection_standard` | 7-12, 22-23, 26-36, 38, 42-49 | 28 |
| `iea_sh_dhw_substation_extract.md` | `dhc_structure_handbook` | 55, 66, 69-80, 85-86 | 16 |
| `swedish_f101_operation_extract.md` | `international_substation_standard` | 11-14, 16-18, 21-23, 25-26, 28-29, 48-50 | 17 |

## Metadata files

- `metadata/rag_sources_manifest.json`: 원본/선별 문서 manifest
- `metadata/rag_chunks.jsonl`: 서버 ingest용 chunk 데이터
- `metadata/ingestion_summary.md`: 포함/제외 범위 및 chunk 수 요약
- `metadata/test_query_results.md`: 검증 query별 상위 검색 결과
