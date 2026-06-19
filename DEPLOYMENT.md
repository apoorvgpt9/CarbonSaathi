# Deployment Runbook

Cloud Run deployment for CarbonSaathi. All infra is managed via `gcloud` CLI — no Terraform, no Cloud Console clicking except the one-time Firebase step.

## Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and authenticated (`gcloud auth login`)
- A GCP billing account ID (find it with `gcloud billing accounts list`)
- A unique GCP project ID (e.g. `carbonsaathi-yourhandle`)
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey)

## One-time GCP setup

```bash
export GCP_PROJECT_ID=carbonsaathi-<your-handle>
export GCP_BILLING_ACCOUNT_ID=XXXXXX-XXXXXX-XXXXXX
export GCP_REGION=asia-south1   # default — omit to use this value

make gcp-setup
```

This script:
- Creates the GCP project and links the billing account
- Enables all required APIs (Cloud Run, Cloud Build, Secret Manager, Firestore, Firebase, IAM)
- Creates the Firestore database in Native mode in `${GCP_REGION}`

## Firebase setup (manual — one-time, ~5 minutes)

This step cannot be automated without the Firebase Management API (requires additional quota approval).

1. Go to <https://console.firebase.google.com>
2. Click **Add project** → select the GCP project you just created (`${GCP_PROJECT_ID}`)
3. Google Analytics: optional — recommend **off** for hackathon speed
4. Once added, go to **Authentication → Sign-in method → Google → Enable**
5. Go to **Project Settings → General → Your apps → Add a Web App**
6. Copy the `firebaseConfig` values and fill in `.env`:

```bash
cp .env.example .env
# Edit .env and set:
# FIREBASE_API_KEY=<apiKey from firebaseConfig>
# FIREBASE_AUTH_DOMAIN=<authDomain from firebaseConfig>  (usually <project>.firebaseapp.com)
# FIREBASE_PROJECT_ID=<same as GCP_PROJECT_ID>
# GEMINI_API_KEY=<your Gemini API key>
```

## Load secrets into Secret Manager

```bash
export GCP_PROJECT_ID=carbonsaathi-<your-handle>
make gcp-secrets
```

This pushes `GEMINI_API_KEY` and `FIREBASE_API_KEY` from `.env` into Secret Manager. The values are passed via stdin — they never appear in process arguments or shell history.

## Deploy

```bash
export GCP_PROJECT_ID=carbonsaathi-<your-handle>
export GCP_REGION=asia-south1
make deploy
```

The script:
1. Creates the `carbonsaathi-runner` service account and binds `roles/datastore.user`, `roles/secretmanager.secretAccessor`, `roles/logging.logWriter`
2. Uploads local source to Cloud Build and builds the container
3. Deploys to Cloud Run (`min-instances=1` to avoid cold starts)
4. On the **first deploy**: sets `ALLOWED_ORIGINS=*` initially, captures the real URL, then re-deploys to tighten CORS to that URL
5. Persists the deployed URL to `.deploy-url` (gitignored) for future re-deploys
6. Runs a smoke test against `/api/health`

Expected output at the end:

```
================================================================
  Deployment successful!

  URL: https://carbonsaathi-<hash>-el.a.run.app
================================================================
```

## Re-deploy after code changes

```bash
make deploy
```

No flags needed — `GCP_PROJECT_ID` and `GCP_REGION` are the only required env vars.

## Verify manually

```bash
curl https://carbonsaathi-<hash>-el.a.run.app/api/health
# Expected: {"status":"ok","version":"0.1.0"}
```

## View logs

```bash
gcloud logging read \
  "resource.type=cloud_run_revision AND resource.labels.service_name=carbonsaathi" \
  --project="${GCP_PROJECT_ID}" \
  --limit=100 \
  --format="value(textPayload)"
```

## Cloud Run service config reference

| Parameter        | Value                          |
|------------------|--------------------------------|
| Region           | `asia-south1`                  |
| CPU              | 1                              |
| Memory           | 512 MiB                        |
| Min instances    | 1 (no cold starts)             |
| Max instances    | 3 (hackathon cap)              |
| Concurrency      | 80                             |
| Request timeout  | 60 s                           |
| Port             | 8080                           |
| Auth             | `--allow-unauthenticated`      |
| Service account  | `carbonsaathi-runner@<project>.iam.gserviceaccount.com` |
