import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const packageDir = path.resolve(scriptDir, "..");
const projectRoot = path.resolve(packageDir, "..");
const ragChunksPath = path.join(projectRoot, "data", "rag_sources", "metadata", "rag_chunks.jsonl");

function normalize(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/<br\s*\/?>/g, " ")
    .replace(/[_/,-]/g, " ")
    .replace(/[^\p{L}\p{N}\s]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function truncate(value, maxLength = 900) {
  const text = String(value ?? "")
    .replace(/<br\s*\/?>/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trimEnd()}…`;
}

async function loadChunks() {
  if (!existsSync(ragChunksPath)) return [];
  const text = await readFile(ragChunksPath, "utf8");
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
}

function searchChunks(chunks, query, topK = 5) {
  const terms = normalize(query)
    .split(" ")
    .filter((term) => term.length >= 2);

  return chunks
    .map((chunk) => {
      const searchable = normalize([
        chunk.chunk_id,
        chunk.document_title,
        chunk.rag_role,
        chunk.section_title,
        chunk.text,
      ].join(" "));
      let score = 0;
      const matched = [];
      for (const term of terms) {
        if (!searchable.includes(term)) continue;
        score += term.length >= 8 ? 3 : 1;
        matched.push(term);
      }
      if (chunk.rag_role === "symptom_cause_action_table") score += 4;
      if (chunk.rag_role === "troubleshooting_manual") score += 3;
      if (chunk.rag_role === "domestic_inspection_standard") score += 2;
      return { chunk, score, matched };
    })
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || String(a.chunk.chunk_id).localeCompare(String(b.chunk.chunk_id)))
    .slice(0, topK)
    .map((item) => ({
      chunk_id: item.chunk.chunk_id,
      document_title: item.chunk.document_title,
      rag_role: item.chunk.rag_role,
      source_file: item.chunk.source_file,
      curated_file: item.chunk.curated_file,
      page_start: item.chunk.page_start,
      page_end: item.chunk.page_end,
      score: item.score,
      matched_terms: [...new Set(item.matched)].slice(0, 10),
      text: truncate(item.chunk.text),
    }));
}

async function main() {
  const cardId = process.argv[2] || "sample-row-1";
  const query = process.argv.slice(3).join(" ") ||
    "leakage water loss pressure flow valve strainer filter district heating substation";

  const chunks = await loadChunks();
  const results = searchChunks(chunks, query, 5);
  const passed = chunks.length > 0 && results.length > 0;
  const externalContext = {
    card_id: cardId,
    status: passed ? "configured" : "configured_no_match",
    weather: {
      status: "not_requested",
    },
    retrieval: {
      status: passed ? "available" : "no_match",
      source: "local_curated_rag_chunks",
      chunk_file: path.relative(projectRoot, ragChunksPath),
      query,
      top_k: results.length,
      chunks: results,
    },
    references: {
      technical_standards: results.map((chunk) => ({
        chunk_id: chunk.chunk_id,
        document_title: chunk.document_title,
        source_file: chunk.source_file,
        curated_file: chunk.curated_file,
        page_start: chunk.page_start,
        page_end: chunk.page_end,
      })),
      regulations: [],
    },
  };

  console.log(passed ? "PASS" : "FAIL");
  console.log(JSON.stringify(externalContext, null, 2));
  if (!passed) process.exitCode = 1;
}

main().catch((error) => {
  console.error("FAIL");
  console.error(error.message);
  process.exitCode = 1;
});
