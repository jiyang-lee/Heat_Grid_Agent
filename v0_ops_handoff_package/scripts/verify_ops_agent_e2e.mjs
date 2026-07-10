import { mkdir, readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createHash, randomUUID } from "node:crypto";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const packageDir = path.resolve(scriptDir, "..");
const projectRoot = path.resolve(packageDir, "..");

const officialCsvPath = path.join(
  projectRoot,
  "output",
  "agent_priority_card.csv",
);
const alternateCsvPath = path.join(
  projectRoot,
  "output",
  "agent",
  "m1_agent_priority_card.csv",
);
const outputSchemaPath = path.join(packageDir, "contracts", "ops_agent_output.schema.json");
const defaultOutputPath = path.join(projectRoot, "output", "ops_agent", "ops_agent_output_sample.json");
const ragChunksPath = path.join(projectRoot, "data", "rag_sources", "metadata", "rag_chunks.jsonl");
const substationContextPath = path.join(
  projectRoot,
  "data",
  "external",
  "substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv",
);
const promptVersion = "ops-agent-v0.3-site-weather";

function fail(step, message) {
  const error = new Error(`${step}: ${message}`);
  error.step = step;
  throw error;
}

function getOutputPath() {
  const configured = process.env.OPS_AGENT_OUTPUT_PATH;
  if (!configured) return defaultOutputPath;
  return path.isAbsolute(configured)
    ? configured
    : path.join(projectRoot, configured);
}

async function loadDotEnv() {
  const candidates = [
    path.join(projectRoot, ".env"),
    path.join(packageDir, ".env"),
  ];

  for (const candidate of candidates) {
    if (!existsSync(candidate)) continue;
    const text = await readFile(candidate, "utf8");
    for (const line of text.split(/\r?\n/)) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const index = trimmed.indexOf("=");
      if (index === -1) continue;
      const key = trimmed.slice(0, index).trim();
      let value = trimmed.slice(index + 1).trim();
      if (
        (value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))
      ) {
        value = value.slice(1, -1);
      }
      if (key && process.env[key] === undefined) {
        process.env[key] = value;
      }
    }
  }
}

async function sha256(filePath) {
  const bytes = await readFile(filePath);
  return createHash("sha256").update(bytes).digest("hex");
}

async function chooseOfficialCsv() {
  if (!existsSync(officialCsvPath) && !existsSync(alternateCsvPath)) {
    fail("official_csv", "공식 priority card CSV를 찾을 수 없습니다.");
  }
  if (!existsSync(officialCsvPath)) {
    return {
      path: alternateCsvPath,
      reason: "output/agent_priority_card.csv가 없어 alternate CSV를 사용했습니다.",
      identical: false,
    };
  }
  if (!existsSync(alternateCsvPath)) {
    return {
      path: officialCsvPath,
      reason: "alternate CSV가 없어 output/agent_priority_card.csv를 사용했습니다.",
      identical: false,
    };
  }

  const officialHash = await sha256(officialCsvPath);
  const alternateHash = await sha256(alternateCsvPath);
  return {
    path: officialCsvPath,
    reason:
      officialHash === alternateHash
        ? "두 CSV가 동일하여 output/agent_priority_card.csv를 공식 기준으로 사용했습니다."
        : "두 CSV가 달라 문서상 공식 경로인 output/agent_priority_card.csv를 사용했습니다.",
    identical: officialHash === alternateHash,
  };
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (char === '"' && inQuotes && next === '"') {
      cell += '"';
      i += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      row.push(cell);
      cell = "";
    } else if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") i += 1;
      row.push(cell);
      if (row.some((value) => value.length > 0)) rows.push(row);
      row = [];
      cell = "";
    } else {
      cell += char;
    }
  }

  if (cell.length > 0 || row.length > 0) {
    row.push(cell);
    rows.push(row);
  }

  const [header, ...dataRows] = rows;
  if (!header) fail("csv_parse", "CSV header가 없습니다.");
  return dataRows.map((values) =>
    Object.fromEntries(header.map((column, index) => [column, values[index] ?? ""])),
  );
}

function toNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function splitReasons(value) {
  const seen = new Set();
  return String(value ?? "")
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => {
      if (seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

function mapDataQuality(row) {
  const trust = String(row.trust_level ?? "").toLowerCase();
  if (trust === "high" || trust === "good") return "Good";
  if (trust === "medium") return "Medium";
  if (trust === "low") return "Low";
  return "Unknown";
}

function selectCsvRow(rows, cardId) {
  const text = String(cardId ?? "").trim();
  const sampleMatch = text.match(/^sample-row-(\d+)$/i);
  const rowNumber = sampleMatch ? Number(sampleMatch[1]) : Number(text);
  const rowIndex = Number.isInteger(rowNumber) && rowNumber >= 1 ? rowNumber - 1 : 0;
  const row = rows[rowIndex];
  if (!row) {
    fail("get_ops_evidence", `CSV row ${rowIndex + 1}를 찾을 수 없습니다. 전체 row 수: ${rows.length}`);
  }
  return {
    row,
    rowIndex,
    rowNumber: rowIndex + 1,
  };
}

function uniqueValues(values) {
  const seen = new Set();
  return values
    .map((value) => String(value ?? "").trim())
    .filter(Boolean)
    .filter((value) => {
      const key = value.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function normalizeForSearch(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/<br\s*\/?>/g, " ")
    .replace(/[_/,-]/g, " ")
    .replace(/[^\p{L}\p{N}\s]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function truncateText(value, maxLength = 1200) {
  const text = String(value ?? "")
    .replace(/<br\s*\/?>/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trimEnd()}…`;
}

function priorityKo(value) {
  const key = String(value ?? "").toLowerCase();
  return {
    urgent: "긴급",
    high: "높음",
    medium: "중간",
    low: "낮음",
  }[key] ?? String(value ?? "확인 필요");
}

function faultGroupKo(value) {
  const key = String(value ?? "").toLowerCase();
  return {
    leakage_water_loss: "누수 또는 보충수 손실 의심",
    control_controller: "제어기/컨트롤러 이상 의심",
    pump_failure: "순환펌프 고장 의심",
    pressure_regulator: "압력 조절 계통 이상 의심",
    valve_actuator: "밸브 구동부 이상 의심",
    unknown_review: "고장 유형 미확정",
  }[key] ?? String(value ?? "고장 유형 미확정");
}

function stateKo(value) {
  const key = String(value ?? "").toLowerCase();
  return {
    fault: "이상 의심",
    normal: "정상 범위",
  }[key] ?? String(value ?? "상태 확인 필요");
}

function agreementKo(value) {
  const key = String(value ?? "").toLowerCase();
  return {
    both_high: "위험도와 의심 유형이 함께 높게 나타남",
    current_only_high: "위험도는 높지만 의심 유형 근거는 약해 추가 확인 필요",
    m1_only_high: "의심 유형 근거가 강해 추가 확인 필요",
    both_low: "주요 위험 신호가 낮음",
  }[key] ?? String(value ?? "판단 신호 관계 확인 필요");
}

function reviewReasonKo(value) {
  const key = String(value ?? "").toLowerCase().replace(/_/g, " ");
  return {
    near_anomaly_threshold: "이상 기준에 근접한 신호",
    risk_high_but_anomaly_not_confirmed: "위험도는 높지만 이상 확정 전 상태",
    current_only_high: "위험도는 높지만 의심 유형 근거는 약해 추가 확인 필요",
    lead_time_1_3d: "1~3일 내 위험 가능성",
    fault_group_leakage_water_loss: "누수 또는 보충수 손실 관련 신호",
    "near anomaly threshold": "이상 기준에 근접한 신호",
    "risk high but anomaly not confirmed": "위험도는 높지만 이상 확정 전 상태",
    "current only high": "위험도는 높지만 의심 유형 근거는 약해 추가 확인 필요",
    "lead time 1 3d": "1~3일 내 위험 가능성",
    "fault group leakage water loss": "누수 또는 보충수 손실 관련 신호",
    "m1 specialist gate near threshold": "의심 유형 근거가 기준에 근접한 신호",
  }[key] ?? String(value ?? "").replace(/_/g, " ");
}

function sanitizeOperatorText(value) {
  return String(value ?? "")
    .replace(/^\s*(?:\d+[.)]|[-*•])\s+/, "")
    .replace(/\s*[|\\]\s*/g, ", ")
    .replace(/\bcurrent[-_ ]?best\b/gi, "위험도 판단")
    .replace(/\bM1 specialist\b/gi, "의심 유형")
    .replace(/\bm1_specialist\b/gi, "의심 유형")
    .replace(/\bfault_group\b/gi, "고장 유형")
    .replace(/\bpump_failure\b/gi, "순환펌프 고장 의심")
    .replace(/\bleakage_water_loss\b/gi, "누수 또는 보충수 손실 의심")
    .replace(/\bcontrol_controller\b/gi, "제어기/컨트롤러 이상 의심")
    .replace(/\bpressure_regulator\b/gi, "압력 조절 계통 이상 의심")
    .replace(/\bvalve_actuator\b/gi, "밸브 구동부 이상 의심")
    .replace(/\bunknown_review\b/gi, "고장 유형 미확정")
    .replace(/\bRAG\b/gi, "운영 참고자료")
    .replace(/\bretrieval\b/gi, "자료 검색")
    .replace(/\bchunk\b/gi, "참고 문단")
    .replace(/\bexternal_context\b/gi, "외부 참고정보")
    .replace(/\bML priority\b/gi, "위험도")
    .replace(/\bKMA API\b/gi, "기상청 기상자료")
    .replace(/\bAPIHub\b/gi, "기상청 기상자료")
    .replace(/\bpgvector\b/gi, "검색 DB")
    .replace(/\bPostgreSQL\b/gi, "운영 DB")
    .replace(/기존 기준 모델/g, "위험도 판단")
    .replace(/보조\s*진단\s*모델/g, "의심 유형")
    .replace(/두 모델/g, "여러 판단 신호")
    .replace(/모델 판단/g, "위험도 판단")
    .replace(/모델 결과/g, "자동 판단 결과")
    .replace(/모델 우선순위/g, "위험도");
}

function sanitizeOperatorItems(items, maxItems) {
  return (items ?? [])
    .filter((item) => typeof item === "string" && item.trim())
    .map((item) => sanitizeOperatorText(item.trim()))
    .slice(0, maxItems);
}

function buildRagTerms(evidence) {
  const pc = evidence.priority_context;
  const faultGroup = pc.model_signals.m1_specialist_fault_group;
  const baseTerms = [
    faultGroup,
    pc.model_signals.m1_specialist_primary_state,
    pc.priority.priority_level,
    pc.explanation.why_reason,
    pc.explanation.recommended_action,
    ...(pc.explanation.review_reasons ?? []),
  ];

  const synonymMap = {
    leakage_water_loss: [
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
    no_heat: [
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
    overheating: [
      "overheating",
      "control valve",
      "thermostat",
      "controller",
      "setpoint",
      "과열",
      "제어밸브",
      "설정값",
    ],
  };

  const synonyms = synonymMap[String(faultGroup ?? "").toLowerCase()] ?? [];
  const genericTerms = [
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
  ];

  return uniqueValues([...baseTerms, ...synonyms, ...genericTerms]);
}

async function loadRagChunks() {
  if (!existsSync(ragChunksPath)) {
    return [];
  }

  const text = await readFile(ragChunksPath, "utf8");
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

async function loadSubstationContextRows() {
  if (!existsSync(substationContextPath)) {
    return [];
  }
  return parseCsv(await readFile(substationContextPath, "utf8"));
}

async function buildLocalSiteContext(evidence) {
  const rows = await loadSubstationContextRows();
  const substationId = String(evidence.raw_context?.window?.substation_id ?? "").trim();
  if (!substationId) {
    return { status: "missing_substation_id" };
  }
  const row = rows.find((item) => String(item.substation_id ?? "").trim() === substationId);
  if (!row) {
    return {
      status: "not_mapped",
      substation_id: toNumber(substationId) ?? substationId,
      mapping_scope: "sejong_virtual_1_31",
    };
  }
  return {
    status: "mapped",
    mapping_scope: "sejong_virtual_1_31",
    mapping_type: row.predist_mapping_type || "virtual_by_substation_id",
    substation_id: toNumber(row.substation_id) ?? row.substation_id,
    apartment_name: row.matched_name || null,
    kapt_code: row.kapt_code || null,
    life_zone: row.life_zone || null,
    dong: row.dong || null,
    village: row.village || null,
    road_address: row.road_address || null,
    jibun_address: row.jibun_address || null,
    latitude: toNumber(row.latitude),
    longitude: toNumber(row.longitude),
    heating_type: row.heating_type || null,
    household_count: toNumber(row.household_count),
    building_count: toNumber(row.building_count),
    gross_floor_area_m2: toNumber(row.gross_floor_area_m2),
    latest_private_usage_cost_krw: toNumber(row.private_usage_cost_latest_month_krw),
    latest_private_usage_unit_krw_per_m2: toNumber(row.private_usage_cost_latest_month_unit_krw_per_m2),
    predist_configuration_type: row.predist_configuration_type || null,
    predist_configuration_ko: row.predist_configuration_ko || null,
    predist_sensor_groups_ko: row.predist_sensor_groups_ko || null,
    predist_sensor_column_count: toNumber(row.predist_sensor_column_count),
    predist_source_file: row.predist_source_file || null,
    caution: row.predist_mapping_note ||
      "세종 아파트와 PreDist 설비의 실제 물리 연결은 검증되지 않은 가상 매핑입니다.",
  };
}

function scoreRagChunk(chunk, terms, evidence) {
  const searchable = normalizeForSearch([
    chunk.chunk_id,
    chunk.document_title,
    chunk.rag_role,
    chunk.section_title,
    chunk.text,
  ].join(" "));
  const faultGroup = String(
    evidence.priority_context.model_signals.m1_specialist_fault_group ?? "",
  ).toLowerCase();
  let score = 0;
  const matchedTerms = [];

  for (const term of terms) {
    const normalized = normalizeForSearch(term);
    if (!normalized || normalized.length < 2) continue;
    if (searchable.includes(normalized)) {
      const weight = normalized.length >= 8 ? 3 : 1;
      score += weight;
      matchedTerms.push(term);
    }
  }

  if (chunk.rag_role === "symptom_cause_action_table") score += 4;
  if (chunk.rag_role === "troubleshooting_manual") score += 3;
  if (chunk.rag_role === "domestic_inspection_standard") score += 2;
  if (chunk.rag_role === "fault_priority_research") score += 1;

  if (faultGroup === "leakage_water_loss") {
    if (searchable.includes("leak") || searchable.includes("water loss")) score += 8;
    if (searchable.includes("pressure") || searchable.includes("차압")) score += 4;
    if (searchable.includes("strainer") || searchable.includes("filter") || searchable.includes("스트레이너")) {
      score += 3;
    }
    if (searchable.includes("flow") || searchable.includes("유량")) score += 2;
  }

  return {
    score,
    matchedTerms: uniqueValues(matchedTerms).slice(0, 12),
  };
}

function selectRagChunks(chunks, evidence, topK = 5) {
  const terms = buildRagTerms(evidence);
  const scored = chunks
    .map((chunk) => ({
      chunk,
      ...scoreRagChunk(chunk, terms, evidence),
    }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || String(a.chunk.chunk_id).localeCompare(String(b.chunk.chunk_id)));

  return {
    query: terms.slice(0, 18).join(" "),
    chunks: scored.slice(0, topK).map((item) => ({
      chunk_id: item.chunk.chunk_id,
      document_title: item.chunk.document_title,
      source_file: item.chunk.source_file,
      curated_file: item.chunk.curated_file,
      rag_role: item.chunk.rag_role,
      language: item.chunk.language,
      page_start: item.chunk.page_start,
      page_end: item.chunk.page_end,
      section_title: item.chunk.section_title,
      download_url: item.chunk.download_url,
      score: item.score,
      matched_terms: item.matchedTerms,
      text: truncateText(item.chunk.text),
    })),
  };
}

async function getOpsEvidence(cardId, csvPath) {
  const rows = parseCsv(await readFile(csvPath, "utf8"));
  if (!rows.length) fail("get_ops_evidence", "공식 priority card CSV에 row가 없습니다.");
  const { row, rowIndex, rowNumber } = selectCsvRow(rows, cardId);

  const reviewReasons = splitReasons(row.review_reasons);
  const priorityScore = toNumber(row.priority_score);
  const priorityLevel = row.priority_level || null;
  const currentBestLevel = row.current_best_priority_level || null;
  const m1FaultGroup = row.m1_specialist_fault_group || null;
  const m1Level = row.m1_specialist_priority_level || null;

  return {
    card_id: cardId,
    selected_row: {
      row_index: rowIndex,
      row_number: rowNumber,
      total_rows: rows.length,
    },
    row_identifier: {
      manufacturer: row.manufacturer,
      substation_id: row.substation_id,
      window_start: row.window_start,
      window_end: row.window_end,
      configuration_type: row.configuration_type,
    },
    raw_context: {
      window: {
        manufacturer_id: row.manufacturer,
        substation_id: toNumber(row.substation_id) ?? row.substation_id,
        configuration_type: row.configuration_type || null,
        window_start: row.window_start,
        window_end: row.window_end,
      },
    },
    priority_context: {
      card: {
        operational_label: row.operational_label || null,
        primary_state: row.primary_state || null,
        trust_level: row.trust_level || null,
      },
      priority: {
        priority_score: priorityScore,
        priority_level: priorityLevel,
        priority_source: row.priority_source || null,
      },
      model_signals: {
        current_best_priority_score: toNumber(row.current_best_priority_score),
        current_best_priority_level: currentBestLevel,
        m1_specialist_priority_score: toNumber(row.m1_specialist_priority_score),
        m1_specialist_priority_level: m1Level,
        m1_specialist_primary_state: row.m1_specialist_primary_state || null,
        m1_specialist_fault_group: m1FaultGroup,
        m1_priority_agreement: row.m1_priority_agreement || null,
      },
      explanation: {
        review_required: String(row.review_required).toLowerCase() === "true",
        review_reasons: reviewReasons,
        why_reason: row.why_reason || null,
        recommended_action: row.recommended_action || null,
      },
    },
    internal_context: {
      data_quality: {
        review_required: String(row.review_required).toLowerCase() === "true",
        trust_level: row.trust_level || null,
        data_quality: mapDataQuality(row),
      },
    },
    expected_output_fields: {
      decision: {
        priority: priorityLevel,
        operator_review:
          String(row.review_required).toLowerCase() === "true" ? "Required" : "Not Required",
        data_quality: mapDataQuality(row),
      },
      evidence: {
        priority_score: priorityScore,
        current_best: currentBestLevel,
        m1_specialist: m1FaultGroup || m1Level,
      },
    },
  };
}

async function getExternalContext(cardId, evidence) {
  if (process.env.HEATGRID_DISABLE_RAG === "1") {
    return {
      card_id: cardId,
      status: "external_context_disabled",
      weather: {
        status: "not_requested",
      },
      retrieval: {
        status: "disabled",
        source: "disabled",
        query: null,
        top_k: 0,
        chunks: [],
      },
      references: {
        technical_standards: [],
        regulations: [],
      },
    };
  }

  const ragServerUrl = getRagServerUrl();
  if (ragServerUrl) {
    return getExternalContextFromServer(cardId, evidence, ragServerUrl);
  }

  const site = await buildLocalSiteContext(evidence);
  const chunks = await loadRagChunks();
  if (chunks.length === 0) {
    return {
      card_id: cardId,
      status: "external_context_unavailable",
      site,
      weather: {
        status: "not_requested",
      },
      retrieval: {
        status: "missing_chunk_file",
        chunk_file: ragChunksPath,
        query: null,
        top_k: 0,
        chunks: [],
      },
      references: {
        technical_standards: [],
        regulations: [],
      },
    };
  }

  const selected = selectRagChunks(chunks, evidence, 5);
  const status = selected.chunks.length > 0 ? "configured" : "configured_no_match";

  return {
    card_id: cardId,
    status,
    site,
    weather: {
      status: "not_requested",
    },
    retrieval: {
      status: selected.chunks.length > 0 ? "available" : "no_match",
      source: "local_curated_rag_chunks",
      chunk_file: path.relative(projectRoot, ragChunksPath),
      query: selected.query,
      top_k: selected.chunks.length,
      chunks: selected.chunks,
    },
    references: {
      technical_standards: selected.chunks.map((chunk) => ({
        chunk_id: chunk.chunk_id,
        document_title: chunk.document_title,
        source_file: chunk.source_file,
        curated_file: chunk.curated_file,
        page_start: chunk.page_start,
        page_end: chunk.page_end,
        download_url: chunk.download_url,
      })),
      regulations: [],
    },
  };
}

function getRagServerUrl() {
  return (process.env.HEATGRID_RAG_URL || "").replace(/\/+$/, "");
}

async function getExternalContextFromServer(cardId, evidence, ragServerUrl) {
  const response = await fetch(`${ragServerUrl}/external-context`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      card_id: cardId,
      ops_evidence: evidence,
      top_k: 5,
    }),
  });

  const payload = await response.json();
  if (!response.ok) {
    fail("get_external_context", `RAG server error: ${JSON.stringify(payload)}`);
  }
  return payload;
}

async function sendOpsLogToServer(payload) {
  const ragServerUrl = getRagServerUrl();
  if (!ragServerUrl) {
    return { ok: false, status: "skipped", message: "HEATGRID_RAG_URL is not configured." };
  }
  try {
    const response = await fetch(`${ragServerUrl}/ops-log`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    return {
      ok: response.ok,
      status: body.status,
      body,
    };
  } catch (error) {
    return {
      ok: false,
      status: "failed",
      message: error.message,
    };
  }
}

function expectedFromEvidence(evidence) {
  const pc = evidence.priority_context;
  return {
    decision: {
      priority: pc.priority.priority_level,
      operator_review: pc.explanation.review_required ? "Required" : "Not Required",
      data_quality: evidence.internal_context.data_quality.data_quality,
    },
    evidence: {
      priority_score: pc.priority.priority_score,
      current_best: pc.model_signals.current_best_priority_level,
      m1_specialist:
        pc.model_signals.m1_specialist_fault_group ||
        pc.model_signals.m1_specialist_priority_level,
    },
  };
}

function hasRagContext(externalContext) {
  return Array.isArray(externalContext?.retrieval?.chunks) &&
    externalContext.retrieval.chunks.length > 0;
}

function topRagChunk(externalContext) {
  return hasRagContext(externalContext) ? externalContext.retrieval.chunks[0] : null;
}

function siteContext(externalContext) {
  return externalContext?.site?.status === "mapped" ? externalContext.site : null;
}

function weatherContext(externalContext) {
  return externalContext?.weather?.status === "available" ? externalContext.weather : null;
}

function weatherFactorsText(weather) {
  if (!weather) return null;
  const factors = Array.isArray(weather.weather_factors)
    ? weather.weather_factors.filter(Boolean)
    : [];
  if (factors.length > 0) return factors.slice(0, 3).join(", ");
  return weather.interpretation ? sanitizeOperatorText(weather.interpretation) : null;
}

function buildSiteSummarySentence(externalContext) {
  const site = siteContext(externalContext);
  if (!site?.apartment_name) return null;
  const substation = site.substation_id ? `${site.substation_id}번 열수급 지점` : "해당 열수급 지점";
  return `대상 지점은 세종시 ${site.apartment_name} ${substation}입니다.`;
}

function formatSensorGroups(value) {
  const items = String(value ?? "")
    .split(/[|\\]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => item.replace(/\s*\/\s*/g, " 및 "));
  if (items.length === 0) return null;
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]}와 ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, ${items.at(-1)}`;
}

function buildWeatherSummarySentence(externalContext) {
  const weather = weatherContext(externalContext);
  if (!weather || !weather.is_relevant) return null;
  const factors = weatherFactorsText(weather);
  if (!factors) return null;
  return `당시 기상 요인(${factors})은 난방 부하 해석 시 함께 볼 운영 맥락입니다.`;
}

function ensureSummaryContext(summary, externalContext) {
  const sentences = [];
  const siteSentence = buildSiteSummarySentence(externalContext);
  if (siteSentence && !summary.includes(siteContext(externalContext)?.apartment_name ?? "")) {
    sentences.push(siteSentence);
  }
  sentences.push(summary);
  const weatherSentence = buildWeatherSummarySentence(externalContext);
  const weather = weatherContext(externalContext);
  const weatherAlreadyMentioned = weather?.weather_factors?.some((factor) => summary.includes(factor));
  if (weatherSentence && !weatherAlreadyMentioned) {
    sentences.push(weatherSentence);
  }
  return sanitizeOperatorText(sentences.join(" ")).trim();
}

function buildSiteActionItem(externalContext) {
  const site = siteContext(externalContext);
  if (!site?.apartment_name) return null;
  const sensors = formatSensorGroups(site.predist_sensor_groups_ko);
  if (sensors) {
    return `${site.apartment_name} 기계실에서 해당 열수급 지점의 운전값과 ${sensors} 계통을 우선 대조합니다.`;
  }
  return `${site.apartment_name} 기계실에서 해당 열수급 지점의 운전값과 주요 센서 계통을 우선 대조합니다.`;
}

function buildWeatherActionItem(externalContext) {
  const weather = weatherContext(externalContext);
  if (!weather || !weather.is_relevant) return null;
  const factors = weatherFactorsText(weather);
  if (!factors) return null;
  return `세종 기상 요인(${factors})으로 난방 부하가 증가했는지 같은 시간대 열사용량과 함께 확인합니다.`;
}

function buildSiteCautionItem(externalContext) {
  const site = siteContext(externalContext);
  if (!site?.caution) return null;
  return "세종 단지명은 현재 가상 매핑 기준이므로 실제 현장 지번과 설비 연결 관계는 운영 DB에서 한 번 더 확인합니다.";
}

function buildWeatherCautionItem(externalContext) {
  const weather = weatherContext(externalContext);
  if (!weather) return null;
  return "기상 요인은 부하 증가 가능성을 설명하는 보조 맥락이며 고장 원인을 단정하는 근거로 사용하지 않습니다.";
}

function appendManyIfMissing(items, values, maxItems) {
  return values.reduce((current, value) => appendIfMissing(current, value, maxItems), items);
}

function formatChunkRef(chunk) {
  if (!chunk) return null;
  const pages = chunk.page_start && chunk.page_end
    ? `p.${chunk.page_start}${chunk.page_start === chunk.page_end ? "" : `-${chunk.page_end}`}`
    : "page unknown";
  return `${chunk.document_title} ${pages}`;
}

function buildRagActionItem(externalContext) {
  const chunk = topRagChunk(externalContext);
  if (!chunk) return null;
  const text = normalizeForSearch(chunk.text);
  if (text.includes("strainer") || text.includes("filter") || text.includes("스트레이너")) {
    return "스트레이너와 필터 막힘 여부, 전후 차압 변화를 함께 확인합니다.";
  }
  if (text.includes("pressure") || text.includes("차압")) {
    return "차압과 압력 변동을 확인하고 제어밸브가 지연 없이 동작하는지 점검합니다.";
  }
  if (text.includes("leak") || text.includes("water loss") || text.includes("누수")) {
    return "배관 연결부와 밸브 주변의 누수 흔적, 유량 급변 여부를 함께 확인합니다.";
  }
  return "관련 설비의 운전값, 알람 이력, 현장 상태를 함께 대조합니다.";
}

function buildRagCautionItem(externalContext) {
  const chunk = topRagChunk(externalContext);
  if (!chunk) return null;
  return "추가 점검 항목은 원인 확정이 아니라 확인 범위를 좁히기 위한 보조 기준입니다.";
}

function appendIfMissing(items, value, maxItems) {
  if (!value) return items;
  const normalizedValue = normalizeForSearch(value);
  const exists = items.some((item) => normalizeForSearch(item) === normalizedValue);
  if (exists) return items;
  if (items.length < maxItems) return [...items, value];
  return [...items.slice(0, maxItems - 1), value];
}

function buildMainSignals(evidence, externalContext) {
  const pc = evidence.priority_context;
  const reviewReasons = pc.explanation.review_reasons;
  const site = siteContext(externalContext);
  const weather = weatherContext(externalContext);
  const weatherFactors = weatherFactorsText(weather);
  return [
    site?.apartment_name
      ? `대상 단지: ${site.apartment_name} (${site.substation_id}번 열수급 지점)`
      : null,
    weather && weatherFactors
      ? `기상 요인: ${weatherFactors}`
      : reviewReasons[0]
        ? `검토 사유: ${reviewReasonKo(reviewReasons[0])}`
        : null,
    `위험도: ${priorityKo(pc.priority.priority_level)}`,
    `의심 유형: ${faultGroupKo(pc.model_signals.m1_specialist_fault_group)}`,
    `판단 근거: ${agreementKo(pc.model_signals.m1_priority_agreement)}`,
  ].filter(Boolean).slice(0, 5);
}

function finalizeOutput(output, evidence, externalContext, usedTools) {
  const expected = expectedFromEvidence(evidence);
  const fallback = buildFallbackOutput(evidence, externalContext, usedTools);
  const actionPlanBase = Array.isArray(output.action_plan) && output.action_plan.length >= 2
    ? sanitizeOperatorItems(output.action_plan, 5)
    : fallback.action_plan;
  const cautionBase = Array.isArray(output.caution) && output.caution.length >= 1
    ? sanitizeOperatorItems(output.caution, 4)
    : fallback.caution;
  const actionPlan = appendManyIfMissing(actionPlanBase, [
    buildRagActionItem(externalContext),
    buildWeatherActionItem(externalContext),
    buildSiteActionItem(externalContext),
  ], 5);
  const caution = appendManyIfMissing(cautionBase, [
    buildWeatherCautionItem(externalContext),
    buildSiteCautionItem(externalContext),
    buildRagCautionItem(externalContext),
  ], 4);
  const summary = typeof output.summary === "string" && output.summary.trim()
    ? sanitizeOperatorText(output.summary.trim())
    : fallback.summary;

  return {
    decision: expected.decision,
    summary: ensureSummaryContext(summary, externalContext),
    action_plan: actionPlan,
    caution,
    evidence: {
      ...expected.evidence,
      main_signals: buildMainSignals(evidence, externalContext),
      used_tools: usedTools,
    },
  };
}

function buildFallbackOutput(evidence, externalContext, usedTools) {
  const expected = expectedFromEvidence(evidence);
  const priority = expected.decision.priority ?? "unknown";
  const m1Specialist = expected.evidence.m1_specialist ?? "unknown";
  const judgmentBasis = agreementKo(evidence.priority_context.model_signals.m1_priority_agreement);
  const siteSummary = buildSiteSummarySentence(externalContext);
  const weatherSummary = buildWeatherSummarySentence(externalContext);
  const ragAction = buildRagActionItem(externalContext);
  const ragCaution = buildRagCautionItem(externalContext);

  return {
    decision: expected.decision,
    summary: [
      siteSummary,
      `위험도는 ${priorityKo(priority)}이고, 주요 의심 유형은 ${faultGroupKo(m1Specialist)}입니다. ${judgmentBasis} 상태이므로 현장 점검 우선순위를 높게 잡아야 합니다.`,
      weatherSummary,
    ].filter(Boolean).join(" "),
    action_plan: appendManyIfMissing([
      "최근 운전값과 알람 이력을 먼저 확인해 신호가 일시 변동인지 지속 이상인지 구분합니다.",
      "의심 설비 주변의 압력, 유량, 온도 변화를 현장 계측값과 함께 대조합니다.",
      "센서 품질과 통신 누락 여부를 확인한 뒤 조치 우선순위를 결정합니다.",
    ], [
      ragAction,
      buildWeatherActionItem(externalContext),
      buildSiteActionItem(externalContext),
    ], 5),
    caution: appendManyIfMissing([
      "자동 판단 결과만으로 고장 원인을 확정하지 말고 현장 계측값과 설비 상태를 함께 확인합니다.",
      hasRagContext(externalContext)
        ? "추가 점검 항목은 확인 범위를 좁히는 용도로만 사용합니다."
        : "외부 참고정보가 없으므로 산정 근거와 현장 확인 결과를 함께 봅니다.",
    ], [
      buildWeatherCautionItem(externalContext),
      buildSiteCautionItem(externalContext),
      ragCaution,
    ], 4),
    evidence: {
      ...expected.evidence,
      main_signals: buildMainSignals(evidence, externalContext),
      used_tools: usedTools,
    },
  };
}

function extractJson(text) {
  const trimmed = text.trim();
  if (trimmed.startsWith("{")) return JSON.parse(trimmed);
  const match = trimmed.match(/\{[\s\S]*\}/);
  if (!match) fail("llm_json_parse", "LLM 응답에서 JSON 객체를 찾지 못했습니다.");
  return JSON.parse(match[0]);
}

async function callOpenAI(evidence, externalContext, usedTools) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    fail("api_key", "OPENAI_API_KEY가 .env 또는 환경변수에 없습니다.");
  }

  const model = process.env.OPENAI_MODEL || "gpt-4.1-mini";
  const expected = expectedFromEvidence(evidence);
  const pc = evidence.priority_context;
  const site = siteContext(externalContext);
  const weather = weatherContext(externalContext);
  const operatorTerms = {
    risk_level: priorityKo(expected.decision.priority),
    suspected_type: faultGroupKo(expected.evidence.m1_specialist),
    suspected_state: stateKo(pc.model_signals.m1_specialist_primary_state),
    judgment_basis: agreementKo(pc.model_signals.m1_priority_agreement),
    review_reasons: (pc.explanation.review_reasons ?? []).map(reviewReasonKo),
    target_site: site ? {
      apartment_name: site.apartment_name,
      substation_label: `${site.substation_id}번 열수급 지점`,
      road_address: site.road_address,
      heating_type: site.heating_type,
      sensor_groups: site.predist_sensor_groups_ko,
    } : null,
    weather_context: weather ? {
      region: weather.region,
      relevance_level: weather.relevance_level,
      weather_factors: weather.weather_factors,
      interpretation: weather.interpretation,
      metrics: weather.metrics,
    } : null,
  };
  const system = [
    "You are a Korean district-heating operations assistant writing for field operators.",
    "Return only valid JSON that matches the required schema.",
    "The decision and evidence values must exactly match required_output_shape.",
    "evidence.main_signals must contain 3 to 5 concise items.",
    "evidence.used_tools must exactly contain the tool names provided in required_output_shape.used_tools.",
    "For summary, action_plan, and caution, write natural Korean that a non-developer operator can read immediately.",
    "Do not expose implementation terms, raw field names, function names, tool names, or variable-like identifiers in summary/action_plan/caution.",
    "Forbidden user-facing terms include: current_best, m1_specialist, M1 specialist, fault_group, pump_failure, leakage_water_loss, control_controller, pressure_regulator, valve_actuator, unknown_review, RAG, retrieval, chunk, external_context, get_ops_evidence, get_external_context, get_site_context, get_weather_context, rag_http_server, pgvector, PostgreSQL, KMA API, APIHub, 기존 기준 모델, 보조 진단 모델, 보조진단 모델, 두 모델, 모델 판단, 모델 결과, 모델 우선순위.",
    "Do not mention model names or model categories in user-facing text. Use '위험도', '의심 유형', '판단 근거', and '점검 항목' instead.",
    "Translate internals into operator language, e.g. '위험도 높음', '순환펌프 고장 의심', '압력 조절 계통 이상 의심', '판단 근거가 일관됨'.",
    "If external_context.site is mapped, mention the Sejong apartment complex name naturally in summary and field checks.",
    "If external_context.weather is available and relevant, mention weather only as operating-load context, never as confirmed fault cause.",
    "Do not mention KMA API, APIHub, API key, station id, raw endpoint, RAG, document titles, page numbers, chunk IDs, source files, retrieval mechanics, or database details to the user.",
    "Use retrieved technical context silently to make action_plan and caution more specific, but do not mention RAG, document titles, page numbers, chunk IDs, source files, or retrieval mechanics to the user.",
    "Retrieved context is supporting evidence only; never override the required priority, score, operator_review, or data_quality.",
    "Make the answer rich enough for operations: summary should state severity, suspected equipment area, and why review/check is needed; action_plan should list concrete field checks in priority order; caution should state safety or uncertainty limits.",
    "Do not include label, fault_label, fault_event_id, or other validation-label fields.",
    "Keep summary as 2 to 3 Korean sentences, action_plan as 4 to 5 Korean items, and caution as 2 to 4 Korean items.",
  ].join("\n");
  const user = {
    task: "Generate final ops agent output JSON using ops evidence and RAG external context.",
    required_output_shape: {
      decision: {
        priority: expected.decision.priority,
        operator_review: expected.decision.operator_review,
        data_quality: expected.decision.data_quality,
      },
      summary: "2~3 Korean sentences for field operators; no implementation terms",
      action_plan: "4~5 concrete Korean field-check items; no RAG/source/page references",
      caution: "2~4 Korean safety/uncertainty cautions; no RAG/source/page references",
      evidence: {
        priority_score: expected.evidence.priority_score,
        current_best: expected.evidence.current_best,
        m1_specialist: expected.evidence.m1_specialist,
        main_signals: "3~5 items",
        used_tools: usedTools,
      },
    },
    ops_evidence: evidence,
    external_context: externalContext,
    operator_terms: operatorTerms,
    external_context_usage_rules: [
      "Use retrieved context only to refine inspection targets and cautions.",
      "Do not treat retrieved context as proof of the current fault.",
      "Do not change required decision/evidence values.",
      "Do not mention RAG, chunks, document titles, page numbers, or source files in user-facing text.",
    ],
  };

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      input: [
        { role: "system", content: system },
        { role: "user", content: JSON.stringify(user) },
      ],
      text: {
        format: {
          type: "json_object",
        },
      },
    }),
  });

  const payload = await response.json();
  if (!response.ok) {
    fail("openai_call", JSON.stringify(payload));
  }

  const text =
    payload.output_text ??
    payload.output?.flatMap((item) => item.content ?? [])
      ?.map((content) => content.text ?? "")
      ?.join("") ??
    "";
  return {
    output: extractJson(text),
    usage: payload.usage ?? null,
    model,
  };
}

function validateOutput(output, schema, expected) {
  const errors = [];
  const keys = Object.keys(output);
  const expectedKeys = ["decision", "summary", "action_plan", "caution", "evidence"];
  if (keys.join(",") !== expectedKeys.join(",")) {
    errors.push(`top-level keys mismatch: ${keys.join(",")}`);
  }
  if (!["Required", "Not Required"].includes(output.decision?.operator_review)) {
    errors.push("decision.operator_review enum mismatch");
  }
  if (!["Good", "Medium", "Low", "Unknown"].includes(output.decision?.data_quality)) {
    errors.push("decision.data_quality enum mismatch");
  }
  if (!Array.isArray(output.action_plan) || output.action_plan.length < 2 || output.action_plan.length > 5) {
    errors.push("action_plan must contain 2 to 5 items");
  }
  if (!Array.isArray(output.caution) || output.caution.length < 1 || output.caution.length > 4) {
    errors.push("caution must contain 1 to 4 items");
  }
  if (!Array.isArray(output.evidence?.main_signals) || output.evidence.main_signals.length < 3 || output.evidence.main_signals.length > 5) {
    errors.push("evidence.main_signals must contain 3 to 5 items");
  }
  if (!Array.isArray(output.evidence?.used_tools) || output.evidence.used_tools.length < 1) {
    errors.push("evidence.used_tools must contain at least 1 item");
  }
  if (output.decision?.priority !== expected.decision.priority) {
    errors.push("decision.priority does not match ML CSV");
  }
  if (output.decision?.operator_review !== expected.decision.operator_review) {
    errors.push("decision.operator_review does not match ML CSV");
  }
  if (output.decision?.data_quality !== expected.decision.data_quality) {
    errors.push("decision.data_quality does not match ML CSV");
  }
  if (Number(output.evidence?.priority_score) !== Number(expected.evidence.priority_score)) {
    errors.push("evidence.priority_score does not match ML CSV");
  }
  if (output.evidence?.current_best !== expected.evidence.current_best) {
    errors.push("evidence.current_best does not match ML CSV");
  }
  if (output.evidence?.m1_specialist !== expected.evidence.m1_specialist) {
    errors.push("evidence.m1_specialist does not match ML CSV");
  }

  return {
    valid: errors.length === 0,
    errors,
    schema_title: schema.title,
  };
}

async function main() {
  const startedAt = Date.now();
  await loadDotEnv();

  const cardId = process.argv[2] || "sample-row-1";
  const runId = randomUUID();
  const report = {
    run_id: runId,
    card_id: cardId,
    prompt_version: promptVersion,
    steps: {},
  };

  const apiKeyPresent = Boolean(process.env.OPENAI_API_KEY);
  report.steps.api_key = {
    ok: apiKeyPresent,
    source: apiKeyPresent ? ".env or environment" : null,
    message: apiKeyPresent
      ? "OPENAI_API_KEY를 환경에서 읽었습니다."
      : "OPENAI_API_KEY가 없어 LLM 호출 단계는 실패 처리됩니다.",
  };

  const csvChoice = await chooseOfficialCsv();
  report.ml_csv = csvChoice;

  const opsEvidence = await getOpsEvidence(cardId, csvChoice.path);
  report.steps.get_ops_evidence = {
    ok: true,
    selected_row: opsEvidence.selected_row,
    row_identifier: opsEvidence.row_identifier,
    priority_score: opsEvidence.priority_context.priority.priority_score,
    priority_level: opsEvidence.priority_context.priority.priority_level,
    current_best_priority_level:
      opsEvidence.priority_context.model_signals.current_best_priority_level,
    m1_specialist_fault_group:
      opsEvidence.priority_context.model_signals.m1_specialist_fault_group,
    review_reasons: opsEvidence.priority_context.explanation.review_reasons,
  };

  const externalContext = await getExternalContext(cardId, opsEvidence);
  report.steps.get_external_context = {
    ok: ["available", "disabled"].includes(externalContext.retrieval?.status),
    status: externalContext.status,
    source: externalContext.retrieval?.source ?? null,
    server_url: getRagServerUrl() || null,
    site_status: externalContext.site?.status ?? null,
    site_apartment_name: externalContext.site?.apartment_name ?? null,
    weather_status: externalContext.weather?.status ?? null,
    weather_relevance: externalContext.weather?.relevance_level ?? null,
    weather_factors: externalContext.weather?.weather_factors ?? [],
    retrieval_status: externalContext.retrieval?.status ?? null,
    query: externalContext.retrieval?.query ?? null,
    chunk_count: externalContext.retrieval?.chunks?.length ?? 0,
    top_chunks: (externalContext.retrieval?.chunks ?? []).map((chunk) => ({
      chunk_id: chunk.chunk_id,
      rag_role: chunk.rag_role,
      document_title: chunk.document_title,
      page_start: chunk.page_start,
      page_end: chunk.page_end,
      score: chunk.score,
    })),
  };

  const usedTools = [
    "get_ops_evidence",
    "get_external_context",
    ...(externalContext.site?.status === "mapped" ? ["get_site_context"] : []),
    ...(externalContext.weather?.status === "available" ? ["get_weather_context"] : []),
    ...(hasRagContext(externalContext)
      ? [
          externalContext.retrieval?.source === "rag_http_server"
            ? "rag_http_server"
            : "local_rag_chunk_search",
        ]
      : []),
  ];
  const schema = JSON.parse(await readFile(outputSchemaPath, "utf8"));
  const expected = expectedFromEvidence(opsEvidence);

  let output;
  let llmMode = "openai";
  let openaiUsage = null;
  try {
    const openaiResult = await callOpenAI(opsEvidence, externalContext, usedTools);
    output = openaiResult.output;
    openaiUsage = {
      model: openaiResult.model,
      usage: openaiResult.usage,
    };
    output = finalizeOutput(output, opsEvidence, externalContext, usedTools);
  } catch (error) {
    report.steps.agent_e2e = {
      ok: false,
      failed_step: error.step || "agent_e2e",
      message: error.message,
    };
    if (process.env.ALLOW_OFFLINE_SAMPLE === "1") {
      llmMode = "offline_sample";
      output = buildFallbackOutput(opsEvidence, externalContext, usedTools);
      report.steps.agent_e2e = {
        ok: true,
        mode: llmMode,
        message: "ALLOW_OFFLINE_SAMPLE=1 이므로 LLM 호출 없이 deterministic sample을 생성했습니다.",
      };
    } else {
      console.log(JSON.stringify(report, null, 2));
      process.exitCode = 1;
      return;
    }
  }

  const validation = validateOutput(output, schema, expected);
  report.steps.schema_validation = validation;
  if (openaiUsage) {
    report.steps.openai_usage = openaiUsage;
  }
  report.mapping = {
    ml_priority_score: expected.evidence.priority_score,
    output_priority_score: output.evidence?.priority_score,
    priority_score_match:
      Number(output.evidence?.priority_score) === Number(expected.evidence.priority_score),
    ml_priority_level: expected.decision.priority,
    output_priority: output.decision?.priority,
    priority_match: output.decision?.priority === expected.decision.priority,
    called_tools: output.evidence?.used_tools ?? [],
    rag_chunk_count: externalContext.retrieval?.chunks?.length ?? 0,
    rag_top_chunk: externalContext.retrieval?.chunks?.[0]?.chunk_id ?? null,
    site_apartment_name: externalContext.site?.apartment_name ?? null,
    weather_status: externalContext.weather?.status ?? null,
    weather_relevance: externalContext.weather?.relevance_level ?? null,
  };

  if (!validation.valid) {
    report.steps.save_output = {
      ok: false,
      message: "schema validation 실패로 output JSON을 저장하지 않았습니다.",
    };
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = 1;
    return;
  }

  const outputPath = getOutputPath();
  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
  report.steps.save_output = {
    ok: true,
    path: outputPath,
    mode: llmMode,
  };

  const latencyMs = Date.now() - startedAt;
  report.steps.ops_log = await sendOpsLogToServer({
    run_id: runId,
    card_id: cardId,
    row_identifier: opsEvidence.row_identifier,
    ops_evidence: opsEvidence,
    external_context: externalContext,
    output,
    openai_usage: openaiUsage,
    validation,
    prompt_version: promptVersion,
    latency_ms: latencyMs,
    output_path: outputPath,
  });

  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => {
  console.error(JSON.stringify({
    ok: false,
    failed_step: error.step || "unknown",
    message: error.message,
  }, null, 2));
  process.exitCode = 1;
});
