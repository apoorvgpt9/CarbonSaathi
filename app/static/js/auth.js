// CarbonSaathi front-end Firebase bootstrap.
//
// Loaded as <script type="module"> from base.html so it executes on every
// page.  Responsibilities:
//   * Fetch the public Firebase web config from /api/auth/config.
//   * initializeApp() + getAuth() using the modular Firebase web SDK.
//   * Track the current user, expose getIdToken(forceRefresh).
//   * Wire [data-action="sign-in"] and [data-action="sign-out"] buttons
//     anywhere in the DOM.
//   * On a fresh sign-in, POST /api/auth/verify and redirect to
//     /onboarding if new OR onboarding incomplete; /dashboard otherwise.
//   * Dispatch a `csaathi:auth-change` CustomEvent on document each time
//     onAuthStateChanged fires.
//
// Other page modules import { getReadyUser, getIdToken } from this file.
// `getReadyUser` resolves to the current User (or null) after the FIRST
// onAuthStateChanged fires, so pages don't race the Firebase restore.

import {
  initializeApp,
} from "https://www.gstatic.com/firebasejs/10.13.0/firebase-app.js";
import {
  getAuth,
  GoogleAuthProvider,
  signInWithPopup,
  onAuthStateChanged,
  signOut,
} from "https://www.gstatic.com/firebasejs/10.13.0/firebase-auth.js";

const configResp = await fetch("/api/auth/config", {
  headers: { Accept: "application/json" },
});
if (!configResp.ok) {
  throw new Error("auth.js: failed to load /api/auth/config: " + configResp.status);
}
const firebaseConfig = await configResp.json();

const firebaseApp = initializeApp(firebaseConfig);
const auth = getAuth(firebaseApp);

let currentUser = null;
let readyResolved = false;
let resolveReady;
const ready = new Promise((res) => {
  resolveReady = res;
});

onAuthStateChanged(auth, (user) => {
  currentUser = user;
  if (!readyResolved) {
    readyResolved = true;
    resolveReady(user);
  }
  document.dispatchEvent(
    new CustomEvent("csaathi:auth-change", { detail: { user } }),
  );
});

/**
 * Resolve to the current Firebase User (or null) after the first
 * onAuthStateChanged callback fires.  Use this in page modules before
 * issuing any API call so you don't race the Firebase restore.
 */
export async function getReadyUser() {
  return ready;
}

/**
 * Return a fresh Firebase ID token for the current user.
 *
 * @param {boolean} forceRefresh - When true, force a network round-trip
 *   to refresh the token (used after a 401 retry).
 * @returns {Promise<string>}
 */
export async function getIdToken(forceRefresh = false) {
  if (!currentUser) {
    await ready;
  }
  if (!currentUser) {
    throw new Error("Not signed in");
  }
  return currentUser.getIdToken(forceRefresh);
}

/**
 * Trigger the Google sign-in popup, POST /api/auth/verify, then route
 * to /onboarding (new user) or /dashboard (returning user).
 */
export async function signInWithGoogle() {
  const provider = new GoogleAuthProvider();
  const credential = await signInWithPopup(auth, provider);
  const token = await credential.user.getIdToken();
  const verifyResp = await fetch("/api/auth/verify", {
    method: "POST",
    headers: {
      Authorization: "Bearer " + token,
      Accept: "application/json",
    },
  });
  if (!verifyResp.ok) {
    throw new Error("auth.js: /api/auth/verify failed: " + verifyResp.status);
  }
  const body = await verifyResp.json();
  if (body.is_new || !body.user.onboarding_complete) {
    window.location.assign("/onboarding");
  } else {
    window.location.assign("/dashboard");
  }
}

/** Sign out the current user and redirect to the sign-in landing page. */
export async function signOutUser() {
  await signOut(auth);
  window.location.assign("/");
}

window.csaathi = window.csaathi || {};
window.csaathi.auth = {
  getReadyUser,
  getIdToken,
  signInWithGoogle,
  signOutUser,
};

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) {
    return;
  }
  const signInBtn = target.closest('[data-action="sign-in"]');
  if (signInBtn) {
    event.preventDefault();
    signInWithGoogle().catch((err) => {
      console.error("sign-in failed", err);
      const slot = document.getElementById("sign-in-error");
      if (slot) {
        slot.textContent = "Sign-in failed. Please try again.";
        slot.classList.remove("hidden");
      }
    });
    return;
  }
  const signOutBtn = target.closest('[data-action="sign-out"]');
  if (signOutBtn) {
    event.preventDefault();
    signOutUser().catch((err) => console.error("sign-out failed", err));
  }
});
