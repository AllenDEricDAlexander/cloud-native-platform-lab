#!/usr/bin/env bash
set -euo pipefail
set +x
: "${ARGOCD_CONFIG:?}" "${APP_NAME:?}" "${ENVIRONMENT:?}" "${APP_URL:?}" "${APP_CURL_CONFIG:?}"
source "$(dirname "$0")/api.sh"
argocd --config "$ARGOCD_CONFIG" app wait "$APP_NAME-$ENVIRONMENT" --sync --health --timeout 600
curl_safe "$APP_CURL_CONFIG" "$APP_URL/health" > release/health.json
curl_safe "$APP_CURL_CONFIG" "$APP_URL/ready" > release/ready.json
curl_safe "$APP_CURL_CONFIG" "$APP_URL/version" > release/version.json
jq -e --arg revision "$(jq -r .source_revision release/release.json)" '.revision==$revision' release/version.json >/dev/null
jq --arg time "$(date -u +%FT%TZ)" '. + {deployment_observed_at:$time,smoke_result:"passed"}' release/release.json > release/observed.json
