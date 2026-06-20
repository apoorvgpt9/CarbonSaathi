// Recommendations page JS — fetches /api/recommendations on load and
// renders the cards.  Accept clicks hit /api/recommendations/{id}/accept
// (POST) and swap the button for the Accepted badge.  Card markup mirrors
// app/templates/partials/recommendation_card.html.

import { getIdToken, getReadyUser } from "./auth.js";

const list = document.getElementById("recommendations-list");
const empty = document.getElementById("recs-empty");

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

async function load() {
  const user = await getReadyUser();
  if (!user) {
    window.location.assign("/");
    return;
  }
  let token;
  try {
    token = await getIdToken();
  } catch (_err) {
    window.location.assign("/");
    return;
  }
  const resp = await fetch("/api/recommendations", {
    headers: { Accept: "application/json", Authorization: "Bearer " + token },
  });
  if (resp.status === 401) {
    window.location.assign("/");
    return;
  }
  if (!resp.ok) {
    console.error("recommendations fetch failed", resp.status);
    return;
  }
  const body = await resp.json();
  const items = body.items || [];
  if (!list) return;
  if (items.length === 0) {
    list.innerHTML = "";
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  list.innerHTML = items.map(renderRecCard).join("");
}

if (list) {
  list.addEventListener("click", async (event) => {
    const btn = event.target.closest('[data-action="accept-rec"]');
    if (!btn) return;
    const recId = btn.getAttribute("data-rec-id");
    if (!recId) return;
    btn.disabled = true;
    try {
      const token = await getIdToken();
      const resp = await fetch(`/api/recommendations/${encodeURIComponent(recId)}/accept`, {
        method: "POST",
        headers: { Authorization: "Bearer " + token, Accept: "application/json" },
      });
      if (resp.ok) {
        const slot = btn.parentElement;
        if (slot) {
          slot.innerHTML = `<span class="inline-flex items-center text-sm font-medium text-emerald-700">✓ Accepted</span>`;
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

load().catch((err) => console.error("recommendations load failed", err));
