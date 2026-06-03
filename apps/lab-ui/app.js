const fallbackRun = {
  run_id: "lab_text_to_sql_spider_proof",
  title: "Text-to-SQL Small Model Lab",
  user_prompt: "fine tune a 4B model for text-to-sql",
  thesis:
    "A small local model can become a useful specialist when the dataset factory, gates, and eval loop are engineered as the product.",
  status: "complete",
  task_type: "Text-to-SQL",
  benchmark: "Spider dev",
  target_metric: "Execution accuracy",
  headline_metrics: [
    { label: "Base Qwen3.5-4B", value: "40.81%", detail: "422 / 1034" },
    { label: "Fine-tuned LoRA", value: "57.83%", detail: "598 / 1034" },
    { label: "Result-voted system", value: "71.47%", detail: "739 / 1034", tone: "good" },
    { label: "Improvement", value: "+30.66 pts", detail: "vs base", tone: "good" },
  ],
  model_candidates: [
    {
      model_id: "Qwen/Qwen3.5-4B",
      backend: "MLX local",
      size: "4B",
      license: "open",
      local_fit: "excellent",
      rationale: "Fits a 64GB Apple Silicon machine and supports fast LoRA iteration.",
    },
  ],
  artifacts: [
    {
      label: "Hugging Face model",
      uri: "https://huggingface.co/sahilsangwan/qwen35-4b-text-to-sql-data-forge-lora",
      kind: "huggingface",
    },
    {
      label: "GitHub repo",
      uri: "https://github.com/sangwansahil/data-forge",
      kind: "github",
    },
  ],
  steps: [],
  next_loop: ["Add live runners.", "Add tool-calling as the second recipe."],
};

const state = {
  run: fallbackRun,
  visibleSteps: 0,
  approved: new Set(),
  running: false,
  live: false,
  currentRunId: null,
  busy: false,
};

const $ = (id) => document.getElementById(id);

function metricClass(metric) {
  return `metric ${metric.tone === "good" ? "good" : ""}`;
}

function renderMetrics(metrics) {
  $("headlineMetrics").innerHTML = metrics
    .map(
      (metric) => `
        <div class="${metricClass(metric)}">
          <p class="eyebrow">${metric.label}</p>
          <div class="value">${metric.value}</div>
          <div class="detail">${metric.detail || ""}</div>
        </div>
      `,
    )
    .join("");
}

function renderModels(models) {
  $("modelCandidates").innerHTML = models
    .map(
      (model) => `
        <div class="model-row">
          <strong>${model.model_id}</strong>
          <p>${model.rationale}</p>
          <div class="meta-line">
            <span class="chip">${model.backend}</span>
            <span class="chip">${model.size}</span>
            <span class="chip">${model.license}</span>
            <span class="chip good">${model.local_fit}</span>
          </div>
        </div>
      `,
    )
    .join("");
}

function renderArtifacts(artifacts) {
  $("artifactList").innerHTML = artifacts
    .map((artifact) => {
      const external = artifact.uri.startsWith("http");
      const href = external ? artifact.uri : state.live ? `/artifacts/${artifact.uri}` : `../../${artifact.uri}`;
      return `
        <a class="artifact-row" href="${href}" ${external ? 'target="_blank" rel="noreferrer"' : ""}>
          <strong>${artifact.label}</strong>
          <p>${artifact.kind}</p>
        </a>
      `;
    })
    .join("");
}

function statusForStep(step, index) {
  if (index >= state.visibleSteps) return "waiting";
  if (step.approval && !state.approved.has(step.approval.gate_id)) return "needs_approval";
  return step.status === "needs_approval" ? "complete" : step.status;
}

function renderStepMetrics(metrics) {
  if (!metrics || metrics.length === 0) return "";
  return `
    <div class="step-metrics">
      ${metrics
        .map(
          (metric) => `
            <div class="mini-metric">
              <span>${metric.label}</span>
              <strong>${metric.value}</strong>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderApproval(step) {
  if (!step.approval || state.approved.has(step.approval.gate_id)) return "";
  return `
    <div class="approval">
      <h3>${step.approval.title}</h3>
      <p>${step.approval.prompt}</p>
      <div class="approval-actions">
        ${step.approval.options
          .map((option, index) => {
            const primary = option === step.approval.recommended || index === 0;
            return `<button class="${primary ? "" : "secondary"}" data-approve="${step.approval.gate_id}">${option}</button>`;
          })
          .join("")}
      </div>
    </div>
  `;
}

function activeStep() {
  const steps = state.run.steps || [];
  return steps[Math.max(0, state.visibleSteps - 1)] || null;
}

function renderRunNextButton() {
  const button = $("runNextButton");
  if (!button) return;
  const step = activeStep();
  const needsApproval = step?.approval && !state.approved.has(step.approval.gate_id);
  const runnable = Boolean(
    state.live &&
      state.currentRunId &&
      step &&
      !needsApproval &&
      ["waiting", "failed"].includes(step.status),
  );
  button.disabled = state.busy || !runnable;
  if (state.busy) {
    button.textContent = "Running...";
  } else if (!state.live) {
    button.textContent = "Live server needed";
  } else if (!step) {
    button.textContent = "No step";
  } else if (needsApproval) {
    button.textContent = "Approval needed";
  } else if (step.status === "complete") {
    button.textContent = "Step complete";
  } else if (step.status === "blocked") {
    button.textContent = "Step blocked";
  } else {
    button.textContent = `Run ${step.title}`;
  }
}

function renderSteps() {
  const steps = state.run.steps || [];
  $("loopCount").textContent = `${Math.min(state.visibleSteps, steps.length)}/${steps.length}`;
  $("steps").innerHTML = steps
    .slice(0, state.visibleSteps)
    .map((step, index) => {
      const status = statusForStep(step, index);
      return `
        <article class="step">
          <div class="step-index">${index + 1}</div>
          <div>
            <div class="step-head">
              <div>
                <div class="agent">${step.agent}</div>
                <h3>${step.title}</h3>
              </div>
              <span class="state ${status}">${status.replace("_", " ")}</span>
            </div>
            <p>${step.summary}</p>
            <ul class="detail-list">
              ${(step.details || []).map((detail) => `<li>${detail}</li>`).join("")}
            </ul>
            ${renderStepMetrics(step.metrics)}
            ${renderApproval(step)}
          </div>
        </article>
      `;
    })
    .join("");

  document.querySelectorAll("[data-approve]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (state.live && state.currentRunId) {
        const envelope = await api(`/api/runs/${encodeURIComponent(state.currentRunId)}/approve`, {
          method: "POST",
          body: JSON.stringify({ gate_id: button.dataset.approve, choice: button.textContent.trim() }),
        });
        applyEnvelope(envelope);
        return;
      }
      state.approved.add(button.dataset.approve);
      state.running = true;
      if (state.visibleSteps === 0) state.visibleSteps = 1;
      render();
      advanceLoop();
    });
  });
}

function renderNextLoop(items) {
  $("nextLoop").innerHTML = items.map((item) => `<div class="next-item">${item}</div>`).join("");
}

function render() {
  $("runTitle").textContent = state.run.title;
  $("runThesis").textContent = state.run.thesis;
  $("runStatus").textContent = state.live ? `live ${state.run.status}` : state.running ? "running" : state.run.status;
  if (document.activeElement !== $("promptInput")) {
    $("promptInput").value = state.run.user_prompt || "";
  }
  renderMetrics(state.run.headline_metrics || []);
  renderModels(state.run.model_candidates || []);
  renderArtifacts(state.run.artifacts || []);
  renderSteps();
  renderRunNextButton();
  renderNextLoop(state.run.next_loop || []);
}

function applyEnvelope(envelope) {
  state.run = envelope.run;
  state.currentRunId = envelope.run.run_id;
  state.visibleSteps = envelope.state?.current_step_index ?? Math.min(1, (state.run.steps || []).length);
  state.approved = new Set(Object.keys(envelope.state?.approved_gates || {}));
  state.running = state.visibleSteps < (state.run.steps || []).length;
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
  } catch (error) {
    console.error(error);
    $("runStatus").textContent = "run failed";
    window.alert("The current step failed. Check the run artifacts or server logs.");
  } finally {
    state.busy = false;
    render();
  }
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

function advanceLoop() {
  if (!state.running) return;
  const steps = state.run.steps || [];
  const current = steps[state.visibleSteps - 1];
  if (current && current.approval && !state.approved.has(current.approval.gate_id)) {
    return;
  }
  if (state.visibleSteps >= steps.length) {
    state.running = false;
    render();
    return;
  }
  window.setTimeout(() => {
    state.visibleSteps += 1;
    render();
    advanceLoop();
  }, 520);
}

async function loadRun() {
  if (window.DATA_FORGE_DEMO_RUN) {
    state.run = window.DATA_FORGE_DEMO_RUN;
  }
  try {
    const health = await fetch("/api/health", { cache: "no-store" });
    if (health.ok) {
      state.live = true;
      const runs = await api("/api/runs");
      const latest = (runs.runs || []).at(-1);
      if (latest) {
        applyEnvelope(latest);
        return;
      }
    }
  } catch {
    state.live = false;
  }
  try {
    const response = await fetch("./demo-run.json", { cache: "no-store" });
    if (response.ok) state.run = await response.json();
  } catch {
    if (!window.DATA_FORGE_DEMO_RUN) state.run = fallbackRun;
  }
  state.visibleSteps = Math.min(1, (state.run.steps || []).length);
  state.currentRunId = state.run.run_id;
  render();
}

async function startRun() {
  const prompt = $("promptInput").value.trim();
  if (state.live) {
    const envelope = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({ prompt: prompt || state.run.user_prompt }),
    });
    applyEnvelope(envelope);
    return;
  }
  state.run = { ...state.run, user_prompt: prompt || state.run.user_prompt };
  state.currentRunId = state.run.run_id;
  state.visibleSteps = 1;
  state.approved = new Set();
  state.running = true;
  render();
  advanceLoop();
}

$("startButton").addEventListener("click", startRun);
$("runNextButton").addEventListener("click", runNextStep);

loadRun();
