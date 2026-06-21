# CarbonSaathi — Project Decisions

> **Status:** Locked at start of Phase 1; §14 and §15 appended during build
> **Owner:** Apoorv Gupta
> **Challenge:** PromptWars Challenge 3 — Carbon Footprint Awareness Platform
> **Submission deadline:** Sunday, June 21, 2026, 23:59 IST
> **Build window:** Fri 19 Jun 09:00 IST → Sun 21 Jun 18:00 IST (~57h wall clock, ~40h productive)

---

## 1. Problem Statement (verbatim)

> Build an application that helps people track and reduce their everyday carbon footprint through simple actions and personalized insights.

---

## 2. Project Identity

**Name:** CarbonSaathi (कार्बन साथी — "carbon companion")

**One-line description:** A personal AI companion that helps Indian metro professionals understand and reduce their daily carbon footprint through natural-language activity logging, state-aware emission calculation, and visible AI reasoning.

**Tagline:** *Your carbon companion, not your carbon scolder.*

**Why this name:** *Saathi* (साथी) means companion in Hindi. The product is built for Indian users — the name signals it. It also reframes the category: most apps in this space are "trackers" (passive measurement); CarbonSaathi is a companion (active partnership), which maps to the *personalized insights* keyword in the PS.

---

## 3. Target User Persona

**Riya / Rahul, 28**
- Software engineer or comparable knowledge worker
- Tier 1 or Tier 2 Indian metro (Bangalore, Mumbai, Pune, Hyderabad, Delhi NCR)
- Lives in a 2BHK with AC, refrigerator, daily commute
- Commute mode varies: metro one day, Uber the next, sometimes WFH
- Pays own electricity bill
- Vaguely climate-aware but does not track anything today
- Has a Google account, signs in to apps comfortably
- Wants to "do something" about climate but doesn't know what specifically moves the needle

**Design implications:** low-friction logging, no guilt-tripping copy, specific actionable advice, Indian context everywhere.

---

## 4. Scope

### In scope (deep coverage)
- **Transport** — cab/Uber, metro, bus, auto-rickshaw, two-wheeler, four-wheeler, walking, WFH
- **Electricity** — monthly bill input + AC/appliance estimates with state-specific grid emission factor
- **Food** — meal logging with vegetarian / non-vegetarian / eggetarian categorization, dairy frequency

### Out of scope (explicit non-goals)
- ❌ Shopping, water, waste activity types
- ❌ Carbon offset purchases (no payment integration)
- ❌ Social features (sharing, leaderboards, friend graphs)
- ❌ Multi-language UI (English only for v1)
- ❌ Mobile-native apps (responsive PWA-ready web only)
- ❌ Wearable / fitness integration
- ❌ Devil's Advocate agent (compressed to 3 agents for time)

---

## 5. Geographic Focus

**India only.** All emission factors, transport modes, electricity grid data, and food categories are India-specific.

### Authoritative data sources
- **Electricity:** Central Electricity Authority (CEA) state-wise grid emission factors, CO₂ Baseline Database
- **Transport:** India GHG Inventory + ICCT for road transport; Metro/DMRC sustainability reports for rail
- **Food:** FAO + Indian dietary survey data, vegetarian-skewed factors

---

## 6. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.13.7 | Native language; better Code Quality score |
| Backend | FastAPI | Async, Pydantic v2, auto OpenAPI, pytest-friendly |
| Frontend | HTMX + Tailwind (via CDN) | Small repo, no build step, server-rendered, accessible |
| AI (Logger) | Gemini 2.5 Flash via `google-generativeai` | Cheap, fast, supports function calling |
| AI (Analyst, Coach) | Gemini 2.5 Pro via `google-generativeai` | Higher reasoning quality for insights and recommendations |
| Database | Firestore (Spark plan) | Free tier covers usage; native Firebase Auth integration |
| Auth | Firebase Authentication — Google Sign-In only | Mandatory persistence; free on Spark |
| Deployment | Cloud Run (asia-south1) | Familiar, scales to zero, simple Dockerfile, low latency for Indian users |
| Secrets | Google Secret Manager → env vars at runtime | No secrets in repo |
| Logging | Structured JSON to Cloud Logging | Searchable, free with Cloud Run |

### Tooling
- **Lint/format:** ruff, black
- **Types:** mypy `--strict`
- **Tests:** pytest, pytest-asyncio, pytest-cov, pytest-mock; `httpx.AsyncClient` for FastAPI testing
- **Security:** bandit, pip-audit, pre-commit secret scanning
- **CI:** GitHub Actions
- **Pre-commit:** ruff, black, mypy, bandit hooks

---

## 7. Architecture

Three sequential AI agents, SSE-streamed to UI for visible reasoning.

```
User input  ──▶  Logger Agent (Flash + function calling)
                   │ structured activity
                   ▼
                Firestore (write activity)
                   │
                   ▼
                Analyst Agent (Pro)
                   │ insights
                   ▼
                Firestore (cache insights)
                   │
                   ▼
                Coach Agent (Pro)
                   │ recommendations
                   ▼
                UI (render with agentReasoning visible)
```

**Why 3 agents:**
- Clear separation of concerns; each independently testable.
- Each contributes to a different rubric value: Logger → PS Alignment via NLP simplicity; Analyst → PS Alignment via personalization; Coach → PS Alignment via the "reduce" mandate.
- The visible reasoning chain is what almost no other submission will have. Manual evaluators will notice.

---

## 8. Data Model (Firestore)

```
users/{uid}
  email: string | null          // null until first sign-in if anonymous; populated post-verify
  displayName: string
  state: string | null          // null until onboarding completes
  homeProfile: map | null       // null until onboarding completes
    bhk: int
    hasAC: boolean
    fridgeClass: string         // 5-star, 3-star, etc.
    dietary: string             // veg, non-veg, eggetarian
  createdAt: timestamp
  lastActive: timestamp
  onboardingComplete: boolean   // false on first verify; true after POST /onboarding

users/{uid}/activities/{activityId}
  type: 'transport' | 'electricity' | 'food'
  timestamp: timestamp          // UTC; convert to IST at read time for user-facing display
  rawInput: string              // what user typed
  structuredData: map           // parsed by Logger
  emissionKgCo2e: float
  confidence: 'high' | 'medium' | 'estimated'
  emissionFactorSource: string  // citation
  agentReasoning: map           // Logger's internal trace

users/{uid}/insights/{insightId}
  generatedAt: timestamp
  type: 'pattern' | 'trend' | 'milestone'
  title: string
  description: string
  supportingActivities: [activityId]
  agentReasoning: map

users/{uid}/recommendations/{recId}
  generatedAt: timestamp
  type: 'swap' | 'reduce' | 'challenge'
  title: string
  description: string
  expectedSavingKg: float
  difficulty: 'easy' | 'medium' | 'hard'
  accepted: boolean
  agentReasoning: map
```

`agentReasoning` is the differentiator — it's what powers the "show your work" UI.

**User lifecycle:**
1. Google Sign-In → Firebase ID token issued client-side
2. Client calls `POST /api/auth/verify` with Bearer token → server creates minimal UserProfile if first-time (state=null, homeProfile=null, onboardingComplete=false), returns `{user, is_new}`
3. Client calls `POST /api/users/onboarding` with state + homeProfile → server sets onboardingComplete=true
4. Activities can be logged at any point post-step-2 (do not gate on onboarding); Coach degrades gracefully to `CoachEmpty` when state/homeProfile are null

---

## 9. API Surface

All routes registered under `/api`. Slashless convention: `POST /api/activities` not `POST /api/activities/`. See §14.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/` | public | Static UI shell |
| GET | `/api/health` | public | Liveness probe |
| POST | `/api/auth/verify` | required | Exchange Firebase ID token for session info; idempotent user-doc upsert |
| GET | `/api/users/me` | required | Return current user profile |
| POST | `/api/users/onboarding` | required | First-time HomeProfile setup; re-onboarding is allowed (just updates) |
| POST | `/api/activities` | required | Triggers Logger agent; returns Activity + AgentReasoning |
| GET | `/api/activities` | required | Paginated history; query params `limit` (default 20, max 50), `before` (ISO timestamp cursor) |
| GET | `/api/activities/{id}` | required | Single activity; 404 if not found OR owned by other uid (never 403, no info leak) |
| GET | `/api/insights` | required | Triggers Analyst if cached insights are stale (Phase 5C) |
| GET | `/api/insights/stream` | required | SSE — streams agent reasoning chunks after agent completes (Phase 5C) |
| GET | `/api/recommendations` | required | Triggers Coach (Phase 5C) |
| POST | `/api/recommendations/{id}/accept` | required | Mark accepted (Phase 5C) |
| GET | `/api/dashboard` | required | Today's footprint + 7-day window + streak count, IST-aligned |

**Auth failure mode (uniform):** every protected route returns `401` with body literally `{"detail":"Authentication failed"}` (content-length 34) for any failure — missing header, malformed prefix, invalid token, expired token, revoked token, or unexpected exception. No method or token-state detail is ever leaked.

---

## 10. Rubric Strategy

| Criterion | Impact | Specific Wins |
|---|---|---|
| **PS Alignment** | HIGH | Indian state grid factors; NLP activity logging ("simple actions"); agent reasoning visibility ("personalized insights"); specific reduction recommendations ("reduce") |
| **Code Quality** | HIGH | Strict mypy; ruff clean; modular structure (core/models/routes/agents/services); Google-style docstrings; type hints everywhere |
| **Security** | MED | Firebase Auth verification on all protected routes; slowapi rate limiting; security headers via `secure`; prompt injection detection layer; secrets in Secret Manager; bandit clean; pip-audit clean; uniform 401 auth-failure body |
| **Efficiency** | MED | Async FastAPI throughout; lazy Gemini/Firebase SDK init; `lru_cache` on emission factors and agent factories; `min-instances=1` on Cloud Run; fire-and-forget Firestore writes for analytics-only updates |
| **Testing** | LOW | 95% coverage gate (line + branch); mocked AI calls; golden-set per agent; integration tests for full chain; httpx.AsyncClient with dep-override pattern |
| **Accessibility** | LOW | Semantic HTML; ARIA labels; keyboard navigation; WCAG AA contrast; `prefers-reduced-motion` |

---

## 11. Schedule (compressed, post-split)

Phase 5 split into 5A/5B/5C during execution. Other phases as planned.

| Window (IST) | Phase | Deliverable |
|---|---|---|
| Fri 09:00 – 13:00 | 1A → 1D | Repo + tooling + FastAPI hello world + CI + first deploy |
| Fri 13:00 – 17:00 | 2 | Pydantic models + governance + prompt injection detection |
| Fri 17:00 – 22:00 | 3 | Emission factor data + service + lookup cache |
| Sat 09:00 – 16:00 | 4A + 4B | Three agents with golden-set tests |
| (overnight Fri→Sat) | 5A | Auth dep + auth/users routes |
| Sat morning | 5B | Activity routes + dashboard + IST/streak logic |
| Sat afternoon | 5C | Insights + recommendations + SSE reasoning stream |
| Sat 20:00 – 24:00 | 6 | HTMX UI |
| Sun 09:00 – 11:00 | 7 | Security hardening (incl. 307-redirect-before-auth audit) |
| Sun 11:00 – 13:00 | 8 | Test sweep + coverage |
| Sun 13:00 – 14:00 | 9 | Deploy + perf check |
| Sun 14:00 – 17:00 | 10 | README + manual eval polish |
| **Sun 17:00 – 18:00** | **11** | **Submission #1 (baseline)** |
| Sun 18:00 – 22:00 | — | Score analysis + targeted fix |
| **Sun 22:00 – 23:00** | **12** | **Submission #2 (only if clear improvement)** |

**Hard rule:** No Submission #3. ElectEd precedent — third attempt regressed Efficiency from 100% → 80%.

---

## 12. Open Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Firebase Auth client config exposed in public repo | Designed to be public; security via Firestore Rules + IAM |
| Gemini API key | In Secret Manager → env var; never in repo; `.env` gitignored |
| Emission factor accuracy disputes | Cite source on every factor; confidence tier visible to user |
| Cold start latency on Cloud Run | `min-instances=1` at deploy |
| 3 attempts hard cap, regression risk | No Submission #3; Submission #2 only with measured improvement |
| Food data methodology controversy | Confidence flagged as "estimated"; limitations documented in README |
| Manual evaluator differs from AI evaluator | Phase 10 dedicated to README narrative + ADR-style decision log |
| ~~307-redirect-before-auth info leak~~ | RESOLVED in Phase 5B — `redirect_slashes=False` + slashless route convention (§14) |

---

## 13. Definition of "Done"

- ✅ Public GitHub repo, single branch, under 10 MB
- ✅ Deployed Cloud Run URL completes the full user journey (sign in → log → insight → recommendation accept) without errors
- ✅ README a non-technical reader can understand
- ✅ All CI checks green: ruff, black, mypy strict, pytest with 95%+ coverage, bandit, pip-audit
- ✅ Architecture diagram in README
- ✅ Honest limitations section in README
- ✅ ADR-style decision log for manual evaluator visibility

---

## 14. Implementation Conventions (load-bearing rules)

These emerged during build but are now **project-level rules** any new code must follow.

### Slashless routes for bare-resource endpoints
Bare-resource routes (e.g. POST and GET on the `/activities` collection root) use `@router.post("")` / `@router.get("")` — the **empty string**, not `"/"`. Combined with §14.2 below, the slashed form (`/api/activities/`) returns 404. Path-param routes are unchanged (`@router.get("/{activity_id}")`). DECISIONS.md §9 documents slashless paths; the Phase 6 frontend and any external client MUST match.

### `redirect_slashes=False` on the FastAPI app
The FastAPI/Starlette default 307 redirect for trailing-slash mismatches fires **before** dependency injection — including auth deps — leaking route-existence to unauthenticated callers. Set `redirect_slashes=False` on the `FastAPI()` constructor. No auto-redirect safety net; every route must be hit at its exact registered path.

### Uniform `401 {"detail":"Authentication failed"}` on every auth failure
Every protected route returns the same status code AND the same byte-identical body for: missing header, malformed prefix, invalid token, expired token, revoked token, cert fetch error, generic exception. No method or token-state detail is leaked. Content-length is always 34 bytes. Verified across `/api/activities`, `/api/dashboard`, `/api/users/me`, `/api/users/onboarding`, `/api/auth/verify`.

### Local dev port is 8080, not 8000
`make run` serves on port 8080 (matches the Cloud Run convention — `PORT` env var defaults to 8080). All local curl commands and validation blocks use `http://localhost:8080`.

### IST (`Asia/Kolkata`) for all user-facing time computations
Activity timestamps are stored UTC in Firestore. All user-facing aggregations — "today", "this week", "streak", "day-by-day breakdown" — compute against IST via `zoneinfo.ZoneInfo("Asia/Kolkata")`. Conversion happens at read time, not write time. Single `IST = ZoneInfo("Asia/Kolkata")` constant at module top of `app/routes/dashboard.py`.

### Streak uses Duolingo-style same-day grace
Streak counts consecutive IST days with ≥1 activity. If today has no activity yet, streak counts backward starting from **yesterday** (grace period — user has the rest of today to log without breaking it). If today has an activity, streak counts forward from today.

### `httpx.AsyncClient` for FastAPI test clients
Tests use `httpx.AsyncClient` (not Starlette's `TestClient`). Repo convention established in Phase 5A and carried forward. Pairs with `pytest-asyncio` and the `app.dependency_overrides` pattern for auth + Firestore mocking.

### Pydantic discriminated-union pattern for agent outcomes
All agent outcomes use `Annotated[Union[Success, Empty|Rejected, Failed], Field(discriminator="status")]` where each member has `status: Literal["..."]` (NOT `str`). Routes pattern-match on `outcome.status` for HTTP translation: success → 201/200, rejected → 400 with safe reason, empty → 200 with empty list + reason, failed → 500 with generic message.

### Coach computes savings; never trusts the model
Coach asks the model for a `saving_basis` (typed discriminated union). Agent validates against `emission_service` and **computes** `expected_saving_kg` from real emission factors. Model never sets the saving number. Same principle for any future agent that produces quantitative output: the agent validates and recomputes.

---

## 15. Build Amendments Log (post-lock spec changes)

Entries here capture spec-level changes made during build. Each entry cross-references PROGRESS.md for full detail.

| # | Date | Change | Origin |
|---|---|---|---|
| 1 | Phase 4A | `Confidence` Literal moved from `activity.py` to `shared.py` to break name clash with `FactorEntry.confidence` | PROGRESS.md § Decisions made during build |
| 2 | Phase 4A | `ElectricityData` gained typed `notes: str \| None` field; bill→kWh conversion writes its assumption there, not into untyped `structured_data` | PROGRESS.md § Decisions |
| 3 | Phase 4A | `AVG_INR_PER_KWH = 8.0` constant; any activity using bill→kWh conversion **must** set `confidence='estimated'` regardless of grid factor confidence | PROGRESS.md § Decisions |
| 4 | Phase 5A | `UserProfile.email`, `.state`, `.home_profile` became `Optional[…] = None`. Spec §8 above already reflects this. Pre-onboarding users have state=None/home_profile=None; Coach falls through to `CoachEmpty` | PROGRESS.md § Phase 5A |
| 5 | Phase 5A | `Authorization` header dep typed `str \| None`; missing header path raises clean 401 inside function body rather than Header(...) raising 422. Enables uniform 401 contract (§14.3) | PROGRESS.md § Phase 5A |
| 6 | Phase 5A | Coach `build_user_prompt(state, home, …)` signature narrowed — takes the narrowed values rather than the full profile object — to make None-handling explicit at the call site | PROGRESS.md § Phase 5A |
| 7 | Phase 5A | `CoachAgent` gained a not-onboarded guard: if state or home_profile is None, returns `CoachEmpty` without calling Gemini | PROGRESS.md § Phase 5A |
| 8 | Phase 5B | `FirestoreService` gained `list_activities_in_range(uid, start, end, limit)` and `get_activity(uid, activity_id)` methods. `list_activities` signature extended with `before: datetime \| None` cursor param (default None preserves prior behavior) | PROGRESS.md § Phase 5B |
| 9 | Phase 5B | `redirect_slashes=False` on `FastAPI()` constructor (§14.2); slashless route convention (§14.1); resolved the 307-before-auth info leak documented as risk in §12 | PROGRESS.md § Phase 5B |
| 10 | Phase 5B | Phase 5 split into 5A (auth foundation), 5B (activities + dashboard), 5C (insights + recs + SSE) to keep prompt scope manageable. §11 schedule updated. | PROGRESS.md § Pending phases |
| 11 | Phase 5C | Single generator endpoint `/api/insights/stream`; `/api/insights` and `/api/recommendations` are read-only listers. Resolves the three-generators duplication in §9 as originally written | PROGRESS.md § Phase 5C |
| 12 | Phase 5C | Content negotiation on `/api/insights/stream`: `Accept: text/event-stream` (or no Accept, or both) → SSE chunks with 80ms inter-event sleep; `Accept: application/json` only → single JSON response, no chunks, no sleep | PROGRESS.md § Phase 5C |
| 13 | Phase 5C | New `GenerationState` doc at `users/{uid}/state/generation`; IST-day-aligned staleness with 10min empty TTL on BOTH `analyst_status` and `coach_status` (independent OR branches, not sequential) | PROGRESS.md § Phase 5C |
| 14 | Phase 5C | 80ms `asyncio.sleep` between non-`done` reasoning events on SSE path only; JSON path skips; tests monkeypatch `SSE_INTER_EVENT_DELAY_S` to 0 to keep suite at ~1.5s | PROGRESS.md § Phase 5C |
| 15 | Phase 5C | Phase 6 frontend MUST use `fetch()` + ReadableStream reader for SSE consumption, NOT `EventSource` (the latter cannot send `Authorization` headers; required by §14.3) | PROGRESS.md § Phase 5C |
| 16 | Phase 5C | Spec-vs-reality reconciliations discovered during build: `AnalystAgent.__init__` takes only `gemini_factory` (NOT `emission_service`); agent method signatures are keyword-only with `user_id` param; `AnalystSuccess`/`CoachSuccess` carry no top-level `agent_reasoning` — reasoning is per-item on `outcome.insights[0].agent_reasoning.reasoning_steps` (first-item aggregation, with empty-list defensive guard); `FirestoreService` already had `add_insight`/`get_recent_insights`/`add_recommendation`/`accept_recommendation` (only 3 new methods added: `get_recent_recommendations`, `get_generation_state`, `set_generation_state`); `accept_recommendation` stays non-transactional (path-scoping under `users/{uid}/recommendations/` makes the transaction theatre) | PROGRESS.md § Phase 5C |
| 17 | Phase 9 / 2026-06-21 | Analyst+Coach ran on `gemini-2.5-flash` during Phase 7 (Saturday night) due to Pro quota=0 at the time; code was restored to `.pro()` before final commit; no env-var override was left in Cloud Run; formally recorded here on billing link in Phase 9 | PROGRESS.md § Phase 9 |
| 31 | Phase 9 / pre-submission | Coach remained on gemini-2.5-flash after the billing fix rather than reverting to Pro per the original DECISIONS.md §6. Empirical validation: Flash produces acceptable recommendation quality end-to-end on the deployed app; the Pro revert was not exercised in Phase 9 verification. Trade-off accepted: nominal quality bound vs deploy-stability risk at the submission window. Logger remains on Flash as originally designed; Analyst remains on Pro. | Phase 9 / pre-submission validation |
