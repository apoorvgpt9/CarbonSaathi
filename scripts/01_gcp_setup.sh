#!/usr/bin/env bash
# One-time GCP project setup for CarbonSaathi.
# Safe to re-run — all steps are idempotent.
set -euo pipefail

# ── Validate required env vars ────────────────────────────────────────────────
: "${GCP_PROJECT_ID:?GCP_PROJECT_ID is required (e.g. carbonsaathi-yourhandle)}"
: "${GCP_BILLING_ACCOUNT_ID:?GCP_BILLING_ACCOUNT_ID is required (e.g. XXXXXX-XXXXXX-XXXXXX)}"
GCP_REGION="${GCP_REGION:-asia-south1}"

echo "================================================================"
echo "  CarbonSaathi — GCP one-time setup"
echo "  Project : ${GCP_PROJECT_ID}"
echo "  Region  : ${GCP_REGION}"
echo "================================================================"
echo ""

# ── Step 1: Verify gcloud is installed and authenticated ──────────────────────
echo "[1/7] Verifying gcloud authentication..."
if ! command -v gcloud &>/dev/null; then
    echo "ERROR: gcloud is not installed. See https://cloud.google.com/sdk/docs/install" >&2
    exit 1
fi
gcloud auth list

# ── Step 2: Create GCP project (no-op if already exists) ─────────────────────
echo ""
echo "[2/7] Creating GCP project ${GCP_PROJECT_ID}..."
if gcloud projects describe "${GCP_PROJECT_ID}" --quiet &>/dev/null; then
    echo "  Project ${GCP_PROJECT_ID} already exists — skipping creation."
else
    gcloud projects create "${GCP_PROJECT_ID}" --quiet
    echo "  Project created."
fi

# ── Step 3: Link billing account ──────────────────────────────────────────────
echo ""
echo "[3/7] Linking billing account ${GCP_BILLING_ACCOUNT_ID}..."
gcloud billing projects link "${GCP_PROJECT_ID}" \
    --billing-account="${GCP_BILLING_ACCOUNT_ID}" \
    --quiet

# ── Step 4: Set active project ────────────────────────────────────────────────
echo ""
echo "[4/7] Setting active project to ${GCP_PROJECT_ID}..."
gcloud config set project "${GCP_PROJECT_ID}"

# ── Step 5: Enable required APIs (idempotent) ─────────────────────────────────
echo ""
echo "[5/7] Enabling required APIs (this may take ~60 seconds)..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    secretmanager.googleapis.com \
    artifactregistry.googleapis.com \
    firestore.googleapis.com \
    firebase.googleapis.com \
    iam.googleapis.com \
    --project="${GCP_PROJECT_ID}" \
    --quiet

# ── Step 6: Create Firestore database in Native mode (no-op if exists) ────────
echo ""
echo "[6/7] Creating Firestore database in ${GCP_REGION} (Native mode)..."
if gcloud firestore databases describe \
        --project="${GCP_PROJECT_ID}" \
        --quiet &>/dev/null 2>&1; then
    echo "  Firestore database already exists — skipping."
else
    gcloud firestore databases create \
        --project="${GCP_PROJECT_ID}" \
        --location="${GCP_REGION}" \
        --type=firestore-native \
        --quiet || echo "  Firestore database may already exist — continuing."
fi

# ── Step 7: Done ──────────────────────────────────────────────────────────────
echo ""
echo "[7/7] Setup complete."
echo ""
echo "================================================================"
echo "  GCP setup finished for project: ${GCP_PROJECT_ID}"
echo "================================================================"
echo ""
echo "Next steps:"
echo "  1. Set up Firebase (manual, ~5 min):"
echo "       https://console.firebase.google.com → Add project → select ${GCP_PROJECT_ID}"
echo "       Authentication → Sign-in method → Google → Enable"
echo "       Project Settings → Your apps → Add Web App → copy firebaseConfig"
echo "  2. Fill in .env with GEMINI_API_KEY and FIREBASE_API_KEY"
echo "  3. Run: make gcp-secrets"
echo "  4. Run: make deploy"
echo ""
