# Architecture Decision Records — CarbonSaathi

These ADRs are **distilled from the project's authoritative logs** for reviewer
convenience — they are not new decisions. The source of truth remains:

- [DECISIONS.md](../DECISIONS.md) — what was decided and **why** (§7 architecture,
  §8 data model, §14 implementation conventions, §15 post-lock amendments).
- [PROGRESS.md](../PROGRESS.md) — what was actually **built**, phase by phase.

Each record cites its origin. Format: Status · Context · Decision · Consequences.

---

## ADR-001 — Three sequential agents; Devil's Advocate dropped

**Status:** Accepted · *Source: DECISIONS.md §4, §7*

**Context.** The brief asks for "simple actions" and "personalized insights."
A single mega-prompt would entangle parsing, analysis, and advice, and would be
hard to test or to make legible to a user. A four-agent design (adding a Devil's
Advocate to challenge recommendations) was considered, but the build window was
~40 productive hours.

**Decision.** Use three sequential agents — **Logger** (parse), **Analyst**
(find patterns), **Coach** (recommend) — each independently testable. Drop the
Devil's Advocate for time.

**Consequences.** Clear separation of concerns; each agent maps to a distinct
rubric value. Recommendations are not adversarially stress-tested by a second
model (recorded as a limitation in the README).

---

## ADR-002 — Visible agent reasoning streamed over SSE

**Status:** Accepted · *Source: DECISIONS.md §7, §8, §10; PROGRESS.md Phase 5C*

**Context.** Most submissions surface only final output. The `agentReasoning`
trace each agent already produces is the highest-leverage, hardest-to-copy
differentiator for a manual evaluator.

**Decision.** Persist each agent's `reasoning_steps` on every insight/
recommendation and stream them to the UI via Server-Sent Events during
generation, through a single endpoint `GET /api/insights/stream`.

**Consequences.** The AI becomes a glass box. The stream is a **paced replay**
(80 ms/event) of the structured trace, not token-level model streaming — an
honest distinction noted in the README. The frontend must consume SSE with
`fetch()` + `ReadableStream` (not `EventSource`, which cannot send the
`Authorization` header).

---

## ADR-003 — The Coach computes savings; it never trusts the model

**Status:** Accepted · *Source: DECISIONS.md §14; PROGRESS.md Phase 4B*

**Context.** An LLM asked for "kg saved" will confidently hallucinate a number.
Quantitative correctness is a code-quality and trust requirement.

**Decision.** The Coach model returns a *typed* `saving_basis` (a discriminated
union). The agent validates it against `emission_service` and **computes**
`expectedSavingKg` from the real factor table. The model may shape an activity;
it may never set its carbon impact.

**Consequences.** Savings are reproducible and auditable. Any future agent that
emits a quantity must follow the same validate-and-recompute rule.

---

## ADR-004 — Single content-negotiated generator endpoint

**Status:** Accepted (supersedes the three-generator sketch in DECISIONS.md §9)
· *Source: DECISIONS.md §15 #11, #12; PROGRESS.md Phase 5C*

**Context.** The original API sketch had three generation entry points, inviting
cache-coherence bugs and double generation under burst load.

**Decision.** Collapse to one generator: `GET /api/insights/stream`.
`GET /api/insights` and `GET /api/recommendations` become read-only listers.
The stream endpoint negotiates on `Accept`: `text/event-stream` (or none/`*/*`/
both) → SSE; `application/json` only → one consolidated payload.

**Consequences.** One code path generates and persists; listers only read. The
orchestrator stays transport-agnostic (no SSE/JSON knowledge); the route adapts.

---

## ADR-005 — `redirect_slashes=False` + slashless routes

**Status:** Accepted · *Source: DECISIONS.md §14.1, §14.2, §15 #9; PROGRESS.md Phase 5B*

**Context.** Starlette's default 307 redirect for trailing-slash mismatches fires
**before** dependency injection — including the auth dependency — leaking
route-existence to unauthenticated callers.

**Decision.** Set `redirect_slashes=False` on the FastAPI app and register
bare-resource routes with the empty string (`@router.post("")`), not `"/"`.

**Consequences.** The 307-before-auth information leak is closed. Every route
must be hit at its exact registered path; the frontend and any client must match
the slashless convention.

---

## ADR-006 — Uniform `401 {"detail":"Authentication failed"}`

**Status:** Accepted · *Source: DECISIONS.md §14.3, §9*

**Context.** Distinct error bodies for missing vs malformed vs expired vs revoked
tokens leak information and create an enumeration surface.

**Decision.** Every authentication failure — missing header, bad prefix, invalid/
expired/revoked token, cert-fetch error, or unexpected exception — returns the
same status and **byte-identical** 34-byte body. Auth never raises a 500.

**Consequences.** No token-state information leaks. Failure categories are still
visible internally via structured logs, never to the client.

---

## ADR-007 — IST for all user-facing time; same-day streak grace

**Status:** Accepted · *Source: DECISIONS.md §14.4, §14.5; PROGRESS.md Phase 5B*

**Context.** Users are in India; "today" and "this week" must mean IST days, but
timestamps are stored UTC. A naive streak shows as 0 for most of every day.

**Decision.** Store UTC; convert to IST (`Asia/Kolkata`) at read time for all
aggregations. The streak uses a Duolingo-style grace: if today has no activity
yet, count backward from yesterday.

**Consequences.** Correct day boundaries for Indian users; the streak doesn't read
as broken before the user has logged today. Always key IST-day buckets off
`.astimezone(IST).date()`, never `.date()` on a UTC datetime.

---

## ADR-008 — Gemini Flash for the Logger, Pro for Analyst & Coach

**Status:** Accepted; Coach later moved to Gemini 2.5 **Flash** (see DECISIONS.md §15 #31) · *Source: DECISIONS.md §6*

**Context.** Logging is high-frequency and mostly structured extraction; analysis
and coaching are low-frequency and reasoning-heavy. One model for both would
overpay on latency/cost or underdeliver on quality.

**Decision.** Logger → Gemini 2.5 **Flash** (cheap, fast, function calling).
Analyst & Coach → Gemini 2.5 **Pro** (higher reasoning quality).

**Consequences.** Cost and latency stay low where volume is high; reasoning
quality stays high where it matters. Each agent reads its model name from its
`GenerativeModel` instance, keeping dependency injection clean.

---

## ADR-009 — State-level grid factors with confidence tiers and citations

**Status:** Accepted · *Source: DECISIONS.md §5*

**Context.** Electricity carbon intensity varies enormously across India
(~0.38 kg/kWh in hydro-rich Sikkim to ~1.05 in coal-belt Jharkhand). A single
national average would erase the most important Indian signal.

**Decision.** Maintain a per-state/UT factor table from the CEA CO₂ Baseline
Database v19.0, with a `confidence` tier (`high`/`medium`/`estimated`) and a
source citation on every entry. Modelled outliers are flagged `estimated` with a
note. Transport (ICCT/DMRC) and food (FAO) factors follow the same shape.

**Consequences.** Numbers are state-specific and auditable; users see confidence.
Resolution stops at state-level annual averages (no DISCOM or time-of-day) —
recorded as a limitation.

---

## ADR-010 — Typed discriminated-union agent outcomes

**Status:** Accepted · *Source: DECISIONS.md §14; PROGRESS.md Phase 4A*

**Context.** Expected failures (governance rejection, no function call, low data,
malformed JSON) are normal control flow, not exceptional conditions.

**Decision.** Every agent returns `Annotated[Union[Success, Empty|Rejected,
Failed], Field(discriminator="status")]` with `status: Literal[...]`. Routes
pattern-match the status to an HTTP response (success→200/201, rejected→400,
empty→200+reason, failed→500+generic message).

**Consequences.** No exceptions for expected failure cases; failure modes are
exhaustively typed and individually testable. The discriminator must be a
`Literal`, never `str`.

---

## ADR-011 — Bill→kWh conversion uses a flat ₹8/kWh and forces "estimated"

**Status:** Accepted · *Source: DECISIONS.md §15 #2, #3; PROGRESS.md Phase 4A*

**Context.** Users often know their monthly bill in rupees, not kWh. Indian
tariffs are slab-based and DISCOM-specific, so any rupee→kWh inversion is
approximate.

**Decision.** Convert with a single `AVG_INR_PER_KWH = 8.0` constant and force
`confidence = "estimated"` on any activity derived this way, regardless of the
grid factor's own confidence. The assumption is written to a typed `notes` field,
not an untyped escape hatch.

**Consequences.** The approximation is explicit and visible to the user. Bill-based
electricity is never over-stated as high-confidence.

---

## ADR-012 — Firestore on Spark, lazy SDK init, cached singletons

**Status:** Accepted · *Source: DECISIONS.md §6, §10; PROGRESS.md Phases 2, 4A, 5B*

**Context.** A hackathon demo needs persistence and auth without standing cost,
and Cloud Run cold starts must not pay SDK-init cost on the request path.

**Decision.** Use Firestore on the free Spark plan with native Firebase Auth.
Initialise the Firebase/Gemini SDKs lazily (no `initialize_app`/`configure` at
import), and wrap clients, settings, emission data, and agent factories in
`@lru_cache` singletons.

**Consequences.** Zero database cost at demo scale and clean per-process
initialisation. The free tier is sized for the demo, not for scale (a documented
limitation); `min-instances=1` keeps one instance warm to avoid cold starts.

---

*For the complete, dated amendment history see [DECISIONS.md](../DECISIONS.md) §15.*
