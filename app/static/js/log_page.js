// Activity-log page JS — intercepts the form submit, POSTs JSON to
// /api/activities, and renders the resulting card (or error) into
// #activity-result.  Card markup mirrors app/templates/partials/activity_card.html.

import { authedFetch } from "./api_client.js";
import { getReadyUser } from "./auth.js";

const form = document.getElementById("log-form");
const result = document.getElementById("activity-result");

(async function gate() {
  const user = await getReadyUser();
  if (!user) {
    window.location.assign("/");
  }
})();

function fmt(value) {
  return (Math.round(value * 100) / 100).toFixed(2);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderActivityCard(activity, agentReasoning) {
  const steps = agentReasoning && agentReasoning.reasoning_steps
    ? agentReasoning.reasoning_steps
    : [];
  const details = steps.length
    ? `<details class="mt-3 text-xs text-slate-600">
        <summary class="cursor-pointer font-medium text-slate-700">
          How the agent reasoned (${steps.length} steps)
        </summary>
        <ol class="mt-2 list-decimal space-y-1 pl-5">
          ${steps.map((s) => `<li class="reasoning-step">${escapeHtml(s)}</li>`).join("")}
        </ol>
      </details>`
    : "";
  return `<article class="activity-card rounded-lg border border-slate-200 bg-white p-4 shadow-sm fade-in">
    <header class="flex items-baseline justify-between">
      <h3 class="text-sm font-semibold uppercase tracking-wide text-slate-500">
        ${escapeHtml(activity.type)}
      </h3>
      <p class="text-lg font-semibold text-slate-900">
        ${fmt(activity.emission_kg_co2e)} kg CO₂e
      </p>
    </header>
    <p class="mt-2 text-sm text-slate-700">${escapeHtml(activity.raw_input)}</p>
    <dl class="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
      <div>
        <dt class="font-medium">Confidence</dt>
        <dd>${escapeHtml(activity.confidence)}</dd>
      </div>
      <div>
        <dt class="font-medium">Factor source</dt>
        <dd>${escapeHtml(activity.emission_factor_source)}</dd>
      </div>
    </dl>
    ${details}
  </article>`;
}

function renderError(message, klass) {
  return `<p class="${klass}">${escapeHtml(message)}</p>`;
}

if (form && result) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    result.innerHTML = renderError("Logging…", "text-sm text-slate-500");
    const raw = String(new FormData(form).get("raw_input") || "").trim();
    if (!raw) {
      result.innerHTML = renderError("Please enter an activity.", "text-sm text-red-600");
      return;
    }
    let resp;
    try {
      resp = await authedFetch("/api/activities", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ raw_input: raw }),
      });
    } catch (err) {
      console.error("log network error", err);
      result.innerHTML = renderError("Network error. Please try again.", "text-sm text-red-600");
      return;
    }
    if (resp.status === 201) {
      const body = await resp.json();
      result.innerHTML = renderActivityCard(body.activity, body.agent_reasoning);
      form.reset();
      return;
    }
    if (resp.status === 400) {
      const body = await resp.json().catch(() => ({}));
      const reason = body && body.reason ? body.reason : "Could not log activity.";
      result.innerHTML = renderError("Rejected: " + reason, "text-sm text-amber-700");
      return;
    }
    const body = await resp.json().catch(() => ({}));
    const detail = body && body.detail ? body.detail : "Server error.";
    result.innerHTML = renderError(detail, "text-sm text-red-600");
  });
}
