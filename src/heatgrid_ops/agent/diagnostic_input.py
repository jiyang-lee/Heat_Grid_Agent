from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from heatgrid_ops.agent.diagnostics import (
    DIAGNOSTIC_INPUT_TOKEN_LIMIT,
    DiagnosticRagChunk,
    DiagnosticWorkerInput,
    estimate_diagnostic_input_tokens,
)

MAX_RAG_CHUNKS: Final = 5
MAX_RAG_EXCERPT_TOKENS: Final = 400
CHARS_PER_TOKEN: Final = 4


@dataclass(frozen=True, slots=True)
class DiagnosticInputPreparation:
    request: DiagnosticWorkerInput | None
    before_tokens: int
    after_tokens: int
    selected_evidence_ids: tuple[str, ...] = ()
    fallback_reason: str | None = None


def prepare_diagnostic_input(
    request: DiagnosticWorkerInput,
) -> DiagnosticInputPreparation:
    before_tokens = estimate_diagnostic_input_tokens(request)
    if request.weather.status != "available":
        return _fallback(request, before_tokens, "diagnostic_weather_unavailable")

    chunks = sorted(
        (chunk for chunk in request.rag_chunks if chunk.excerpt.strip()),
        key=lambda chunk: (-chunk.score, chunk.evidence_id),
    )[:MAX_RAG_CHUNKS]
    if not chunks:
        return _fallback(request, before_tokens, "diagnostic_citable_rag_unavailable")

    compact = request.model_copy(update={"rag_chunks": []})
    fixed_tokens = estimate_diagnostic_input_tokens(compact)
    if fixed_tokens > DIAGNOSTIC_INPUT_TOKEN_LIMIT:
        return DiagnosticInputPreparation(
            request=None,
            before_tokens=before_tokens,
            after_tokens=fixed_tokens,
            fallback_reason="diagnostic_minimum_input_exceeds_3000_tokens",
        )

    selected: list[DiagnosticRagChunk] = []
    for chunk in chunks:
        candidate = chunk.model_copy(update={"excerpt": ""})
        with_metadata = compact.model_copy(
            update={"rag_chunks": [*selected, candidate]}
        )
        metadata_tokens = estimate_diagnostic_input_tokens(with_metadata)
        remaining = DIAGNOSTIC_INPUT_TOKEN_LIMIT - metadata_tokens
        if remaining <= 0:
            break
        excerpt_tokens = min(MAX_RAG_EXCERPT_TOKENS, remaining)
        selected.append(
            candidate.model_copy(
                update={"excerpt": chunk.excerpt[: excerpt_tokens * CHARS_PER_TOKEN]}
            )
        )
        compact = request.model_copy(update={"rag_chunks": selected})

    compact = _trim_to_limit(compact)
    after_tokens = estimate_diagnostic_input_tokens(compact)
    if not compact.rag_chunks or after_tokens > DIAGNOSTIC_INPUT_TOKEN_LIMIT:
        return DiagnosticInputPreparation(
            request=None,
            before_tokens=before_tokens,
            after_tokens=after_tokens,
            fallback_reason="diagnostic_compaction_exhausted",
        )
    return DiagnosticInputPreparation(
        request=compact,
        before_tokens=before_tokens,
        after_tokens=after_tokens,
        selected_evidence_ids=tuple(chunk.evidence_id for chunk in compact.rag_chunks),
    )


def _trim_to_limit(request: DiagnosticWorkerInput) -> DiagnosticWorkerInput:
    compact = request
    while estimate_diagnostic_input_tokens(compact) > DIAGNOSTIC_INPUT_TOKEN_LIMIT:
        chunks = list(compact.rag_chunks)
        last = chunks[-1]
        overflow = (
            estimate_diagnostic_input_tokens(compact) - DIAGNOSTIC_INPUT_TOKEN_LIMIT
        )
        trimmed = last.excerpt[: max(0, len(last.excerpt) - overflow * CHARS_PER_TOKEN)]
        if not trimmed:
            chunks.pop()
        else:
            chunks[-1] = last.model_copy(update={"excerpt": trimmed})
        compact = compact.model_copy(update={"rag_chunks": chunks})
        if not chunks:
            break
    return compact


def _fallback(
    request: DiagnosticWorkerInput,
    before_tokens: int,
    reason: str,
) -> DiagnosticInputPreparation:
    return DiagnosticInputPreparation(
        request=None,
        before_tokens=before_tokens,
        after_tokens=estimate_diagnostic_input_tokens(request),
        fallback_reason=reason,
    )
