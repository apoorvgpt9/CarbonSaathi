# CarbonSaathi — Project Decisions

> **Status:** Locked at start of Phase 1; reviewed and current as of end of Phase 4B (2026-06-20)
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
- **Tests:** pytest, pytest-asyncio, pytest-cov, pytest-mock
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
  email: string
  displayName: string
  state: string                 // Karnataka, Maharashtra, ...
  homeProfile:
    bhk: int                    // 1, 2, 3
    hasAC: boolean
    fridgeClass: string         // 5-star, 3-star, etc.
    dietary: string             // veg, non-veg, eggetarian
  createdAt: timestamp
  lastActive: timestamp
  onboardingComplete: boolean

users/{uid}/activities/{activityId}
  type: 'transport' | 'electricity' | 'food'
  timestamp: timestamp
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

---

## 9. API Surface

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Static UI shell |
| GET | `/api/health` | Liveness probe |
| POST | `/api/auth/verify` | Exchange Firebase ID token for session |
| GET | `/api/users/me` | Return user profile |
| POST | `/api/onboarding` | First-time setup |
| POST | `/api/activities` | Triggers Logger agent |
| GET | `/api/activities` | Paginated history |
| GET | `/api/activities/{id}` | Single activity |
| GET | `/api/insights` | Triggers Analyst if stale |
| GET | `/api/insights/stream` | SSE — streams agent reasoning live |
| GET | `/api/recommendations` | Triggers Coach |
| POST | `/api/recommendations/{id}/accept` | Mark accepted |
| GET | `/api/dashboard` | Today's footprint + week trend + streak |

---

## 10. Rubric Strategy

| Criterion | Impact | Specific Wins |
|---|---|---|
| **PS Alignment** | HIGH | Indian state grid factors; NLP activity logging ("simple actions"); agent reasoning visibility ("personalized insights"); specific reduction recommendations ("reduce") |
| **Code Quality** | HIGH | Strict mypy; ruff clean; modular structure (core/models/routes/agents/services); Google-style docstrings; type hints everywhere |
| **Security** | MED | Firebase Auth verification on all protected routes; slowapi rate limiting; security headers via `secure`; prompt injection detection layer; secrets in Secret Manager; bandit clean; pip-audit clean |
| **Efficiency** | MED | Async FastAPI throughout; lazy Gemini/Firebase SDK init; `lru_cache` on emission factors; `min-instances=1` on Cloud Run; fire-and-forget Firestore writes |
| **Testing** | LOW | 95% coverage; mocked AI calls; golden-set per agent; integration tests for full chain |
| **Accessibility** | LOW | Semantic HTML; ARIA labels; keyboard navigation; WCAG AA contrast; `prefers-reduced-motion` |

---

## 11. Schedule (compressed 48h productive)

| Window (IST) | Phase | Deliverable |
|---|---|---|
| Fri 09:00 – 13:00 | 1A → 1D | Repo + tooling + FastAPI hello world + CI + first deploy |
| Fri 13:00 – 17:00 | 2 | Pydantic models + governance + prompt injection detection |
| Fri 17:00 – 22:00 | 3 | Emission factor data + service + lookup cache |
| Sat 09:00 – 16:00 | 4 | Three agents with golden-set tests |
| Sat 16:00 – 20:00 | 5 | API routes (mocked agents in tests) |
| Sat 20:00 – 24:00 | 6 | HTMX UI |
| Sun 09:00 – 11:00 | 7 | Security hardening |
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

---

## 13. Definition of "Done"

- ✅ Public GitHub repo, single branch, under 10 MB
- ✅ Deployed Cloud Run URL completes the full user journey (sign in → log → insight → recommendation accept) without errors
- ✅ README a non-technical reader can understand
- ✅ All CI checks green: ruff, black, mypy strict, pytest with 95%+ coverage, bandit, pip-audit
- ✅ Architecture diagram in README
- ✅ Honest limitations section in README
- ✅ ADR-style decision log for manual evaluator visibility
