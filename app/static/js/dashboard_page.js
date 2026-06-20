// Dashboard page JS — fetches /api/dashboard, populates the summary
// tiles, and hand-rolls a 7-bar SVG sparkline.
//
// All values shown to the user are formatted by the server already;
// this module renders the strings as-given.

import { getIdToken, getReadyUser } from "./auth.js";

const TODAY_KG = "today-kg";
const TODAY_TRANSPORT = "today-transport-kg";
const TODAY_ELECTRICITY = "today-electricity-kg";
const TODAY_FOOD = "today-food-kg";
const WEEK_TOTAL = "week-total-kg";
const STREAK = "streak-days";
const LIFETIME = "lifetime-count";
const SPARKLINE = "week-sparkline";

function fmt(value) {
  return (Math.round(value * 100) / 100).toFixed(2);
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = text;
  }
}

function renderSparkline(weekByDay) {
  const slot = document.getElementById(SPARKLINE);
  if (!slot) {
    return;
  }
  slot.replaceChildren();
  const max = Math.max(1e-6, ...weekByDay.map((d) => d.total_kg));
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 140 60");
  svg.setAttribute("class", "h-full w-full");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Daily emissions for the last 7 days");
  weekByDay.forEach((day, i) => {
    const x = 4 + i * 19;
    const h = (day.total_kg / max) * 48;
    const y = 56 - h;
    const rect = document.createElementNS(ns, "rect");
    rect.setAttribute("x", String(x));
    rect.setAttribute("y", String(y));
    rect.setAttribute("width", "14");
    rect.setAttribute("height", String(h));
    rect.setAttribute("rx", "2");
    rect.setAttribute("fill", "#059669");
    const title = document.createElementNS(ns, "title");
    title.textContent = day.date_ist + ": " + fmt(day.total_kg) + " kg CO2e";
    rect.appendChild(title);
    svg.appendChild(rect);
  });
  slot.appendChild(svg);
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
  const resp = await fetch("/api/dashboard", {
    headers: { Accept: "application/json", Authorization: "Bearer " + token },
  });
  if (resp.status === 401) {
    window.location.assign("/");
    return;
  }
  if (!resp.ok) {
    console.error("dashboard fetch failed", resp.status);
    return;
  }
  const data = await resp.json();
  setText(TODAY_KG, fmt(data.today_kg));
  setText(TODAY_TRANSPORT, fmt(data.today_by_type.transport_kg));
  setText(TODAY_ELECTRICITY, fmt(data.today_by_type.electricity_kg));
  setText(TODAY_FOOD, fmt(data.today_by_type.food_kg));
  setText(WEEK_TOTAL, fmt(data.week_total_kg));
  setText(STREAK, data.streak_days + " day streak");
  setText(LIFETIME, data.lifetime_activity_count + " logged");
  renderSparkline(data.week_by_day);
}

load().catch((err) => console.error("dashboard load failed", err));
