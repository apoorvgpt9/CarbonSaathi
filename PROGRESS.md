# CarbonSaathi — Build Progress Log

> **Purpose:** Hand off full build state to a new Claude session so quality does not degrade.
> **Last updated:** End of Phase 4B
> **Source files of truth:** This file + `DECISIONS.md` (in repo root). Read both at session start.

---

## How the next Claude session should use this file

1. Read `DECISIONS.md` first (project spec — name, persona, scope, stack, architecture, rubric strategy, schedule)
2. Read this file second (build state, gotchas, conventions, pending work)
3. **Do not re-derive decisions already locked.** If something here conflicts with the user's new message, ask before overriding.
4. Maintain the established workflow conventions (see § "Operational conventions" below)
5. Maintain the established phase prompt template (see § "Phase prompt template" below)
6. Continue from where § "Pending phases" picks up

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
| **GCP project ID** | `prompt-wars-virtual-carbon-3` |
| **GCP region** | `asia-south1` |
| **Cloud Run service name** | `carbonsaathi` |
| **Deployed URL** | `https://carbonsaathi-ahkpdce5pa-el.a.run.app` |
| **Service account** | `carbonsaathi-runner@prompt-wars-virtual-carbon-3.iam.gserviceaccount.com` |
| **Secret Manager secrets** | `gemini-api-key`, `firebase-api-key` |
| **Python version** | 3.13.7 (on user's Mac) |
| **Python command** | `python3` (NOT `python`) |
| **Coverage target** | **95%** (NOT the default 80% — user explicitly raised this) |
| **GitHub status** | Local commits only. **Not yet pushed.** User will push once the majority of changes are done. |
| **Test coverage at end of 4B** | 99.73% on `app/` (line + branch), 315 tests, suite ~1.2s |
| **Deployment health** | `/api/health` returns `{"status":"ok","version":"0.1.0"}` |

---

## Completed phases

### Phase 0 — Decisions

Locked: project name, persona (Riya/Rahul, 28, Indian metro professional), 3-activity scope (Transport + Electricity + Food, food as stretch), 3-agent architecture (Logger + Analyst + Coach, Devil's Advocate dropped), tech stack, Indian-only geographic focus, Firestore on Spark plan (free), Google Sign-In persistence requirement, compressed 48h schedule, hard rule of no Submission #3.

Output: `DECISIONS.md` in repo root.

### Phase 1A — Scaffold + tooling

**Files created:**
- `pyproject.toml` (PEP 621 format, requires-python `>=3.13,<3.14`)
- All ruff/black/mypy/pytest/bandit/coverage configs inline in pyproject.toml
- `.pre-commit-config.yaml`
- `.gitignore`, `.env.example`, `LICENSE` (MIT), `README.md` skeleton
- Empty `__init__.py` files for `app/core/`, `app/models/`, `app/routes/`, `app/agents/`, `app/services/`
- `tests/__init__.py` and `tests/conftest.py` (placeholders)

**Key config decisions:**
- ruff `line-length = 100`, `target-version = "py313"`, Google docstring convention, `select = ["E","W","F","I","B","C4","UP","N","D","S","RUF"]`
- mypy `strict = true`, `python_version = "3.13"`
- pytest `--cov-fail-under=95` (raised from 80 mid-build)
- bandit `skips = ["B101"]`
- pre-commit hooks: trailing-whitespace, end-of-file-fixer, check-yaml, check-toml, check-added-large-files (500KB cap), detect-private-key, ruff, ruff-format, mypy, bandit

### Phase 1B — FastAPI app core

**Files created:**
- `app/main.py` — `create_app()` factory pattern with lifespan, CORS, slowapi rate limiting, security headers middleware, `/api` prefix for routes
- `app/core/config.py` — `Settings` via pydantic-settings v2 with `SecretStr` for `gemini_api_key`, `@lru_cache` singleton `get_settings()`, validators on `app_env`, `log_level`, `allowed_origins` (CSV split)
- `app/core/logging.py` — structlog setup: `ConsoleRenderer` in dev (`app_env == "development"`), `JSONRenderer` in prod
- `app/core/security.py` — `secure` library default headers via FastAPI middleware
- `app/routes/health.py` — `GET /api/health` returns `HealthResponse(status="ok", version="0.1.0")`, version pulled from package metadata
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
- `README.md` updated with CI status badge (owner set to `apoorvgpt9`)

**Note:** Workflow file is committed locally but **not pushed**, so CI has not actually run on GitHub. It will validate when the user pushes (planned once the majority of changes are done).

### Phase 1D — GCP setup + first Cloud Run deploy

**Files created:**
- `scripts/01_gcp_setup.sh` — idempotent GCP project + APIs enabled + Firestore + IAM
- `scripts/02_load_secrets.sh` — pushes secrets into Secret Manager via stdin (no leak in process args)
- `scripts/03_deploy.sh` — `gcloud run deploy --source .` (Cloud Build handles image), two-pass ALLOWED_ORIGINS handling
- `DEPLOYMENT.md` — runbook including manual Firebase setup steps
- `Makefile` updated with `deploy`, `gcp-setup`, `gcp-secrets` targets
- `.gitignore` updated with `.deploy-url`, `*-sa-key.json`, `*-service-account.json`

**APIs enabled on GCP project:**
`run.googleapis.com`, `cloudbuild.googleapis.com`, `secretmanager.googleapis.com`, `artifactregistry.googleapis.com`, `firestore.googleapis.com`, `firebase.googleapis.com`, `iam.googleapis.com`

**Firestore:** Native mode, region `asia-south1`

**Cloud Run service config:**
- `--min-instances=1` (no cold starts)
- `--max-instances=3`
- `--cpu=1`, `--memory=512Mi`, `--port=8080`, `--timeout=60s`, `--concurrency=80`
- `--allow-unauthenticated`
- IAM roles on runner SA: `roles/datastore.user`, `roles/secretmanager.secretAccessor`, `roles/logging.logWriter`
- Plain env vars: `APP_ENV=production`, `LOG_LEVEL=INFO`, `FIREBASE_PROJECT_ID`, `FIREBASE_AUTH_DOMAIN`, `ALLOWED_ORIGINS`, `RATE_LIMIT_PER_MINUTE=30`
- Secret env vars: `GEMINI_API_KEY=gemini-api-key:latest`, `FIREBASE_API_KEY=firebase-api-key:latest`

### Phase 2 — Domain models + governance + Firestore service

**Files created:**
- `app/models/shared.py` — `AgentReasoning`, `IsoTimestamp` (UTC-enforcing `AfterValidator`), `Confidence` literal
- `app/models/user.py` — `IndianState` `StrEnum` (28 states + 8 UTs = 36), `Dietary`/`FridgeClass` literals, `HomeProfile`, `UserProfile`
- `app/models/activity.py` — `Activity`, `ActivityType`, `TransportData`, `ElectricityData` (kWh-or-bill `model_validator`), `FoodData`
- `app/models/insight.py` — `Insight`, `InsightType`
- `app/models/recommendation.py` — `Recommendation`, `RecType`, `Difficulty`
- `app/models/emission.py` — `FactorEntry`, `FactorLookupResult`
- `app/core/governance.py` — sync `check_input() -> GovernanceResult`; first-match precedence `empty` → `injection` → `abuse` → `off_topic` → `ok`
- `app/core/firebase.py` — lazy `@lru_cache` `get_firebase_app()` + `get_firestore_async_client()` (ADC; no init at import)
- `app/services/firestore_service.py` — async `FirestoreService` (`get_user`, `upsert_user`, `add_activity`, `list_activities`, `add_insight`, `get_recent_insights`, `add_recommendation`, `accept_recommendation`) + `fire_and_forget` helper + cached `get_firestore_service()`
- Tests: `test_models_*.py`, `test_governance.py`, `test_firebase_init.py`, `test_firestore_service.py`

**Key decisions:** all domain models `frozen=True` / `extra="forbid"`; timestamps tz-aware UTC (naive rejected); `float` for emissions (4-decimal precision documented). 130 tests at commit time.

### Phase 3 — Emission factor data layer

**Files created:**
- `app/data/state_grid_factors.json`, `transport_factors.json`, `food_factors.json` — every entry carries `value`, `unit`, `source`, `confidence`, `last_verified`, optional `notes`
- `app/services/emission_service.py` — `EmissionService` loads + validates all three datasets at construction, pure in-memory dict lookups afterwards; cached `get_emission_service()`
- `scripts/verify_emission_data.py` — data-integrity checks (source length, `estimated` entries require `notes`, all 36 states present)
- Tests: `test_emission_service.py`, `test_models_emission.py`, `test_verify_emission_data.py`

**Key decisions:** every `IndianState` member must have a grid entry (lookup raises `KeyError` otherwise — a data bug); all emission maths is deterministic in the service, never produced by the model.

### Phase 4A — Base agent + Gemini client + Logger

**Files created:**
- `app/core/gemini.py` — lazy `get_gemini_client()` → `GenerativeModelFactory` exposing `.flash()` / `.pro()`; `genai.configure` runs once per process
- `app/agents/base.py` — `BaseAgent` (governance gate, monotonic latency ms, `AgentReasoning` assembly, structured logging)
- `app/agents/logger_agent.py` — `LoggerAgent` (Flash + function calling); `LoggerOutcome` discriminated union (`success` / `rejected` / `failed`)
- `app/agents/prompts/logger_v1.py` — `SYSTEM_INSTRUCTION` + three `FunctionDeclaration`s; mode/category enums sourced from `EmissionService` so schemas can't drift from data
- Tests: `test_core_gemini.py`, `test_agents_base.py`, `test_agents_logger.py` + logger golden fixtures

### Phase 4B — Analyst + Coach + integration chain

**Files created:**
- `app/agents/analyst_agent.py` — `AnalystAgent` (Pro + JSON `response_schema`), `bucket_by_week`, `AnalystOutcome` (`success` / `empty` / `failed`); insights grounded to real activity IDs only
- `app/agents/coach_agent.py` — `CoachAgent` (Pro + JSON `response_schema`), typed `SavingBasis` union, deterministic `_evaluate_basis`; `CoachOutcome` (`success` / `empty` / `failed`)
- `app/agents/prompts/analyst_v1.py`, `coach_v1.py` — system instructions, response schemas, `build_user_prompt`
- Tests: `test_agents_analyst.py`, `test_agents_coach.py`, `test_integration_agent_chain.py` + analyst/coach golden fixtures

**Key decisions:** agents return typed outcomes — governance rejections and model failures are values, not exceptions; Gemini only extracts/phrases, every emission and saving figure is computed locally; every output carries a populated `AgentReasoning` trace.

---

## Critical gotchas (DO NOT re-discover)

These cost us real time. Capture them so the next session avoids them.

### Coverage threshold

The default plan said 80%. User pushed back early in the build — **target raised to 95%**. Don't reset this. Every phase from 2 onwards must add tests to keep the threshold met.

### mypy + third-party libs without stubs

`secure`, `slowapi`, `structlog` ship without type stubs. Added `[[tool.mypy.overrides]]` blocks with `ignore_missing_imports = true` for these modules in `pyproject.toml`. Any new dep added later that lacks stubs needs the same treatment.

### pre-commit mypy hook misses imports

The pre-commit mypy hook runs in its own isolated venv. It cannot see prod deps unless they're listed in `additional_dependencies` on the mypy hook entry. The current list includes: `fastapi`, `pydantic>=2.0`, `pydantic-settings`, `structlog`, `slowapi`, `secure`, `httpx`, `starlette`, `pytest`, `python-dotenv`, `google-generativeai`, `firebase-admin`. **Add to this list whenever a new prod dep lands.**

### GCP IAM propagation race

Service account creation and IAM policy binding hit a race: SA exists but IAM API hasn't seen it yet → "Service account does not exist" on `add-iam-policy-binding`. Mitigation: re-run the script (idempotent). For future projects, add a retry-with-backoff loop around the IAM bindings.

### `--condition=None` required on `add-iam-policy-binding`

Without it, gcloud prompts about binding conditions and the script breaks in non-interactive mode. All `gcloud projects add-iam-policy-binding` calls must have `--condition=None --quiet`.

### `gcloud run deploy` requires `--source` or `--image` on every call

A two-pass deploy pattern (deploy once → capture URL → "re-deploy" to update env vars) breaks if the second call uses `gcloud run deploy` without source. **Use `gcloud run services update --update-env-vars=...` for env-var-only changes.** No rebuild, ~10s vs ~5min.

### gcloud format projection — slashes in annotation keys

`autoscaling.knative.dev/minScale` contains a `/` which is special in format projections. Escape with quotes: `--format='value(spec.template.metadata.annotations."autoscaling.knative.dev/minScale")'`. Or just `gcloud run services describe ... | grep -i minscale`.

### ALLOWED_ORIGINS handling on first deploy

Cloud Run URL is not known until after first deploy. The current `scripts/03_deploy.sh` deploys with `ALLOWED_ORIGINS=*` on first run, captures URL, then `services update` to set actual URL. State is persisted to `.deploy-url` (gitignored).

### Python version

User has Python 3.13.7. All configs target 3.13. Earlier draft plans referenced 3.11; the stale `DECISIONS.md` § 6 reference was corrected at end of Phase 4B. If any 3.11 reference resurfaces, flag it as stale.

### Use `python3`, not `python`

User's shell uses `python3` as the command. All shell scripts, Makefile targets, and validation commands must use `python3` (outside the venv). Inside an activated venv, both work but stay consistent.

---

## Operational conventions

These were established during Phase 1. Continue applying them.

### User is NOT pushing to GitHub during the build

Local commits only. The user will push once the majority of changes are done (not on a fixed clock time). CI workflow exists but has never actually run yet (only push triggers it). User acknowledged the risks (no CI validation until the batched push, single point of failure, batched-push debug pain) and chose this path.

### Deployment from local, not from GitHub

`gcloud run deploy --source .` uploads local source to Cloud Build directly. No need to push to GitHub before deploying.

### Model selection per phase

User has GitHub Copilot with Claude models. Switch model per phase to control credit cost:

| Phase | Recommended model | Rationale |
|---|---|---|
| 1A scaffold | Sonnet 4.6 | Boilerplate |
| 1B FastAPI core | Opus 4.8 (used) | Slightly heavy |
| 1C CI | Sonnet 4.6 | YAML, well-trodden |
| 1D GCP scripts | Sonnet 4.6 | Shell, well-trodden |
| 2 Models + governance | Sonnet 4.6 | Pydantic + logic |
| 3 Emission data | Sonnet 4.6 | Data structures |
| 4 Agents | **Opus 4.8** | Architecture-heavy; this is the differentiator |
| 5 API routes | Sonnet 4.6 | CRUD-shaped |
| 6 Frontend | Sonnet 4.6 | HTMX + Tailwind, simple |
| 7 Security hardening | Sonnet 4.6 | Mostly config |
| 8 Test sweep | Sonnet 4.6 | Routine |
| 9 Deploy + perf | Sonnet 4.6 | Routine |
| 10 README + polish | **Opus 4.8** | Narrative quality matters for manual eval |
| 11 Submission #1 | n/a | No code |
| 12 Submission #2 | Sonnet 4.6 | Targeted fixes |

**Always flag model recommendation at the start of each phase prompt.**

### Long-context cost mitigation

Each new Copilot session needs a compact context block (not the full conversation). The block is ~50 lines: project + stack + completed phases + hard rules + repo state command. The format is established in earlier messages; preserve it.

### Phase prompt template

Every phase prompt I generate follows this structure. **Continue using it.**

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

Every Copilot prompt MUST tell Copilot to output a numbered plan first and **STOP** before writing files. This catches scope drift before code is generated. Step 2 only runs after user confirms the plan.

---

## Quality gates (apply to every phase)

- **95% test coverage** maintained on the `app/` package (line + branch)
- `mypy --strict` zero errors
- `ruff check .` zero warnings
- `bandit -c pyproject.toml -r app` zero issues
- `pip-audit` clean
- Every file with code beyond a docstring starts with `from __future__ import annotations`
- Every public function/class has a Google-style docstring with Args/Returns/Raises
- No hardcoded secrets — only load from `Settings`
- No new dependency added without updating `pyproject.toml` AND `.pre-commit-config.yaml` mypy `additional_dependencies`
- Every async path is truly async — no sync I/O inside async
- All new routes register under the `/api` prefix
- `/api/health` must always remain functional (existing tests guard this)

---

## Pending phases

Phases 2, 3, 4A, and 4B are complete (see § "Completed phases" above). Phase 5 is next. The original 48h schedule slipped on debug iterations (mypy stubs, IAM race, ALLOWED_ORIGINS, gcloud syntax); re-prioritise the remaining phases against the Sunday 18:00 IST target.

### Phase 5 — API routes (NEXT)

`POST /api/activities`, `GET /api/activities`, `GET /api/insights`, `GET /api/insights/stream` (SSE), `GET /api/recommendations`, `POST /api/recommendations/{id}/accept`, `GET /api/dashboard`, `POST /api/onboarding`, `POST /api/auth/verify`, `GET /api/users/me`.

Firebase ID token verification on all protected routes via dependency.

### Phase 6 — Frontend (HTMX + Tailwind)

Dashboard with footprint visualization (trend chart), activity logging form (NL input), insights feed, agent reasoning stream view, settings. Semantic HTML + ARIA + keyboard nav + WCAG AA contrast.

Tighten CORS: change `ALLOWED_ORIGINS=*` (set during Phase 1D) to the actual deployed URL.

### Phase 7 — Security hardening

CSP/HSTS/X-Frame-Options/X-Content-Type-Options/Referrer-Policy/Permissions-Policy verified, rate limiting tuned, prompt injection tests added, OWASP Top 10 manually walked through with documented mitigations.

### Phase 8 — Test sweep

Push coverage to 95%+, fix any flakes, add golden-set regression tests for each agent, add integration tests for full chain.

### Phase 9 — Deploy + perf check

Re-deploy with all changes. Load test 50 concurrent requests. Verify p95 < 2s. Verify min-instances still 1. Verify no 500s under load.

### Phase 10 — README + manual eval polish

**This is the second phase needing Opus 4.8.** Manual evaluators read the README. Sections needed:
- Project narrative (problem → user → approach → result)
- Architecture diagram (Mermaid)
- Agent flow diagram
- 3–5 ADR-style decisions with alternatives considered
- Screenshots
- Honest limitations
- Run / deploy instructions
- License + credits

### Phase 11 — Submission #1 (baseline)

Push everything to GitHub (single branch, public, <10MB). Capture AI evaluator score per criterion.

### Phase 12 — Submission #2 (conditional)

Only if Submission #1 reveals a clear, fixable gap on a specific criterion AND we have a hypothesis for the fix. Each change must have a measurable expected delta. **No Submission #3 under any circumstance** (ElectEd precedent: third attempt regressed Efficiency 100% → 80%).

---

## Open questions for the next session

1. **Current time / schedule recovery.** We are behind schedule because of debug iterations. The user has not stated the current time. New session should ask "what time is it now?" to re-plan remaining phases against the Sunday 18:00 IST submission target.
2. **ALLOWED_ORIGINS tightening.** Currently set to the deployed URL after `services update`. When the UI ships in Phase 6 this stays correct. No action needed unless something changes.
3. **README CI badge owner — RESOLVED.** The badge points at `apoorvgpt9/carbonsaathi`; no placeholder remains.
4. **Push timing.** The user pushes once the majority of changes are done (no fixed clock deadline). CI first runs at that batched push.
5. **Live Gemini calls deferred to Phase 5.** Phases 4A/4B shipped on fully mocked Gemini; no real quota was consumed. Confirm the Gemini API key in Secret Manager works before Phase 5 wires the agents into live routes.

---

## Reference: handoff to a new Claude session

When opening a new Claude conversation, paste in this order:

```
Continuing CarbonSaathi PromptWars Challenge 3 build.

Attached:
1. DECISIONS.md — locked project spec (read first)
2. PROGRESS.md — build state through Phase 4B (read second)

Status: Phase 4B green (315 tests, 99.73% coverage). Deployed through Phase 1D.
Ready for Phase 5 (API routes).

User preferences are in system context — push back first, no glazing, lead with the most useful thing.

Continue using the established phase prompt template documented in PROGRESS.md.
First action: confirm you've read both files and ask for the current time so we can re-plan against the Sunday 18:00 IST submission deadline.
```

End of progress log.
