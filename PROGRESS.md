# CarbonSaathi — Build Progress Log

> **Purpose:** Hand off full build state to a new Claude session so quality does not degrade.
> **Last updated:** End of Phase 5B (Saturday)
> **Source files of truth:** This file + `DECISIONS.md` (in repo root). Read both at session start.

---

## How the next Claude session should use this file

1. Read `DECISIONS.md` first (project spec — name, persona, scope, stack, architecture, rubric strategy, schedule, implementation conventions §14, build amendments log §15)
2. Read this file second (build state, gotchas, conventions, decisions made during build, pending work)
3. **Do not re-derive decisions already locked.** If something here conflicts with the user's new message, ask before overriding.
4. Maintain the established workflow conventions (see § "Operational conventions" below)
5. Maintain the established phase prompt template (see § "Phase prompt template" below)
6. Continue from where § "Pending phases" picks up. Phase 5C (insights + recs + SSE) is next.

---

## User preferences (already in system context, restated for emphasis)

- Push back first, validate second. No glazing. No filler affirmations.
- Lead with the most useful thing. If the answer is "no," say it in the first sentence.
- Call out bad logic, weak assumptions, and blind spots — especially when the user sounds certain.
- Minimal formatting unless structure aids clarity.
- The user is **Apoorv Gupta**, Consultant Data Engineer at Principal Global Services, Pune. Strong Python background. Direct communication style. No motivational filler.

---

## Project state snapshot

| Item | Value |
|---|---|
| **Project name** | CarbonSaathi (कार्बन साथी) |
| **Challenge** | PromptWars Challenge 3 — Carbon Footprint Awareness Platform |
| **Submission deadline** | Sunday, June 21, 2026, 23:59 IST |
| **Build deadline** | Sunday, June 21, 2026, 18:00 IST |
| **GCP project ID** | `prompt-wars-virtual-carbon-3` |
| **GCP region** | `asia-south1` |
| **Cloud Run service name** | `carbonsaathi` |
| **Deployed URL** | `https://carbonsaathi-ahkpdce5pa-el.a.run.app` |
| **Service account** | `carbonsaathi-runner@prompt-wars-virtual-carbon-3.iam.gserviceaccount.com` |
| **Secret Manager secrets** | `gemini-api-key`, `firebase-api-key` |
| **Python version** | 3.13.7 (on user's Mac) |
| **Python command** | `python3` (NOT `python`) |
| **Local dev port** | **8080** (NOT 8000) — Cloud Run convention via `PORT` env var |
| **Coverage target** | **95%** (line + branch). Current actual after 5B: ~99.7% |
| **GitHub status** | Open question — confirm with user at session start whether push happened |
| **Deployment health** | `/api/health` returns `{"status":"ok","version":"0.1.0"}` (last verified Phase 1D; code changes since then are NOT yet deployed — Phase 9 re-deploys) |
| **Phases complete** | 1A, 1B, 1C, 1D, 2, 3, 4A, 4B, **5A, 5B** |
| **Next phase** | **5C — Insights + recommendations routes + SSE reasoning stream** |

---

## Completed phases

### Phase 0 — Decisions

Locked: project name, persona (Riya/Rahul, 28, Indian metro professional), 3-activity scope (Transport + Electricity + Food), 3-agent architecture (Logger + Analyst + Coach, Devil's Advocate dropped), tech stack, Indian-only geographic focus, Firestore on Spark plan (free), Google Sign-In persistence requirement, compressed 48h schedule, hard rule of no Submission #3.

Output: `DECISIONS.md` in repo root.

### Phase 1A — Scaffold + tooling

**Files created:**
- `pyproject.toml` (PEP 621 format, requires-python `>=3.13,<3.14`)
- All ruff/black/mypy/pytest/bandit/coverage configs inline in pyproject.toml
- `.pre-commit-config.yaml`
- `.gitignore`, `.env.example`, `LICENSE` (MIT), `README.md` skeleton
- Empty `__init__.py` files for `app/core/`, `app/models/`, `app/routes/`, `app/agents/`, `app/services/`
- `tests/__init__.py` and `tests/conftest.py`

**Key config decisions:**
- ruff `line-length = 100`, `target-version = "py313"`, Google docstring convention, `select = ["E","W","F","I","B","C4","UP","N","D","S","RUF"]`
- mypy `strict = true`, `python_version = "3.13"`
- pytest `--cov-fail-under=95`
- bandit `skips = ["B101"]`
- pre-commit hooks: trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, check-added-large-files (500KB cap), detect-private-key, ruff, ruff-format, mypy, bandit

### Phase 1B — FastAPI app core

**Files created:**
- `app/main.py` — `create_app()` factory with lifespan, CORS, slowapi rate limiting, security headers middleware, `/api` prefix for routes
- `app/core/config.py` — `Settings` via pydantic-settings v2 with `SecretStr` for `gemini_api_key`, `@lru_cache` singleton `get_settings()`, validators on `app_env`, `log_level`, `allowed_origins` (CSV split). **Phase 4A added:** `gemini_model_flash`, `gemini_model_pro` defaults.
- `app/core/logging.py` — structlog setup: `ConsoleRenderer` in dev, `JSONRenderer` in prod
- `app/core/security.py` — `secure` library default headers via FastAPI middleware
- `app/routes/health.py` — `GET /api/health` returns `HealthResponse(status="ok", version="0.1.0")`
- `tests/conftest.py` — autouse fixture sets test env vars + clears settings cache via `monkeypatch`
- `tests/test_config.py`, `tests/test_logging.py`, `tests/test_security.py`, `tests/test_health.py`
- `Dockerfile` — multi-stage `python:3.13.7-slim`, non-root user (uid 1000), HEALTHCHECK, exec-form CMD for SIGTERM propagation
- `.dockerignore` (preserves `README.md` because pyproject references it)
- `Makefile` — targets: `install`, `run`, `test`, `lint`, `format`, `typecheck`, `security`, `all`, `clean`, `docker-build`, `docker-run`

### Phase 1C — GitHub Actions CI

**Files created:**
- `.github/workflows/ci.yml` — 6 jobs: `lint`, `typecheck`, `test`, `security`, `docker`, `ci-success` (summary)
- Workflow-level: `permissions: contents: read`, `concurrency` with `cancel-in-progress: true`, `env.PYTHON_VERSION: "3.13.7"`
- Each Python job uses `actions/setup-python@v5` with `cache: pip`
- Docker job uses `docker/setup-buildx-action@v3` + `docker/build-push-action@v5` with GHA cache
- `README.md` updated with CI status badge

### Phase 1D — GCP setup + first Cloud Run deploy

**Files created:**
- `scripts/01_gcp_setup.sh` — idempotent GCP project + APIs enabled + Firestore + IAM
- `scripts/02_load_secrets.sh` — pushes secrets into Secret Manager via stdin
- `scripts/03_deploy.sh` — `gcloud run deploy --source .`, two-pass ALLOWED_ORIGINS handling
- `DEPLOYMENT.md` — runbook including manual Firebase setup steps
- `Makefile` updated with `deploy`, `gcp-setup`, `gcp-secrets` targets
- `.gitignore` updated with `.deploy-url`, `*-sa-key.json`, `*-service-account.json`

**Cloud Run service config:** `min-instances=1`, `max-instances=3`, cpu=1, memory=512Mi, port=8080, timeout=60s, concurrency=80, `--allow-unauthenticated`. IAM on runner SA: `roles/datastore.user`, `roles/secretmanager.secretAccessor`, `roles/logging.logWriter`.

### Phase 2 — Domain models + governance + Firestore service

**Files created:**
- `app/models/shared.py` — `AgentReasoning`, `Confidence` Literal (canonical home)
- `app/models/user.py` — `IndianState` (StrEnum, 28 states + 8 UTs), `Dietary`, `FridgeClass`, `HomeProfile`, `UserProfile`. Timestamp validators enforce UTC tz-aware. **Phase 5A modified: `email`/`state`/`home_profile` became `Optional[…] = None`.**
- `app/models/activity.py` — `ActivityType = Literal["transport","electricity","food"]`, `Activity` (frozen=True, extra=forbid), typed sub-models added in 4A.
- `app/models/insight.py`, `recommendation.py`, `emission.py`
- `app/core/governance.py` — `GovernanceResult(allowed, reason, category)`. `check_input(text) -> GovernanceResult` is sync, no I/O. Injection patterns + carbon-vocab allowlist. Precedence: empty > injection > abuse > off_topic > ok.
- `app/core/firebase.py` — `@lru_cache(maxsize=1) get_firebase_app()`, `get_firestore_async_client()` using `google.cloud.firestore.AsyncClient`. **No `initialize_app` at import.**
- `app/services/firestore_service.py` — `FirestoreService` async class. **Phase 5B extended with `list_activities_in_range`, `get_activity`, and `before` cursor on `list_activities`.**

### Phase 3 — Emission factor data layer

**Files created:**
- `app/models/emission.py` — `FactorEntry`, `FactorLookupResult`. Both frozen.
- `app/data/state_grid_factors.json` — every IndianState entry, mapped to regional grid. Coal-heavy and renewable-heavy outliers marked `estimated`.
- `app/data/transport_factors.json` — 11 transport modes. Walking and WFH = 0 by definition.
- `app/data/food_factors.json` — 10 food categories with per-serving sizes documented in notes.
- `app/services/emission_service.py` — `EmissionService` loads all three JSONs at construction with `FactorEntry.model_validate`; raises `EmissionDataError` on malformed data. Sync after construction. `get_emission_service()` cached singleton.
- `scripts/verify_emission_data.py` — standalone runnable + importable functions for test reuse.

### Phase 4A — BaseAgent + Gemini client + LoggerAgent

**Files created:**
- `app/core/gemini.py` — `@lru_cache(maxsize=1) get_gemini_client()` factory exposing `.flash()` and `.pro()`. No module-level `configure` or model init.
- `app/models/activity.py` (additions): `TransportData`, `ElectricityData` (with typed `notes` and at-least-one-of validator), `FoodData`.
- `app/agents/base.py` — `AgentInvocationError`, `BaseAgent(ABC)` with protected `_check_governance`, `_now_ms`, `_build_reasoning`, `_log`. **No abstract `run`** — subclasses define typed entrypoints.
- `app/agents/prompts/logger_v1.py` — `PROMPT_VERSION = "logger-v1"`, function declarations sourced from `emission_service.list_transport_modes()` and `list_food_categories()` at import time (parity test enforces).
- `app/agents/logger_agent.py` — `LoggerOutcome = Annotated[Union[Success, Rejected, Failed], Field(discriminator="status")]`. `AVG_INR_PER_KWH: Final = 8.0` with forced-estimated rule.

### Phase 4B — AnalystAgent + CoachAgent + integration test

**Files created:**
- `app/agents/prompts/analyst_v1.py` — defense-in-depth framing (activity data = DATA TO ANALYZE not instructions); response schema fallback; max 3 insights; supporting_activity_ids must come from input set.
- `app/agents/prompts/coach_v1.py` — GOOD vs BAD examples; JSON-only; max 3 recs; each must include valid `saving_basis`. **Phase 5A modified: `build_user_prompt(state, home, …)` signature narrowed.**
- `app/agents/analyst_agent.py` — `AnalystOutcome`. `MIN_ACTIVITIES_FOR_INSIGHTS = 3`. Pre-bucket by week in Python before calling Gemini.
- `app/agents/coach_agent.py` — `SavingBasis` discriminated union with 3 kinds. **Phase 5A added: not-onboarded guard returns `CoachEmpty` without calling Gemini if state or home_profile is None.**
- Integration test chains Logger → Analyst → Coach with all Gemini calls mocked.

### Phase 5A — Authentication foundation + user routes

**Files created:**
- `app/core/auth.py` — `CurrentUser(BaseModel, frozen=True)` with `uid`, `email`, `email_verified`, `name`. `async def verify_firebase_token(authorization: str | None = Header(...))` FastAPI dependency. Maps every Firebase exception class (`InvalidIdTokenError`, `ExpiredIdTokenError`, `RevokedIdTokenError`, `CertificateFetchError`, `ValueError`, bare `Exception`) to a uniform `HTTPException(401, "Authentication failed")`. Structured logging at WARNING for known auth failures, ERROR for unexpected. **Never lets auth raise 500.**
- `app/routes/auth.py` — `POST /api/auth/verify`. Looks up uid; if missing creates minimal UserProfile (state=None, home_profile=None, onboarding_complete=False) via `upsert_user`, is_new=True. If exists, `fire_and_forget(upsert_user(profile_with_updated_last_active))`, is_new=False. Returns `VerifyResponse(user, is_new)`.
- `app/routes/users.py` — `GET /api/users/me` (returns UserProfile or 404), `POST /api/users/onboarding` (takes `OnboardingPayload(state, home_profile)`, updates, sets onboarding_complete=True, 404 if user not found). Re-onboarding allowed — treated as update.
- `tests/test_core_auth.py`, `tests/test_routes_auth.py`, `tests/test_routes_users.py` — 25 new tests covering success + every exception branch.

**Files modified:**
- `app/main.py` — registered auth and users routers under `/api`
- `app/models/user.py` — `email: str | None = None`, `state: IndianState | None = None`, `home_profile: HomeProfile | None = None`
- `app/agents/coach_agent.py` — not-onboarded guard at top of `generate_recommendations`
- `app/agents/prompts/coach_v1.py` — `build_user_prompt(state, home, …)` signature narrowed
- `tests/conftest.py` — added `firestore_service_mock`, `current_user`, `client_with_user` fixtures (use `httpx.AsyncClient`, `app.dependency_overrides`, finalizer clears overrides)

**Coverage delta:** 99.73% → 99.76%. New modules at 100%.

### Phase 5B — Activity routes + dashboard

**Files created:**
- `app/agents/factories.py` — `@lru_cache(maxsize=1) get_logger_agent()` — constructs LoggerAgent with `emission_service=get_emission_service()` and `gemini_factory=get_gemini_client()`. Future agent factories live here too.
- `app/routes/activities.py`:
  - `LogActivityRequest(raw_input: Annotated[str, Field(min_length=1, max_length=500, strip_whitespace=True)])`
  - `LogActivityResponse(activity: Activity, agent_reasoning: AgentReasoning)`
  - `ActivityListResponse(items: list[Activity], next_cursor: str | None)`
  - `POST ""` → calls Logger, pattern-matches `outcome.status`: success → 201 + LogActivityResponse, rejected → 400 with `{detail, reason, category}` (governance category IS safe to expose), failed → 500 with generic `{"detail":"Could not log activity"}` + ERROR log with event="activity.log_failed"
  - `GET ""` → query params `limit: int = Query(20, ge=1, le=50)`, `before: datetime | None = Query(None)`. Returns paginated list. `next_cursor` = last item's `timestamp.isoformat()` iff `len(items) == limit`, else `None`.
  - `GET "/{activity_id}"` → returns Activity or 404 with generic `"Activity not found"` (same message whether actually missing OR owned by other uid — DO NOT differentiate)
- `app/routes/dashboard.py`:
  - `IST = ZoneInfo("Asia/Kolkata")` at module top
  - `DashboardResponse(today_kg, today_by_type, week_total_kg, week_by_day, streak_days, lifetime_activity_count)`
  - `DashboardByType(transport_kg, electricity_kg, food_kg)`
  - `DashboardDayBreakdown(date_ist: date, total_kg: float)`
  - `GET ""` → computes week window in IST, fetches `list_activities_in_range`, buckets by IST date, returns 7 entries oldest→today (zero-emission days included), computes streak with same-day grace period
- `tests/test_routes_activities.py`, `tests/test_routes_dashboard.py` — ~37 new tests including streak grace path, IST boundary, cross-user isolation
- `tests/conftest.py` — added `logger_agent_mock` fixture

**Files modified:**
- `app/main.py` — registered activities and dashboard routers; **added `redirect_slashes=False` to FastAPI() constructor** (resolves the 307-before-auth info leak)
- `app/services/firestore_service.py` — added `list_activities_in_range(uid, start, end, limit=200)`, `get_activity(uid, activity_id)`, extended `list_activities` with `before: datetime | None = None` param
- All routes normalized to slashless convention: bare-resource decorators use `@router.post("")` / `@router.get("")` rather than `"/"`. DECISIONS.md §9 and §14 document this.

**Coverage delta:** 99.76% → maintained ~99.7%. New modules at or near 100%.

**Validation gauntlet completed (12 stages):** static analysis, file inventory, full suite + coverage, live HTTP probes against port 8080, slashless convention acid test (5.4/5.5 confirm slashed form 404s, no rogue 307), uniform-401 auth-failure body across every protected route (content-length 34 on all), security headers preserved on 200/401/404.

---

## Decisions made during build (not in DECISIONS.md original spec)

These emerged during implementation. Capture so they aren't relitigated. Cross-referenced as build amendments §15 in DECISIONS.md.

### Confidence literal consolidated to `shared.py` (Phase 3)
Phase 3 needed Confidence for `FactorEntry`. Phase 2 had defined it in `activity.py`. Canonical definition moved to `app/models/shared.py`; `activity.py` re-exports for backward compat.

### ElectricityData has a `notes` field (Phase 4A)
Typed field for bill→kWh conversion assumption. **Do not push into `structured_data["conversion_note"]`** — that's an untyped escape hatch.

### `AVG_INR_PER_KWH = 8.0` with forced-estimated confidence (Phase 4A)
Any Activity derived from bill→kWh conversion sets `confidence='estimated'` regardless of grid factor confidence. Documented in constant docstring. Tested.

### Agents read model name from GenerativeModel instance, not Settings (Phase 4A)
Each agent caches `self._model` at `__init__` and reads `self._model.model_name` for `AgentReasoning.model`. Dependency injection stays clean.

### Phase 4 split into 4A + 4B (Phase 4)
Original 7h continuous for "three agents" was unrealistic. 4A = BaseAgent + Gemini client + LoggerAgent; 4B = Analyst + Coach + integration. Recovery checkpoint at lunch.

### Outcome discriminated union pattern (Phase 4A onward)
LoggerOutcome, AnalystOutcome, CoachOutcome all `Annotated[Union[...], Field(discriminator="status")]` with `status: Literal["..."]` (NOT `str`). **No exceptions for expected failure cases** — governance reject, no function call, unknown mode, low data, malformed JSON all return typed outcomes. Routes pattern-match `status` for HTTP translation.

### Coach computes savings; never trusts the model (Phase 4B)
Coach validates `saving_basis` against `emission_service` and computes `expected_saving_kg` from real factors. Model never sets the number.

### UserProfile fields became Optional (Phase 5A — Q1)
`email`, `state`, `home_profile` changed from required to `… | None = None` to support the pre-onboarding user state (created by `/auth/verify`, completed by `/onboarding`). DECISIONS.md §8 updated. Coach was patched for `state=None` / `home_profile=None`; no other module reads those fields. **Always grep `profile\.\(state\|email\|home_profile\)` after adding new code that touches UserProfile.**

### Authorization header dep typed `str | None` (Phase 5A — Q2)
Missing header → uniform 401 raised inside function body, NOT FastAPI's default 422 from `Header(...)`. Pairs with §14.3 uniform auth-failure contract.

### Coach `build_user_prompt(state, home, …)` signature narrowed (Phase 5A)
Takes narrowed values rather than the full profile object. Makes None-handling explicit at the call site rather than deep inside the prompt builder.

### CoachAgent not-onboarded guard (Phase 5A)
If `profile.state is None or profile.home_profile is None` at the top of `generate_recommendations`, returns `CoachEmpty` without calling Gemini. Reason string is user-facing ("Complete onboarding to unlock recommendations").

### `httpx.AsyncClient` for FastAPI tests (Phase 5A — Q4)
Repo convention. Pairs with `app.dependency_overrides` for mocking auth + Firestore. The `client_with_user` fixture in conftest sets up both overrides and clears on finalizer.

### `lru_cache` agent factories in `app/agents/factories.py` (Phase 5B)
Cached singleton pattern parallel to `get_emission_service()` and `get_firestore_service()`. Future Analyst/Coach factories will live here too — Phase 5C will add `get_analyst_agent()` and `get_coach_agent()`.

### IST timezone for all user-facing time (Phase 5B)
Single `IST = ZoneInfo("Asia/Kolkata")` constant at top of `dashboard.py`. Activity timestamps stored UTC; conversion at read time only. **Always use `.astimezone(IST).date()` for IST-day keys**, never `.date()` on a UTC-aware datetime.

### Duolingo-style streak with same-day grace (Phase 5B)
If today has activity, streak counts from today backward. If today is empty, streak counts from yesterday backward (grace — user has rest of day to log without breaking streak). Without grace, streak would show as 0 for most of every day. UX matters even on the backend.

### `redirect_slashes=False` + slashless routes (Phase 5B)
FastAPI's default 307 for trailing-slash mismatch fires **before** auth dep. Set `redirect_slashes=False` on FastAPI() AND use `@router.post("")` / `@router.get("")` (empty string) for bare-resource routes. DECISIONS.md §14.1, §14.2 document. Phase 6 frontend MUST match slashless paths.

### Pre-bucket activities by week in Python before Analyst (Phase 4B)
Analyst receives `{"this_week": [...], "last_week": [...], "earlier": [...]}` already grouped — model does not perform date math. Use `>` not `>=` when comparing day delta (so "exactly 7 days ago" goes to last_week). Tested at day=7 boundary.

### JSON output for Analyst/Coach via `response_mime_type` + fallback (Phase 4B)
Pro models accept `generation_config={"response_mime_type": "application/json"}` and `response_schema` in newer SDKs. Use both if available. Fallback: drop `response_schema`, keep `response_mime_type`, add explicit "Output valid JSON only" to system prompt, strip ``` fences before `json.loads`. JSONDecodeError → typed `*Failed`.

---

## Critical gotchas (DO NOT re-discover)

### Coverage threshold is 95% (NOT 80%)
Default plan said 80%. User raised to 95% early. Every phase must keep the threshold. Current actual ~99.7%.

### mypy + third-party libs without stubs
`secure`, `slowapi`, `structlog`, `google.cloud.firestore`, `firebase_admin`, `google.generativeai` ship without stubs. `[[tool.mypy.overrides]]` blocks with `ignore_missing_imports = true` (and `implicit_reexport = true` for firebase_admin to access `firebase_admin.auth`). Any new dep without stubs needs the same treatment.

### pre-commit mypy hook misses imports
Add prod deps to `additional_dependencies` on the mypy hook: `fastapi`, `pydantic>=2.0`, `pydantic-settings`, `structlog`, `slowapi`, `secure`, `httpx`, `starlette`, `pytest`, `python-dotenv`, `google-generativeai`, `firebase-admin`, `google-cloud-firestore`. Add to this list when new prod deps land.

### GCP IAM propagation race
SA exists but IAM hasn't seen it. Mitigation: re-run the idempotent script. For future projects, retry-with-backoff around IAM bindings.

### `--condition=None` required on `add-iam-policy-binding`
All `gcloud projects add-iam-policy-binding` calls must include `--condition=None --quiet` for non-interactive mode.

### `gcloud run deploy` vs `gcloud run services update` for env-vars-only
Use `gcloud run services update --update-env-vars=...` for env-var-only changes. ~10s vs ~5min.

### ALLOWED_ORIGINS first-deploy chicken-and-egg
Cloud Run URL unknown before first deploy. `scripts/03_deploy.sh` deploys with `ALLOWED_ORIGINS=*` on first run, captures URL, then `services update` sets actual URL. State persisted to `.deploy-url` (gitignored). **Tighten in Phase 6** when frontend lands.

### Python version is 3.13.7
All configs target 3.13. Flag any 3.11 references as stale.

### Use `python3`, not `python`
User's shell uses `python3`. All scripts must use `python3` outside venv.

### Pydantic discriminated union gotcha
Discriminator field must be `Literal["..."]`, NOT `str`. `Annotated[Union[...], Field(discriminator="...")]` is the wrapping pattern.

### `asyncio.wait_for` exception handling
Wrap SDK-specific exceptions inside the `wait_for`-protected coroutine; let `TimeoutError` propagate from `wait_for` to your handler. Don't double-wrap, don't swallow.

### Pytest test runtime budget
Total suite must run in < 60s. Current actual ~1.0s. `asyncio.wait_for` with real timeouts in tests kills this — use small mock timeouts (0.01s) or patch `asyncio.wait_for` to raise immediately.

### LRU cache + Gemini factory
`@lru_cache(maxsize=1)` on `get_gemini_client()` means `genai.configure` is called exactly once per process. Tests must patch `google.generativeai.configure` BEFORE first import of `app.core.gemini` if asserting it wasn't called at import.

### Discriminated-union JSON parsing from Gemini
If the model omits the `status`/`kind` field, `model_validate` fails — handle as `*Failed` (or drop the rec for Coach). Don't try to infer the discriminator from other fields.

### Local dev port is 8080, not 8000
`make run` serves on 8080 (Cloud Run convention via `PORT` env var). All curl validation commands use `http://localhost:8080`. Phase 1A–4B prompts incorrectly used 8000 in some places; subsequent prompts corrected.

### `redirect_slashes=False` is load-bearing (Phase 5B)
`FastAPI(redirect_slashes=False)` is required to prevent 307-before-auth info leak. **Do not flip back.** With this disabled, every route must be at its exact registered path. See §14.1, §14.2.

### Slashless route convention (Phase 5B)
Bare-resource routes use `@router.post("")` / `@router.get("")`, not `"/"`. With `redirect_slashes=False`, the slashed form 404s. **Every new route in Phase 5C, 6, etc. MUST follow this.** Validation step: `grep -nE '@router\.(get|post|put|delete|patch)\("/"\)' app/routes/` should always return ZERO matches.

### Uniform 401 auth-failure body (Phase 5A)
Every protected route returns content-length 34 = `{"detail":"Authentication failed"}` for any auth failure. Validation step: loop curl across all protected routes with the correct verb for each route (GET routes use GET, POST routes use POST — POSTing to a GET-only route correctly 405s because Starlette method-resolves before auth dep).

### Stage 0 grep false positives
Stage 0.3 grep `grep -rnE '/api/(activities|dashboard)/[^{"]' tests/` matches the first character after the path segment — legitimate `{activity_id}` tests with `nonexistent-id` or `other-users-activity-id` look like hits but aren't. Use `--include='*.py'` to skip `.pyc` cache files.

### UserProfile.Optional[] ripple
`email`, `state`, `home_profile` are nullable. Any new code reading these must handle None. Before adding new agent code or routes that touch UserProfile, grep `grep -rn "profile\.\(state\|email\|home_profile\)" app/` to find existing consumers and verify their None-handling matches.

---

## Operational conventions

### GitHub push timing
**Original plan was Saturday 09:00 IST.** As of end of 5B, push status is an open question — confirm at session start. **Strong recommendation:** push at every phase boundary. Each phase ships meaningful new surface area; CI on cumulative repo is more useful than CI on Phase 1A. If user has not pushed, SPOF risk grows linearly and CI validation is being deferred to the worst possible moment.

### Deployment from local, not from GitHub
`gcloud run deploy --source .` uploads local source to Cloud Build. No GitHub dependency for deploy. Phase 9 re-deploys with all Phase 5–7 changes batched.

### Model selection per phase

User has GitHub Copilot with Claude models. Switch per phase to control cost.

| Phase | Recommended model | Status |
|---|---|---|
| 1A scaffold | Sonnet 4.6 | done |
| 1B FastAPI core | Opus 4.8 | done |
| 1C CI | Sonnet 4.6 | done |
| 1D GCP scripts | Sonnet 4.6 | done |
| 2 Models + governance | Sonnet 4.6 | done |
| 3 Emission data | Sonnet 4.6 | done |
| 4A Base + Gemini + Logger | **Opus 4.8** | done |
| 4B Analyst + Coach + integration | **Opus 4.8** | done |
| 5A Auth dep + auth/users routes | Sonnet 4.6 | done |
| 5B Activity routes + dashboard | Sonnet 4.6 | done |
| **5C Insights + recs + SSE** | **Opus 4.8** | NEXT |
| 6 Frontend | Sonnet 4.6 | |
| 7 Security hardening | Sonnet 4.6 | |
| 8 Test sweep | Sonnet 4.6 | |
| 9 Deploy + perf | Sonnet 4.6 | |
| 10 README + polish | **Opus 4.8** | |
| 11 Submission #1 | n/a | |
| 12 Submission #2 | Sonnet 4.6 | |

**Always flag model recommendation at the start of each phase prompt.**

### Phase prompt template

Every phase prompt follows this structure. **Continue using it.**

```
## My chain of thought on Phase X
(2-4 paragraphs: what's in scope, what's not, why)

## Model recommendation
(Sonnet 4.6 or Opus 4.8 with reasoning)

## Compact context block (paste FIRST in new Copilot session)
(handoff block, ~50 lines)

## The Phase X Copilot Prompt (paste SECOND)
(detailed prompt with: context, goal, what NOT to include, mandatory planning step,
file list, per-file specs, quality requirements, output format)

## Setup before pasting
(any prerequisite shell commands)

## Validation block — run after Copilot finishes Step 2
(numbered table: # | Command | Expected output)
Multiple stages: file inventory, static analysis, tests, runs, commit/push

## Troubleshooting
(named failure modes + fixes)

## Validation gate
(✅ "X green" or ⚠️ "X failed at step N" with paste request)
```

### Mandatory planning step in Copilot prompts
Every Copilot prompt MUST tell Copilot to output a numbered plan first and **STOP** before writing files. This catches scope drift before code is generated. Step 2 only runs after user confirms. Copilot may also ask clarifying questions during planning — answer definitively before approving.

### Pre-flight checks before phases that hit external APIs
Phase 4 introduced pre-flight: confirm `gcloud secrets versions access` works for the secret the phase will use, confirm the SDK imports cleanly. Add per-phase pre-flight whenever a new external dependency is introduced. Phase 5C does not introduce new deps but uses real Gemini at runtime (tests still mock) — confirm `gemini-api-key` secret has live key with quota.

### Long-context cost mitigation
Each new Copilot session gets a compact context block (~50 lines) of project + stack + completed phases + hard rules + repo state command, NOT the full conversation history.

### Comprehensive validation gauntlet
Phase 5B introduced a 12-stage validation block. **Use the same shape for 5C and onward.** Stages: (0) Copilot completed normalization, (1) static analysis, (2) file inventory + new surface, (3) test suite + coverage, (4) start server, (5) functional acid tests for the phase, (6) auth consistency, (7) validation contracts via grep, (8) security headers preserved, (9) shutdown, (10) PROGRESS.md update, (11) commit + push + CI.

---

## Quality gates (apply to every phase)

- **95% test coverage** maintained on `app/` (line + branch). Current actual ~99.7%.
- `mypy --strict` zero errors
- `ruff check .` zero warnings
- `bandit -c pyproject.toml -r app` zero issues
- `pip-audit` clean
- Every code file starts with `from __future__ import annotations`
- Every public function/class has a Google-style docstring (Args/Returns/Raises)
- No hardcoded secrets — only via `Settings`
- No new dependency without updating `pyproject.toml` AND `.pre-commit-config.yaml` mypy `additional_dependencies`
- Every async path is truly async — no sync I/O in `async def`
- All routes register under `/api`
- `/api/health` always remains functional
- **Zero Gemini network calls in tests.** Every `generate_content_async` is mocked.
- Total test suite runtime < 60 seconds (currently ~1.0s)
- **Slashless convention for all new bare-resource routes** — `@router.post("")` not `"/"`. Validation: `grep -nE '@router\.(get|post|put|delete|patch)\("/"\)' app/routes/` returns zero matches.

---

## Pending phases

### Phase 5C — Insights + recommendations routes + SSE reasoning stream (NEXT, Opus 4.8)

**Goal:** Wire AnalystAgent and CoachAgent behind FastAPI routes; add the SSE reasoning-stream endpoint that powers the "visible AI thinking" rubric differentiator.

**Files to create:**
- `app/agents/factories.py` — extend with `get_analyst_agent()` and `get_coach_agent()` cached factories.
- `app/routes/insights.py`:
  - `GET /api/insights` — triggers Analyst if cached insights are stale; "stale" = no insight generated in last 6 hours OR new activities since last gen. Reuses `service.get_recent_insights` and `service.add_insight`.
  - `GET /api/insights/stream` — SSE endpoint; `text/event-stream` content type; generator yields `data: {json}\n\n` chunks. For v1: emit `agent_reasoning.reasoning_steps` in chunks AFTER agent completes (Gemini SDK doesn't stream function calls natively). Document this constraint honestly in README. The chunks include heartbeats and a terminal `event: done` marker.
- `app/routes/recommendations.py`:
  - `GET /api/recommendations` — triggers CoachAgent, returns list of Recommendation
  - `POST /api/recommendations/{rec_id}/accept` — flips `accepted=True` via `service.accept_recommendation`
- `app/main.py` updates — register new routers (slashless convention)
- Tests for every route with mocked agents, mocked auth, mocked Firestore

**Design notes:**
- Pattern-match on `AnalystOutcome.status` / `CoachOutcome.status` for HTTP:
  - success → 200 with list
  - empty → 200 with empty list + reason string
  - failed → 500 with generic message; log actual reason server-side
- SSE generator pattern:
  ```python
  async def reasoning_stream(...):
      yield f"event: start\ndata: {{\"phase\":\"analyst\"}}\n\n"
      outcome = await analyst.generate_insights(...)
      for step in outcome.agent_reasoning.reasoning_steps:
          yield f"event: reasoning\ndata: {json.dumps({'agent': 'analyst', 'step': step})}\n\n"
      yield f"event: start\ndata: {{\"phase\":\"coach\"}}\n\n"
      coach_outcome = await coach.generate_recommendations(...)
      for step in coach_outcome.agent_reasoning.reasoning_steps:
          yield f"event: reasoning\ndata: {json.dumps({'agent': 'coach', 'step': step})}\n\n"
      yield f"event: done\ndata: {json.dumps({'insights': ..., 'recommendations': ...})}\n\n"
  ```
- Return `StreamingResponse(reasoning_stream(...), media_type="text/event-stream")` with `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no` (disables nginx/proxy buffering)
- Rate limit: per-user 30/min on insights generation, 60/min on stream. Phase 7 implementation; for 5C just use existing app-wide limiter.

**Pre-flight before Phase 5C:**
```bash
# Confirm Gemini SDK still importable
python3 -c "from google import generativeai; print(generativeai.__version__)"

# Confirm Cloud Run env var has gemini-api-key (this won't hit Gemini, just confirms secret is wired)
gcloud run services describe carbonsaathi --region asia-south1 --format='value(spec.template.spec.containers[0].env)' | grep -i gemini
```

### Phase 6 — Frontend (HTMX + Tailwind, Sonnet 4.6)

Server-rendered HTMX pages with Tailwind via CDN. Pages: sign-in (Firebase Google Sign-In), onboarding, dashboard (today's footprint + week chart + streak), log activity (textarea POSTing to `/api/activities`, response renders parsed Activity + agent_reasoning), insights feed (cards with reasoning expandable, optional SSE live render), recommendations (cards with Accept button).

Semantic HTML, ARIA labels, keyboard navigation, WCAG AA contrast, `prefers-reduced-motion` respected. Slashless paths in all `hx-post` / `hx-get` attributes. Tighten `ALLOWED_ORIGINS` from `*` to deployed URL.

### Phase 7 — Security hardening (Sonnet 4.6)

CSP / HSTS / X-Frame-Options / X-Content-Type-Options / Referrer-Policy / Permissions-Policy verified on every response status. Per-user rate limiting via Firebase uid keying on slowapi. Prompt injection tests against real route handlers. OWASP Top 10 manually walked with documented mitigations. Confirm `redirect_slashes=False` still in place.

### Phase 8 — Test sweep (Sonnet 4.6)

Push coverage to 99%+ on Phase 5C-7 deltas. Fix any flakes. Add golden-set regression tests for Analyst and Coach via 4B fixtures. Integration tests for full route → agent → Firestore chain (Firestore mocked).

### Phase 9 — Deploy + perf check (Sonnet 4.6)

Re-deploy. Load test 50 concurrent. Verify p95 < 2s. Verify `min-instances=1` still set. Verify no 500s under load. Verify SSE endpoint streams correctly through Cloud Run's HTTP/2 load balancer (this is the most uncertain piece — has caused issues for others).

### Phase 10 — README + manual eval polish (Opus 4.8)

Manual evaluators read the README. Sections needed:
- Project narrative (problem → user → approach → result)
- Architecture diagram (Mermaid)
- Agent flow diagram (Mermaid)
- 3–5 ADR-style decisions with alternatives considered
- Screenshots
- Honest limitations (single-language UI, no historical import, India-only, food factor methodology rough, SSE chunks emit post-completion not mid-flight)
- Run / deploy instructions
- License + credits

### Phase 11 — Submission #1 (baseline)

Push everything to GitHub. Capture AI evaluator score per criterion. Save scores for Phase 12 decision.

### Phase 12 — Submission #2 (conditional)

Only if Submission #1 reveals a clear, fixable gap on a specific criterion AND a hypothesis for the fix with measurable expected delta. **No Submission #3 under any circumstance** (ElectEd precedent: third attempt regressed Efficiency 100% → 80%).

---

## Open questions for the next session

1. **Current time / schedule recovery.** Phase 5B was the last completed phase. Re-plan remaining phases (5C–11) against the Sun 18:00 IST submission target.
2. **GitHub push status.** As of end of 5B, push was deferred ("push everything once dev and docs are done"). This is bad practice — SPOF risk and CI deferred. Confirm at session start whether push has happened; if not, recommend pushing through 5B at the next phase boundary at minimum.
3. **Firebase Auth client setup.** Phase 1D enabled the firebase API. The actual Firebase Authentication client config (web SDK config for Google Sign-In) needs to be created in the Firebase console before Phase 6 frontend can sign users in. Confirm whether this is done.
4. **Gemini quota / billing.** Phases 4, 5A, 5B all mocked Gemini. Phase 5C routes will hit real Gemini in dev/prod. Confirm `gemini-api-key` secret has live key with quota.
5. **OAuth client redirect URI.** Firebase Google Sign-In needs the Cloud Run URL added as an authorized redirect. Do this when UI ships in Phase 6.
6. **README owner placeholder.** CI badge in README.md has `<owner>` placeholder unless already sed-substituted. Confirm.
7. **SSE behind Cloud Run load balancer.** Cloud Run HTTP/2 buffering can break SSE in subtle ways. Phase 9 will validate; flag if any odd behavior shows up earlier.

---

## Reference: handoff to a new Claude session

When opening a new Claude conversation, paste in this order:

```
Continuing CarbonSaathi PromptWars Challenge 3 build.

Attached:
1. DECISIONS.md — locked project spec + §14 conventions + §15 amendments log (read first)
2. PROGRESS.md — build state through Phase 5B (read second)

Status: Phases 1A through 5B all green. Auth foundation, activity routes, dashboard
with IST timezone and streak grace, slashless route convention, redirect_slashes=False,
uniform 401 auth-failure contract — all in place. ~99.7% coverage, suite ~1.0s.

Ready for Phase 5C (insights + recommendations routes + SSE reasoning stream).

User preferences are in system context — push back first, no glazing, lead with the
most useful thing.

Continue using the established phase prompt template documented in PROGRESS.md
§ "Phase prompt template" and the 12-stage validation gauntlet established in 5B.

First actions:
1. Confirm you've read both files
2. Ask the current IST time so we can re-plan Phases 5C–11 against the Sun 18:00 IST
   submission deadline
3. Ask whether the GitHub push has happened yet (as of end of 5B it had not)
4. Then generate the Phase 5C prompt (Opus 4.8 — SSE design + dual-agent orchestration
   is more reasoning-heavy than 5A/5B) following the template
```

End of progress log.
