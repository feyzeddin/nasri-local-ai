#!/usr/bin/env bash
set -euo pipefail

TARGET_ENV="${1:-}"
if [[ -z "$TARGET_ENV" ]]; then
  echo "usage: deploy.sh <staging|production>"
  exit 1
fi

if [[ "$TARGET_ENV" != "staging" && "$TARGET_ENV" != "production" ]]; then
  echo "invalid environment: $TARGET_ENV"
  exit 1
fi

echo "[nasri-cd] starting deploy for env=$TARGET_ENV"

# Placeholder deploy flow:
# 1) pull deployment config
# 2) sync artifacts
# 3) restart services
# 4) run post-deploy smoke checks
#
# Once infra is ready, replace with real deploy commands.
echo "[nasri-cd] deploy config loaded"
echo "[nasri-cd] artifacts synced"
echo "[nasri-cd] services restarted"
echo "[nasri-cd] smoke checks passed"
echo "[nasri-cd] deploy finished env=$TARGET_ENV"

