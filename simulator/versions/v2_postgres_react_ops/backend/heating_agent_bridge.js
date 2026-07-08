(function () {
  const bridgeState = {
    enqueue: null,
    alerts: [],
    byBuilding: new Map(),
    selectedAlert: null,
    lastSimulation: null,
  };

  const tierForPriority = (priorityLevel) =>
    priorityLevel === "urgent" ? "urgent" : "caution";

  const priorityRank = (priorityLevel) =>
    priorityLevel === "urgent" ? 2 : 1;

  function ensureBridgePanel() {
    let panel = document.querySelector("#bridgePanel");
    if (panel) {
      return panel;
    }
    panel = document.createElement("div");
    panel.id = "bridgePanel";
    panel.style.cssText = [
      "margin:10px 0 0",
      "padding:10px 12px",
      "border:1px solid rgba(0,229,255,.35)",
      "border-radius:10px",
      "background:rgba(4,12,30,.72)",
      "font:12px Consolas,D2Coding,monospace",
      "color:#bfe4ff",
      "line-height:1.5",
    ].join(";");
    document.querySelector("header")?.append(panel);
    return panel;
  }

  function setBridgeStatus(message) {
    ensureBridgePanel().textContent = message;
  }

  async function requestJson(path, options) {
    const response = await fetch(path, options);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || response.statusText);
    }
    return payload;
  }

  function selectRepresentativeAlert(alerts) {
    return alerts
      .slice()
      .sort(
        (left, right) =>
          priorityRank(right.priority_level) - priorityRank(left.priority_level) ||
          Number(right.priority_score || 0) - Number(left.priority_score || 0),
      )[0];
  }

  function groupAlerts(alerts) {
    const grouped = new Map();
    alerts.forEach((alert) => {
      const id = Number(alert.substation_id);
      if (!Number.isFinite(id)) {
        return;
      }
      const items = grouped.get(id) || [];
      items.push(alert);
      grouped.set(id, items);
    });
    return grouped;
  }

  function resetBuildingState() {
    BUILDINGS.forEach((building) => {
      building.tier = "normal";
      MACHINES.forEach((machine) => {
        building.st[machine.key] = "normal";
      });
      building.bridgeAlerts = [];
      building.bridgeAlert = null;
    });
  }

  function applyAlertsToBuildings() {
    resetBuildingState();
    bridgeState.byBuilding = groupAlerts(bridgeState.alerts);
    BUILDINGS.forEach((building) => {
      const alerts = bridgeState.byBuilding.get(building.id) || [];
      if (!alerts.length) {
        return;
      }
      const representative = selectRepresentativeAlert(alerts);
      building.bridgeAlerts = alerts;
      building.bridgeAlert = representative;
      building.tier = tierForPriority(representative.priority_level);
      const monitored = MACHINES.filter((machine) => machineMonitored(building, machine));
      const primary = monitored[building.id % monitored.length];
      if (primary) {
        building.st[primary.key] = building.tier;
      }
    });
  }

  function alertSummary(alert) {
    if (!alert) {
      return "open alert 없음";
    }
    const score = Number(alert.priority_score || 0).toFixed(2);
    return `${alert.priority_level.toUpperCase()} score=${score} alert=${alert.alert_id}`;
  }

  function decorateCityRows() {
    document.querySelectorAll("#asideBody .row[data-bld]").forEach((row) => {
      const buildingId = Number(row.getAttribute("data-bld"));
      const alert = selectRepresentativeAlert(bridgeState.byBuilding.get(buildingId) || []);
      const info = row.querySelector(".info");
      if (!alert || !info || row.querySelector(".bridge-alert-line")) {
        return;
      }
      const line = document.createElement("div");
      line.className = "bridge-alert-line";
      line.style.cssText = "margin-top:3px;color:#9fe9ff;font-size:10.5px";
      line.textContent = alertSummary(alert);
      info.append(line);
    });
  }

  function renderOpsOutput(container) {
    if (!bridgeState.lastSimulation) {
      return;
    }
    const output = bridgeState.lastSimulation.ops_output;
    const block = document.createElement("pre");
    block.style.cssText = [
      "white-space:pre-wrap",
      "margin-top:8px",
      "padding:9px",
      "border-radius:8px",
      "background:rgba(0,0,0,.28)",
      "color:#dff0ff",
      "font:11px/1.45 Consolas,D2Coding,monospace",
    ].join(";");
    block.textContent = [
      `[summary] ${output.summary}`,
      `[action_plan] ${output.action_plan}`,
      `[caution] ${output.caution}`,
    ].join("\n");
    container.append(block);
  }

  function decorateRoomPanel() {
    if (state.view !== "room") {
      return;
    }
    const building = BUILDINGS.find((item) => item.id === state.selBld);
    const asideMeta = document.querySelector("#asideMeta .aside-meta");
    if (!building || !asideMeta || asideMeta.querySelector(".bridge-room-card")) {
      return;
    }
    const alert = building.bridgeAlert;
    bridgeState.selectedAlert = alert || null;

    const card = document.createElement("div");
    card.className = "bridge-room-card";
    card.style.cssText = [
      "margin-top:10px",
      "padding:10px",
      "border:1px solid rgba(0,229,255,.22)",
      "border-radius:9px",
      "background:rgba(4,12,30,.48)",
    ].join(";");
    card.innerHTML = `<div style="font:12px Consolas,D2Coding,monospace;color:#9fe9ff">${alertSummary(alert)}</div>`;

    if (alert) {
      const actions = document.createElement("div");
      actions.style.cssText = "display:flex;gap:8px;margin-top:8px;flex-wrap:wrap";
      const simulateButton = document.createElement("button");
      simulateButton.type = "button";
      simulateButton.textContent = "설명 생성";
      const ackButton = document.createElement("button");
      ackButton.type = "button";
      ackButton.textContent = "확인 완료";
      [simulateButton, ackButton].forEach((button) => {
        button.style.cssText = [
          "cursor:pointer",
          "padding:6px 10px",
          "border-radius:8px",
          "border:1px solid rgba(0,229,255,.45)",
          "background:rgba(0,120,200,.22)",
          "color:#dff0ff",
          "font:12px Consolas,D2Coding,monospace",
        ].join(";");
      });
      simulateButton.addEventListener("click", () => simulateAlert(alert));
      ackButton.addEventListener("click", () => ackAlert(alert));
      actions.append(simulateButton, ackButton);
      card.append(actions);
    }
    renderOpsOutput(card);
    asideMeta.append(card);
  }

  function decorate() {
    decorateCityRows();
    decorateRoomPanel();
  }

  async function refreshAlerts() {
    setBridgeStatus("DB alert queue 연결 중...");
    bridgeState.enqueue = await requestJson("/alerts/enqueue", { method: "POST" });
    bridgeState.alerts = await requestJson("/heating-agent/api/alerts?status=open");
    applyAlertsToBuildings();
    render();
    const urgent = bridgeState.alerts.filter((item) => item.priority_level === "urgent").length;
    const high = bridgeState.alerts.filter((item) => item.priority_level === "high").length;
    setBridgeStatus(
      `DB alert queue 연결됨 · urgent ${urgent} / high ${high} · queued ${bridgeState.enqueue.queued_count} · existing ${bridgeState.enqueue.existing_count} · open ${bridgeState.enqueue.open_count}`,
    );
  }

  async function simulateAlert(alert) {
    setBridgeStatus(`설명 생성 중 · alert ${alert.alert_id}`);
    bridgeState.lastSimulation = await requestJson(`/alerts/${alert.alert_id}/simulate`, {
      method: "POST",
    });
    render();
    setBridgeStatus(`설명 생성 완료 · card ${bridgeState.lastSimulation.card_id}`);
  }

  async function ackAlert(alert) {
    await requestJson(`/alerts/${alert.alert_id}/ack`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ acked_by: "heating-agent-ui" }),
    });
    bridgeState.lastSimulation = null;
    await refreshAlerts();
  }

  const originalRender = render;
  render = function renderWithBridge() {
    originalRender();
    decorate();
  };

  refreshAlerts().catch((error) => {
    setBridgeStatus(`DB alert queue 연결 실패 · ${error.message}`);
  });
})();
