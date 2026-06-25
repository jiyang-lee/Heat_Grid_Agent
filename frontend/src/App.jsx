import React, { useEffect, useState } from "react";

// 우선순위 표 → 상세(근거 센서) → 보고서/메일 초안 검토.
const LEVEL_COLOR = {
  urgent: "#c0392b",
  high: "#e67e22",
  medium: "#f1c40f",
  low: "#7f8c8d",
};

export default function App() {
  const [rows, setRows] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [drafts, setDrafts] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/priority?limit=50")
      .then((r) => r.json())
      .then(setRows)
      .catch((e) => setError(String(e)));
  }, []);

  function openRow(row) {
    setSelected(row.key);
    setDetail(null);
    setDrafts(null);
    fetch(`/priority/${row.key}`).then((r) => r.json()).then(setDetail);
    fetch(`/agent/output/${row.key}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setDrafts)
      .catch(() => setDrafts(null));
  }

  return (
    <div style={{ fontFamily: "system-ui, sans-serif", padding: 20, display: "flex", gap: 20 }}>
      <div style={{ flex: "1 1 55%" }}>
        <h2>HeatGrid 우선순위 점검 대상</h2>
        {error && <p style={{ color: "red" }}>API 오류: {error} (서버 8000 실행 확인)</p>}
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f4f4f4", textAlign: "left" }}>
              <th style={th}>#</th>
              <th style={th}>제조사</th>
              <th style={th}>substation</th>
              <th style={th}>윈도우</th>
              <th style={th}>점수</th>
              <th style={th}>등급</th>
              <th style={th}>위험/리드타임</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={row.key}
                onClick={() => openRow(row)}
                style={{
                  cursor: "pointer",
                  background: selected === row.key ? "#eaf2ff" : "transparent",
                }}
              >
                <td style={td}>{i + 1}</td>
                <td style={td}>{row.manufacturer}</td>
                <td style={td}>{row.substation_id}</td>
                <td style={td}>{row.window_start?.slice(0, 16)}</td>
                <td style={{ ...td, fontWeight: 600 }}>{row.priority_score}</td>
                <td style={td}>
                  <span style={{ color: LEVEL_COLOR[row.priority_level] || "#333", fontWeight: 600 }}>
                    {row.priority_level}
                  </span>
                </td>
                <td style={td}>
                  {row.risk_level_calibrated} / {row.predicted_lead_time_bucket}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ flex: "1 1 45%" }}>
        {!detail && <p style={{ color: "#888" }}>행을 클릭하면 상세 근거와 보고서/메일 초안이 표시됩니다.</p>}
        {detail && (
          <div>
            <h3>상세 — substation {detail.substation_id}</h3>
            <ul style={{ fontSize: 13, lineHeight: 1.6 }}>
              <li>점수: <b>{detail.priority_score}</b> ({detail.priority_level})</li>
              <li>위험등급: {detail.risk_level_calibrated} · 리드타임: {detail.predicted_lead_time_bucket}</li>
              <li>anomaly: {detail.anomaly_score} · risk_prob: {detail.risk_probability}</li>
              <li>주요 이상 센서: {detail.main_abnormal_sensors || "-"}</li>
              <li>구성: {detail.configuration_type} (DHW={detail.has_dhw}, buffer={detail.has_buffer_tank})</li>
            </ul>
            <h4>보고서 초안 (검토 필요, 자동발송 아님)</h4>
            <pre style={pre}>{drafts?.work_order_md || "초안 없음 (run_agent 실행 필요)"}</pre>
            <h4>메일 초안</h4>
            <pre style={pre}>{drafts?.email_md || "초안 없음"}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

const th = { padding: "6px 8px", borderBottom: "2px solid #ddd" };
const td = { padding: "6px 8px", borderBottom: "1px solid #eee" };
const pre = {
  background: "#fafafa",
  border: "1px solid #eee",
  padding: 12,
  fontSize: 12,
  whiteSpace: "pre-wrap",
  maxHeight: 280,
  overflow: "auto",
};
