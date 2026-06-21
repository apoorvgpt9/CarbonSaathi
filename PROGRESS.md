# CarbonSaathi — Build Progress Log

> **Purpose:** Hand off full build state to a new Claude session so quality does not degrade.
> **Last updated:** End of Phase 5C (Saturday mid-afternoon IST)
> **Source files of truth:** This file + `DECISIONS.md` (in repo root). Read both at session start.

---

## How the next Claude session should use this file

1. Read `DECISIONS.md` first (project spec — name, persona, scope, stack, architecture, rubric strategy, schedule, implementation conventions §14, build amendments log §15)
2. Read this file second (build state, gotchas, conventions, decisions made during build, pending work)
3. **Do not re-derive decisions already locked.** If something here conflicts with the user's new message, ask before overriding.
4. Maintain the established workflow conventions (see § "Operational conventions" below)
5. Maintain the established phase prompt template (see § "Phase prompt template" below)
6. Continue from where § "Pending phases" picks up. Phase 6 (HTMX + Tailwind frontend) is next.

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
| **Coverage target** | **95%** (line + branch). Current actual after 5C: **99.66%** |
| **Test count** | **415 tests, ~1.58s** total runtime |
| **GitHub status** | Open question — confirm with user at session start whether push happened |
| **Deployment health** | `/api/health` returns `{"status":"ok","version":"0.1.0"}` (last verified Phase 1D; code changes since then are NOT yet deployed — Phase 9 re-deploys) |
| **Phases complete** | 1A, 1B, 1C, 1D, 2, 3, 4A, 4B, 5A, 5B, **5C** |
| **Next phase** | **6 — Frontend (HTMX + Tailwind, Sonnet 4.6)** |

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

### Phase 5C — Insights + recommendations routes + SSE reasoning stream

**Goal achieved:** Single generator endpoint orchestrates Analyst → Coach, with SSE reasoning stream as the rubric differentiator. Read-only listers for cached results. Recommendation accept mutation.

**Spec-vs-reality reconciliations (DECISIONS.md §15 #16):**
- `AnalystAgent.__init__` takes **only** `gemini_factory`, NOT `emission_service`. Coach takes both. Get this right in any future factory wiring.
- Agent method signatures are keyword-only with `user_id` (NOT `uid`) param: `analyst.generate_insights(*, activities, user_id, now=None)` — no profile param. `coach.generate_recommendations(*, profile, activities, insights, user_id, now=None)` — param is `activities`, not `recent_activities`.
- `AnalystSuccess` / `CoachSuccess` carry **no top-level `agent_reasoning`**. Reasoning is per-item on `outcome.insights[0].agent_reasoning.reasoning_steps`. The orchestrator uses first-item aggregation (all items in a single Gemini call share the same reasoning trace — denormalized across items because §8's data model has nowhere else to put it) with a defensive `if outcome.insights:` guard before indexing.
- `FirestoreService` already had `add_insight`, `get_recent_insights`, `add_recommendation`, `accept_recommendation` (added during Phase 4B integration test scaffolding). Only **3** new methods added in 5C: `get_recent_recommendations`, `get_generation_state`, `set_generation_state`.
- `accept_recommendation` stays **non-transactional**. Path-scoping under `users/{uid}/recommendations/` makes cross-user writes impossible; same-user double-accept is idempotent at `accepted=True`. Transaction would be theatre.

**Files created:**
- `app/models/generation_state.py` — `GenerationState` frozen model with `analyst_status: Literal["success","empty","failed"]` + `coach_status: Literal["success","empty","failed","skipped"]` (NO overall `status` field), `last_completed_at: IsoTimestamp`, `empty_reason`, `failed_reason`. Stored at `users/{uid}/state/generation` (collection `state`, doc `generation`).
- `app/services/staleness.py` — `is_pipeline_stale()` pure function + `StalenessResult` frozen model. Five branches: `no_prior_run`, `ist_day_change`, `new_activity_since_last_run`, `analyst_empty_ttl_expired`, `coach_empty_ttl_expired`. Branches 4 and 5 are **independent OR `if` statements** (not if/elif) — `analyst_status="success" AND coach_status="empty"` correctly hits branch 5. Local `IST = ZoneInfo("Asia/Kolkata")` constant per DECISIONS.md §14.5.
- `app/services/orchestrator.py` — `run_insight_pipeline()` async generator + `OrchestratorEvent` discriminated union (`PhaseStart` / `ReasoningStep` / `PhaseComplete` / `Done`, each `frozen=True, extra="forbid"`, with `event: Literal[...]` discriminator). Pure orchestration logic — no FastAPI imports, no SSE knowledge. Cached path emits two `PhaseComplete(status="cached")` events + `Done` with cached insights/recs fetched from Firestore; **no `PhaseStart` events on cached path**; **no `set_generation_state` call on cached path** (asserted in tests).
- `app/routes/insights.py` — `GET /api/insights` (read-only lister) + `GET /api/insights/stream` (content-negotiated generator). DTOs: `InsightListResponse`. Module constant `SSE_INTER_EVENT_DELAY_S = 0.08` (tests monkeypatch to 0). Content negotiation: JSON only when `"application/json" in accept and "text/event-stream" not in accept`; otherwise SSE (no Accept, `*/*` httpx default, `text/event-stream`, AND both-present all → SSE). Profile fetched at route layer; if `firestore.get_user(uid)` returns None, raises `HTTPException(500, "Server error")` with structlog ERROR `event="route.profile_missing"`.
- `app/routes/recommendations.py` — `GET /api/recommendations` (read-only) + `POST /api/recommendations/{rec_id}/accept`. DTOs: `RecommendationListResponse`, `AcceptResponse`. 404 with `{"detail":"Recommendation not found"}` on missing (same message for nonexistent and other-user — path-scoped, no info leak).
- `tests/_sse.py` — minimal `parse_sse(text) -> list[SSEEvent]` helper.
- `tests/test_services_orchestrator.py`, `tests/test_services_staleness.py`, `tests/test_routes_insights.py`, `tests/test_routes_recommendations.py` — full coverage of all 6 orchestrator flows + all 6 staleness branches + content negotiation + auth + cached path.

**Files modified:**
- `app/agents/factories.py` — added `get_analyst_agent()` (gemini_factory only) and `get_coach_agent()` (gemini_factory + emission_service), both `@lru_cache(maxsize=1)`.
- `app/services/firestore_service.py` — added 3 methods only (`get_recent_recommendations`, `get_generation_state`, `set_generation_state`). All follow existing patterns (AsyncClient, `order_by(..., DESCENDING)` where ordering matters, `model_validate` on read, `model_dump(mode="json")` on write, structured logging on error).
- `app/main.py` — registered `insights.router` and `recommendations.router` under `/api`.
- `tests/conftest.py` — added `analyst_agent_mock` and `coach_agent_mock` fixtures; extended `client_with_user` to override `get_analyst_agent` and `get_coach_agent`.
- `tests/test_firestore_service.py`, `tests/test_agents_factories.py` — appended coverage tests for new methods/factories.

**Coverage delta:** ~99.7% → **99.66%** (415 tests, 1.58s). All 5 new Phase 5C modules at **100% coverage**. The 5 remaining `firestore_service.py` partials are pre-existing defensive branches, untouched by this phase.

**Validation gauntlet status (12 stages):**
- Stages 0–4: passed
- Stage 5 (functional acid tests): passed AFTER fixing `curl -sI` HEAD-default trap (see Critical gotchas below) — all 8 sub-checks return expected status/length/content-type
- Stage 6 (auth consistency loop across all 4 routes × 4 bad-header variants): **NOT run** — open for Phase 6 session or before submission
- Stage 7 (grep contracts): partially run — 7.3 (no `EventSource`) and 7.10 (orchestrator ERROR logging) not explicitly verified; slashless invariant confirmed via direct file reads of both new route files
- Stage 8 (security headers): confirmed clean via Stage 5's 401 response header dump (CSP, HSTS, X-Frame-Options, X-Content-Type-Options all present; X-Accel-Buffering correctly absent on 401)
- Stage 9 (shutdown): pending
- Stage 10 (PROGRESS.md update): completed via this session
- Stage 11 (commit + push + CI): **NOT done** — see Open questions

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

### Single generator endpoint, content-negotiated (Phase 5C)
DECISIONS.md §9 originally had three generation entry points (`/api/insights`, `/api/insights/stream`, `/api/recommendations`). Phase 5C collapsed this to ONE: `/api/insights/stream`. `/api/insights` and `/api/recommendations` are read-only listers. The stream endpoint does content negotiation: SSE for `text/event-stream`, single JSON for `application/json`-only. Removes cache-coherence bugs and double-generation under burst load. See §15 #11, #12.

### Two independent empty-TTL branches in staleness (Phase 5C)
`is_pipeline_stale` has two parallel `if` statements (not if/elif): `analyst_status == "empty" AND age > 10min` AND `coach_status == "empty" AND age > 10min`. Handles the post-onboarding-without-new-activity edge case where Coach was empty (not-onboarded) and user has since onboarded but not logged. Independent branches mean `analyst_status="success" AND coach_status="empty"` correctly returns stale on the second branch. See §15 #13.

### Cached path emits no PhaseStart and no set_generation_state (Phase 5C)
When `is_pipeline_stale` returns False, the orchestrator fetches cached insights + recommendations from Firestore and yields: two `PhaseComplete(status="cached")` events + one `Done`. No `PhaseStart` (no phase actually runs). No `set_generation_state` call (cached state is what it was). Tests assert zero agent calls AND zero `set_generation_state` calls on this path.

### First-item reasoning aggregation with defensive guard (Phase 5C)
`AnalystSuccess`/`CoachSuccess` carry no top-level `agent_reasoning`. Reasoning lives per-item on `outcome.insights[0].agent_reasoning.reasoning_steps`. Since one Gemini call produces 1-3 items sharing one trace (denormalized across items by data model constraint), first-item is the canonical reading. Defensive `if outcome.insights:` / `if outcome.recommendations:` guards before indexing — protects against future success-contract drift.

### Profile fetched at route layer, not orchestrator (Phase 5C)
Routes call `firestore.get_user(uid)` themselves; orchestrator's `profile: UserProfile` param is strict (not Optional). If profile is None at the route, raise `HTTPException(500, "Server error")` with structlog ERROR `event="route.profile_missing"`. This is server-state corruption (every authenticated user has a profile created by `/auth/verify` in 5A) — graceful-empty would mask the bug.

### SSE inter-event sleep in route, not orchestrator (Phase 5C)
`SSE_INTER_EVENT_DELAY_S = 0.08` lives in `app/routes/insights.py`. Tests monkeypatch to 0. Orchestrator is pure logic with no sleep — keeps it framework-agnostic and lets the JSON path skip the delay entirely.

### Non-transactional accept_recommendation is correct (Phase 5C)
`accept_recommendation(uid, rec_id)` uses read-then-update, NOT a transaction. Recs are path-scoped under `users/{uid}/recommendations/`, so cross-user writes are structurally impossible. Same-user double-accept is idempotent at the data level (`accepted=True` regardless of write count). Transaction would be theatre.

---

## Critical gotchas (DO NOT re-discover)

### Coverage threshold is 95% (NOT 80%)
Default plan said 80%. User raised to 95% early. Every phase must keep the threshold. Current actual ~99.66% after Phase 5C.

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

### `curl -sI` defaults to HEAD — false 405s on stream/POST routes (Phase 5C)
`curl -sI` sends `HEAD` by default. Routes that return a non-standard `Response` (e.g. `StreamingResponse` for `/api/insights/stream`, or routes typed for content negotiation) may not auto-support HEAD via Starlette's usual GET→HEAD inference, returning **405 Method Not Allowed** instead of the expected 401. This makes validation runs look broken when they aren't — and the `content-length: 31` of Starlette's auto-generated 405 body is also a different shape than the uniform 401 contract's 34 bytes, which is a separate false alarm. **Always use explicit `-X GET` / `-X POST` in gauntlet curl commands**, not bare `-sI` against GET-only or POST-only routes. Phase 5C stages 4.3, 5.1–5.8, 6.1–6.4 all needed this fix.

### grep against multi-line route decorators silently misses (Phase 5C)
`black` wraps long `@router.get(...)` / `@router.post(...)` decorators onto multiple lines when args (path + `response_model=` + `summary=`) exceed line-length 100. A regex like `grep -nE '@router\.(get|post)\("' app/routes/foo.py` matches only single-line decorators and silently returns no output for multi-line ones. The slashless invariant check (stages 2.2, 2.3, 7.1) needs either a multi-line-aware pattern (`grep -rnE '@router\.(get|post|put|delete|patch)\(\s*"/"\s*,?\s*$' app/routes/`) or direct file inspection. **Don't trust an empty grep result against route files; verify by file dump.**

### Double `Server:` header is pre-existing, deferred to Phase 7 (discovered Phase 5C)
Every response carries TWO `Server:` headers: `server: uvicorn` AND a blank `server: ` (the `secure` library appends a blank one to obscure server software; uvicorn's own header isn't stripped). Present since Phase 1B; confirmed by curl on `/api/health`. Not 5C-introduced. **Phase 7 fix:** either configure `uvicorn.run(server_header=False)` (or set in Cloud Run startup config), OR have the security headers middleware overwrite rather than append. Out of scope for 5C.

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
| **5C Insights + recs + SSE** | **Opus 4.8** | done |
| **6 Frontend** | **Sonnet 4.6** | **NEXT** |
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

### Phase 6 — Frontend (HTMX + Tailwind, Sonnet 4.6, NEXT)

Server-rendered HTMX pages with Tailwind via CDN. Pages: sign-in (Firebase Google Sign-In), onboarding, dashboard (today's footprint + week chart + streak), log activity (textarea POSTing to `/api/activities`, response renders parsed Activity + agent_reasoning), insights feed (cards with reasoning expandable + live render via SSE), recommendations (cards with Accept button).

Semantic HTML, ARIA labels, keyboard navigation, WCAG AA contrast, `prefers-reduced-motion` respected. Slashless paths in all `hx-post` / `hx-get` attributes. Tighten `ALLOWED_ORIGINS` from `*` to deployed URL.

**SSE consumption note (DECISIONS.md §15 #15):** Phase 6 MUST use `fetch()` + ReadableStream reader for SSE consumption, NOT `EventSource`. EventSource cannot send custom `Authorization` headers, and the uniform 401 contract requires `Authorization: Bearer …` on `/api/insights/stream`. The fetch+stream pattern is more code but is the only path that works with header auth.

**Content negotiation reminder:** `/api/insights/stream` returns SSE for `Accept: text/event-stream` (or no Accept, or `*/*`, or both Accept types) and single JSON for `Accept: application/json` only. Phase 6's `fetch()` call should set `Accept: text/event-stream` explicitly to lock in the streaming path.

**Phase 6 entry-point checklist:**
- Firebase Auth web SDK config must exist in the Firebase console (currently an open question — see below).
- OAuth client redirect URI: add the Cloud Run URL to authorized redirects.
- `ALLOWED_ORIGINS` tightening: replace `*` with the actual Cloud Run URL.

### Phase 7 — Security hardening (Sonnet 4.6)

CSP / HSTS / X-Frame-Options / X-Content-Type-Options / Referrer-Policy / Permissions-Policy verified on every response status. Per-user rate limiting via Firebase uid keying on slowapi (per-user 30/min on insight generation, 60/min on stream). Prompt injection tests against real route handlers. OWASP Top 10 manually walked with documented mitigations. Confirm `redirect_slashes=False` still in place.

**Phase 7 carry-ins (logged from 5C):**
- Fix the double `Server:` header (uvicorn + blank from `secure` middleware) — see Critical gotchas.
- Complete unfinished 5C validation gauntlet stages 6 (auth consistency loop), 7.3 (no `EventSource`), 7.10 (orchestrator ERROR logging) if not already verified by then.
- Verify `pip-audit` status for `pydantic-settings` 2.14.1 (installed) vs 2.14.2 (pinned in pyproject) — currently unverified; was 5C's only `pip-audit` finding and is pre-existing (not 5C-introduced). Likely just `pip install -e ".[dev]" --upgrade` realigns the venv.

### Phase 7 — Security hardening (DONE)

Phase 7 hardened the security posture without adding agent code, prompt changes, or new functional features. 11 tasks executed across 6 batches (A1–A6, B1–B5) and validated end-to-end with the standard gauntlet.

**Delivered (code changes):**

- **A1 — Double `Server` header fixed.** Switched dev/prod entrypoints to `uvicorn --no-server-header`; the secure-headers middleware no longer collides with uvicorn's default header. Verified by live curl on `/api/health` — no `server:` line in response. Added a regression test that asserts the `server` header is absent.
- **A2 — HTMX CDN removed.** Deleted the unpkg.com HTMX include and the `htmx_bearer.js` shim. Replaced with a hand-rolled [`app/static/js/api_client.js`](app/static/js/api_client.js) `authedFetch(url, options)` that pulls the ID token from `window.csaathi.auth`, refreshes once on 401, and redirects to `/` on the second 401. All page-level fetches in `dashboard_page.js`, `log_page.js`, `insights_page.js`, `onboarding_page.js`, and `recommendations_page.js` now route through it. CSP `script-src` updated to drop `unpkg.com`.
- **A3 — auth.js comment fix.** Trivial doc fix — `Promise` casing and removed a stale HTMX reference.
- **A4 — `ALLOWED_ORIGINS` tightened.** Default now lists only the two production hosts (Cloud Run service URL + Firebase hosting URL); `*` is no longer the fallback. Documented in `.env.example`.
- **A5 — `pip-audit` clean.** Upgraded `pip` (CVE-2025-8869, 2 advisories) and `pydantic-settings` to 2.14.2 (3 advisories). Audit run at end of phase reports zero known vulnerabilities.
- **A6 — Staleness `previous_run_failed` branch.** Added explicit handling in [`app/services/staleness.py`](app/services/staleness.py) so a partially-written orchestrator state is detected and triggers regeneration rather than serving stale half-results. Two new tests cover the branch.
- **B1 — Security headers on every status.** Wrapped `_set_security_headers` in a `try/except` that logs `unhandled_exception` via structlog and returns a `JSONResponse({"detail": "Internal Server Error"})` — with all security headers still applied. New parametrized test ([`tests/test_security.py`](tests/test_security.py)::`test_security_headers_emitted_on_every_status`) walks 200/401/404/422/500 via a sub-app fixture with four synthetic probe routes.
- **B2 — Per-user rate limiting.** Pulled `slowapi.Limiter` construction out into [`app/core/ratelimit.py`](app/core/ratelimit.py) with a `key_uid_or_ip(request)` key function that prefers `request.state.user.uid` (set by `verify_firebase_token`) and falls back to source IP for pre-auth routes. Decorators applied per the table below:

  | Route                                | Limit       | Key       |
  |--------------------------------------|-------------|-----------|
  | `POST /api/auth/verify`              | 30/min      | source IP |
  | `POST /api/activities`               | 30/min      | uid       |
  | `GET  /api/activities`               | 60/min      | uid       |
  | `GET  /api/dashboard`                | 60/min      | uid       |
  | `GET  /api/insights`                 | 60/min      | uid       |
  | `GET  /api/insights/stream`          | 30/min      | uid       |
  | `GET  /api/recommendations`          | 60/min      | uid       |
  | `POST /api/recommendations/{id}/accept` | 30/min   | uid       |
  | `GET  /api/users/me`                 | 60/min      | uid       |
  | `POST /api/users/onboarding`         | 30/min      | uid       |

  Four new tests in [`tests/test_ratelimit.py`](tests/test_ratelimit.py) cover the key function plus an integration test that fires 30 successful requests + a 31st that gets 429. Limiter is disabled at module load in `tests/conftest.py` so the rest of the suite isn't 429'd.
- **B3 — Prompt-injection integration tests.** [`tests/test_security_injection.py`](tests/test_security_injection.py) drives 12 representative payloads (`ignore_previous`, `disregard_above`, `system_prompt_leak`, `role_override`, `act_as_pirate`, `reveal_instructions`, `sudo_priv_escalation`, `system_tag_injection`, `forget_everything`, `forget_all_previous`, `assistant_tag_inject`, `ignore_all_prior`) through the real route + real LoggerAgent with **only** `_model.generate_content_async` swapped for an `AsyncMock` that raises if invoked. Every payload returns 400 with a `reason` field and the Gemini SDK call count stays at 0.
- **B4 — `SECURITY.md` walkthrough.** Added [`SECURITY.md`](SECURITY.md) at repo root: full OWASP Top 10 (2021) walkthrough, one paragraph per category, citing the specific code path or test that backs each claim.

**Out of scope per pre-approved decisions (D7):** no agent code changes, no prompt-template changes, no model-selection changes, no edits to `scripts/03_deploy.sh`, no README changes, no `redirect_slashes` flip, no auth-failure contract changes, no IST-policy changes.

**Files NOT touched (pre-existing uncommitted WIP, owner: prior phase):**
- `app/core/config.py` — commented `gemini_model_pro`
- `app/core/gemini.py` — `pro_model=settings.gemini_model_flash` workaround
- `app/services/firestore_service.py` — `_iso_z()` helper + range-filter timestamp fix

**B5 — Validation gauntlet results:**

| Stage                                                    | Result          |
|----------------------------------------------------------|-----------------|
| 1. `ruff check .` (touched files)                        | clean           |
| 2. `mypy app` (strict)                                   | clean — 44 files, 0 issues |
| 3. `bandit -r app`                                       | clean — 0 issues across 4 447 LOC |
| 4. `pip_audit`                                           | clean — 0 known vulnerabilities |
| 5. `pytest --cov-fail-under=95`                          | **469 passed, 1 failed**, 99.68% coverage, 4.95 s |
| 6. Test budget < 60 s                                    | 4.95 s — under by 12× |
| 7. `uvicorn` smoke + `curl` `/api/health` headers        | 200 OK, all security headers present, no `server:` line |
| 8. CSP excludes `unpkg.com`                              | verified by curl |
| 9. HSTS = `max-age=31536000; includeSubDomains`          | verified by curl |
| 10. `SECURITY.md` present at repo root                   | done |
| 11. PROGRESS.md updated with Phase 7 results             | (this section) |
| 12. Carry-ins triaged                                    | see below |

The one failing test (`tests/test_core_gemini.py::test_pro_builds_pro_model`) is the D7 Pro→Flash workaround and is pre-existing — explicitly excluded from Phase 7 scope.

**Known lint carry-ins (deferred — both protected by D7):**
- `app/core/gemini.py:105` — E501 (line too long) from the inline TODO comment on the Pro→Flash workaround.
- `app/services/firestore_service.py:464` — W292 (no trailing newline) from prior-phase WIP.

These two will fall out naturally when the Pro→Flash workaround is reverted and the firestore_service WIP lands.

### Phase 8 — Test sweep (Sonnet 4.6)

Push coverage to 99%+ on Phase 6–7 deltas. Fix any flakes. Add golden-set regression tests for Analyst and Coach via 4B fixtures. Integration tests for full route → agent → Firestore chain (Firestore mocked).

### Phase 9 — Deploy + perf check (Sonnet 4.6)

Re-deploy. Load test 50 concurrent. Verify p95 < 2s. Verify `min-instances=1` still set. Verify no 500s under load. **Verify SSE endpoint streams correctly through Cloud Run's HTTP/2 load balancer** (the most uncertain piece — Cloud Run HTTP/2 buffering can break SSE in subtle ways; flag if any odd behavior shows up).

### Phase 10 — README + manual eval polish (Opus 4.8)

Manual evaluators read the README. Sections needed:
- Project narrative (problem → user → approach → result)
- Architecture diagram (Mermaid)
- Agent flow diagram (Mermaid)
- 3–5 ADR-style decisions with alternatives considered
- Screenshots
- Honest limitations (single-language UI, no historical import, India-only, food factor methodology rough, **SSE chunks emit post-completion not mid-flight**, **`fetch()` + ReadableStream consumer required for SSE auth**)
- Run / deploy instructions
- License + credits

### Phase 11 — Submission #1 (baseline)

Push everything to GitHub. Capture AI evaluator score per criterion. Save scores for Phase 12 decision.

### Phase 12 — Submission #2 (conditional)

Only if Submission #1 reveals a clear, fixable gap on a specific criterion AND a hypothesis for the fix with measurable expected delta. **No Submission #3 under any circumstance** (ElectEd precedent: third attempt regressed Efficiency 100% → 80%).

---

## Open questions for the next session

1. **Current time / schedule recovery.** Phase 5C completed Saturday mid-afternoon IST. Re-plan remaining phases (6–11) against the Sun 18:00 IST submission target. Phase 6 (frontend) is the longest remaining phase; budget accordingly.
2. **GitHub push status.** As of end of 5C, push was still deferred. SPOF risk has compounded across 11 phases now. **Strong recommendation:** push at the start of the next session, before Phase 6 work begins. CI on the cumulative repo is overdue.
3. **Phase 5C unfinished validation gauntlet stages.** Stage 6 (auth consistency loop: 4 routes × 4 bad-header variants), stage 7.3 (`grep EventSource`), stage 7.10 (`grep ERROR logging in orchestrator`), and stage 11 (commit + push + CI) were NOT run. None block Phase 6 start, but should be cleared before submission.
4. **`pip-audit` finding: `pydantic-settings` 2.14.1 vs 2.14.2 pin.** Not 5C-introduced; pre-existing venv-vs-pin drift. Likely cleared by `pip install -e ".[dev]" --upgrade`. Verify before Phase 9 deploy.
5. **Empty-list defensive guard test coverage.** The orchestrator has `if outcome.insights:` / `if outcome.recommendations:` defensive guards before first-item indexing. These are structurally unreachable on a well-behaved `AnalystSuccess`/`CoachSuccess` (which by spec carry ≥1 item). Whether the orchestrator's 100% coverage actually exercises these branches (via synthetic empty-list success constructors) vs. tooling counting them as covered some other way is unverified.
6. **Firebase Auth client setup.** Phase 1D enabled the firebase API. The actual Firebase Authentication client config (web SDK config for Google Sign-In) needs to be created in the Firebase console **before** Phase 6 frontend can sign users in. Confirm at session start.
7. **Gemini quota / billing.** Phases 4, 5A, 5B, 5C all mocked Gemini. Phase 6 frontend hitting `/api/insights/stream` will hit real Gemini in dev. Confirm `gemini-api-key` secret has live key with quota.
8. **OAuth client redirect URI.** Firebase Google Sign-In needs the Cloud Run URL added as an authorized redirect. Do this when UI ships in Phase 6.
9. **README owner placeholder.** CI badge in README.md has `<owner>` placeholder unless already sed-substituted. Confirm.
10. **SSE behind Cloud Run load balancer.** Cloud Run HTTP/2 buffering can break SSE in subtle ways. Phase 9 will validate; flag if any odd behavior shows up earlier in Phase 6 once a real client is consuming the stream.

---

## Reference: handoff to a new Claude session

When opening a new Claude conversation, paste in this order:

```
Continuing CarbonSaathi PromptWars Challenge 3 build.

Attached:
1. DECISIONS.md — locked project spec + §14 conventions + §15 amendments log
   (includes Phase 5C amendments #11–#16; read first)
2. PROGRESS.md — build state through Phase 5C (read second)

Status: Phases 1A through 5C all green. Auth foundation, activity routes, dashboard
with IST timezone and streak grace, insights + recommendations routes, SSE reasoning
stream with content negotiation, slashless route convention, redirect_slashes=False,
uniform 401 auth-failure contract — all in place. 415 tests / 99.66% coverage / ~1.58s
suite.

Ready for Phase 6 (HTMX + Tailwind frontend, Sonnet 4.6).

User preferences are in system context — push back first, no glazing, lead with the
most useful thing.

Continue using the established phase prompt template documented in PROGRESS.md
§ "Phase prompt template" and the 12-stage validation gauntlet established in 5B
§ "Comprehensive validation gauntlet". For curl commands in stages 4–6, use explicit
-X GET / -X POST flags — bare `curl -sI` causes false 405s on stream/POST routes
(see Critical gotchas).

First actions:
1. Confirm you've read both files (and call out anything in DECISIONS.md §14, §15,
   or the Phase 5C section of PROGRESS.md that's load-bearing for Phase 6 frontend
   work — especially §15 #15 about fetch+ReadableStream for SSE consumption)
2. Flag any of the Open questions in PROGRESS.md that are now actionable (GitHub
   push status, Firebase Auth web SDK config, Gemini quota for live calls, the
   unfinished 5C gauntlet stages 6/7.3/7.10/11)
3. Then generate the Phase 6 prompt (Sonnet 4.6 — HTMX + Tailwind, server-rendered,
   no build step) following the established phase prompt template
```

End of progress log.
