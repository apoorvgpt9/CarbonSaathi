# CarbonSaathi — Pre-Submission Validation Strategy

> **Purpose:** Hand off a focused validation pass to a new Claude session before Phase 11 submission. Optimized for deadline pressure: ~30–45 min execution, sequential checklist, stop at first failure.
> **Created:** End of Phase 10 / pre-Phase 11 (Sunday afternoon IST, pre-submission deadline 23:59 IST)
> **Owner:** Apoorv Gupta
> **Submission deadline:** Sunday, June 21, 2026, 23:59 IST

---

## Why this document exists

Phases 7, 8, 9, 10 were executed under time pressure. Copilot reported each as successful, but **none of Phases 7–10 have been validated by browser click-through against the live deployed URL.** Phase 10's README was authored before the deployed app was confirmed working end-to-end.

The known concrete issue: **"Sign in with Google" is currently broken on the deployed URL.** This was the same class of bug that hit Phase 6 locally (CSP not whitelisting an `apis.google.com` script that Firebase's SDK dynamically injects). It may be the same root cause, or something different — but it must be diagnosed and fixed before submission, because the AI evaluator will hit the deployed URL and a broken sign-in score-walls the entire app.

Beyond that one confirmed break, the user wants to verify on the live URL:
1. Sign-in actually completes (post-fix)
2. Activity logging works and renders parsed activity + reasoning steps
3. Dashboard shows today's footprint, 7-day chart, streak
4. Insights generation actually streams reasoning + renders insights (Pro model responding, not 429)
5. Recommendations render and "Accept" persists

This is **not** "thorough testing" — it's verifying that the deployed app does what the rubric will be evaluated against. The AI evaluator scores Code Quality, Testing, etc. from the repo; PS Alignment scores from clicking through the live demo.

---

## Hard rules for this session

- **No code changes unless validation surfaces a specific bug with a specific fix.** Vague "let me just improve X" changes are forbidden — that's how regressions ship at the last hour.
- **No new features.**
- **No restructuring of any phase work that's already shipped.** Touch only what's broken.
- **If a check fails, stop. Don't keep running checks past a known failure.** Each failure cascades — running them all and triaging at the end wastes time.
- **No Submission #3.** (DECISIONS.md §11 hard rule, ElectEd precedent.)
- **Submission #2 is conditional**, only triggered if Submission #1 reveals a specific, named, fixable gap with measurable expected delta.

---

## Pre-flight before running validation

```bash
# 1. Confirm git state is clean and Phase 10 changes are pushed
cd /Users/apoorvgupta/Coding/CarbonSaathi
git status                                   # expect clean
git log --oneline -5                         # expect last commit references Phase 10

# 2. Confirm deployed URL responds at all (cheapest possible smoke test)
curl -sS https://carbonsaathi-ahkpdce5pa-el.a.run.app/api/health
# expect: {"status":"ok","version":"0.1.0"}
# if non-200 or different URL: STOP, the deploy isn't where you think it is.

# 3. Confirm the deployed revision is actually the current code
gcloud run revisions list --service=carbonsaathi --region=asia-south1 --limit=3 \
  --format="table(metadata.name,status.conditions[0].lastTransitionTime,metadata.labels.serving)"
# expect: most recent revision is from today (Phase 9 deploy)
# if the most recent revision is from days ago: Phase 9's deploy didn't actually land.
```

If any of those three fail: that's the first thing to fix. Don't run the rest of the validation against a stale or broken deploy.

---

## The validation sequence — 5 stages, sequential

### Stage 1 — Diagnose the broken sign-in (highest priority)

**Step 1.1.** Open the deployed URL in a fresh incognito window with DevTools open BEFORE clicking anything. Tabs: Console + Network.

**Step 1.2.** Click "Sign in with Google." Watch both tabs carefully.

**Step 1.3.** Three failure modes to differentiate:

- **Console shows `auth/unauthorized-domain`** → the Cloud Run domain isn't in Firebase Authentication → Settings → Authorized domains. Manual fix in Firebase console, takes effect immediately, no redeploy.

- **Console shows a CSP violation** naming a blocked host → CSP doesn't cover that host. Most likely `apis.google.com` (was added during Phase 6 local fix, may not be in the deployed CSP). Less likely: a Firebase analytics endpoint, Google fonts, etc.

  Fix: edit `app/core/security.py`, add the host to the appropriate CSP directive (usually `script-src` or `frame-src`), redeploy.

- **Console shows `auth/internal-error`** (the generic Firebase error) → could be many things; the DETERMINATIVE evidence is in the Network tab. Click the failed `identitytoolkit.googleapis.com` request, look at the Response body. Firebase's backend returns specific error codes there (`OPERATION_NOT_ALLOWED`, `INVALID_IDP_RESPONSE`, etc.) that name the actual cause.

**Step 1.4.** Once sign-in works on the deployed URL, immediately confirm the verify chain completes:
- After Google account picker, expect redirect to `/onboarding` (new user) or `/dashboard` (returning user).
- DevTools Network → see `/api/auth/verify` request with `Authorization: Bearer ...` header → response 200 with user profile JSON.
- If `/api/auth/verify` returns 401 or 500: the backend isn't accepting the ID token. Check Cloud Run logs:
  ```bash
  gcloud logging read \
    "resource.type=cloud_run_revision AND resource.labels.service_name=carbonsaathi AND severity>=WARNING" \
    --limit=20 --format="value(timestamp,severity,jsonPayload.event,jsonPayload.message)"
  ```

**Do not proceed past Stage 1 until sign-in completes successfully and lands on a logged-in page.**

### Stage 2 — Verify Gemini Pro is actually responding (independent of app)

This is the question "is the billing fix real" — and the cheapest verification is a direct curl, no app involved:

```bash
curl -s -X POST \
  "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key=$(gcloud secrets versions access latest --secret=gemini-api-key)" \
  -H 'Content-Type: application/json' \
  -d '{"contents":[{"parts":[{"text":"respond with the single word ok"}]}]}' | python3 -m json.tool
```

Three outcomes:

- **Real response with `text` field containing `ok`** → Pro quota is live, billing is propagated. Proceed.
- **`429` with `"limit: 0"` for `gemini-2.5-pro`** → billing fix didn't propagate. Until this is resolved, insights generation will fail with the same error you saw Saturday night. **You can still submit** with the Flash workaround documented as a limitation, but the rubric impact of insights-failing-because-of-Pro-quota is severe.
- **Any other error** → paste the response, diagnose.

If Pro quota is broken, the decision is: submit with Flash documented as a limitation, OR fix billing first. Don't silently degrade Coach quality and hope nobody notices — the manual evaluator will notice when reading DECISIONS.md says Pro and the model field in agent_reasoning says Flash.

### Stage 3 — End-to-end UI walkthrough on the deployed URL

Once Stages 1 and 2 are clean, run the full user journey in the browser. DevTools open throughout. Take screenshots as you go — they're useful evidence for PROGRESS.md updates and for the limitations section of the README if anything is imperfect.

| Step | Action | Expect | Failure mode → action |
|---|---|---|---|
| 3.1 | Complete onboarding (if shown) | Form submits → dashboard | If form errors: check Network for the POST response. Onboarding is `POST /api/users/onboarding`. |
| 3.2 | Navigate to `/log` | Textarea + submit button visible | If page errors: check Console for JS errors. |
| 3.3 | Log activity: "took uber to office, 10 km" | Activity card renders below with reasoning steps visible | If hangs > 30s: Logger (Flash) is timing out — check Cloud Run logs. If renders blank: check Network for `POST /api/activities` response. |
| 3.4 | Log activity: "had biryani for lunch" | Same | Same |
| 3.5 | Log activity: "AC ran 6 hours today" | Same — confirms all 3 activity types work | Same |
| 3.6 | Navigate to `/dashboard` | Today's total, 3 activities counted, week chart with today as the only non-zero bar, streak = 1 | If empty: dashboard isn't reading the activities — check Network for `GET /api/dashboard`. |
| 3.7 | Navigate to `/insights`, click "Generate insights" | THE rubric differentiator. Reasoning steps stream visibly over a few seconds, then insights array + recommendations array render. | This is the most fragile path. See Stage 4 below. |
| 3.8 | Click "Accept" on a recommendation | Card updates to "✓ Accepted" | If no visible change: check Network for `POST /api/recommendations/{id}/accept`. |
| 3.9 | Refresh `/insights` page | Cached insights + recommendations still there, "Accepted" state preserved on the accepted rec | Confirms persistence. |
| 3.10 | Sign out | Returns to sign-in page, clean state | Confirms full lifecycle. |

### Stage 4 — Specific scrutiny on insights generation (the rubric differentiator)

`/insights/stream` is the highest-stakes feature for PS Alignment scoring. Even if Stage 3.7 "works," verify it's working the way it's supposed to:

- **Open DevTools Network tab.** Filter for `stream`. Click "Generate insights."
- **Click into the `/api/insights/stream` request.**
- **Response tab** — should show SSE frames: `event: phase_start`, `event: reasoning_step`, `event: phase_complete`, `event: done`. Multiple reasoning_step events per phase indicates real streaming.
- **EventStream tab (Chrome)** — shows frames with timestamps. If all timestamps cluster at the end (within 100ms of each other), Cloud Run is buffering the stream — reasoning arrives all at once, defeating the visible-reasoning rubric play. This is a known Cloud Run HTTP/2 buffering risk flagged in PROGRESS.md Phase 9.

If buffering is observed: the feature still works functionally (insights generate, render), but the live-streaming visual is broken. **Don't try to fix this now** — document it in PROGRESS.md as a known Phase 9 limitation, document it in the README's limitations section, submit. Fixing Cloud Run streaming behavior at this point in the clock is a tar pit.

If a Gemini call genuinely times out mid-generation:
- Server logs (`gcloud logging read ...` above) will name which agent. Coach is the prime suspect (larger prompt, structured response schema) per the Saturday-night Flash debugging.
- If Pro is responding (Stage 2 was green) and it's still timing out, the timeout constant in `app/core/gemini.py` may be too tight for the deployed environment's network latency. Bump from whatever it is to 60s, redeploy. Don't bump tests' mock timeouts.
- If timeout is intermittent (works sometimes, fails sometimes): this IS a real limitation. Document and move on.

### Stage 5 — Decision: submit, fix, or defer

Three outcomes from Stages 1–4:

**A. Everything green.** Sign-in works, Pro responds, full journey clicks through cleanly, insights stream visibly. → Proceed to Phase 11 submission. Update PROGRESS.md with verification results, update README limitations section if anything Stage 3/4 surfaced was imperfect-but-shipping.

**B. Sign-in works, insights generate, but with caveats** (Cloud Run buffering, Coach occasionally times out, etc.) → Submit with caveats documented in README's "Honest limitations" section AND in PROGRESS.md. The rubric rewards honest documentation more than performative hiding.

**C. Something genuinely broken that blocks the user journey** (sign-in still failing after Stage 1 fix, Pro returning 429, insights endpoint 500-ing) → Stop. Fix the specific thing. Re-run Stage 3 against the fix. If can't fix in remaining time, submit anyway and document the broken path clearly in README — a partially-broken honest submission scores better than a hidden-broken one when the evaluator clicks through.

---

## Copilot prompt for the next Claude session

When opening the new session, attach DECISIONS.md, PROGRESS.md (updated), and this VALIDATION_STRATEGY.md file. Then paste:

```
Continuing CarbonSaathi PromptWars Challenge 3 build — pre-submission validation.

Attached:
1. DECISIONS.md — locked project spec + §14 conventions + §15 amendments
2. PROGRESS.md — build state through Phase 10 (Phases 1A–10 complete)
3. VALIDATION_STRATEGY.md — validation plan for this session (read this first)

Status: Phases 1A through 10 reported complete by Copilot, but Phases 7/8/9/10
were not validated against the deployed app. Phase 10's README ships before
deployed-app verification. Submission #1 deadline: Sunday 23:59 IST.

Known broken: "Sign in with Google" not working on the deployed URL.
Known unverified: billing live, Pro responding (vs 429), deploy is current
revision, full UI journey works end-to-end.

User preferences are in system context — push back first, no glazing, lead
with the most useful thing. The validation strategy doc has stop-at-first-
failure flow — follow it; don't run all stages and triage at the end.

First actions:
1. Confirm you've read all three files. Call out anything load-bearing for
   today's validation: the Stage 1 sign-in diagnosis flow, the Stage 2 Pro
   quota check, the Stage 4 SSE-through-Cloud-Run buffering concern.
2. Run the pre-flight (3 commands) and report results.
3. Then walk Stage 1 — sign-in diagnosis — and stop after the first failure
   mode is identified, BEFORE proposing a fix. The user clicks through; I
   diagnose; we fix one thing at a time.

Do not skip ahead to later stages. Each stage has prerequisites from the
prior stage. Submission readiness is the goal, not coverage of all checks.
```

---

## What to NOT do in the validation session

- Don't run a full 12-stage gauntlet — that was for build phases, not validation. This is a checklist.
- Don't add new tests, new code, new features. Touch only what Stage 1–4 surfaces as broken.
- Don't try to fix Cloud Run streaming buffering if it's imperfect — document, ship.
- Don't try to fix intermittent Coach timeouts if Pro is responding overall — document, ship.
- Don't run another deploy unless Stage 1 fix specifically requires it (CSP change, env var change). Deploys at the last hour are how regressions ship.
- Don't worry about the AI evaluator's score before submitting. You can't predict it; submit, capture, then decide on Submission #2 from real data.

---

## Submission #2 decision framework (read AFTER Submission #1 scores arrive)

After Submission #1, the AI evaluator returns scores per criterion. The DECISIONS.md §11 hard rule: Submission #2 only if there's a specific, named, fixable gap with measurable expected delta.

Use this filter:

1. **Look at the lowest-scoring criterion.** Read the AI evaluator's text feedback if any.
2. **Name a specific change that would move that criterion measurably.** Not "more polish" — a specific file change, a specific feature, a specific limitation removed.
3. **Estimate the time cost honestly.** If it's > 2 hours, skip. Time pressure at end of day produces regressions.
4. **Estimate the regression risk honestly.** Any change touching the deploy, the auth flow, the agent code, or the SSE consumer carries real regression risk. Documentation changes (README, ADRs) are nearly free.
5. **Default to skip.** ElectEd's third attempt regressed Efficiency 100% → 80%. The bias should be "don't resubmit" unless the case is overwhelming.

If skipping: document the decision in PROGRESS.md (Submission #2 declined, reasoning, named the considered fix). That documentation itself is engineering maturity worth showing.
