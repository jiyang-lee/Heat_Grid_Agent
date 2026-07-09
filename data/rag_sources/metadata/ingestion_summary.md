# RAG ingestion summary

## Scope

원본 PDF는 `data/rag_sources/raw/`에 보존했고, RAG ingestion 대상은 `curated/` markdown 및 `metadata/rag_chunks.jsonl`입니다.
PDF 전체를 통째로 색인하지 않았습니다.

## Document summary

| document | role | included pages | chunks | excluded summary |
|---|---|---:|---:|---|
| Danfoss Troubleshooting Table - Heating and Domestic Hot Water | `symptom_cause_action_table` | 23-24 | 12 | Excluded non-troubleshooting manual pages and generic installation text. |
| Danfoss Akva Lux II VXe Manual - Selected Operation and Maintenance Extract | `troubleshooting_manual` | 5, 10, 14, 16, 18, 20-24 | 10 | Excluded cover, table of contents, generic safety text, dimension-heavy component listings, commissioning certificate form, and unrelated installation details. |
| Prioritisation of faults in district heating substations - Selected Extract | `fault_priority_research` | 1, 4-9 | 7 | Excluded reference list, publication boilerplate, and pages without priority/fault-ranking content. |
| 열사용시설 점검업무 기술 기준서 - 선별 추출본 | `domestic_inspection_standard` | 7-12, 22-23, 26-36, 38, 42-49 | 28 | Excluded cover/revision pages, blank-like forms not needed for retrieval, and repetitive table/form areas. |
| IEA DHC Connection Handbook - Selected DH/Substation Extract | `dhc_structure_handbook` | 55, 66, 69-80, 85-86 | 16 | Excluded district-cooling-focused chapters, case histories, broad appendices, and generic glossary entries. |
| Swedish F:101 District Heating Substations - Selected Extract | `international_substation_standard` | 11-14, 16-18, 21-23, 25-26, 28-29, 48-50 | 17 | Excluded preface/table of contents, appendices dominated by diagrams, and low-relevance technical formula pages. |

## Chunk counts by rag_role

| rag_role | chunks |
|---|---:|
| `dhc_structure_handbook` | 16 |
| `domestic_inspection_standard` | 28 |
| `fault_priority_research` | 7 |
| `international_substation_standard` | 17 |
| `symptom_cause_action_table` | 12 |
| `troubleshooting_manual` | 10 |

## Generated files

- `data/rag_sources/raw/*.pdf`
- `data/rag_sources/curated/*.md`
- `data/rag_sources/metadata/rag_sources_manifest.json`
- `data/rag_sources/metadata/rag_chunks.jsonl`
- `data/rag_sources/metadata/test_query_results.md`

## Known limitations

- PDF text extraction can break some table line breaks and hyphenated words.
- Figures and diagrams are represented only by their extracted text/captions unless table extraction succeeded.
- This script prepares chunk metadata for RAG ingestion; it does not create vector embeddings.
