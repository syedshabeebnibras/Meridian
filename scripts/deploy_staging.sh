#!/usr/bin/env bash
# Staging deploy helper. Defaults to Fly.io; pass --compose to deploy via
# docker-compose locally (useful for smoke-testing the staging config
# before pushing to the cloud).
#
# Usage:
#   scripts/deploy_staging.sh                       # Fly.io
#   scripts/deploy_staging.sh --compose             # local docker-compose
#   scripts/deploy_staging.sh --dry-run             # just print what would run

set -euo pipefail

MODE="fly"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --compose) MODE="compose"; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

run() {
  if $DRY_RUN; then
    echo "+ $*"
  else
    echo "+ $*" >&2
    "$@"
  fi
}

case "$MODE" in
  fly)
    if ! command -v fly >/dev/null 2>&1; then
      echo "ERROR: 'fly' CLI not installed. See https://fly.io/docs/flyctl/install/" >&2
      exit 1
    fi
    echo "Deploying orchestrator to Fly.io..."
    run fly deploy --config fly.toml --dockerfile services/orchestrator/Dockerfile
    echo ""
    echo "Running post-deploy smoke test..."
    run bash -c 'APP_URL=$(fly info --json | python -c "import json,sys; print(\"https://\"+json.load(sys.stdin)[\"Hostname\"])"); STAGING_URL=$APP_URL uv run python scripts/staging_smoke.py'
    ;;
  compose)
    echo "Bringing up the staging overlay..."
    run docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d --build orchestrator
    echo ""
    echo "Waiting for /healthz..."
    for _ in $(seq 1 30); do
      if curl -fsS http://localhost:8080/healthz >/dev/null 2>&1; then
        echo "Orchestrator healthy."
        STAGING_URL=http://localhost:8080 uv run python scripts/staging_smoke.py
        exit 0
      fi
      sleep 1
    done
    echo "Orchestrator failed to report ready within 30s" >&2
    exit 1
    ;;
esac
