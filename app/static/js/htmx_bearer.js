// HTMX bearer-token bridge.
//
// Classic <script defer> (NOT a module) so it can register the
// htmx:configRequest handler before HTMX dispatches its first request.
// Module scripts are deferred *and* parsed asynchronously, which can race
// HTMX initialization on slow connections.
//
// Responsibilities:
//   * On every HTMX request, inject Authorization: Bearer <token>.
//   * On a 401 response, force a token refresh and retry exactly once.
//     On a second 401, redirect to / so the user re-signs in.
//
// Relies on window.csaathi.auth being populated by auth.js.

(function () {
  "use strict";

  function whenAuthReady() {
    if (window.csaathi && window.csaathi.auth && window.csaathi.auth.getIdToken) {
      return Promise.resolve();
    }
    return new Promise(function (resolve) {
      var waited = 0;
      var poll = setInterval(function () {
        if (window.csaathi && window.csaathi.auth && window.csaathi.auth.getIdToken) {
          clearInterval(poll);
          resolve();
        } else if (waited > 5000) {
          clearInterval(poll);
          resolve();
        }
        waited += 50;
      }, 50);
    });
  }

  document.addEventListener("htmx:configRequest", function (event) {
    event.preventDefault();
    whenAuthReady()
      .then(function () {
        return window.csaathi.auth.getIdToken(false);
      })
      .then(function (token) {
        event.detail.headers["Authorization"] = "Bearer " + token;
      })
      .catch(function (err) {
        console.error("htmx_bearer: failed to attach token", err);
      });
  });

  document.addEventListener("htmx:responseError", function (event) {
    var xhr = event.detail.xhr;
    if (!xhr || xhr.status !== 401) {
      return;
    }
    var retried = event.detail.requestConfig && event.detail.requestConfig.__csaathiRetried;
    if (retried) {
      window.location.assign("/");
      return;
    }
    if (!window.csaathi || !window.csaathi.auth) {
      window.location.assign("/");
      return;
    }
    window.csaathi.auth
      .getIdToken(true)
      .then(function () {
        var elt = event.detail.elt;
        var config = event.detail.requestConfig || {};
        config.__csaathiRetried = true;
        if (window.htmx && elt) {
          window.htmx.trigger(elt, "csaathi:retry");
        } else {
          window.location.assign("/");
        }
      })
      .catch(function () {
        window.location.assign("/");
      });
  });
})();
