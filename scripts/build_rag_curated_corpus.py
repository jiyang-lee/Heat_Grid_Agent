from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = Path(r"C:\Users\Admin\Desktop\ragfile")
RAG_DIR = ROOT / "data" / "rag_sources"
RAW_DIR = RAG_DIR / "raw"
CURATED_DIR = RAG_DIR / "curated"
METADATA_DIR = RAG_DIR / "metadata"

DOMAIN = "district_heating_substation"


@dataclass(frozen=True)
class SourceSpec:
    key: str
    source_pdf: Path
    raw_file: str
    curated_file: str
    document_title: str
    source_type: str
    rag_role: str
    language: str
    download_url: str
    included_pages: tuple[int, ...]
    extraction_reason: str
    excluded_summary: str


SPECS: list[SourceSpec] = [
    SourceSpec(
        key="danfoss_operation",
        source_pdf=SOURCE_DIR / "VXe_Instruction_uk.pdf",
        raw_file="danfoss_vxe_manual.pdf",
        curated_file="danfoss_substation_operation_extract.md",
        document_title="Danfoss Akva Lux II VXe Manual - Selected Operation and Maintenance Extract",
        source_type="manufacturer_manual_pdf",
        rag_role="troubleshooting_manual",
        language="en",
        download_url="https://files.danfoss.com/download/Drives/VXe_Instruction_uk.pdf",
        included_pages=(5, 10, 14, 16, 18, 20, 21, 22, 23, 24),
        extraction_reason=(
            "Selected pages cover start-up, commissioning, heating control, pump operation, DHW operation, "
            "maintenance schedule, and heating/DHW troubleshooting."
        ),
        excluded_summary=(
            "Excluded cover, table of contents, generic safety text, dimension-heavy component listings, "
            "commissioning certificate form, and unrelated installation details."
        ),
    ),
    SourceSpec(
        key="fault_priority",
        source_pdf=SOURCE_DIR / "930_Volltext.pdf",
        raw_file="prioritisation_faults_substations.pdf",
        curated_file="fault_priority_extract.md",
        document_title="Prioritisation of faults in district heating substations - Selected Extract",
        source_type="research_paper_pdf",
        rag_role="fault_priority_research",
        language="en",
        download_url="https://publica.fraunhofer.de/bitstreams/07b656d0-fcae-4493-b84b-70a26a650c90/download",
        included_pages=(1, 4, 5, 6, 7, 8, 9),
        extraction_reason=(
            "Selected pages cover FMEA/O&M-FMEA rationale, occurrence/severity/monitoring/maintenance criteria, "
            "MPN calculation context, and high-priority fault ranking discussion."
        ),
        excluded_summary="Excluded reference list, publication boilerplate, and pages without priority/fault-ranking content.",
    ),
    SourceSpec(
        key="kdhc_inspection",
        source_pdf=SOURCE_DIR / "열사용시설 점검업무 기술 기준서.pdf",
        raw_file="kdhc_inspection_standard.pdf",
        curated_file="kdhc_inspection_extract.md",
        document_title="열사용시설 점검업무 기술 기준서 - 선별 추출본",
        source_type="domestic_inspection_standard_pdf",
        rag_role="domestic_inspection_standard",
        language="ko",
        download_url="https://www.kdhc.co.kr/kdhc/bbs/B0000012/view.do?menuNo=200194&nttId=6215&pageIndex=5",
        included_pages=(
            7,
            8,
            9,
            10,
            11,
            12,
            22,
            23,
            26,
            27,
            28,
            29,
            30,
            31,
            32,
            33,
            34,
            35,
            36,
            38,
            42,
            43,
            44,
            45,
            46,
            47,
            48,
            49,
        ),
        extraction_reason=(
            "Selected pages cover inspection workflow, mid/final inspection targets, machine-room and piping checks, "
            "heat exchanger, DPV, strainer, control devices, remote metering, outdoor shutoff valve, and buried inlet pipe checks."
        ),
        excluded_summary="Excluded cover/revision pages, blank-like forms not needed for retrieval, and repetitive table/form areas.",
    ),
    SourceSpec(
        key="iea_structure",
        source_pdf=SOURCE_DIR / "DHC_Connection_Handbook.pdf",
        raw_file="iea_dhc_connection_handbook.pdf",
        curated_file="iea_sh_dhw_substation_extract.md",
        document_title="IEA DHC Connection Handbook - Selected DH/Substation Extract",
        source_type="international_handbook_pdf",
        rag_role="dhc_structure_handbook",
        language="en",
        download_url="https://www.iea-dhc.org/fileadmin/documents/Annex_VI/DHC_Connection_Handbook.pdf",
        included_pages=(55, 66, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 85, 86),
        extraction_reason=(
            "Selected pages focus on district heating substation structure, primary/secondary side concepts, "
            "heat exchangers, control valves, strainers, heat meters, SH and DHW."
        ),
        excluded_summary="Excluded district-cooling-focused chapters, case histories, broad appendices, and generic glossary entries.",
    ),
    SourceSpec(
        key="swedish_f101",
        source_pdf=SOURCE_DIR / "f101-district-heating-substations-design-and-installation.pdf",
        raw_file="swedish_f101_substations.pdf",
        curated_file="swedish_f101_operation_extract.md",
        document_title="Swedish F:101 District Heating Substations - Selected Extract",
        source_type="international_substation_standard_pdf",
        rag_role="international_substation_standard",
        language="en",
        download_url=(
            "https://www.energiforetagen.se/4a4e6b/globalassets/energiforetagen/"
            "det-erbjuder-vi/publikationer/f101-district-heating-substations-design-and-installation.pdf"
        ),
        included_pages=(11, 12, 13, 14, 16, 17, 18, 21, 22, 23, 25, 26, 28, 29, 48, 49, 50),
        extraction_reason=(
            "Selected pages cover supplier coordination, technical/design requirements, heat exchanger and control equipment, "
            "substation equipment, filters, heat meter, DHW/SH equipment, installation, commissioning, maintenance, and definitions."
        ),
        excluded_summary="Excluded preface/table of contents, appendices dominated by diagrams, and low-relevance technical formula pages.",
    ),
]


TROUBLESHOOTING_SPEC = SourceSpec(
    key="danfoss_troubleshooting_table",
    source_pdf=SOURCE_DIR / "VXe_Instruction_uk.pdf",
    raw_file="danfoss_vxe_manual.pdf",
    curated_file="danfoss_troubleshooting_table.md",
    document_title="Danfoss Troubleshooting Table - Heating and Domestic Hot Water",
    source_type="manufacturer_manual_table_extract",
    rag_role="symptom_cause_action_table",
    language="en",
    download_url="https://files.danfoss.com/download/Drives/VXe_Instruction_uk.pdf",
    included_pages=(23, 24),
    extraction_reason="Troubleshooting tables are separated so Agent action generation can search symptom-cause-action rows first.",
    excluded_summary="Excluded non-troubleshooting manual pages and generic installation text.",
)


TEST_QUERIES = [
    "DHW 온수가 충분히 뜨겁지 않을 때 가능한 원인은?",
    "공급/환수 온도차 이상과 유량 변동성이 같이 나타나면 무엇을 점검해야 하는가?",
    "strainer 막힘은 fault priority에서 어떤 의미를 가지는가?",
    "substation에서 SH와 DHW는 어떻게 구분하는가?",
    "국내 열사용시설 점검에서 기계실 관련 확인 항목은 무엇인가?",
    "risk score가 높은 substation의 점검 우선순위를 어떻게 설명할 수 있는가?",
]

QUERY_EXPANSIONS = {
    "DHW": ["dhw", "domestic hot water", "hot water", "급탕", "온수"],
    "온수": ["domestic hot water", "dhw", "hot water", "급탕"],
    "급탕": ["domestic hot water", "dhw", "hot water"],
    "SH": ["space heating", "heating circuit", "radiator", "난방"],
    "난방": ["space heating", "heating circuit", "radiator"],
    "공급": ["supply", "supply temperature", "primary"],
    "환수": ["return", "return temperature", "secondary"],
    "온도차": ["temperature difference", "delta t", "differential temperature"],
    "유량": ["flow", "flow rate"],
    "strainer": ["strainer", "filter", "clogged", "contamination", "막힘"],
    "막힘": ["strainer", "filter", "clogged", "contamination", "blockage"],
    "priority": ["priority", "MPN", "severity", "occurrence", "monitoring potential", "maintenance capability"],
    "risk": ["risk", "priority", "MPN", "severity", "occurrence"],
    "점검": ["점검", "inspection", "maintenance", "commissioning", "확인"],
    "기계실": ["기계실", "equipment room", "machine room", "substation equipment room"],
    "substation": ["substation", "district heating substation", "1차측", "2차측", "primary", "secondary"],
}


def ensure_dirs() -> None:
    for path in [RAW_DIR, CURATED_DIR, METADATA_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def clean_cell(value: str | None) -> str:
    if value is None:
        return ""
    text = clean_text(value).replace("|", "/").strip()
    return re.sub(r"\n+", "<br>", text)


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def strip_repeated_lines(text: str, spec: SourceSpec) -> str:
    cleaned: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            cleaned.append("")
            continue
        if re.fullmatch(r"\d{1,3}", line):
            continue
        lowered = line.lower()
        if spec.key.startswith("danfoss") and lowered.startswith("instructions for installation and use akva lux"):
            continue
        if spec.key == "fault_priority" and "energy 333 (2025) 137210" in lowered:
            continue
        if spec.key == "swedish_f101" and "energiföretagen sverige" in lowered:
            continue
        cleaned.append(line)
    return clean_text("\n".join(cleaned))


def extract_page_text(pdf: pdfplumber.PDF, page_no: int, spec: SourceSpec) -> str:
    if page_no < 1 or page_no > len(pdf.pages):
        return ""
    text = pdf.pages[page_no - 1].extract_text(x_tolerance=1, y_tolerance=3) or ""
    return strip_repeated_lines(text, spec)


def page_section_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if len(line) <= 140 and (
            re.match(r"^(\d+(\.\d+)*|[A-Z]\.|【|[가-힣]\.)", line)
            or line.isupper()
            or any(token in line.lower() for token in ["trouble shooting", "commissioning", "maintenance", "substation"])
        ):
            return line
    return fallback


def copy_raw_pdfs(specs: Iterable[SourceSpec]) -> None:
    seen: set[str] = set()
    for spec in specs:
        if spec.raw_file in seen:
            continue
        seen.add(spec.raw_file)
        destination = RAW_DIR / spec.raw_file
        if not spec.source_pdf.exists():
            raise FileNotFoundError(f"Missing source PDF: {spec.source_pdf}")
        shutil.copy2(spec.source_pdf, destination)


def yaml_header(spec: SourceSpec) -> str:
    return "\n".join(
        [
            "---",
            f"document_title: {spec.document_title}",
            f"source_file: {spec.raw_file}",
            f"curated_file: {spec.curated_file}",
            f"source_type: {spec.source_type}",
            f"rag_role: {spec.rag_role}",
            f"domain: {DOMAIN}",
            f"language: {spec.language}",
            f"page_start: {min(spec.included_pages)}",
            f"page_end: {max(spec.included_pages)}",
            f"download_url: {spec.download_url}",
            "---",
            "",
        ]
    )


def page_ranges(pages: Iterable[int]) -> str:
    pages = sorted(set(pages))
    if not pages:
        return ""
    ranges: list[str] = []
    start = prev = pages[0]
    for page in pages[1:]:
        if page == prev + 1:
            prev = page
            continue
        ranges.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = page
    ranges.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(ranges)


def build_selected_extract(spec: SourceSpec) -> tuple[list[dict[str, object]], dict[str, object]]:
    chunks: list[dict[str, object]] = []
    parts = [yaml_header(spec)]
    parts.extend(
        [
            f"# {spec.document_title}",
            "",
            "## Curation scope",
            "",
            f"- Included pages: {page_ranges(spec.included_pages)}",
            f"- Extraction reason: {spec.extraction_reason}",
            f"- Excluded content: {spec.excluded_summary}",
            "",
        ]
    )
    with pdfplumber.open(spec.source_pdf) as pdf:
        for page_no in spec.included_pages:
            text = extract_page_text(pdf, page_no, spec)
            if not text:
                continue
            section = page_section_title(text, f"Selected extract page {page_no}")
            parts.extend([f"## Page {page_no}: {section}", "", text, ""])
            chunks.extend(
                chunk_text(
                    text=text,
                    spec=spec,
                    page_start=page_no,
                    page_end=page_no,
                    section_title=section,
                    base_id=f"{Path(spec.curated_file).stem}__p{page_no:03d}",
                )
            )
    curated_path = CURATED_DIR / spec.curated_file
    curated_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    info = {
        "document_title": spec.document_title,
        "source_file": spec.raw_file,
        "curated_file": spec.curated_file,
        "source_type": spec.source_type,
        "rag_role": spec.rag_role,
        "language": spec.language,
        "included_pages": list(spec.included_pages),
        "included_page_ranges": page_ranges(spec.included_pages),
        "extraction_reason": spec.extraction_reason,
        "excluded_summary": spec.excluded_summary,
        "download_url": spec.download_url,
        "chunk_count": len(chunks),
    }
    return chunks, info


def infer_component(*texts: str) -> str:
    haystack = " ".join(texts).lower()
    component_terms = [
        ("strainer/filter", ["strainer", "filter"]),
        ("pump", ["pump"]),
        ("control valve/actuator/controller", ["valve", "actuator", "controller"]),
        ("temperature sensor", ["sensor", "thermostat"]),
        ("heat exchanger", ["heat exchanger", "calified"]),
        ("differential pressure controller", ["differential pressure"]),
        ("air/venting", ["air pocket", "vent"]),
        ("non-return valve/mixer", ["non-return", "mixer"]),
    ]
    for label, terms in component_terms:
        if any(term in haystack for term in terms):
            return label
    return "general"


def build_troubleshooting_table() -> tuple[list[dict[str, object]], dict[str, object]]:
    spec = TROUBLESHOOTING_SPEC
    rows: list[dict[str, str]] = []
    chunks: list[dict[str, object]] = []
    with pdfplumber.open(spec.source_pdf) as pdf:
        for page_no in spec.included_pages:
            tables = pdf.pages[page_no - 1].extract_tables() or []
            for table in tables:
                if not table:
                    continue
                header = [clean_cell(cell).lower() for cell in table[0]]
                if not {"problem", "possible cause", "solution"}.issubset(set(header)):
                    continue
                current_problem = ""
                for row in table[1:]:
                    padded = list(row) + [""] * 3
                    problem = clean_cell(padded[0])
                    possible_cause = clean_cell(padded[1])
                    recommended_action = clean_cell(padded[2])
                    if problem:
                        current_problem = problem
                    else:
                        problem = current_problem
                    if not any([problem, possible_cause, recommended_action]):
                        continue
                    rows.append(
                        {
                            "symptom": problem,
                            "possible_cause": possible_cause,
                            "recommended_action": recommended_action,
                            "component": infer_component(problem, possible_cause, recommended_action),
                            "source_page": str(page_no),
                        }
                    )

    parts = [yaml_header(spec)]
    parts.extend(
        [
            f"# {spec.document_title}",
            "",
            "## Curation scope",
            "",
            f"- Included pages: {page_ranges(spec.included_pages)}",
            f"- Extraction reason: {spec.extraction_reason}",
            f"- Excluded content: {spec.excluded_summary}",
            "",
            "## Symptom-cause-action table",
            "",
            "| symptom | possible_cause | recommended_action | component | source_page |",
            "|---|---|---|---|---|",
        ]
    )
    for idx, row in enumerate(rows, start=1):
        parts.append(
            "| {symptom} | {possible_cause} | {recommended_action} | {component} | {source_page} |".format(**row)
        )
        text = (
            f"Symptom: {row['symptom']}\n"
            f"Possible cause: {row['possible_cause']}\n"
            f"Recommended action: {row['recommended_action']}\n"
            f"Component: {row['component']}"
        )
        chunks.append(
            make_chunk(
                chunk_id=f"danfoss_troubleshooting_table__row{idx:03d}",
                text=text,
                spec=spec,
                page_start=int(row["source_page"]),
                page_end=int(row["source_page"]),
                section_title="Symptom-cause-action table",
            )
        )

    curated_path = CURATED_DIR / spec.curated_file
    curated_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    info = {
        "document_title": spec.document_title,
        "source_file": spec.raw_file,
        "curated_file": spec.curated_file,
        "source_type": spec.source_type,
        "rag_role": spec.rag_role,
        "language": spec.language,
        "included_pages": list(spec.included_pages),
        "included_page_ranges": page_ranges(spec.included_pages),
        "extraction_reason": spec.extraction_reason,
        "excluded_summary": spec.excluded_summary,
        "download_url": spec.download_url,
        "table_row_count": len(rows),
        "chunk_count": len(chunks),
    }
    return chunks, info


def tokenish_words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_.+-]+|[가-힣]+", text)


def make_chunk(
    *,
    chunk_id: str,
    text: str,
    spec: SourceSpec,
    page_start: int,
    page_end: int,
    section_title: str,
) -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "document_title": spec.document_title,
        "source_file": spec.raw_file,
        "curated_file": spec.curated_file,
        "source_type": spec.source_type,
        "rag_role": spec.rag_role,
        "domain": DOMAIN,
        "language": spec.language,
        "page_start": page_start,
        "page_end": page_end,
        "section_title": section_title,
        "extraction_reason": spec.extraction_reason,
        "download_url": spec.download_url,
        "text": clean_text(text),
    }


def chunk_text(
    *,
    text: str,
    spec: SourceSpec,
    page_start: int,
    page_end: int,
    section_title: str,
    base_id: str,
    max_words: int = 520,
) -> list[dict[str, object]]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", clean_text(text)) if p.strip()]
    chunks: list[dict[str, object]] = []
    current: list[str] = []
    current_words = 0
    for paragraph in paragraphs:
        words = tokenish_words(paragraph)
        if current and current_words + len(words) > max_words:
            idx = len(chunks) + 1
            chunks.append(
                make_chunk(
                    chunk_id=f"{base_id}__c{idx:02d}",
                    text="\n\n".join(current),
                    spec=spec,
                    page_start=page_start,
                    page_end=page_end,
                    section_title=section_title,
                )
            )
            current = []
            current_words = 0
        current.append(paragraph)
        current_words += len(words)
    if current:
        idx = len(chunks) + 1
        chunks.append(
            make_chunk(
                chunk_id=f"{base_id}__c{idx:02d}",
                text="\n\n".join(current),
                spec=spec,
                page_start=page_start,
                page_end=page_end,
                section_title=section_title,
            )
        )
    return chunks


def write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def doc_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def query_terms(query: str) -> list[str]:
    terms = [query.lower()]
    simple = re.findall(r"[A-Za-z0-9_.+-]+|[가-힣]+", query)
    terms.extend(term.lower() for term in simple)
    for key, expansions in QUERY_EXPANSIONS.items():
        if key.lower() in query.lower():
            terms.extend(expansion.lower() for expansion in expansions)
    return sorted(set(term for term in terms if len(term) >= 2))


def score_chunk(query: str, chunk: dict[str, object]) -> float:
    terms = query_terms(query)
    query_lower = query.lower()
    text = " ".join(
        [
            str(chunk.get("document_title", "")),
            str(chunk.get("rag_role", "")),
            str(chunk.get("section_title", "")),
            str(chunk.get("text", "")),
        ]
    ).lower()
    length_norm = math.sqrt(max(len(tokenish_words(text)), 1))
    score = 0.0
    for term in terms:
        count = text.count(term)
        if not count:
            continue
        weight = 2.5 if " " in term else 1.0
        score += weight * count
    role = str(chunk.get("rag_role", ""))
    if any(word in query.lower() for word in ["조치", "원인", "dhw", "온수", "급탕"]) and role in {
        "symptom_cause_action_table",
        "troubleshooting_manual",
    }:
        score += 7.0
    if any(word in query.lower() for word in ["priority", "risk", "우선순위", "strainer"]) and role == "fault_priority_research":
        score += 10.0
    if any(word in query for word in ["국내", "점검", "기계실"]) and role == "domestic_inspection_standard":
        score += 5.0
    structure_query = (
        any(word in query_lower for word in ["sh", "dhw", "space heating", "domestic hot water"])
        or any(word in query for word in ["난방", "급탕", "1차", "2차"])
    ) and any(word in query for word in ["구분", "구조", "어떻게"])
    if structure_query and role in {"dhc_structure_handbook", "international_substation_standard"}:
        score += 25.0
    if structure_query and role == "fault_priority_research":
        score *= 0.35
    priority_query = any(word in query_lower for word in ["risk", "priority", "mpn"]) or any(
        word in query for word in ["우선순위", "위험"]
    )
    if priority_query and role == "fault_priority_research":
        score += 20.0
    if priority_query and role == "international_substation_standard":
        score *= 0.5
    return score / length_norm


def write_test_query_results(chunks: list[dict[str, object]]) -> None:
    lines: list[str] = ["# RAG test query results", ""]
    for query in TEST_QUERIES:
        ranked = sorted(
            ((score_chunk(query, chunk), chunk) for chunk in chunks),
            key=lambda item: item[0],
            reverse=True,
        )
        lines.extend([f"## {query}", "", "| rank | score | document | page | section | chunk_id |", "|---:|---:|---|---:|---|---|"])
        for rank, (score, chunk) in enumerate(ranked[:5], start=1):
            lines.append(
                "| {rank} | {score:.4f} | {document} | {page} | {section} | `{chunk_id}` |".format(
                    rank=rank,
                    score=score,
                    document=str(chunk["document_title"]).replace("|", "/"),
                    page=chunk["page_start"],
                    section=str(chunk["section_title"]).replace("|", "/"),
                    chunk_id=chunk["chunk_id"],
                )
            )
        lines.append("")
    (METADATA_DIR / "test_query_results.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_readme(document_infos: list[dict[str, object]]) -> None:
    lines = [
        "# HeatGrid RAG curated corpus",
        "",
        "이 폴더는 원본 PDF 전체를 그대로 색인하지 않고, HeatGrid Agent의 위험 설명/원인 추정/조치안 생성에 필요한 부분만 선별한 RAG 입력 자료입니다.",
        "",
        "## 사용 원칙",
        "",
        "- `raw/`에는 원본 PDF를 보존합니다.",
        "- 실제 RAG ingestion은 `curated/`의 markdown과 `metadata/rag_chunks.jsonl`만 사용합니다.",
        "- 표지, 목차, 회사 소개, 광고성 페이지, 반복 안전문구, 프로젝트와 무관한 설치 세부사항은 제외했습니다.",
        "- 최종 답변 생성 시 모델 수치 근거와 RAG 문서 근거를 분리해서 설명해야 합니다.",
        "",
        "## Curated files",
        "",
        "| file | rag_role | included pages | chunks |",
        "|---|---|---:|---:|",
    ]
    for info in document_infos:
        lines.append(
            "| `{curated_file}` | `{rag_role}` | {included_page_ranges} | {chunk_count} |".format(**info)
        )
    lines.extend(
        [
            "",
            "## Metadata files",
            "",
            "- `metadata/rag_sources_manifest.json`: 원본/선별 문서 manifest",
            "- `metadata/rag_chunks.jsonl`: 서버 ingest용 chunk 데이터",
            "- `metadata/ingestion_summary.md`: 포함/제외 범위 및 chunk 수 요약",
            "- `metadata/test_query_results.md`: 검증 query별 상위 검색 결과",
        ]
    )
    (CURATED_DIR / "README.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_manifest(document_infos: list[dict[str, object]], chunks: list[dict[str, object]]) -> None:
    raw_files = []
    for path in sorted(RAW_DIR.glob("*.pdf")):
        raw_files.append(
            {
                "file": path.name,
                "sha256": doc_hash(path),
                "bytes": path.stat().st_size,
            }
        )
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_folder": str(SOURCE_DIR),
        "raw_dir": str(RAW_DIR.relative_to(ROOT)),
        "curated_dir": str(CURATED_DIR.relative_to(ROOT)),
        "metadata_dir": str(METADATA_DIR.relative_to(ROOT)),
        "domain": DOMAIN,
        "ingestion_policy": "Use curated markdown/chunks only. Do not ingest raw PDFs wholesale.",
        "raw_files": raw_files,
        "documents": document_infos,
        "chunk_count": len(chunks),
        "chunk_file": "rag_chunks.jsonl",
        "required_chunk_metadata": [
            "document_title",
            "source_file",
            "curated_file",
            "source_type",
            "rag_role",
            "domain",
            "language",
            "page_start",
            "page_end",
            "section_title",
            "chunk_id",
            "extraction_reason",
            "download_url",
        ],
    }
    (METADATA_DIR / "rag_sources_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_ingestion_summary(document_infos: list[dict[str, object]], chunks: list[dict[str, object]]) -> None:
    role_counts = Counter(str(chunk["rag_role"]) for chunk in chunks)
    lines = [
        "# RAG ingestion summary",
        "",
        "## Scope",
        "",
        "원본 PDF는 `data/rag_sources/raw/`에 보존했고, RAG ingestion 대상은 `curated/` markdown 및 `metadata/rag_chunks.jsonl`입니다.",
        "PDF 전체를 통째로 색인하지 않았습니다.",
        "",
        "## Document summary",
        "",
        "| document | role | included pages | chunks | excluded summary |",
        "|---|---|---:|---:|---|",
    ]
    for info in document_infos:
        lines.append(
            "| {document_title} | `{rag_role}` | {included_page_ranges} | {chunk_count} | {excluded_summary} |".format(
                **{key: str(value).replace("|", "/") for key, value in info.items()}
            )
        )
    lines.extend(["", "## Chunk counts by rag_role", "", "| rag_role | chunks |", "|---|---:|"])
    for role, count in sorted(role_counts.items()):
        lines.append(f"| `{role}` | {count} |")
    lines.extend(
        [
            "",
            "## Generated files",
            "",
            "- `data/rag_sources/raw/*.pdf`",
            "- `data/rag_sources/curated/*.md`",
            "- `data/rag_sources/metadata/rag_sources_manifest.json`",
            "- `data/rag_sources/metadata/rag_chunks.jsonl`",
            "- `data/rag_sources/metadata/test_query_results.md`",
            "",
            "## Known limitations",
            "",
            "- PDF text extraction can break some table line breaks and hyphenated words.",
            "- Figures and diagrams are represented only by their extracted text/captions unless table extraction succeeded.",
            "- This script prepares chunk metadata for RAG ingestion; it does not create vector embeddings.",
        ]
    )
    (METADATA_DIR / "ingestion_summary.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build() -> None:
    ensure_dirs()
    all_specs = [TROUBLESHOOTING_SPEC, *SPECS]
    copy_raw_pdfs(all_specs)

    all_chunks: list[dict[str, object]] = []
    document_infos: list[dict[str, object]] = []

    table_chunks, table_info = build_troubleshooting_table()
    all_chunks.extend(table_chunks)
    document_infos.append(table_info)

    for spec in SPECS:
        chunks, info = build_selected_extract(spec)
        all_chunks.extend(chunks)
        document_infos.append(info)

    write_jsonl(METADATA_DIR / "rag_chunks.jsonl", all_chunks)
    write_manifest(document_infos, all_chunks)
    write_readme(document_infos)
    write_ingestion_summary(document_infos, all_chunks)
    write_test_query_results(all_chunks)

    print(f"raw PDFs: {len(list(RAW_DIR.glob('*.pdf')))}")
    print(f"curated markdown files: {len(list(CURATED_DIR.glob('*.md')))}")
    print(f"chunks: {len(all_chunks)}")
    for info in document_infos:
        print(f"- {info['curated_file']}: {info['chunk_count']} chunks, pages {info['included_page_ranges']}")


if __name__ == "__main__":
    build()
