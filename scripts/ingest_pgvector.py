from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    import psycopg
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit("psycopg is required. Run `uv sync` first.") from exc

from heatgrid_rag.embedding import hash_embedding, vector_literal
from heatgrid_rag.pgstore import DEFAULT_DATABASE_URL, database_url_from_env


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHUNKS = ROOT / "data" / "rag_sources" / "metadata" / "rag_chunks.jsonl"
DEFAULT_SITE_CONTEXT = (
    ROOT
    / "data"
    / "external"
    / "substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv"
)

REQUIRED_CHUNK_FIELDS = {
    "chunk_id",
    "document_title",
    "source_file",
    "curated_file",
    "source_type",
    "rag_role",
    "domain",
    "language",
    "section_title",
    "text",
}

ALLOWED_RAG_ROLES = {
    "symptom_cause_action_table",
    "troubleshooting_manual",
    "fault_priority_research",
    "domestic_inspection_standard",
    "dhc_structure_handbook",
    "international_substation_standard",
    "work_order_procedure",
    "monthly_ops_context",
    "fault_case_history",
}

REPORT_DOCUMENT_ROLES = {
    "work_order_procedure": "작업지시서",
    "monthly_ops_context": "월간리포트",
    "fault_case_history": "고장보고서",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def validate_chunks(chunks: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        chunk_id = str(chunk.get("chunk_id") or f"line-{index}")
        missing = sorted(field for field in REQUIRED_CHUNK_FIELDS if chunk.get(field) in {None, ""})
        if missing:
            errors.append(f"{chunk_id}: missing required metadata fields: {', '.join(missing)}")

        rag_role = str(chunk.get("rag_role") or "").strip()
        if rag_role and rag_role not in ALLOWED_RAG_ROLES:
            errors.append(f"{chunk_id}: unsupported rag_role '{rag_role}'")

        curated_file = str(chunk.get("curated_file") or "").strip().lower()
        if not curated_file.endswith((".md", ".markdown", ".jsonl", ".csv")):
            errors.append(f"{chunk_id}: curated_file must point to a curated artifact, not a raw document")

        text = str(chunk.get("text") or "")
        if len(text) > 12000:
            errors.append(f"{chunk_id}: chunk text is too large; split before DB ingestion")

        if rag_role in REPORT_DOCUMENT_ROLES:
            source_type = str(chunk.get("source_type") or "").strip()
            if source_type not in {"work_order", "monthly_report", "fault_report"}:
                errors.append(
                    f"{chunk_id}: {REPORT_DOCUMENT_ROLES[rag_role]} chunks must use source_type "
                    "work_order/monthly_report/fault_report"
                )
            if not chunk.get("extraction_reason"):
                errors.append(f"{chunk_id}: report document chunks require extraction_reason")

    if errors:
        preview = "\n".join(errors[:20])
        suffix = f"\n... {len(errors) - 20} more errors" if len(errors) > 20 else ""
        raise SystemExit(f"Invalid RAG chunk input. DB ingestion stopped.\n{preview}{suffix}")


def document_id_for(chunk: dict[str, Any]) -> str:
    source = "|".join(
        [
            str(chunk.get("document_title") or ""),
            str(chunk.get("source_file") or ""),
            str(chunk.get("curated_file") or ""),
        ]
    )
    return hashlib.sha1(source.encode("utf-8")).hexdigest()[:16]


def infer_fault_type(chunk: dict[str, Any]) -> str | None:
    text = " ".join(
        [
            str(chunk.get("chunk_id") or ""),
            str(chunk.get("section_title") or ""),
            str(chunk.get("text") or ""),
        ]
    ).lower()
    if any(term in text for term in ["pump", "펌프"]):
        return "pump_failure"
    if any(term in text for term in ["leak", "water loss", "누수", "보충수"]):
        return "leakage_water_loss"
    if any(term in text for term in ["pressure", "차압", "압력"]):
        return "pressure_regulator"
    if any(term in text for term in ["valve", "actuator", "밸브"]):
        return "valve_actuator"
    if any(term in text for term in ["controller", "control", "제어"]):
        return "control_controller"
    return None


def to_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def ingest_chunks(conn: psycopg.Connection, chunks: list[dict[str, Any]]) -> int:
    documents: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        document_id = document_id_for(chunk)
        documents.setdefault(
            document_id,
            {
                "document_id": document_id,
                "title": chunk.get("document_title") or document_id,
                "document_type": chunk.get("rag_role"),
                "source_path": chunk.get("source_file"),
                "metadata": {
                    "curated_file": chunk.get("curated_file"),
                    "download_url": chunk.get("download_url"),
                },
            },
        )

    with conn.cursor() as cur:
        for document in documents.values():
            cur.execute(
                """
                insert into rag_documents (
                    document_id, title, document_type, source_path, metadata
                )
                values (%s, %s, %s, %s, %s::jsonb)
                on conflict (document_id) do update set
                    title = excluded.title,
                    document_type = excluded.document_type,
                    source_path = excluded.source_path,
                    metadata = excluded.metadata,
                    updated_at = now()
                """,
                (
                    document["document_id"],
                    document["title"],
                    document["document_type"],
                    document["source_path"],
                    json.dumps(document["metadata"], ensure_ascii=False),
                ),
            )

        for order, chunk in enumerate(chunks, start=1):
            text = str(chunk.get("text") or "")
            document_id = document_id_for(chunk)
            embedding = vector_literal(hash_embedding(" ".join([
                str(chunk.get("document_title") or ""),
                str(chunk.get("section_title") or ""),
                text,
            ])))
            cur.execute(
                """
                insert into rag_chunks (
                    chunk_id, document_id, chunk_text, chunk_order, section_title,
                    rag_role, language, source_file, curated_file, page_start, page_end,
                    download_url, equipment_type, fault_type, risk_level, output_target,
                    embedding, embedding_source, metadata
                )
                values (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s::vector, %s, %s::jsonb
                )
                on conflict (chunk_id) do update set
                    document_id = excluded.document_id,
                    chunk_text = excluded.chunk_text,
                    section_title = excluded.section_title,
                    rag_role = excluded.rag_role,
                    page_start = excluded.page_start,
                    page_end = excluded.page_end,
                    fault_type = excluded.fault_type,
                    embedding = excluded.embedding,
                    metadata = excluded.metadata,
                    updated_at = now()
                """,
                (
                    chunk.get("chunk_id"),
                    document_id,
                    text,
                    order,
                    chunk.get("section_title"),
                    chunk.get("rag_role"),
                    chunk.get("language"),
                    chunk.get("source_file"),
                    chunk.get("curated_file"),
                    to_int(chunk.get("page_start")),
                    to_int(chunk.get("page_end")),
                    chunk.get("download_url"),
                    None,
                    infer_fault_type(chunk),
                    None,
                    None,
                    embedding,
                    "hash-v1",
                    json.dumps(chunk, ensure_ascii=False),
                ),
            )
    return len(chunks)


def ingest_site_context(conn: psycopg.Connection, path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as file, conn.cursor() as cur:
        for row in csv.DictReader(file):
            substation_id = to_int(row.get("substation_id"))
            if substation_id is None:
                continue
            cur.execute(
                """
                insert into substation_building_context (
                    substation_id, apartment_name, kapt_code, life_zone, dong, village,
                    road_address, jibun_address, latitude, longitude, heating_type,
                    household_count, building_count, gross_floor_area_m2,
                    private_usage_cost_latest_month_krw,
                    private_usage_cost_latest_month_unit_krw_per_m2,
                    predist_configuration_type, predist_configuration_ko,
                    predist_sensor_groups_ko, predist_sensor_column_count,
                    predist_has_outdoor_temperature_sensor,
                    predist_has_space_heating_sensor,
                    predist_has_dhw_sensor,
                    predist_has_dhw_storage_sensor,
                    predist_has_primary_heat_meter_sensor,
                    predist_has_primary_supply_return_temp_sensor,
                    mapping_note, metadata
                )
                values (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s, %s, %s, %s,
                    %s, %s::jsonb
                )
                on conflict (substation_id) do update set
                    apartment_name = excluded.apartment_name,
                    road_address = excluded.road_address,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    heating_type = excluded.heating_type,
                    household_count = excluded.household_count,
                    predist_configuration_ko = excluded.predist_configuration_ko,
                    predist_sensor_groups_ko = excluded.predist_sensor_groups_ko,
                    mapping_note = excluded.mapping_note,
                    metadata = excluded.metadata,
                    updated_at = now()
                """,
                (
                    substation_id,
                    row.get("matched_name"),
                    row.get("kapt_code"),
                    row.get("life_zone"),
                    row.get("dong"),
                    row.get("village"),
                    row.get("road_address"),
                    row.get("jibun_address"),
                    to_float(row.get("latitude")),
                    to_float(row.get("longitude")),
                    row.get("heating_type"),
                    to_int(row.get("household_count")),
                    to_int(row.get("building_count")),
                    to_float(row.get("gross_floor_area_m2")),
                    to_float(row.get("private_usage_cost_latest_month_krw")),
                    to_float(row.get("private_usage_cost_latest_month_unit_krw_per_m2")),
                    row.get("predist_configuration_type"),
                    row.get("predist_configuration_ko"),
                    row.get("predist_sensor_groups_ko"),
                    to_int(row.get("predist_sensor_column_count")),
                    to_int(row.get("predist_has_outdoor_temperature_sensor")),
                    to_int(row.get("predist_has_space_heating_sensor")),
                    to_int(row.get("predist_has_dhw_sensor")),
                    to_int(row.get("predist_has_dhw_storage_sensor")),
                    to_int(row.get("predist_has_primary_heat_meter_sensor")),
                    to_int(row.get("predist_has_primary_supply_return_temp_sensor")),
                    row.get("predist_mapping_note"),
                    json.dumps(row, ensure_ascii=False),
                ),
            )
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest HeatGrid RAG chunks and Sejong site context into pgvector")
    parser.add_argument("--database-url", default=database_url_from_env() or DEFAULT_DATABASE_URL)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS)
    parser.add_argument("--site-context", type=Path, default=DEFAULT_SITE_CONTEXT)
    args = parser.parse_args()

    chunks = read_jsonl(args.chunks)
    validate_chunks(chunks)
    with psycopg.connect(args.database_url, connect_timeout=10) as conn:
        chunk_count = ingest_chunks(conn, chunks)
        site_count = ingest_site_context(conn, args.site_context)
        conn.commit()

    print(json.dumps({
        "status": "ok",
        "chunks": chunk_count,
        "site_context_rows": site_count,
        "database_url": args.database_url.replace(args.database_url.split("@")[0].split("//")[-1], "***") if "@" in args.database_url else args.database_url,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
