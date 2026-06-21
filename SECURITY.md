# CarbonSaathi Security Posture

This document walks through the OWASP Top 10 (2021) and records, for each
category, the specific controls CarbonSaathi has in place plus any known
limitations.  It is meant as both an evidence trail (so a reviewer can map a
threat to a control without re-reading the codebase) and a punch-list of
gaps to close before scaling beyond the v1 demo deployment.

For vulnerability reports please email the maintainer directly; do **not**
file a public issue.

---

## A01:2021 — Broken Access Control

Every `/api/*` route except `GET /api/health`, `GET /api/auth/config`, and
`POST /api/auth/verify` runs through the
[`verify_firebase_token`](app/core/auth.py) FastAPI dependency, which 401s
on any missing, malformed, expired, revoked, or otherwise invalid Firebase
ID token.  All Firestore reads/writes are scoped by the authenticated
caller's UID (`current.uid`) — there is no path-supplied user identifier
that a caller could tamper with, and resource-not-found vs
resource-belongs-to-another-user both return identical 404s to avoid
information leakage.  Authentication failures never surface a 500 nor leak
the underlying cause; the catch-all in `verify_firebase_token` ensures a
plain 401 with `"Authentication failed"`.

## A02:2021 — Cryptographic Failures

All traffic terminates at Cloud Run over HTTPS; the
`Strict-Transport-Security` header (`max-age=31536000; includeSubDomains`)
is applied to every response by the security-headers middleware.  We do
not store credentials, payment data, or other regulated PII — only
self-reported activity descriptions and the user's home/transport
profile.  Firebase ID tokens are short-lived JWTs verified server-side
against Google's public keys on every protected request; we never store
the raw tokens.

## A03:2021 — Injection

User text is never concatenated into SQL or shell commands; Firestore is
accessed exclusively through typed `FirestoreService` methods using
parameter binding.  All HTML is rendered through Jinja2 templates with
auto-escaping enabled, and the client-side renderers in
`app/static/js/*_page.js` route user content through an `escapeHtml`
helper before string-templating it into the DOM.  Prompt-injection inputs
targeting the LLM are caught by the regex-based governance gate in
[`app/core/governance.py`](app/core/governance.py); see
[`tests/test_security_injection.py`](tests/test_security_injection.py) for
12 representative payloads that are rejected with HTTP 400 before any
model call.

## A04:2021 — Insecure Design

The agent pipeline is built around a "visible reasoning + tool-call
function-calling" contract rather than free-form output, which constrains
the surface area a malicious prompt can affect.  Emission arithmetic is
performed locally against a static factors table; the model can only
*propose* the activity shape, never the numeric impact.  Recommendation
acceptance is idempotent and scoped to the caller's UID; insights and
recommendations are read-only views over a per-user collection with no
cross-tenant fan-out.

## A05:2021 — Security Misconfiguration

A custom `secure`-based middleware emits a strict CSP, HSTS,
`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, a
strict-origin Referrer-Policy, and a Permissions-Policy on **every**
response — including Starlette-synthesised 404s and 422s and
middleware-synthesised 500s (see
[`tests/test_security.py`](tests/test_security.py)
`test_security_headers_emitted_on_every_status`).  `script-src` does not
contain `'unsafe-inline'`; the only style exception is the Tailwind CDN's
runtime style injection.  `ALLOWED_ORIGINS` is locked to the two known
deployment hosts.  Uvicorn ships with `--no-server-header` so we do not
advertise the server version.  `redirect_slashes=False` and a hard rule
that prefixed routers use slashless paths eliminate an entire class of
trailing-slash open-redirect ambiguity.

## A06:2021 — Vulnerable and Outdated Components

Dependencies are pinned in `pyproject.toml` and audited with `pip-audit`
as part of the Phase 7 validation gauntlet.  Pre-release Phase 7 sweep
upgraded `pip` and `pydantic-settings` to clear five CVE advisories; the
audit currently reports no known vulnerabilities.  Frontend has zero npm
dependencies — all client code is hand-rolled ES modules served from
`/static`; Tailwind and the Firebase Web SDK are the only third-party
scripts and both are loaded from their official CDN hosts whitelisted in
the CSP.

## A07:2021 — Identification and Authentication Failures

Identity is delegated entirely to Firebase Authentication (Google
Sign-In); the application never sees, stores, or rotates user passwords.
`POST /api/auth/verify` is rate-limited 30/minute per source IP to slow
credential-stuffing or token-replay probing.  ID tokens are validated
with `check_revoked=True` on every request, so a revoked session is
killed within the next token-refresh window (Firebase default ~1 hour;
the client-side `authedFetch` helper performs a forced refresh and one
retry on 401 to keep legitimate sessions alive without re-prompting).

## A08:2021 — Software and Data Integrity Failures

The container is built reproducibly from a single multi-stage Dockerfile
that installs from the pinned `pyproject.toml`; no curl-pipe-to-bash
during the build.  The web frontend has no build step and no npm
dependencies — every file under `app/static/js/` is committed source.
Firestore documents are written through Pydantic-validated models, so a
corrupted-shape write cannot silently bypass the schema; staleness
detection in [`app/services/staleness.py`](app/services/staleness.py)
explicitly handles the `previous_run_failed` state so a partially-written
pipeline does not poison subsequent runs.

## A09:2021 — Security Logging and Monitoring Failures

Every request and every auth failure is recorded through `structlog` as
single-line JSON to stdout, which Cloud Run ships to Cloud Logging.
Sensitive fields are never logged — auth failures log only the failure
category (`auth.expired_token`, `auth.invalid_token`, …), never the
token itself.  The unhandled-exception path in the security middleware
emits an `unhandled_exception` event with method + path so a 500 is
always visible in logs, even though the client-facing response is the
generic `"Internal Server Error"`.

## A10:2021 — Server-Side Request Forgery (SSRF)

The application makes no outbound HTTP calls that take a user-supplied
URL.  The only external network destinations are Google Cloud
(Firestore, Firebase Auth, Gemini), each addressed via vendor SDKs that
hardcode their endpoints.  There is no proxy/fetcher route, no
webhook-target field, and no image-by-URL upload path that an attacker
could redirect inward.
