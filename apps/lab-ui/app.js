const fallbackRun = {
  run_id: "lab_text_to_sql_spider_proof",
  title: "Text-to-SQL Small Model Lab",
  user_prompt: "fine tune a 4B model for text-to-sql",
  thesis: "A small local model can become a useful specialist when data quality, evals, and promotion gates are the product.",
  status: "complete",
  task_type: "Text-to-SQL",
  benchmark: "Spider dev",
  target_metric: "Execution accuracy",
  headline_metrics: [
    { label: "Base", value: "40.81%", detail: "422 / 1034" },
    { label: "Fine-tune", value: "57.83%", detail: "598 / 1034", tone: "good" },
    { label: "System", value: "71.47%", detail: "result-voted", tone: "good" },
  ],
  model_candidates: [],
  artifacts: [
    {
      label: "Hugging Face model",
      uri: "https://huggingface.co/sahilsangwan/qwen35-4b-text-to-sql-data-forge-lora",
      kind: "huggingface",
    },
  ],
  steps: [],
  next_loop: [],
};

const state = {
  run: window.DATA_FORGE_DEMO_RUN || fallbackRun,
  approved: new Set(),
  live: false,
  busy: false,
  currentRunId: null,
  view: "landing",
};

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function currentStepIndex() {
  const steps = state.run.steps || [];
  const index = Math.max(1, Math.min(state.visibleStepIndex || 1, steps.length || 1));
  return index;
}

function activeStep() {
  const steps = state.run.steps || [];
  return steps[currentStepIndex() - 1] || null;
}

function statusForStep(step, index) {
  if (!step) return "waiting";
  if (step.approval && !state.approved.has(step.approval.gate_id)) return "needs_approval";
  if (index + 1 === currentStepIndex() && step.status === "waiting") return "ready";
  return step.status === "needs_approval" ? "complete" : step.status;
}

function importantArtifacts() {
  const artifacts = state.run.artifacts || [];
  const packageArtifact = artifacts.find((artifact) => artifact.label === "Checkpoint package");
  const promotion = artifacts.find((artifact) => artifact.label === "Promotion decision");
  const checkpoint = artifacts.find((artifact) => artifact.label === "Checkpoint contract");
  const prioritized = [packageArtifact, promotion, checkpoint].filter(Boolean);
  const fallback = artifacts.slice(-3).reverse();
  return prioritized.length ? prioritized : fallback;
}

function artifactHref(artifact) {
  if (artifact.uri.startsWith("http")) return artifact.uri;
  return state.live ? `/artifacts/${artifact.uri}` : `../../${artifact.uri}`;
}

function renderMetrics(metrics) {
  if (!metrics || metrics.length === 0) return "";
  return metrics
    .slice(0, 4)
    .map(
      (metric) => `
        <div class="metric-pill ${metric.tone || ""}">
          <span>${escapeHtml(metric.label)}</span>
          <strong>${escapeHtml(metric.value)}</strong>
        </div>
      `,
    )
    .join("");
}

function renderApproval(step) {
  if (!step?.approval || state.approved.has(step.approval.gate_id)) {
    $("approvalBlock").classList.add("hidden");
    $("approvalBlock").innerHTML = "";
    return;
  }
  $("approvalBlock").classList.remove("hidden");
  $("approvalBlock").innerHTML = `
    <p>${escapeHtml(step.approval.prompt)}</p>
    <div class="approval-actions">
      ${step.approval.options
        .map((option, index) => {
          const primary = option === step.approval.recommended || index === 0;
          return `<button class="${primary ? "primary-action" : "secondary-action"}" data-approve="${escapeHtml(
            step.approval.gate_id,
          )}">${escapeHtml(option)}</button>`;
        })
        .join("")}
    </div>
  `;
  document.querySelectorAll("[data-approve]").forEach((button) => {
    button.addEventListener("click", () => approveGate(button.dataset.approve, button.textContent.trim()));
  });
}

function renderRunNextButton(step) {
  const needsApproval = step?.approval && !state.approved.has(step.approval.gate_id);
  const runnable = Boolean(
    state.live &&
      state.currentRunId &&
      step &&
      !needsApproval &&
      ["waiting", "failed"].includes(step.status),
  );
  const button = $("runNextButton");
  button.disabled = state.busy || !runnable;
  if (state.busy) button.textContent = "Running";
  else if (!state.live) button.textContent = "Live server needed";
  else if (!step) button.textContent = "No step";
  else if (needsApproval) button.textContent = "Approve decision";
  else if (step.status === "complete") button.textContent = "Complete";
  else if (step.status === "blocked") button.textContent = "Blocked";
  else button.textContent = `Run ${step.title}`;
}

function renderPlan() {
  const steps = state.run.steps || [];
  $("steps").innerHTML = steps
    .map((step, index) => {
      const status = statusForStep(step, index);
      const active = index + 1 === currentStepIndex();
      return `
        <li class="plan-row ${active ? "active" : ""} ${status}">
          <div class="status-dot"></div>
          <div class="plan-copy">
            <div class="plan-title">
              <span>${escapeHtml(step.title)}</span>
              <small>${escapeHtml(status.replace("_", " "))}</small>
            </div>
            <p>${active ? escapeHtml(step.summary) : ""}</p>
          </div>
        </li>
      `;
    })
    .join("");
}

function renderArtifacts() {
  const artifacts = importantArtifacts();
  if (!artifacts.length || state.view === "landing") {
    $("evidenceDock").classList.add("hidden");
    $("artifactList").innerHTML = "";
    return;
  }
  $("evidenceDock").classList.remove("hidden");
  $("artifactList").innerHTML = artifacts
    .map((artifact) => {
      const external = artifact.uri.startsWith("http");
      return `
        <a class="artifact-link" href="${escapeHtml(artifactHref(artifact))}" ${
          external ? 'target="_blank" rel="noreferrer"' : ""
        }>
          <span>${escapeHtml(artifact.kind)}</span>
          <strong>${escapeHtml(artifact.label)}</strong>
        </a>
      `;
    })
    .join("");
}

function render() {
  const landing = $("landingView");
  const runView = $("runView");
  landing.classList.toggle("hidden", state.view !== "landing");
  runView.classList.toggle("hidden", state.view !== "run");

  if (state.view === "landing") return;

  const step = activeStep();
  const steps = state.run.steps || [];
  $("runTaskType").textContent = state.run.task_type || "Data Forge Lab";
  $("runTitle").textContent = state.run.title || "Data Forge Lab";
  $("runStatus").textContent = state.live ? `live ${state.run.status}` : state.run.status;
  $("loopCount").textContent = `${Math.min(currentStepIndex(), steps.length)}/${steps.length}`;
  $("activeAgent").textContent = step?.agent || "Agent";
  $("activeTitle").textContent = step?.title || state.run.title;
  $("activeSummary").textContent = step?.summary || state.run.thesis || "";
  $("activeStepMarker").className = `step-marker ${step ? statusForStep(step, currentStepIndex() - 1) : ""}`;
  $("activeMetrics").innerHTML = renderMetrics(step?.metrics || []);
  renderApproval(step);
  renderRunNextButton(step);
  renderPlan();
  renderArtifacts();
}

function applyEnvelope(envelope) {
  state.run = envelope.run;
  state.currentRunId = envelope.run.run_id;
  state.visibleStepIndex = envelope.state?.current_step_index ?? 1;
  state.approved = new Set(Object.keys(envelope.state?.approved_gates || {}));
  state.view = "run";
  render();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  return response.json();
}

async function approveGate(gateId, choice) {
  if (state.live && state.currentRunId) {
    state.busy = true;
    render();
    try {
      const envelope = await api(`/api/runs/${encodeURIComponent(state.currentRunId)}/approve`, {
        method: "POST",
        body: JSON.stringify({ gate_id: gateId, choice }),
      });
      applyEnvelope(envelope);
    } finally {
      state.busy = false;
      render();
    }
    return;
  }
  state.approved.add(gateId);
  render();
}

async function runNextStep() {
  if (!state.live || !state.currentRunId || state.busy) return;
  state.busy = true;
  render();
  try {
    const envelope = await api(`/api/runs/${encodeURIComponent(state.currentRunId)}/run-next`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    applyEnvelope(envelope);
  } finally {
    state.busy = false;
    render();
  }
}

function resizePrompt() {
  const input = $("promptInput");
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
}

async function startRun(event) {
  event.preventDefault();
  const prompt = $("promptInput").value.trim();
  if (state.live) {
    state.busy = true;
    try {
      const envelope = await api("/api/runs", {
        method: "POST",
        body: JSON.stringify({ prompt: prompt || "fine tune a small model for tool calling" }),
      });
      applyEnvelope(envelope);
    } finally {
      state.busy = false;
      render();
    }
    return;
  }
  state.run = { ...state.run, user_prompt: prompt || state.run.user_prompt };
  state.visibleStepIndex = Math.min(1, (state.run.steps || []).length || 1);
  state.currentRunId = state.run.run_id;
  state.view = "run";
  render();
}

async function loadRun() {
  try {
    const health = await fetch("/api/health", { cache: "no-store" });
    state.live = health.ok;
  } catch {
    state.live = false;
  }
  try {
    if (!window.DATA_FORGE_DEMO_RUN) {
      const response = await fetch("./demo-run.json", { cache: "no-store" });
      if (response.ok) state.run = await response.json();
    }
  } catch {
    state.run = fallbackRun;
  }
  $("promptInput").value = "fine tune a small model for tool calling";
  resizePrompt();
  render();
}

$("promptForm").addEventListener("submit", startRun);
$("runNextButton").addEventListener("click", runNextStep);
$("backButton").addEventListener("click", () => {
  state.view = "landing";
  render();
});
$("promptInput").addEventListener("input", resizePrompt);
$("promptInput").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    $("promptForm").requestSubmit();
  }
});

loadRun();
