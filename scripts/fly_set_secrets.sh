#!/usr/bin/env bash
#
# Push a whitelist of secrets from a local .env into a Fly.io app so the
# orchestrator can reach LiteLLM, Langfuse, Postgres, Redis, and model
# providers without them ever living in the repo.
#
# Usage:
#   scripts/fly_set_secrets.sh                      # reads .env, deploys to $FLY_APP
#   scripts/fly_set_secrets.sh path/to/.env.prod    # custom env file
#   FLY_APP=meridian-orch-prod scripts/fly_set_secrets.sh
#
# Why this exists:
#   `fly secrets import < .env` would ship EVERY variable including
#   dev-only POSTGRES_HOST=localhost and other values that would break
#   the prod wiring. This script pushes only the names we expect prod
#   to consume, and redacts anything empty.

set -euo pipefail

ENV_FILE="${1:-.env}"
FLY_APP="${FLY_APP:-meridian-orch}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "env file not found: $ENV_FILE" >&2
  exit 1
fi

# Whitelist — add here only what the orchestrator actually reads.
SECRET_NAMES=(
  ANTHROPIC_API_KEY
  OPENAI_API_KEY
  AZURE_API_KEY
  AZURE_API_BASE
  AZURE_API_VERSION
  LITELLM_MASTER_KEY
  LANGFUSE_PUBLIC_KEY
  LANGFUSE_SECRET_KEY
  LANGFUSE_HOST
  NEXTAUTH_SECRET
  SALT
  ENCRYPTION_KEY
  DATABASE_URL
  REDIS_URL
  MERIDIAN_ENV
  MERIDIAN_RATELIMIT_ENABLED
  MERIDIAN_RATELIMIT_BURST
  MERIDIAN_RATELIMIT_PER_SECOND
  MERIDIAN_DAILY_BUDGET_USD
  MERIDIAN_SEMANTIC_CACHE_ENABLED
)

declare -a FLY_ARGS=()

# Source the env file in a subshell so we don't pollute our own env.
# `set -a` exports; `set +a` turns it off right after.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

for name in "${SECRET_NAMES[@]}"; do
  val="${!name:-}"
  if [[ -z "$val" ]]; then
    echo "skip  $name (unset in $ENV_FILE)"
    continue
  fi
  # Pass the value via the =val syntax so flyctl doesn't print it.
  FLY_ARGS+=("${name}=${val}")
done

if [[ ${#FLY_ARGS[@]} -eq 0 ]]; then
  echo "no secrets to set" >&2
  exit 1
fi

echo "setting ${#FLY_ARGS[@]} secret(s) on fly app '$FLY_APP'"
fly secrets set --app "$FLY_APP" "${FLY_ARGS[@]}"
