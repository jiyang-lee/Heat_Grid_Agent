from __future__ import annotations

from dataclasses import dataclass

from heatgrid_ops.agent.run_models import (
    ExternalDataRequest,
    ExternalDataSnapshot,
    RagEvidenceRequest,
    RagEvidenceSnapshot,
)
from heatgrid_rag.search import RagSearcher


@dataclass(frozen=True, slots=True)
class InternalRagEvidenceAdapter:
    searcher: RagSearcher

    async def search(self, request: RagEvidenceRequest) -> RagEvidenceSnapshot:
        terms = self.searcher.build_terms_from_evidence(request.source_input)
        retrieval = self.searcher.search(
            query=" ".join(terms[:24]),
            top_k=request.top_k,
            evidence=request.source_input,
        )
        references = {
            "technical_standards": [
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "document_title": chunk.get("document_title"),
                    "source_file": chunk.get("source_file"),
                    "curated_file": chunk.get("curated_file"),
                    "page_start": chunk.get("page_start"),
                    "page_end": chunk.get("page_end"),
                    "download_url": chunk.get("download_url"),
                }
                for chunk in retrieval.get("chunks", [])
                if isinstance(chunk, dict)
            ],
            "regulations": [],
        }
        return RagEvidenceSnapshot.model_validate(
            {
                "status": retrieval.get("status", "unavailable"),
                "retrieval": retrieval,
                "references": references,
            }
        )


@dataclass(frozen=True, slots=True)
class StructuredExternalDataAdapter:
    searcher: RagSearcher

    async def snapshot(self, request: ExternalDataRequest) -> ExternalDataSnapshot:
        evidence = {
            "raw_context": {
                "window": {
                    "substation_id": request.substation_id,
                    "window_start": request.window_start,
                    "window_end": request.window_end,
                }
            }
        }
        site = self.searcher.site_context_for_evidence(evidence)
        weather = self.searcher.weather_context_for_evidence(evidence)
        status = "available" if weather.get("status") == "available" else "partial"
        return ExternalDataSnapshot.model_validate(
            {"status": status, "site": site, "weather": weather}
        )
