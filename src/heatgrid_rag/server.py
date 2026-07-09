from __future__ import annotations

import argparse
import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .search import ROOT, RagSearcher


CASES_DIR = ROOT / "output" / "ops_agent" / "cases"


def display_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def case_title(case_id: str) -> str:
    titles = {
        "control_controller_urgent": "제어기 이상 의심 / 긴급",
        "pump_failure_urgent": "순환펌프 고장 의심 / 긴급",
        "leakage_water_loss_high": "누수 또는 보충수 손실 의심 / 높음",
        "pressure_regulator_urgent": "압력 조절 계통 이상 의심 / 긴급",
        "valve_actuator_high": "밸브 구동부 이상 의심 / 높음",
        "unknown_review_urgent": "고장 유형 미확정 / 긴급",
        "unknown_review_medium_disagreement": "판단 신호 불일치 / 중간",
        "unknown_review_low_disagreement": "판단 신호 불일치 / 낮음",
    }
    return titles.get(case_id, case_id.replace("_", " "))


def collect_comparisons() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    if not CASES_DIR.exists():
        return {
            "status": "missing_cases",
            "case_dir": display_path(CASES_DIR.relative_to(ROOT)),
            "cases": [],
        }

    no_rag_files = sorted(CASES_DIR.glob("*_no_rag.json"))
    for no_rag_path in no_rag_files:
        case_id = no_rag_path.name.removesuffix("_no_rag.json")
        with_rag_path = CASES_DIR / f"{case_id}_with_rag.json"
        if not with_rag_path.exists():
            continue
        no_rag = _read_json(no_rag_path)
        with_rag = _read_json(with_rag_path)
        cases.append(
            {
                "case_id": case_id,
                "title": case_title(case_id),
                "files": {
                    "no_rag": display_path(no_rag_path.relative_to(ROOT)),
                    "with_rag": display_path(with_rag_path.relative_to(ROOT)),
                },
                "decision": {
                    "priority": no_rag.get("decision", {}).get("priority"),
                    "operator_review": no_rag.get("decision", {}).get("operator_review"),
                    "data_quality": no_rag.get("decision", {}).get("data_quality"),
                },
                "no_rag": no_rag,
                "with_rag": with_rag,
            }
        )

    return {
        "status": "ok",
        "case_dir": display_path(CASES_DIR.relative_to(ROOT)),
        "case_count": len(cases),
        "cases": cases,
    }


def comparison_html() -> bytes:
    page = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>HeatGrid 운영 답변 비교</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d7dce3;
      --text: #17202a;
      --muted: #657181;
      --accent: #1f6feb;
      --accent-soft: #e8f1ff;
      --plain: #f3f4f6;
      --rag: #ecfdf3;
      --rag-line: #b7ebc6;
      --warn: #fff7e6;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    header {
      position: sticky;
      top: 0;
      z-index: 2;
      background: rgba(246, 247, 249, 0.94);
      border-bottom: 1px solid var(--line);
      backdrop-filter: blur(10px);
    }
    .top {
      max-width: 1320px;
      margin: 0 auto;
      padding: 18px 20px 14px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    h1 {
      margin: 0;
      font-size: 22px;
      line-height: 1.2;
      letter-spacing: 0;
    }
    .meta {
      color: var(--muted);
      font-size: 13px;
      margin-top: 4px;
    }
    .toolbar {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    select, button {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      min-height: 36px;
      border-radius: 6px;
      padding: 0 10px;
      font-size: 14px;
    }
    button.active {
      border-color: var(--accent);
      color: var(--accent);
      background: var(--accent-soft);
    }
    main {
      max-width: 1320px;
      margin: 0 auto;
      padding: 18px 20px 32px;
    }
    .case {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 18px;
      overflow: hidden;
    }
    .case-head {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
    }
    .case-title {
      font-size: 17px;
      font-weight: 700;
    }
    .location-line {
      margin-top: 6px;
      color: #334155;
      font-size: 14px;
      line-height: 1.45;
    }
    .location-line b {
      color: #0f172a;
    }
    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      justify-content: flex-end;
    }
    .badge {
      font-size: 12px;
      color: #334155;
      background: #eef2f7;
      border: 1px solid #d8dee8;
      border-radius: 999px;
      padding: 4px 8px;
      white-space: nowrap;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0;
    }
    .col {
      padding: 16px;
      min-width: 0;
    }
    .col + .col {
      border-left: 1px solid var(--line);
    }
    .col.rag {
      background: linear-gradient(0deg, rgba(236, 253, 243, 0.45), rgba(255,255,255,0.8));
    }
    .label {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      height: 26px;
      border-radius: 999px;
      padding: 0 9px;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 10px;
    }
    .label.no { background: var(--plain); color: #374151; }
    .label.rag { background: var(--rag); color: #176434; border: 1px solid var(--rag-line); }
    .section {
      margin-top: 12px;
    }
    .section h3 {
      margin: 0 0 7px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    .summary {
      font-size: 15px;
      line-height: 1.55;
      margin: 0;
    }
    ol, ul {
      margin: 0;
      padding-left: 20px;
    }
    li {
      margin: 6px 0;
      line-height: 1.45;
    }
    .evidence {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 10px;
      font-size: 13px;
      color: #334155;
      overflow-wrap: anywhere;
    }
    .rag-note {
      background: var(--warn);
      border: 1px solid #f4d68c;
      border-radius: 6px;
      padding: 9px 10px;
      font-size: 13px;
      line-height: 1.45;
    }
    .empty {
      padding: 28px;
      text-align: center;
      color: var(--muted);
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    @media (max-width: 860px) {
      .top, .case-head { align-items: flex-start; flex-direction: column; }
      .toolbar, .badges { justify-content: flex-start; }
      .grid { grid-template-columns: 1fr; }
      .col + .col { border-left: 0; border-top: 1px solid var(--line); }
    }
  </style>
</head>
<body>
  <header>
    <div class="top">
      <div>
        <h1>HeatGrid 운영 답변 비교</h1>
        <div class="meta" id="meta">불러오는 중...</div>
      </div>
      <div class="toolbar">
        <select id="caseFilter" aria-label="case filter"></select>
        <button id="showAll" class="active" type="button">전체</button>
        <button id="showDiff" type="button">참고자료 반영만</button>
      </div>
    </div>
  </header>
  <main id="app">
    <div class="empty">비교 데이터를 불러오는 중입니다.</div>
  </main>
  <script>
    const app = document.getElementById("app");
    const meta = document.getElementById("meta");
    const filter = document.getElementById("caseFilter");
    const showAll = document.getElementById("showAll");
    const showDiff = document.getElementById("showDiff");
    let payload = null;
    let ragOnly = false;

    const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[ch]));

    function labelKey(value) {
      return String(value ?? "").trim().toLowerCase().replace(/[\\s-]+/g, "_");
    }

    function priorityLabel(value) {
      const map = { urgent: "긴급", high: "높음", medium: "중간", low: "낮음" };
      return map[labelKey(value)] || String(value ?? "확인 필요");
    }

    function reviewLabel(value) {
      const map = {
        required: "검토 필요",
        not_required: "추가 검토 낮음",
        optional: "선택 검토",
        true: "검토 필요",
        false: "추가 검토 낮음"
      };
      return map[labelKey(value)] || String(value ?? "확인 필요");
    }

    function qualityLabel(value) {
      const map = {
        high: "양호",
        good: "양호",
        medium: "보통",
        fair: "보통",
        low: "주의",
        poor: "주의",
        unknown: "확인 필요"
      };
      return map[labelKey(value)] || String(value ?? "확인 필요");
    }

    function scoreLabel(value) {
      const numeric = Number(value);
      return Number.isFinite(numeric) ? numeric.toFixed(2) : String(value ?? "확인 필요");
    }

    function faultLabel(value) {
      const map = {
        leakage_water_loss: "누수 또는 보충수 손실 의심",
        control_controller: "제어기/컨트롤러 이상 의심",
        pump_failure: "순환펌프 고장 의심",
        pressure_regulator: "압력 조절 계통 이상 의심",
        valve_actuator: "밸브 구동부 이상 의심",
        unknown_review: "고장 유형 미확정"
      };
      return map[labelKey(value)] || String(value ?? "고장 유형 미확정");
    }

    function toolLabel(tools) {
      const labels = [];
      if ((tools || []).includes("get_ops_evidence")) labels.push("운영 데이터");
      if ((tools || []).includes("get_site_context")) labels.push("세종 단지 매핑");
      if ((tools || []).includes("get_weather_context")) labels.push("기상청 기상자료");
      if ((tools || []).includes("rag_http_server") || (tools || []).includes("local_rag_chunk_search")) labels.push("운영 참고자료");
      return labels.length ? labels.join(", ") : "기본 판단 근거";
    }

    function list(items, ordered = true) {
      const tag = ordered ? "ol" : "ul";
      const clean = (item) => cleanDisplayText(String(item ?? "").replace(/^\\s*(?:\\d+[.)]|[-*•])\\s+/, ""));
      return `<${tag}>${(items || []).map((item) => `<li>${esc(clean(item))}</li>`).join("")}</${tag}>`;
    }

    function cleanDisplayText(value) {
      return String(value ?? "")
        .replace(/\\s*[|\\\\]\\s*/g, ", ")
        .replace(/공급\\s*\\/\\s*환수/g, "공급 및 환수")
        .replace(/\\s+,\\s+/g, ", ")
        .trim();
    }

    function targetLocation(data) {
      const signals = data.evidence?.main_signals || [];
      const target = signals.find((item) => String(item).startsWith("대상 단지:"));
      if (target) return String(target).replace(/^대상 단지:\\s*/, "");
      const summary = String(data.summary || "");
      const match = summary.match(/([가-힣A-Za-z0-9]+(?:마을|단지)[가-힣A-Za-z0-9]*아파트)\\s*([0-9]+번 열수급 지점)?/);
      return match ? [match[1], match[2]].filter(Boolean).join(" ") : "";
    }

    function evidence(data) {
      const ev = data.evidence || {};
      return `
        <div class="evidence">
          <div><b>위험도 점수</b>: ${esc(scoreLabel(ev.priority_score))}</div>
          <div><b>위험도</b>: ${esc(priorityLabel(data.decision?.priority || ev.current_best))}</div>
          <div><b>의심 유형</b>: ${esc(faultLabel(ev.m1_specialist))}</div>
          <div><b>판단 근거</b>: ${esc(toolLabel(ev.used_tools))}</div>
          <div><b>핵심 신호</b>: ${esc((ev.main_signals || []).map(cleanDisplayText).join(" · "))}</div>
        </div>
      `;
    }

    function panel(title, data, kind) {
      const isRag = kind === "rag";
      const ragSignals = (data.evidence?.main_signals || []).filter((item) => item.includes("참고자료"));
      const ragActions = (data.action_plan || []).filter((item) => item.includes("스트레이너") || item.includes("차압") || item.includes("밸브") || item.includes("열교환기"));
      const ragCautions = (data.caution || []).filter((item) => item.includes("참고자료") || item.includes("원인 확정"));
      return `
        <section class="col ${isRag ? "rag" : ""}">
          <div class="label ${isRag ? "rag" : "no"}">${esc(title)}</div>
          <div class="section"><h3>요약</h3><p class="summary">${esc(data.summary)}</p></div>
          <div class="section"><h3>점검 계획</h3>${list(data.action_plan || [])}</div>
          <div class="section"><h3>주의사항</h3>${list(data.caution || [], false)}</div>
          ${isRag && (ragSignals.length || ragActions.length || ragCautions.length)
            ? `<div class="section"><h3>참고자료 반영</h3><div class="rag-note">${esc([...ragSignals, ...ragActions, ...ragCautions].join(" / "))}</div></div>`
            : ""}
          <div class="section"><h3>판단 근거</h3>${evidence(data)}</div>
        </section>
      `;
    }

    function caseCard(item) {
      const no = item.no_rag || {};
      const rag = item.with_rag || {};
      const location = targetLocation(rag) || targetLocation(no);
      const ragEvidence = (rag.evidence?.main_signals || []).some((line) => line.includes("참고자료")) ||
        (rag.evidence?.used_tools || []).includes("rag_http_server");
      if (ragOnly && !ragEvidence) return "";
      return `
        <article class="case">
          <div class="case-head">
            <div>
              <div class="case-title">${esc(item.title)}</div>
              ${location ? `<div class="location-line"><b>문제 발생 위치</b>: ${esc(location)}</div>` : ""}
            </div>
            <div class="badges">
              <span class="badge">위험도 ${esc(priorityLabel(item.decision?.priority))}</span>
              <span class="badge">${esc(reviewLabel(item.decision?.operator_review))}</span>
              <span class="badge">데이터 ${esc(qualityLabel(item.decision?.data_quality))}</span>
              <span class="badge">비교 케이스</span>
            </div>
          </div>
          <div class="grid">
            ${panel("원본", no, "no")}
            ${panel("참고자료 사용", rag, "rag")}
          </div>
        </article>
      `;
    }

    function render() {
      if (!payload) return;
      const selected = filter.value;
      const cases = payload.cases.filter((item) => selected === "__all__" || item.case_id === selected);
      const html = cases.map(caseCard).filter(Boolean).join("");
      app.innerHTML = html || `<div class="empty">표시할 비교 케이스가 없습니다.</div>`;
      meta.textContent = `${payload.case_count}개 케이스 · ${payload.case_dir}`;
    }

    showAll.addEventListener("click", () => {
      ragOnly = false;
      showAll.classList.add("active");
      showDiff.classList.remove("active");
      render();
    });
    showDiff.addEventListener("click", () => {
      ragOnly = true;
      showDiff.classList.add("active");
      showAll.classList.remove("active");
      render();
    });
    filter.addEventListener("change", render);

    fetch("/api/comparisons")
      .then((response) => response.json())
      .then((data) => {
        payload = data;
        filter.innerHTML = `<option value="__all__">전체 케이스</option>` +
          data.cases.map((item) => `<option value="${esc(item.case_id)}">${esc(item.title)}</option>`).join("");
        render();
      })
      .catch((error) => {
        app.innerHTML = `<div class="empty">비교 데이터를 불러오지 못했습니다: ${esc(error.message)}</div>`;
      });
  </script>
</body>
</html>
"""
    return page.encode("utf-8")


def make_handler(searcher: RagSearcher) -> type[BaseHTTPRequestHandler]:
    class RagHandler(BaseHTTPRequestHandler):
        server_version = "HeatGridRagHTTP/0.1"

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length <= 0:
                return {}
            body = self.rfile.read(length).decode("utf-8")
            return json.loads(body) if body.strip() else {}

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, body: bytes, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path in {"/", "/compare"}:
                self._send_html(comparison_html())
                return
            if path == "/health":
                self._send_json(searcher.health())
                return
            if path == "/api/comparisons":
                self._send_json(collect_comparisons())
                return
            if path == "/api/runs":
                query = parse_qs(parsed.query)
                limit = int((query.get("limit") or ["20"])[0])
                self._send_json(searcher.recent_runs(limit=limit))
                return
            self._send_json(
                {"status": "not_found", "path": path},
                HTTPStatus.NOT_FOUND,
            )

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                payload = self._read_json()
                if path == "/search":
                    query = str(payload.get("query") or "")
                    if not query.strip():
                        self._send_json({"status": "bad_request", "message": "query is required"}, HTTPStatus.BAD_REQUEST)
                        return
                    top_k = int(payload.get("top_k") or 5)
                    self._send_json(searcher.search(query=query, top_k=top_k))
                    return

                if path == "/external-context":
                    card_id = str(payload.get("card_id") or "")
                    evidence = payload.get("ops_evidence")
                    if not card_id:
                        self._send_json({"status": "bad_request", "message": "card_id is required"}, HTTPStatus.BAD_REQUEST)
                        return
                    if not isinstance(evidence, dict):
                        self._send_json({"status": "bad_request", "message": "ops_evidence object is required"}, HTTPStatus.BAD_REQUEST)
                        return
                    top_k = int(payload.get("top_k") or 5)
                    self._send_json(searcher.external_context(card_id=card_id, evidence=evidence, top_k=top_k))
                    return

                if path == "/ops-log":
                    self._send_json(searcher.log_agent_run(payload))
                    return

                self._send_json(
                    {"status": "not_found", "path": path},
                    HTTPStatus.NOT_FOUND,
                )
            except Exception as exc:  # pragma: no cover - server boundary
                self._send_json(
                    {"status": "error", "message": str(exc)},
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                )

        def log_message(self, format: str, *args: Any) -> None:
            print(f"{self.address_string()} - {format % args}")

    return RagHandler


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="HeatGrid local RAG HTTP server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()

    searcher = RagSearcher()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(searcher))
    print(
        json.dumps(
            {
                "status": "serving",
                "host": args.host,
                "port": args.port,
                "health": searcher.health(),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
