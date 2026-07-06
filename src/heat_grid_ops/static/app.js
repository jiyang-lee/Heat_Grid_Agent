const dbStatus = document.querySelector("#db-status");
const openaiStatus = document.querySelector("#openai-status");
const cardId = document.querySelector("#card-id");
const runButton = document.querySelector("#run-button");
const inputJson = document.querySelector("#input-json");
const summary = document.querySelector("#summary");
const actionPlan = document.querySelector("#action-plan");
const caution = document.querySelector("#caution");

let selectedCardId = "";

function setChip(element, value) {
  element.textContent = value;
  element.className = "chip";
  if (value === "connected" || value === "configured") {
    element.classList.add("success");
    return;
  }
  if (value === "unavailable" || value === "missing_key") {
    element.classList.add("warning");
    return;
  }
  element.classList.add("error");
}

async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

async function loadStatus() {
  const health = await getJson("/api/health");
  setChip(dbStatus, health.database);
  setChip(openaiStatus, health.openai);
  const cards = await getJson("/api/cards");
  selectedCardId = cards[0];
  cardId.textContent = selectedCardId;
}

async function runSimulation() {
  runButton.disabled = true;
  runButton.textContent = "실행 중";
  try {
    const result = await getJson(`/api/simulate/${selectedCardId}`, { method: "POST" });
    inputJson.textContent = JSON.stringify(result.ops_input, null, 2);
    summary.textContent = result.ops_output.summary;
    actionPlan.textContent = result.ops_output.action_plan;
    caution.textContent = result.ops_output.caution;
  } catch (error) {
    caution.textContent = error.message;
  } finally {
    runButton.disabled = false;
    runButton.textContent = "카드 1건 실행";
  }
}

runButton.addEventListener("click", runSimulation);
loadStatus().catch((error) => {
  setChip(dbStatus, "error");
  setChip(openaiStatus, "error");
  caution.textContent = error.message;
});
