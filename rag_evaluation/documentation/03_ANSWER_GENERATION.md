# 03 Answer Generation

## 1. 단계 개요

Answer Generation(답변 생성)은 Retrieval 결과를 입력으로 사용해 case별 답변을 생성하는 단계다. 이 단계는 검색 결과가 실제 사용자 답변으로 어떻게 연결되는지 확인하기 위해 수행했다.

Generation 단계에서는 평가 정답 라벨을 모델에게 직접 제공하지 않는다. Judge나 평가 단계에서만 expected answer points와 forbidden claims를 사용한다.

## 2. 왜 필요한가?

Retrieval Evaluation은 검색 품질을 보여주지만, RAG의 최종 사용자 경험은 답변 품질로 결정된다. 따라서 다음 질문에 답해야 한다.

- Retrieval Hit case에서 근거를 실제로 잘 활용하는가
- Retrieval Miss case에서 무리하게 단정하지 않는가
- Citation(근거 인용)이 retrieved context 안의 Chunk ID만 사용되는가
- answerable=false case에서 유보 표현을 적절히 사용하는가

## 3. 사용 모델과 Prompt

| 항목 | 값 |
| --- | --- |
| Generation Model | `gpt-5.4-mini` |
| Prompt Version | `answer-generation-v1.1` 계열 |
| Temperature | 0 |
| 입력 | `query`, `retrieved_contexts`, `metadata`, `answerable`, `retrieval_hit_at_5` |
| 금지 | expected answer points를 Generation 입력으로 사용하지 않음 |

## 4. Retrieval Hit와 Retrieval Miss 정책

| 상황 | 답변 정책 |
| --- | --- |
| Retrieval Hit | 질문의 핵심 답변을 직접 뒷받침하는 Chunk만 Citation으로 사용 |
| Retrieval Miss | 직접 근거가 없으면 유보 답변을 생성하고 `cited_chunk_ids=[]` 허용 |
| answerable=false | 무리하게 답변하지 않고 현재 근거 범위에서 확인 불가를 명시 |

Retrieval Miss에서 약한 관련 Chunk를 근거처럼 인용하면 Citation Accuracy가 낮아질 수 있다. 이 문제를 줄이기 위해 Prompt에는 직접 근거 기준과 유보 표현 정책이 추가되었다.

## 5. 실행 방법

사전 계획 확인:

```bash
python rag_evaluation/scripts/run_answer_generation.py --plan-only
```

전체 실행:

```bash
python rag_evaluation/scripts/run_answer_generation.py
```

API Key 값은 출력하거나 파일에 기록하지 않는다.

## 6. 주요 입력 및 출력 파일

| 파일 | 역할 |
| --- | --- |
| `rag_evaluation/results/real_retrieval_results.jsonl` | Retrieval 결과 |
| `rag_evaluation/answer_evaluation/answer_eval.draft.jsonl` | 평가용 질문 및 라벨 |
| `rag_evaluation/answer_generation/answer_generation_prompt.md` | Answer Generation Prompt |
| `rag_evaluation/results/answer_generation_all.jsonl` | 전체 28건 생성 결과 |
| `rag_evaluation/results/answer_generation_all_summary.json` | 생성 결과 Summary |

## 7. 생성 결과에서 확인할 필드

| 필드 | 의미 |
| --- | --- |
| `generated_answer` | 생성된 답변 |
| `cited_chunk_ids` | 답변이 참조한 Chunk ID |
| `retrieved_contexts` | 모델이 받은 검색 근거 |
| `generation_metadata` | 모델, Prompt Version, token usage 등 |

## 8. 해석

Answer Generation 결과는 아직 평가 결과가 아니다. 이 단계의 결과는 다음 단계인 Automatic Evaluation과 LLM Judge의 입력으로 사용된다.

특히 Retrieval Miss case에서는 답변이 짧거나 유보적이어도 정책상 올바를 수 있다. 반대로 근거 없는 확정 표현이 있으면 후속 평가에서 문제로 분류된다.

## 9. 한계

- 같은 모델이 Generation과 LLM Judge에 사용되었으므로 후속 평가에서 Self-preference Bias(자기 선호 편향)를 고려해야 한다.
- Retrieval 결과가 부정확하면 Generation이 안전하게 유보해도 사용자 관점의 답변 만족도는 낮을 수 있다.
- 생성 답변의 의미적 정확성은 이 단계가 아니라 LLM Judge와 Manual Review에서 판단한다.

## 10. 관련 문서

- [Retrieval Evaluation](./02_RETRIEVAL_EVALUATION.md)
- [Automatic Evaluation](./04_AUTOMATIC_EVALUATION.md)
- [Evaluation Report](./EVALUATION_REPORT.md)

---

## 핵심 요약

✅ 이 단계에서는 Retrieval 결과를 바탕으로 LLM 답변과 Citation을 생성했다.  
✅ Retrieval 품질이 실제 운영 답변 품질로 이어지는지 확인하려면 Generation 단계가 필요하다.  
✅ 주요 결과 파일은 `rag_evaluation/results/answer_generation_all.jsonl`과 관련 Summary 파일이다.  
✅ 다음 단계는 생성된 답변을 Rule-based Automatic Evaluation으로 1차 점검하는 것이다.

