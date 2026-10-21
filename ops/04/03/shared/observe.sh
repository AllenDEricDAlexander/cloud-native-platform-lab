#!/usr/bin/env bash
set -euo pipefail
set +x
: "${ARGOCD_CONFIG:?}" "${APP_NAME:?}" "${ENVIRONMENT:?}" "${APP_URL:?}" "${APP_CURL_CONFIG:?}"
source "$(dirname "$0")/api.sh"
argocd --config "$ARGOCD_CONFIG" app wait "$APP_NAME-$ENVIRONMENT" --sync --health --timeout 600
argocd --config "$ARGOCD_CONFIG" app get "$APP_NAME-$ENVIRONMENT" --refresh -o json > release/argocd.json
jq -e --arg image "$(jq -r .image release/release.json)" '.status.sync.status=="Synced" and .status.health.status=="Healthy" and (.status.summary.images|index($image))!=null' release/argocd.json >/dev/null
curl_safe "$APP_CURL_CONFIG" "$APP_URL/health" > release/health.json
curl_safe "$APP_CURL_CONFIG" "$APP_URL/ready" > release/ready.json
curl_safe "$APP_CURL_CONFIG" "$APP_URL/version" > release/version.json
jq -e --arg revision "$(jq -r .source_revision release/release.json)" '.revision==$revision' release/version.json >/dev/null
jq --arg time "$(date -u +%FT%TZ)" --arg gitops "$(jq -er .status.sync.revision release/argocd.json)" '. + {deployment_observed_at:$time,gitops_revision:$gitops,smoke_result:"passed"}' release/release.json > release/observed.json
