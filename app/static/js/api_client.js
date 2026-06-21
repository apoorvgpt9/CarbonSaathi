// CarbonSaathi shared authenticated-fetch helper.
//
// Replaces the now-removed HTMX + htmx_bearer.js stack.  Every page module
// that calls a protected /api/* endpoint imports authedFetch from this file
// instead of attaching the Bearer header and 401-redirecting itself.
//
// Refresh-and-retry semantics (matches the htmx:responseError behaviour
// htmx_bearer.js previously provided):
//   * On the first 401, force a token refresh and retry the request once.
//   * On the second 401, redirect to / so the user re-signs in.
//
// Network errors propagate to the caller (so pages can show
// "Network error. Please try again." inline).
//
// Relies on window.csaathi.auth.getIdToken() being populated by auth.js.

/**
 * Authenticated fetch wrapper.
 *
 * @param {string} url - Request URL.
 * @param {RequestInit} [options] - Standard fetch options.  Any caller-supplied
 *   `headers` are merged with the injected Authorization header.
 * @returns {Promise<Response>} The Response after at most one 401 retry.
 *   On a final 401 the page is redirected to "/" and the returned Promise
 *   never resolves (callers should not branch on its value in that case).
 */
export async function authedFetch(url, options = {}) {
  const getToken =
    window.csaathi && window.csaathi.auth && window.csaathi.auth.getIdToken;
  if (!getToken) {
    window.location.assign("/");
    return new Promise(() => {});
  }

  let token;
  try {
    token = await getToken(false);
  } catch (_err) {
    window.location.assign("/");
    return new Promise(() => {});
  }

  const resp = await fetch(url, _withAuth(options, token));
  if (resp.status !== 401) {
    return resp;
  }

  let freshToken;
  try {
    freshToken = await getToken(true);
  } catch (_err) {
    window.location.assign("/");
    return new Promise(() => {});
  }
  const retryResp = await fetch(url, _withAuth(options, freshToken));
  if (retryResp.status === 401) {
    window.location.assign("/");
    return new Promise(() => {});
  }
  return retryResp;
}

function _withAuth(options, token) {
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", "Bearer " + token);
  return { ...options, headers };
}

window.csaathi = window.csaathi || {};
window.csaathi.api = { authedFetch };
