// Insights page JS — wires the "Generate insights" button to the
// hand-rolled SSE consumer.  Live reasoning is appended to
// #reasoning-stream; the final `done` event populates #insights-list and
// #recommendations-list with cards that mirror the corresponding
// partial templates.

import { streamInsights } from "./sse_consumer.js";
import { getReadyUser } from "./auth.js";

const generateBtn = document.querySelector('[data-action="stream-insights"]');
const stopBtn = document.querySelector('[data-action="stop-stream"]');
const streamRoot = document.getElementById("reasoning-stream");
const insightsList = document.getElementById("insights-list");
const recsList = document.getElementById("recommendations-list");
const errorBox = document.getElementById("stream-error");

let abortController = null;
const phaseBlocks = new Map(); // phase -> { headerEl, listEl }

(async function gate() {
  const user = await getReadyUser();
  if (!user) {
    window.location.assign("/");
  }
})();

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function fmt(value) {
  return (Math.round(value * 100) / 100).toFixed(2);
}

function resetStream() {
  if (streamRoot) {
    streamRoot.replaceChildren();
  }
  phaseBlocks.clear();
  if (errorBox) {
    errorBox.classList.add("hidden");
    errorBox.textContent = "";
  }
}

function ensurePhaseBlock(phase) {
  if (phaseBlocks.has(phase)) {
    return phaseBlocks.get(phase);
  }
  const section = document.createElement("section");
  section.className = "rounded-lg border border-slate-200 bg-white p-4 shadow-sm fade-in";
  section.dataset.phase = phase;

  const header = document.createElement("h3");
  header.className = "text-sm font-semibold text-slate-700";
  header.textContent = phase + " · thinking…";
  section.appendChild(header);

  const list = document.createElement("ol");
  list.className = "mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-700";
  section.appendChild(list);

  streamRoot.appendChild(section);
  const block = { headerEl: header, listEl: list };
  phaseBlocks.set(phase, block);
  return block;
}

function renderInsightCard(insight) {
  const steps = insight.agent_reasoning && insight.agent_reasoning.reasoning_steps
    ? insight.agent_reasoning.reasoning_steps
    : [];
  const reasoning = steps.length
    ? `<details class="mt-3 text-xs text-slate-600">
        <summary class="cursor-pointer font-medium text-slate-700">
          Analyst reasoning (${steps.length} steps)
        </summary>
        <ol class="mt-2 list-decimal space-y-1 pl-5">
          ${steps.map((s) => `<li class="reasoning-step">${escapeHtml(s)}</li>`).join("")}
        </ol>
      </details>`
    : "";
  const supportCount = (insight.supporting_activity_ids || []).length;
  const support = supportCount
    ? `<p class="mt-2 text-xs text-slate-500">Based on ${supportCount} recent ${
        supportCount === 1 ? "activity" : "activities"
      }.</p>`
    : "";
  return `<li class="insight-card rounded-lg border border-slate-200 bg-white p-4 shadow-sm fade-in">
    <div class="flex items-baseline justify-between">
      <h3 class="text-sm font-semibold text-slate-900">${escapeHtml(insight.title)}</h3>
      <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">${escapeHtml(insight.type)}</span>
    </div>
    <p class="mt-2 text-sm text-slate-700">${escapeHtml(insight.description)}</p>
    ${support}
    ${reasoning}
  </li>`;
}

function renderRecCard(rec) {
  const steps = rec.agent_reasoning && rec.agent_reasoning.reasoning_steps
    ? rec.agent_reasoning.reasoning_steps
    : [];
  const reasoning = steps.length
    ? `<details class="mt-3 text-xs text-slate-600">
        <summary class="cursor-pointer font-medium text-slate-700">
          Coach reasoning (${steps.length} steps)
        </summary>
        <ol class="mt-2 list-decimal space-y-1 pl-5">
          ${steps.map((s) => `<li class="reasoning-step">${escapeHtml(s)}</li>`).join("")}
        </ol>
      </details>`
    : "";
  const action = rec.accepted
    ? `<span class="inline-flex items-center text-sm font-medium text-emerald-700">✓ Accepted</span>`
    : `<button type="button" data-action="accept-rec" data-rec-id="${escapeHtml(rec.id)}" class="rounded-md border border-emerald-600 px-3 py-1 text-sm font-medium text-emerald-700 hover:bg-emerald-50 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-2">Accept</button>`;
  return `<li class="rec-card rounded-lg border border-slate-200 bg-white p-4 shadow-sm fade-in" data-rec-id="${escapeHtml(rec.id)}">
    <div class="flex items-baseline justify-between">
      <h3 class="text-sm font-semibold text-slate-900">${escapeHtml(rec.title)}</h3>
      <span class="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">${escapeHtml(rec.type)} · ${escapeHtml(rec.difficulty)}</span>
    </div>
    <p class="mt-2 text-sm text-slate-700">${escapeHtml(rec.description)}</p>
    <p class="mt-2 text-xs text-slate-500">Expected saving: <span class="font-medium text-slate-700">${fmt(rec.expected_saving_kg)} kg CO₂e</span></p>
    ${reasoning}
    <div class="mt-3">${action}</div>
  </li>`;
}

function setBusy(isBusy) {
  if (generateBtn) {
    generateBtn.disabled = isBusy;
    generateBtn.classList.toggle("opacity-50", isBusy);
    generateBtn.classList.toggle("cursor-not-allowed", isBusy);
  }
  if (stopBtn) {
    stopBtn.disabled = !isBusy;
  }
}

if (generateBtn) {
  generateBtn.addEventListener("click", async () => {
    resetStream();
    setBusy(true);
    abortController = new AbortController();
    await streamInsights({
      signal: abortController.signal,
      onPhaseStart(evt) {
        ensurePhaseBlock(evt.phase);
      },
      onReasoningStep(evt) {
        const block = ensurePhaseBlock(evt.phase);
        const li = document.createElement("li");
        li.className = "reasoning-step";
        li.textContent = evt.step;
        block.listEl.appendChild(li);
      },
      onPhaseComplete(evt) {
        const block = ensurePhaseBlock(evt.phase);
        const symbol =
          evt.status === "success" || evt.status === "cached" ? "✓" : "•";
        block.headerEl.textContent =
          evt.phase + " · " + symbol + " " + evt.status +
          (evt.reason ? " (" + evt.reason + ")" : "");
      },
      onDone(evt) {
        if (insightsList) {
          insightsList.innerHTML = (evt.insights || []).map(renderInsightCard).join("") ||
            `<li class="text-sm text-slate-500">No insights yet — log a few activities and try again.</li>`;
        }
        if (recsList) {
          recsList.innerHTML = (evt.recommendations || []).map(renderRecCard).join("") ||
            `<li class="text-sm text-slate-500">No recommendations yet.</li>`;
        }
        setBusy(false);
        abortController = null;
      },
      onError(err) {
        if (errorBox) {
          errorBox.textContent = "Stream failed: " + err.message;
          errorBox.classList.remove("hidden");
        }
        setBusy(false);
        abortController = null;
      },
    });
  });
}

if (stopBtn) {
  stopBtn.addEventListener("click", () => {
    if (abortController) {
      abortController.abort();
      abortController = null;
    }
    setBusy(false);
  });
}

if (recsList) {
  recsList.addEventListener("click", async (event) => {
    const btn = event.target.closest('[data-action="accept-rec"]');
    if (!btn) return;
    const recId = btn.getAttribute("data-rec-id");
    if (!recId) return;
    btn.disabled = true;
    try {
      const token = await window.csaathi.auth.getIdToken();
      const resp = await fetch(`/api/recommendations/${encodeURIComponent(recId)}/accept`, {
        method: "POST",
        headers: { Authorization: "Bearer " + token, Accept: "application/json" },
      });
      if (resp.ok) {
        const card = btn.closest(".rec-card");
        if (card) {
          const slot = btn.parentElement;
          if (slot) {
            slot.innerHTML = `<span class="inline-flex items-center text-sm font-medium text-emerald-700">✓ Accepted</span>`;
          }
        }
      } else {
        btn.disabled = false;
        console.error("accept failed", resp.status);
      }
    } catch (err) {
      btn.disabled = false;
      console.error("accept network error", err);
    }
  });
}
