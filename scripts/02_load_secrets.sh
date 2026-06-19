#!/usr/bin/env bash
# Push secrets from .env into GCP Secret Manager.
# Safe to re-run — adds a new version if the secret already exists.
set -euo pipefail

# ── Validate required env vars ────────────────────────────────────────────────
: "${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"

ENV_FILE="${ENV_FILE:-.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "ERROR: ${ENV_FILE} not found." >&2
    echo "       Copy .env.example to .env and fill in all values before running this script." >&2
    exit 1
fi

echo "================================================================"
echo "  CarbonSaathi — load secrets into Secret Manager"
echo "  Project  : ${GCP_PROJECT_ID}"
echo "  Env file : ${ENV_FILE}"
echo "================================================================"
echo ""

# ── Helper: read a single KEY=value line from .env (no shell export) ──────────
_read_env_value() {
    local var_name="$1"
    local value
    # Match only lines starting with VAR_NAME= (handles optional quotes)
    value=$(grep -E "^${var_name}=" "${ENV_FILE}" \
        | head -n1 \
        | cut -d'=' -f2- \
        | sed 's/^[[:space:]"'"'"']*//;s/[[:space:]"'"'"']*$//')
    echo "${value}"
}

# ── Helper: create or update a secret (value via stdin to avoid CLI leakage) ──
_upsert_secret() {
    local secret_name="$1"
    local secret_value="$2"

    echo "[secret] ${secret_name}"

    if gcloud secrets describe "${secret_name}" \
            --project="${GCP_PROJECT_ID}" --quiet &>/dev/null; then
        echo "  Exists — adding new version..."
        printf '%s' "${secret_value}" \
            | gcloud secrets versions add "${secret_name}" \
                --project="${GCP_PROJECT_ID}" \
                --data-file=- \
                --quiet
    else
        echo "  Creating secret and adding first version..."
        gcloud secrets create "${secret_name}" \
            --project="${GCP_PROJECT_ID}" \
            --replication-policy=automatic \
            --quiet
        printf '%s' "${secret_value}" \
            | gcloud secrets versions add "${secret_name}" \
                --project="${GCP_PROJECT_ID}" \
                --data-file=- \
                --quiet
    fi
    echo "  Done."
    echo ""
}

# ── Load each secret ──────────────────────────────────────────────────────────

GEMINI_API_KEY_VALUE=$(_read_env_value "GEMINI_API_KEY")
if [[ -z "${GEMINI_API_KEY_VALUE}" ]]; then
    echo "ERROR: GEMINI_API_KEY is empty or missing in ${ENV_FILE}" >&2
    exit 1
fi
_upsert_secret "gemini-api-key" "${GEMINI_API_KEY_VALUE}"

FIREBASE_API_KEY_VALUE=$(_read_env_value "FIREBASE_API_KEY")
if [[ -z "${FIREBASE_API_KEY_VALUE}" ]]; then
    echo "ERROR: FIREBASE_API_KEY is empty or missing in ${ENV_FILE}" >&2
    exit 1
fi
_upsert_secret "firebase-api-key" "${FIREBASE_API_KEY_VALUE}"

# ── Done ──────────────────────────────────────────────────────────────────────
echo "================================================================"
echo "  All secrets loaded successfully into project: ${GCP_PROJECT_ID}"
echo "================================================================"
echo ""
echo "Next step: make deploy"
echo ""
