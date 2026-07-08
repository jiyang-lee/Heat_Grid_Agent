const cardSelect = document.querySelector("#cardSelect");
const cardSearch = document.querySelector("#cardSearch");
const priorityFilter = document.querySelector("#priorityFilter");
const cardCount = document.querySelector("#cardCount");
const activeFilter = document.querySelector("#activeFilter");
const runButton = document.querySelector("#runButton");
const traceList = document.querySelector("#traceList");
const runState = document.querySelector("#runState");
const inputStatus = document.querySelector("#inputStatus");
const openaiStatus = document.querySelector("#openaiStatus");
const agentMode = document.querySelector("#agentMode");
const modelEvidence = document.querySelector("#modelEvidence");
const cardSummary = document.querySelector("#cardSummary");
const summary = document.querySelector("#summary");
const actionPlan = document.querySelector("#actionPlan");
const caution = document.querySelector("#caution");
const tokenUsage = document.querySelector("#tokenUsage");
const tokenTotal = document.querySelector("#tokenTotal");
const costTotal = document.querySelector("#costTotal");

let cards = [];
let stream = null;

function setStatus(element, text, className = "") {
  element.textContent = text;
  element.className = `status ${className}`.trim();
}

function addTrace(type, message) {
  const item = document.createElement("li");
  item.className = "trace-item";
  item.innerHTML = `<span class="trace-type"></span><span class="trace-message"></span>`;
  item.querySelector(".trace-type").textContent = type;
  item.querySelector(".trace-message").textContent = message;
  traceList.append(item);
  traceList.scrollTop = traceList.scrollHeight;
}

function toNumberOrPlaceholder(value, fallback = "-") {
  return value === null || value === undefined || Number.isNaN(value)
    ? fallback
    : value;
}

function cardLabel(card) {
  const priorityText =
    card.priority_level ? ` / ${card.priority_level}` : "";
  const scoreText =
    card.priority_score === null || card.priority_score === undefined
      ? "score:-"
      : `score:${toFixedSafe(card.priority_score)}`;
  return `${card.card_id} | ${card.manufacturer_id} #${card.substation_id}${priorityText} (${scoreText})`;
}

function toFixedSafe(value, digits = 2) {
  const num = Number(value);
  return Number.isNaN(num) ? "-" : num.toFixed(digits);
}

function updateCardSummary(selectedCard) {
  if (!selectedCard) {
    cardSummary.textContent = "카드를 선택해 주세요.";
    return;
  }

  cardSummary.textContent =
    `${selectedCard.manufacturer_id}/${selectedCard.substation_id} ` +
    `우선순위 ${toNumberOrPlaceholder(
      selectedCard.priority_level,
      "미지정",
    )}, 모델 점수 ${toNumberOrPlaceholder(
      selectedCard.priority_score,
      "0",
    )}, 권장점수 가중치 cb=${toNumberOrPlaceholder(
      selectedCard.current_best_weight,
    )}, m1=${toNumberOrPlaceholder(selectedCard.m1_specialist_weight, "-")}, ` +
    `리뷰필요=${selectedCard.review_required ? "있음" : "없음"}`;
}

async function fetchCards() {
  const params = new URLSearchParams();
  if (cardSearch.value.trim()) {
    params.set("search", cardSearch.value.trim());
  }
  if (priorityFilter.value) {
    params.set("priority_level", priorityFilter.value);
  }
  const query = params.toString();
  const response = await fetch(`/cards${query ? `?${query}` : ""}`);
  cards = await response.json();
  return cards;
}

function renderCardOptions() {
  const hasCards = cards.length > 0;
  cardSelect.replaceChildren();

  if (!hasCards) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "표시할 카드가 없습니다.";
    option.disabled = true;
    cardSelect.append(option);
    runButton.disabled = true;
    cardSummary.textContent = "조건을 바꾸고 다시 조회하세요.";
    modelEvidence.textContent = "카드가 없습니다.";
    cardCount.textContent = "0";
    return;
  }

  const levels = new Set();
  const options = cards.map((card) => {
    const option = document.createElement("option");
    option.value = card.card_id;
    option.textContent = cardLabel(card);
    levels.add(card.priority_level || "미지정");
    return option;
  });

  cardSelect.append(...options);
  runButton.disabled = false;
  cardCount.textContent = String(cards.length);

  const selectedValue = cardSelect.value || options[0]?.value;
  cardSelect.value = selectedValue;
  updateActiveFilterLabel();
  loadSelectedCardEvidence();
}

function updateActiveFilterLabel() {
  const level = priorityFilter.value || "전체";
  const search = cardSearch.value.trim() || "없음";
  activeFilter.textContent = `${level} / ${search}`;
}

function populatePriorityFilter() {
  const levels = new Set([""]);
  cards.forEach((card) => levels.add(card.priority_level || ""));
  const preservedValue = priorityFilter.value;
  priorityFilter.replaceChildren(...Array.from(levels).map((level) => {
    const option = document.createElement("option");
    option.value = level;
    option.textContent = level || "전체";
    return option;
  }));
  priorityFilter.value = preservedValue && [...priorityFilter.options].some((o) => o.value === preservedValue)
    ? preservedValue
    : "";
}

async function loadSelectedCardEvidence() {
  if (!cardSelect.value) {
    modelEvidence.textContent = "카드를 선택해 주세요.";
    return;
  }

  try {
    const response = await fetch(`/cards/${cardSelect.value}/evidence`);
    const payload = await response.json();
    const data = payload.data || {};
    const priority = data.priority_context || {};
    const card = priority.card || {};
    const explain = priority.explanation || {};
    const source = data.raw_context?.window || {};
    const currentBest = data.raw_context?.current_best_sensor_values || {};
    const m1 = data.raw_context?.m1_specialist_features || {};
    const evidenceLines = [
      `Window: ${source.manufacturer_id || "-"} / ${source.substation_id || "-"} (start ${source.window_start || "-"}`,
      `Priority: ${card.priority_level || "-"} / score ${card.priority_score ?? "-"}`,
      `이유: ${explain.why_reason || "-"}`,
      `권고: ${explain.recommended_action || "-"}`,
      `Current-best: n=${currentBest.top_n || 0}, M1: n=${m1.feature_count || 0}`,
    ];
    modelEvidence.textContent = evidenceLines.join(" | ");

    const selectedCard = cards.find((item) => item.card_id === cardSelect.value);
    updateCardSummary(selectedCard);
  } catch (error) {
    addTrace("evidence", `근거 조회 실패: ${error.message}`);
    modelEvidence.textContent = "근거 조회에 실패했습니다.";
  }
}

async function loadInitialState() {
  const [healthResponse, initialCards] = await Promise.all([fetch("/health"), fetchCards()]);
  const health = await healthResponse.json();
  setStatus(inputStatus, `입력 ${health.input}`, "ok");
  setStatus(
    openaiStatus,
    `LLM ${health.openai}`,
    health.openai === "configured" ? "ok" : "warn",
  );

  cards = initialCards;
  populatePriorityFilter();
  renderCardOptions();
}

function runSimulation() {
  if (stream) {
    stream.close();
  }
  traceList.replaceChildren();
  runButton.disabled = true;
  tokenTotal.textContent = "0";
  costTotal.textContent = "$0.000000";
  tokenUsage.textContent = "실행 중입니다.";
  setStatus(runState, "실행 중", "ok");
  setStatus(agentMode, "stream", "ok");
  addTrace("ui", "브라우저가 PostgreSQL v2 서버 스트림에 연결");

  stream = new EventSource(`/simulate-stream/${cardSelect.value}`);
  stream.onmessage = (event) => {
    const data = JSON.parse(event.data);
    addTrace(data.type, data.message);
    if (data.type === "token") {
      renderTokenUsage(data.payload);
    }
    if (data.type === "final") {
      summary.textContent = data.payload.ops_output.summary;
      actionPlan.textContent = data.payload.ops_output.action_plan;
      caution.textContent = data.payload.ops_output.caution;
      renderTokenUsage(data.payload.token_usage);
      setStatus(runState, "완료", "ok");
      setStatus(agentMode, "done", "ok");
      runButton.disabled = false;
      stream.close();
    }
  };
  stream.onerror = () => {
    addTrace("error", "스트림 연결이 종료됐습니다.");
    setStatus(runState, "확인 필요", "warn");
    runButton.disabled = false;
    stream.close();
  };
}

function renderTokenUsage(usage) {
  const cost = usage.cost_estimate;
  const totalCost = cost?.total_cost_usd || 0;
  tokenTotal.textContent = String(usage.total_tokens || 0);
  costTotal.textContent = formatUsd(totalCost);
  tokenUsage.textContent =
    `모델 호출 ${usage.model_calls}회, 입력 ${usage.input_tokens} tokens, ` +
    `캐시 입력 ${usage.cached_input_tokens || 0} tokens, ` +
    `출력 ${usage.output_tokens} tokens, 전체 ${usage.total_tokens} tokens, ` +
    `예상 비용 ${formatUsd(totalCost)} ` +
    `(입력 $${cost?.input_usd_per_1m || 0}/1M, ` +
    `캐시 입력 $${cost?.cached_input_usd_per_1m || 0}/1M, ` +
    `출력 $${cost?.output_usd_per_1m || 0}/1M), ` +
    `근거 payload ${usage.evidence_payload_chars}자`;
}

function formatUsd(value) {
  return `$${Number(value || 0).toFixed(6)}`;
}

cardSearch.addEventListener("input", async () => {
  const nextCards = await fetchCards();
  cards = nextCards;
  populatePriorityFilter();
  renderCardOptions();
});

priorityFilter.addEventListener("change", async () => {
  const nextCards = await fetchCards();
  cards = nextCards;
  renderCardOptions();
  updateActiveFilterLabel();
});

cardSelect.addEventListener("change", loadSelectedCardEvidence);
runButton.addEventListener("click", runSimulation);

loadInitialState().catch((error) => {
  addTrace("error", error.message);
  setStatus(runState, "초기화 실패", "warn");
});
