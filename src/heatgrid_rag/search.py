from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHUNKS_PATH = ROOT / "data" / "rag_sources" / "metadata" / "rag_chunks.jsonl"
DEFAULT_SITE_CONTEXT_PATH = (
    ROOT
    / "data"
    / "external"
    / "substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv"
)


def unique_values(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def normalize_for_search(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"[_/,\-]", " ", text)
    text = re.sub(r"[^\w\s가-힣]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def truncate_text(value: Any, max_length: int = 1200) -> str:
    text = str(value or "").replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1].rstrip()}..."


def _get_path(data: dict[str, Any], dotted_path: str) -> Any:
    current: Any = data
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _is_historical_external_chunk(chunk: dict[str, Any]) -> bool:
    metadata = chunk.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    document_type = str(chunk.get("document_type") or "").strip().lower()
    source_type = str(
        chunk.get("source_type") or metadata.get("source_type") or ""
    ).strip().lower()
    origin = str(chunk.get("origin") or metadata.get("origin") or "").strip().lower()
    query = chunk.get("query")
    if query is None:
        query = metadata.get("query")
    return bool(
        document_type in {"external_search", "web"}
        or source_type in {"external_search", "web"}
        or origin == "external_search"
        or query is not None
    )


@dataclass(frozen=True)
class ScoredChunk:
    chunk: dict[str, Any]
    score: int
    matched_terms: list[str]


class RagSearcher:
    def __init__(
        self,
        chunks_path: Path = DEFAULT_CHUNKS_PATH,
        site_context_path: Path = DEFAULT_SITE_CONTEXT_PATH,
    ) -> None:
        self.chunks_path = chunks_path
        self.site_context_path = site_context_path
        self.chunks = self._load_chunks()
        self.site_context = self._load_site_context()
        self.pg_store = self._load_pg_store()

    def _load_chunks(self) -> list[dict[str, Any]]:
        if not self.chunks_path.exists():
            return []
        chunks: list[dict[str, Any]] = []
        for line in self.chunks_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            chunks.append(json.loads(line))
        return chunks

    def _load_site_context(self) -> dict[int, dict[str, Any]]:
        if not self.site_context_path.exists():
            return {}
        result: dict[int, dict[str, Any]] = {}
        with self.site_context_path.open("r", encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                substation_id = _to_int(row.get("substation_id"))
                if substation_id is None:
                    continue
                result[substation_id] = row
        return result

    def _load_pg_store(self) -> Any | None:
        backend = os.getenv("HEATGRID_RAG_BACKEND", "auto").strip().lower()
        if backend not in {"auto", "pgvector"}:
            return None
        try:
            from .pgstore import PgVectorStore
        except Exception:
            return None
        store = PgVectorStore()
        return store if store.available else None

    def health(self) -> dict[str, Any]:
        roles: dict[str, int] = {}
        for chunk in self.chunks:
            role = str(chunk.get("rag_role") or "unknown")
            roles[role] = roles.get(role, 0) + 1
        pg_health = self.pg_store.health() if self.pg_store else {"status": "disabled"}
        active_backend = "pgvector" if self.pg_store else "jsonl"
        return {
            "status": "ok" if self.chunks else "missing_chunks",
            "active_backend": active_backend,
            "chunk_count": len(self.chunks),
            "chunk_file": str(self.chunks_path.relative_to(ROOT)) if self.chunks_path.exists() else str(self.chunks_path),
            "site_context_count": len(self.site_context),
            "roles": roles,
            "pgvector": pg_health,
        }

    def build_terms_from_evidence(self, evidence: dict[str, Any]) -> list[str]:
        fault_group = _get_path(evidence, "priority_context.model_signals.m1_specialist_fault_group")
        base_terms = [
            fault_group,
            _get_path(evidence, "priority_context.model_signals.m1_specialist_primary_state"),
            _get_path(evidence, "priority_context.priority.priority_level"),
            _get_path(evidence, "priority_context.explanation.why_reason"),
            _get_path(evidence, "priority_context.explanation.recommended_action"),
            *(_get_path(evidence, "priority_context.explanation.review_reasons") or []),
        ]
        synonym_map = {
            "leakage_water_loss": [
                "leak",
                "leakage",
                "water loss",
                "pressure",
                "differential pressure",
                "flow",
                "valve",
                "strainer",
                "filter",
                "meter",
                "pipe",
                "누수",
                "압력",
                "차압",
                "유량",
                "밸브",
                "스트레이너",
                "필터",
                "배관",
            ],
            "no_heat": [
                "no heat",
                "low temperature",
                "strainer",
                "filter",
                "air pockets",
                "pump",
                "난방",
                "온도",
                "미공급",
            ],
            "overheating": [
                "overheating",
                "control valve",
                "thermostat",
                "controller",
                "setpoint",
                "과열",
                "제어밸브",
                "설정값",
            ],
        }
        synonyms = synonym_map.get(str(fault_group or "").lower(), [])
        generic_terms = [
            "district heating",
            "substation",
            "heat exchanger",
            "operation",
            "maintenance",
            "inspection",
            "지역난방",
            "기계실",
            "열교환기",
            "점검",
            "유지관리",
        ]
        return unique_values([*base_terms, *synonyms, *generic_terms])

    def score_chunk(self, chunk: dict[str, Any], terms: list[str], evidence: dict[str, Any] | None = None) -> ScoredChunk:
        searchable = normalize_for_search(
            " ".join(
                [
                    str(chunk.get("chunk_id") or ""),
                    str(chunk.get("document_title") or ""),
                    str(chunk.get("rag_role") or ""),
                    str(chunk.get("section_title") or ""),
                    str(chunk.get("text") or ""),
                ]
            )
        )
        score = 0
        matched_terms: list[str] = []
        for term in terms:
            normalized = normalize_for_search(term)
            if len(normalized) < 2:
                continue
            if normalized in searchable:
                score += 3 if len(normalized) >= 8 else 1
                matched_terms.append(term)

        role = chunk.get("rag_role")
        if role == "symptom_cause_action_table":
            score += 4
        elif role == "troubleshooting_manual":
            score += 3
        elif role == "domestic_inspection_standard":
            score += 2
        elif role == "fault_priority_research":
            score += 1

        if evidence:
            fault_group = str(
                _get_path(evidence, "priority_context.model_signals.m1_specialist_fault_group") or ""
            ).lower()
            if fault_group == "leakage_water_loss":
                if "leak" in searchable or "water loss" in searchable:
                    score += 8
                if "pressure" in searchable or "차압" in searchable:
                    score += 4
                if "strainer" in searchable or "filter" in searchable or "스트레이너" in searchable:
                    score += 3
                if "flow" in searchable or "유량" in searchable:
                    score += 2

        return ScoredChunk(chunk=chunk, score=score, matched_terms=unique_values(matched_terms)[:12])

    def search(self, query: str, top_k: int = 5, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        top_k = max(1, min(int(top_k or 5), 20))
        if self.pg_store is not None:
            return self.pg_store.search_chunks(query=query, top_k=top_k)

        terms = unique_values(normalize_for_search(query).split(" "))
        scored = [
            self.score_chunk(chunk, terms, evidence=evidence)
            for chunk in self.chunks
            if not _is_historical_external_chunk(chunk)
        ]
        selected = sorted(
            [item for item in scored if item.score > 0],
            key=lambda item: (-item.score, str(item.chunk.get("chunk_id") or "")),
        )[:top_k]
        return {
            "status": "available" if selected else "no_match",
            "source": "rag_http_server",
            "backend": "jsonl",
            "chunk_file": str(self.chunks_path.relative_to(ROOT)) if self.chunks_path.exists() else str(self.chunks_path),
            "query": query,
            "top_k": len(selected),
            "chunks": [self._serialize(item) for item in selected],
        }

    def external_context(self, card_id: str, evidence: dict[str, Any], top_k: int = 5) -> dict[str, Any]:
        terms = self.build_terms_from_evidence(evidence)
        query = " ".join(terms[:24])
        retrieval = self.search(query=query, top_k=top_k, evidence=evidence)
        chunks = retrieval["chunks"]
        site = self.site_context_for_evidence(evidence)
        weather = self.weather_context_for_evidence(evidence)
        return {
            "card_id": card_id,
            "status": "configured" if chunks else "configured_no_match",
            "site": site,
            "weather": weather,
            "retrieval": retrieval,
            "references": {
                "technical_standards": [
                    {
                        "chunk_id": chunk["chunk_id"],
                        "document_title": chunk["document_title"],
                        "source_file": chunk["source_file"],
                        "curated_file": chunk["curated_file"],
                        "page_start": chunk["page_start"],
                        "page_end": chunk["page_end"],
                        "download_url": chunk.get("download_url"),
                    }
                    for chunk in chunks
                ],
                "regulations": [],
            },
        }

    def site_context_for_evidence(self, evidence: dict[str, Any]) -> dict[str, Any]:
        substation_id = _to_int(_get_path(evidence, "raw_context.window.substation_id"))
        if substation_id is None:
            return {"status": "missing_substation_id"}
        row = self.site_context.get(substation_id)
        if not row:
            return {
                "status": "not_mapped",
                "substation_id": substation_id,
                "mapping_scope": "sejong_virtual_1_31",
            }
        return {
            "status": "mapped",
            "mapping_scope": "sejong_virtual_1_31",
            "mapping_type": row.get("predist_mapping_type") or "virtual_by_substation_id",
            "substation_id": substation_id,
            "apartment_name": row.get("matched_name"),
            "kapt_code": row.get("kapt_code"),
            "life_zone": row.get("life_zone"),
            "dong": row.get("dong"),
            "village": row.get("village"),
            "road_address": row.get("road_address"),
            "jibun_address": row.get("jibun_address"),
            "latitude": _to_float(row.get("latitude")),
            "longitude": _to_float(row.get("longitude")),
            "heating_type": row.get("heating_type"),
            "household_count": _to_int(row.get("household_count")),
            "building_count": _to_int(row.get("building_count")),
            "gross_floor_area_m2": _to_float(row.get("gross_floor_area_m2")),
            "latest_private_usage_cost_krw": _to_float(row.get("private_usage_cost_latest_month_krw")),
            "latest_private_usage_unit_krw_per_m2": _to_float(
                row.get("private_usage_cost_latest_month_unit_krw_per_m2")
            ),
            "predist_configuration_type": row.get("predist_configuration_type"),
            "predist_configuration_ko": row.get("predist_configuration_ko"),
            "predist_sensor_groups_ko": row.get("predist_sensor_groups_ko"),
            "predist_sensor_column_count": _to_int(row.get("predist_sensor_column_count")),
            "predist_source_file": row.get("predist_source_file"),
            "caution": row.get("predist_mapping_note")
            or "세종 아파트와 PreDist 설비의 실제 물리 연결은 검증되지 않은 가상 매핑입니다.",
        }

    def weather_context_for_evidence(self, evidence: dict[str, Any]) -> dict[str, Any]:
        if os.getenv("HEATGRID_DISABLE_WEATHER", "0") == "1":
            return {"status": "disabled"}
        if not os.getenv("KMA_SERVICE_KEY", "").strip():
            return {
                "status": "not_configured",
                "source": "KMA APIHub ASOS hourly observations",
                "message": "KMA_SERVICE_KEY is not configured.",
            }
        window_start = _get_path(evidence, "raw_context.window.window_start")
        window_end = _get_path(evidence, "raw_context.window.window_end")
        if not window_start or not window_end:
            return {"status": "missing_window"}
        try:
            from heatgrid_weather import build_weather_context

            weather = build_weather_context(window_start=window_start, window_end=window_end)
            weather["status"] = "available"
            return weather
        except Exception as exc:
            return {
                "status": "unavailable",
                "source": "KMA APIHub ASOS hourly observations",
                "window_start": window_start,
                "window_end": window_end,
                "message": str(exc),
            }

    def log_agent_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        from .pgstore import append_local_run_log

        return append_local_run_log(payload)

    def recent_runs(self, limit: int = 20) -> dict[str, Any]:
        from .pgstore import recent_local_run_logs

        return recent_local_run_logs(limit=limit)

    def _serialize(self, item: ScoredChunk) -> dict[str, Any]:
        chunk = item.chunk
        return {
            "chunk_id": chunk.get("chunk_id"),
            "document_id": chunk.get("document_id"),
            "document_title": chunk.get("document_title"),
            "document_type": (
                "operator_manual_evidence"
                if chunk.get("document_type") == "operator_manual_evidence"
                else "internal_rag"
            ),
            "source_owner": chunk.get("source_owner"),
            "source_file": chunk.get("source_file"),
            "curated_file": chunk.get("curated_file"),
            "rag_role": chunk.get("rag_role"),
            "language": chunk.get("language"),
            "page_start": chunk.get("page_start"),
            "page_end": chunk.get("page_end"),
            "section_title": chunk.get("section_title"),
            "download_url": chunk.get("download_url"),
            "score": item.score,
            "matched_terms": item.matched_terms,
            "text": truncate_text(chunk.get("text")),
            "provenance": {
                "backend": "jsonl",
                "document_id": chunk.get("document_id"),
                "chunk_id": chunk.get("chunk_id"),
                "document_type": chunk.get("document_type"),
                "source_path": chunk.get("source_path") or chunk.get("source_file"),
                "source_owner": chunk.get("source_owner"),
            },
        }


def _to_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
