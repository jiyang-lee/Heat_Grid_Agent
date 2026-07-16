# HeatGrid RAG Evaluation Documentation

## HeatGrid RAG Evaluation Framework 소개

HeatGrid RAG Evaluation Framework는 HeatGrid 프로젝트의 RAG(Retrieval-Augmented Generation, 검색 증강 생성) 품질을 단계별로 확인하기 위한 평가 체계다. 이 Framework는 단순히 "검색이 잘 되었는가"만 보지 않고, Retrieval Evaluation(검색 평가)에서 시작해 Answer Generation(답변 생성), Automatic Evaluation(자동 평가), LLM Judge(대규모 언어 모델 기반 평가), Manual Review(수동 검토)까지 이어지는 전체 흐름을 평가한다.

이 문서는 프로젝트 결과보고서가 아니라 평가 절차와 재현 방법을 설명하는 문서다. 최종 결과 수치와 해석은 [Evaluation Report](./EVALUATION_REPORT.md)에 정리되어 있으며, 이 문서와 단계별 문서는 누가 다시 평가를 실행하더라도 같은 구조를 이해하고 재현할 수 있도록 돕는 인수인계용 안내서다.

## 1. 문서 목적

이 폴더는 HeatGrid RAG Evaluation Framework의 단계별 산출물과 재현 절차를 설명한다. 프로젝트를 처음 보는 사람도 다음 내용을 이해할 수 있도록 구성했다.

- 평가 데이터셋이 어떻게 만들어졌는가
- Retrieval, Generation, Automatic Evaluation, LLM Judge, Manual Review가 어떤 순서로 연결되는가
- 각 단계에서 어떤 입력 파일과 출력 파일을 사용하는가
- 현재 결과를 재현하려면 어떤 명령을 실행해야 하는가
- 어떤 한계가 있고 후속 작업은 무엇인가

## 2. 전체 Pipeline

```text
Dataset
  ↓
Retrieval Evaluation
  ↓
Answer Generation
  ↓
Automatic Evaluation
  ↓
LLM Judge
  ↓
Manual Review
```

각 단계는 이전 단계의 결과를 입력으로 사용한다. 따라서 Retrieval 결과가 좋지 않으면 Answer Generation 품질에도 영향을 주고, Automatic Evaluation과 LLM Judge는 그 영향을 다시 분석한다.

## 3. 문서 목록

| 순서 | 문서 | 역할 |
| --- | --- | --- |
| 01 | [Evaluation Dataset](./01_EVALUATION_DATASET.md) | 평가 case와 Gold Chunk(정답 근거 Chunk) 구조 설명 |
| 02 | [Retrieval Evaluation](./02_RETRIEVAL_EVALUATION.md) | Recall, Precision, MRR, nDCG 기반 검색 평가 |
| 03 | [Answer Generation](./03_ANSWER_GENERATION.md) | Retrieval 결과를 이용한 답변 생성 절차 |
| 04 | [Automatic Evaluation](./04_AUTOMATIC_EVALUATION.md) | Rule-based Evaluation(규칙 기반 자동 평가) 설명 |
| 05 | [LLM Judge](./05_LLM_JUDGE.md) | LLM Judge 평가 기준과 실행 결과 설명 |
| 06 | [Manual Review](./06_MANUAL_REVIEW.md) | 사람 검토 기준과 주요 발견 사항 |
| Scope | [기존 목표와 확장 범위](./SCOPE_AND_EXTENSION.md) | dev2-rag 보존 범위와 dev2-raglogic 추가 요구사항 |
| Report | [Evaluation Report](./EVALUATION_REPORT.md) | 전체 평가 결과를 종합한 최종 보고서 |

## 4. 주요 용어

| 용어 | 의미 |
| --- | --- |
| RAG | Retrieval-Augmented Generation, 검색 결과를 근거로 답변을 생성하는 구조 |
| Semantic Retrieval | 의미 기반 검색 |
| Lexical Search | 키워드 기반 검색 |
| Gold Chunk | 정답 근거 Chunk |
| Retrieval Hit | Gold Chunk가 검색 결과 안에 포함된 상태 |
| Retrieval Miss | Gold Chunk가 검색 결과 안에 포함되지 않은 상태 |
| Citation | 답변이 참조한 근거 Chunk ID |
| Rule-based Evaluation | 코드 규칙으로 자동 판정 가능한 항목을 평가하는 방식 |
| LLM Judge | LLM을 평가자로 사용해 의미 품질을 채점하는 방식 |
| Manual Review | 사람이 evidence와 Judge 결과를 비교해 재검토하는 단계 |

## 5. 재현 순서

각 단계별 세부 명령은 개별 문서에 정리되어 있다. 전체 흐름은 다음 순서로 확인한다.

1. 데이터셋 구조 확인: [01_EVALUATION_DATASET.md](./01_EVALUATION_DATASET.md)
2. Retrieval 평가 재현: [02_RETRIEVAL_EVALUATION.md](./02_RETRIEVAL_EVALUATION.md)
3. Answer Generation 실행 조건 확인: [03_ANSWER_GENERATION.md](./03_ANSWER_GENERATION.md)
4. Rule-based Evaluation 실행: [04_AUTOMATIC_EVALUATION.md](./04_AUTOMATIC_EVALUATION.md)
5. LLM Judge 결과 확인: [05_LLM_JUDGE.md](./05_LLM_JUDGE.md)
6. Manual Review 결과 확인: [06_MANUAL_REVIEW.md](./06_MANUAL_REVIEW.md)

## 6. 주의사항

- 이 문서들은 평가 절차 설명용이며, 기존 결과 JSON/JSONL을 수정하지 않는다.
- 결과 수치는 각 Summary 파일과 Validation 문서를 기준으로 작성한다.
- LLM Judge 결과는 사람이 직접 검토한 최종 판정이 아니라 의미 기반 자동 평가 결과다.
- Generation과 Judge에 같은 모델(`gpt-5.4-mini`)이 사용되었으므로 Self-preference Bias(자기 선호 편향)를 고려해야 한다.
