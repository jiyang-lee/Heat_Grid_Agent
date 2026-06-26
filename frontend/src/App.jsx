import React, { useEffect, useMemo, useState } from "react";
import "./App.css";

const LEVEL_META = {
  urgent: { label: "긴급", className: "level-urgent" },
  high: { label: "높음", className: "level-high" },
  medium: { label: "중간", className: "level-medium" },
  low: { label: "낮음", className: "level-low" },
};

const RISK_META = {
  critical: { label: "Critical", className: "risk-critical" },
  high: { label: "High", className: "risk-high" },
  medium: { label: "Medium", className: "risk-medium" },
  low: { label: "Low", className: "risk-low" },
};

export default function App() {
  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [drafts, setDrafts] = useState(null);
  const [draftTab, setDraftTab] = useState("work_order");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    refresh();
  }, []);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/priority?limit=50");
      if (!response.ok) throw new Error(`priority API ${response.status}`);
      const data = await response.json();
      setRows(data);
      if (data.length) {
        await openRow(data[0], { silent: true });
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function openRow(row, options = {}) {
    setSelected(row.key);
    setDetail(null);
    setDrafts(null);
    try {
      const [detailResponse, draftResponse] = await Promise.all([
        fetch(`/priority/${row.key}`),
        fetch(`/agent/output/${row.key}`),
      ]);
      if (!detailResponse.ok) throw new Error(`detail API ${detailResponse.status}`);
      setDetail(await detailResponse.json());
      setDrafts(draftResponse.ok ? await draftResponse.json() : null);
    } catch (e) {
      if (!options.silent) setError(String(e));
    }
  }

  const summary = useMemo(() => buildSummary(rows), [rows]);
  const visibleRows = rows.slice(0, 10);
  const sensors = splitSensors(detail?.main_abnormal_sensors);

  return (
    <div className="dashboard-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">HeatGrid Agent</p>
          <h1>운영 점검 우선순위 대시보드</h1>
        </div>
        <div className="header-actions">
          <div className="run-status">
            <span className="status-dot" />
            실제 모델 체인 기준
          </div>
          <button className="refresh-button" onClick={refresh} type="button">
            새로고침
          </button>
        </div>
      </header>

      {error && <div className="alert-bar">API 오류: {error}</div>}

      <section className="kpi-strip" aria-label="운영 요약">
        <Metric label="점검 후보" value={summary.total} note="상위 50건" />
        <Metric label="긴급/높음" value={summary.hot} note="즉시 검토 대상" tone="danger" />
        <Metric label="평균 점수" value={summary.avgScore} note="priority score" />
        <Metric label="0-24h" value={summary.lead24} note="리드타임 예측" tone="warning" />
      </section>

      <main className="workspace">
        <section className="queue-panel">
          <div className="section-title-row">
            <div>
              <h2>점검 큐</h2>
              <p>점수순 정렬, 행 선택 시 근거와 초안을 함께 확인</p>
            </div>
            <span className="row-count">{loading ? "불러오는 중" : `상위 ${visibleRows.length} / ${rows.length}건`}</span>
          </div>

          <div className="queue-table-wrap">
            <table className="queue-table">
              <thead>
                <tr>
                  <th>순위</th>
                  <th>대상</th>
                  <th>윈도우</th>
                  <th>점수</th>
                  <th>우선도</th>
                  <th>위험</th>
                  <th>리드타임</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row, index) => (
                  <tr
                    className={selected === row.key ? "selected" : ""}
                    key={row.key}
                    onClick={() => openRow(row)}
                  >
                    <td className="rank-cell">{index + 1}</td>
                    <td>
                      <div className="target-cell">
                        <strong>{row.manufacturer}</strong>
                        <span>Substation {row.substation_id}</span>
                      </div>
                    </td>
                    <td className="time-cell">{formatWindow(row.window_start)}</td>
                    <td className="score-cell">{formatNumber(row.priority_score, 2)}</td>
                    <td>
                      <Badge meta={LEVEL_META[row.priority_level]} fallback={row.priority_level} />
                    </td>
                    <td>
                      <Badge meta={RISK_META[row.risk_level_calibrated]} fallback={row.risk_level_calibrated} />
                    </td>
                    <td className="lead-cell">{row.predicted_lead_time_bucket || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <aside className="detail-panel">
          {!detail && (
            <div className="empty-state">
              <h2>상세 대기</h2>
              <p>점검 큐에서 행을 선택하면 모델 근거와 작업 초안이 표시됩니다.</p>
            </div>
          )}

          {detail && (
            <>
              <div className="detail-header">
                <div>
                  <p className="eyebrow">선택 대상</p>
                  <h2>
                    {detail.manufacturer} / Substation {detail.substation_id}
                  </h2>
                  <p>{formatWindow(detail.window_start)} - {formatWindow(detail.window_end)}</p>
                </div>
                <Badge meta={LEVEL_META[detail.priority_level]} fallback={detail.priority_level} large />
              </div>

              <div className="score-grid">
                <Metric label="Priority" value={formatNumber(detail.priority_score, 2)} />
                <Metric label="Risk prob" value={formatNumber(detail.risk_probability, 3)} />
                <Metric label="Anomaly" value={formatNumber(detail.anomaly_score, 3)} />
                <Metric label="Lead conf" value={formatNumber(detail.predicted_lead_time_confidence, 3)} />
              </div>

              <section className="evidence-section">
                <h3>모델 체인 근거</h3>
                <div className="chain-rail">
                  <ChainStep label="IF" value={formatNumber(detail.anomaly_score, 3)} />
                  <ChainStep label="Risk" value={`${detail.risk_level_calibrated || "-"} / ${formatNumber(detail.risk_probability, 3)}`} />
                  <ChainStep label="Leadtime" value={detail.predicted_lead_time_bucket || "-"} />
                  <ChainStep label="Priority" value={`${formatNumber(detail.priority_score, 2)} (${detail.priority_level})`} />
                </div>
              </section>

              <section className="evidence-section">
                <h3>주요 이상 센서</h3>
                <div className="sensor-list">
                  {sensors.length ? sensors.map((sensor) => <span key={sensor}>{sensor}</span>) : <span>근거 센서 없음</span>}
                </div>
              </section>

              <section className="evidence-section">
                <h3>설비 컨텍스트</h3>
                <dl className="context-list">
                  <div><dt>구성</dt><dd>{detail.configuration_type || "-"}</dd></div>
                  <div><dt>DHW</dt><dd>{displayNullable(detail.has_dhw)}</dd></div>
                  <div><dt>Buffer</dt><dd>{displayNullable(detail.has_buffer_tank)}</dd></div>
                  <div><dt>최근 고장 이후</dt><dd>{formatDays(detail.days_since_last_fault_event)}</dd></div>
                  <div><dt>최근 정비 이후</dt><dd>{formatDays(detail.days_since_last_task_event)}</dd></div>
                </dl>
              </section>

              <section className="draft-section">
                <div className="section-title-row compact">
                  <div>
                    <h3>운영자 검토 초안</h3>
                    <p>자동 발송 없음, 검토 후 전달</p>
                  </div>
                  <span className={drafts ? "draft-status ready" : "draft-status missing"}>
                    {drafts ? "초안 생성됨" : "초안 없음"}
                  </span>
                </div>
                <DraftTabs active={draftTab} drafts={drafts} onChange={setDraftTab} />
              </section>
            </>
          )}
        </aside>
      </main>
    </div>
  );
}

function Metric({ label, value, note, tone }) {
  return (
    <div className={`metric-card ${tone ? `metric-${tone}` : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {note && <small>{note}</small>}
    </div>
  );
}

function Badge({ meta, fallback, large = false }) {
  return (
    <span className={`badge ${meta?.className || ""} ${large ? "badge-large" : ""}`}>
      {meta?.label || fallback || "-"}
    </span>
  );
}

function ChainStep({ label, value }) {
  return (
    <div className="chain-step">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DraftTabs({ active, drafts, onChange }) {
  const tabs = [
    { id: "work_order", label: "작업지시", content: drafts?.work_order_md },
    { id: "email", label: "메일", content: drafts?.email_md },
  ];
  const current = tabs.find((tab) => tab.id === active) || tabs[0];

  return (
    <div className="draft-tabs">
      <div className="draft-tab-list" role="tablist" aria-label="운영자 초안">
        {tabs.map((tab) => (
          <button
            aria-selected={current.id === tab.id}
            className={current.id === tab.id ? "active" : ""}
            key={tab.id}
            onClick={() => onChange(tab.id)}
            role="tab"
            type="button"
          >
            {tab.label}
          </button>
        ))}
      </div>
      <DraftBlock title={current.label} content={current.content} />
    </div>
  );
}

function DraftBlock({ title, content }) {
  const preview = buildDraftPreview(content, title);
  return (
    <div className="draft-block">
      <h4>{title} 미리보기</h4>
      <pre>{preview || "초안 없음"}</pre>
    </div>
  );
}

function buildDraftPreview(content, title) {
  if (!content) return "";

  const lines = String(content)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const selectedLines = lines.filter((line) => {
    if (title === "작업지시") {
      return (
        line.startsWith("# ") ||
        line.startsWith("- 대상:") ||
        line.startsWith("- 윈도우:") ||
        line.startsWith("- 우선순위:") ||
        line.startsWith("- 주요 이상 센서:") ||
        line.startsWith("- anomaly_score:") ||
        line.startsWith("- risk_probability:")
      );
    }

    return (
      line.startsWith("제목:") ||
      line.startsWith("- 대상:") ||
      line.startsWith("- 점검 윈도우:") ||
      line.startsWith("- 우선순위:") ||
      line.startsWith("- 주요 근거:")
    );
  });

  return selectedLines.slice(0, title === "작업지시" ? 6 : 5).join("\n") || lines.slice(0, 5).join("\n");
}

function buildSummary(rows) {
  const total = rows.length;
  const hot = rows.filter((row) => ["urgent", "high"].includes(row.priority_level)).length;
  const avg = total ? rows.reduce((sum, row) => sum + Number(row.priority_score || 0), 0) / total : 0;
  const lead24 = rows.filter((row) => row.predicted_lead_time_bucket === "0-24h").length;
  return {
    total,
    hot,
    avgScore: formatNumber(avg, 1),
    lead24,
  };
}

function splitSensors(value) {
  if (!value) return [];
  return String(value).split(";").map((sensor) => sensor.trim()).filter(Boolean);
}

function formatNumber(value, digits) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return number.toFixed(digits);
}

function formatDays(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number.toFixed(1)}일`;
}

function formatWindow(value) {
  if (!value) return "-";
  return String(value).replace("T", " ").slice(0, 16);
}

function displayNullable(value) {
  return value === null || value === undefined || value === "" ? "-" : String(value);
}
