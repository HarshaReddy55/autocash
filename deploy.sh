#!/usr/bin/env bash
# AutoCash - one-command Cloud Run deployment (Google Cloud Shell or local gcloud).
# Usage:
#   PROJECT_ID=<your-project> ./deploy.sh            # private-by-default, secured mode
#   PROJECT_ID=<your-project> DEMO=1 ./deploy.sh     # public demo link for sharing
# DEMO mode: no secrets, --allow-unauthenticated, app runs its built-in demo
# workspace (synthetic data). Send this URL to reviewers. Switch to secured
# mode for any real data: it creates a bootstrap secret and locks the app
# behind API keys.
set -euo pipefail
PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID to your GCP project id}"
REGION="${REGION:-asia-south1}"
SERVICE="${SERVICE:-autocash}"
DEMO="${DEMO:-0}"

gcloud config set project "$PROJECT_ID" >/dev/null
echo "==> Enabling required APIs"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

if [ "$DEMO" = "1" ]; then
  echo "==> DEMO deploy: public URL, demo workspace, no secrets"
  gcloud run deploy "$SERVICE" --source . --region "$REGION" \
    --allow-unauthenticated --memory 1Gi --cpu 1 \
    --set-env-vars AUTOCASH_DATA_DIR=/tmp/autocash-data
else
  echo "==> Secured deploy: secrets from Secret Manager, API keys enforced"
  if ! gcloud secrets describe autocash-bootstrap >/dev/null 2>&1; then
    read -rsp "Enter a strong AUTOCASH_BOOTSTRAP_KEY: " BOOT; echo
    printf '%s' "$BOOT" | gcloud secrets create autocash-bootstrap --data-file=-
  fi
  if ! gcloud secrets describe autocash-gemini >/dev/null 2>&1; then
    read -rsp "Enter GEMINI_API_KEY (optional, Enter to skip): " GEM; echo
    printf '%s' "${GEM:-DISABLED}" | gcloud secrets create autocash-gemini --data-file=-
  fi
  PN="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  SA="${PN}-compute@developer.gserviceaccount.com"
  for S in autocash-bootstrap autocash-gemini; do
    gcloud secrets add-iam-policy-binding "$S" --member="serviceAccount:${SA}" \
      --role="roles/secretmanager.secretAccessor" >/dev/null
  done
  gcloud run deploy "$SERVICE" --source . --region "$REGION" \
    --no-allow-unauthenticated --memory 1Gi --cpu 1 \
    --set-env-vars AUTOCASH_DATA_DIR=/tmp/autocash-data \
    --set-secrets AUTOCASH_BOOTSTRAP_KEY=autocash-bootstrap:latest,GEMINI_API_KEY=autocash-gemini:latest
fi

echo "==> Service URL"
gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)'
echo "Check <URL>/ready shows ready:true, then open the URL."
