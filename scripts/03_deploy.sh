#!/usr/bin/env bash
# Deploy CarbonSaathi to Cloud Run via gcloud run deploy --source .
# Safe to re-run — subsequent runs update the existing service.
set -euo pipefail

# ── Validate required env vars ────────────────────────────────────────────────
: "${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
GCP_REGION="${GCP_REGION:-asia-south1}"

SERVICE_NAME="carbonsaathi"
SA_NAME="carbonsaathi-runner"
SA_EMAIL="${SA_NAME}@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_URL_FILE=".deploy-url"

echo "================================================================"
echo "  CarbonSaathi — deploy to Cloud Run"
echo "  Service : ${SERVICE_NAME}"
echo "  Project : ${GCP_PROJECT_ID}"
echo "  Region  : ${GCP_REGION}"
echo "================================================================"
echo ""

# ── Step 1: Ensure runner service account exists with required IAM roles ──────
echo "[1/5] Ensuring runner service account: ${SA_EMAIL}"
if ! gcloud iam service-accounts describe "${SA_EMAIL}" \
        --project="${GCP_PROJECT_ID}" --quiet &>/dev/null; then
    echo "  Creating service account ${SA_NAME}..."
    gcloud iam service-accounts create "${SA_NAME}" \
        --project="${GCP_PROJECT_ID}" \
        --display-name="CarbonSaathi Cloud Run runner" \
        --quiet
else
    echo "  Service account already exists."
fi

echo "  Binding IAM roles (idempotent)..."
for ROLE in roles/datastore.user roles/secretmanager.secretAccessor roles/logging.logWriter; do
    gcloud projects add-iam-policy-binding "${GCP_PROJECT_ID}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="${ROLE}" \
        --condition=None \
        --quiet > /dev/null
    echo "    Bound: ${ROLE}"
done

# ── Step 2: Determine ALLOWED_ORIGINS ─────────────────────────────────────────
echo ""
echo "[2/5] Determining ALLOWED_ORIGINS..."
if [[ -f "${DEPLOY_URL_FILE}" ]]; then
    LAST_URL=$(cat "${DEPLOY_URL_FILE}")
    ALLOWED_ORIGINS="${LAST_URL}"
    FIRST_DEPLOY=false
    echo "  Using persisted URL: ${ALLOWED_ORIGINS}"
else
    ALLOWED_ORIGINS="*"
    FIRST_DEPLOY=true
    echo "  First deploy detected — using ALLOWED_ORIGINS=* temporarily."
fi

# ── Step 3: Deploy from local source via Cloud Build ──────────────────────────
echo ""
echo "[3/5] Running gcloud run deploy --source . (Cloud Build will handle image build)..."
gcloud run deploy "${SERVICE_NAME}" \
    --source=. \
    --region="${GCP_REGION}" \
    --project="${GCP_PROJECT_ID}" \
    --allow-unauthenticated \
    --min-instances=1 \
    --max-instances=3 \
    --cpu=1 \
    --memory=512Mi \
    --port=8080 \
    --timeout=60s \
    --concurrency=80 \
    --service-account="${SA_EMAIL}" \
    --set-env-vars="APP_ENV=production,LOG_LEVEL=INFO,FIREBASE_PROJECT_ID=${GCP_PROJECT_ID},FIREBASE_AUTH_DOMAIN=${GCP_PROJECT_ID}.firebaseapp.com,ALLOWED_ORIGINS=${ALLOWED_ORIGINS},RATE_LIMIT_PER_MINUTE=30" \
    --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,FIREBASE_API_KEY=firebase-api-key:latest" \
    --quiet

# ── Step 4: Capture deployed URL and tighten CORS on first deploy ─────────────
echo ""
echo "[4/5] Capturing deployed URL..."
DEPLOYED_URL=$(gcloud run services describe "${SERVICE_NAME}" \
    --region="${GCP_REGION}" \
    --project="${GCP_PROJECT_ID}" \
    --format="value(status.url)")

echo "  Deployed URL: ${DEPLOYED_URL}"

if [[ "${FIRST_DEPLOY}" == true ]]; then
    echo "  First deploy — updating ALLOWED_ORIGINS to actual URL (no rebuild)..."
    gcloud run services update "${SERVICE_NAME}" \
        --region="${GCP_REGION}" \
        --project="${GCP_PROJECT_ID}" \
        --update-env-vars="ALLOWED_ORIGINS=${DEPLOYED_URL}" \
        --quiet
    echo "  CORS tightened."
fi

# Persist the URL for future re-deploys
echo "${DEPLOYED_URL}" > "${DEPLOY_URL_FILE}"

# ── Step 5: Smoke test ────────────────────────────────────────────────────────
echo ""
echo "[5/5] Smoke testing ${DEPLOYED_URL}/api/health..."
RESPONSE=$(curl --silent --fail --max-time 15 "${DEPLOYED_URL}/api/health" || true)
if echo "${RESPONSE}" | grep -q '"status":"ok"'; then
    echo "  Health check passed: ${RESPONSE}"
else
    echo "ERROR: Health check failed." >&2
    echo "  Response was: ${RESPONSE}" >&2
    echo "  Check Cloud Run logs: gcloud logging read 'resource.type=cloud_run_revision' --project=${GCP_PROJECT_ID} --limit=50" >&2
    exit 1
fi

echo ""
echo "================================================================"
echo "  Deployment successful!"
echo ""
echo "  URL: ${DEPLOYED_URL}"
echo "================================================================"
echo ""
