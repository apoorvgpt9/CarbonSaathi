// Onboarding page JS — intercepts the form submit, builds the nested JSON
// shape that POST /api/users/onboarding expects, and on success routes to
// /dashboard.
//
// We can't use plain HTMX hx-post here because the endpoint requires a
// nested `{state, home_profile: {bhk, has_ac, fridge_class, dietary}}`
// body, which form-encoding can't express without a wrapper.

import { getIdToken, getReadyUser } from "./auth.js";

const form = document.getElementById("onboarding-form");
const result = document.getElementById("onboarding-result");

(async function gate() {
  const user = await getReadyUser();
  if (!user) {
    window.location.assign("/");
  }
})();

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (result) {
      result.textContent = "Saving…";
      result.className = "text-sm text-slate-500";
    }
    const data = new FormData(form);
    const payload = {
      state: data.get("state"),
      home_profile: {
        bhk: Number(data.get("bhk")),
        has_ac: data.get("has_ac") === "on",
        fridge_class: data.get("fridge_class"),
        dietary: data.get("dietary"),
      },
    };

    let token;
    try {
      token = await getIdToken();
    } catch (_err) {
      window.location.assign("/");
      return;
    }

    let resp;
    try {
      resp = await fetch("/api/users/onboarding", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          Authorization: "Bearer " + token,
        },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      console.error("onboarding network error", err);
      if (result) {
        result.textContent = "Network error. Please try again.";
        result.className = "text-sm text-red-600";
      }
      return;
    }

    if (resp.status === 401) {
      window.location.assign("/");
      return;
    }
    if (!resp.ok) {
      let detail = "Save failed (" + resp.status + ")";
      try {
        const body = await resp.json();
        if (body && body.detail) {
          detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        }
      } catch (_err) {
        // fall through with default message
      }
      if (result) {
        result.textContent = detail;
        result.className = "text-sm text-red-600";
      }
      return;
    }
    window.location.assign("/dashboard");
  });
}
