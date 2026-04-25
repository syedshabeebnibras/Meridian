#!/usr/bin/env bash
# Public-deploy smoke. Runs against the live web app (Vercel).
#
# Usage:
#   DEPLOY_URL=https://web-tawny-nine-43.vercel.app bash scripts/deploy_smoke.sh
#
# Asserts:
#   - / and /sign-in/sign-up render (200)
#   - /api/auth/session returns ``null`` for an anonymous request
#   - /api/metrics proxies to a live orchestrator (200 + JSON shape)
#   - Every protected route 307s to /sign-in?callbackUrl=...
#   - HSTS header is present
#
# Exits non-zero on any failure. Designed to fit cleanly into a
# post-deploy GitHub Actions step.

set -euo pipefail

URL="${DEPLOY_URL:-}"
if [ -z "$URL" ]; then
  echo "DEPLOY_URL is required" >&2
  exit 2
fi
URL="${URL%/}"

ALL_OK=1

check_status() {
  local path="$1" expected="$2" label="$3"
  local actual
  actual=$(curl -sS -o /dev/null -w "%{http_code}" "$URL$path")
  if [ "$actual" = "$expected" ]; then
    echo "[PASS] $label  ($path → $actual)"
  else
    echo "[FAIL] $label  ($path → $actual, expected $expected)"
    ALL_OK=0
  fi
}

check_redirect() {
  local path="$1" label="$2"
  # Append \n so ``read`` sees a complete record under ``set -e``.
  local out
  out=$(curl -sS -o /dev/null -w "%{http_code} %{redirect_url}\n" "$URL$path")
  local code redirect
  code="${out%% *}"
  redirect="${out#* }"
  if [ "$code" = "307" ] && [[ "$redirect" == *"/sign-in?callbackUrl="* ]]; then
    echo "[PASS] $label  ($path → 307 → sign-in)"
  else
    echo "[FAIL] $label  ($path → $code, redirect=$redirect)"
    ALL_OK=0
  fi
}

# 1. Public surfaces.
check_status "/"        200 "landing"
check_status "/sign-in" 200 "sign-in"
check_status "/sign-up" 200 "sign-up"

# 2. Auth + metrics.
auth_session=$(curl -sS "$URL/api/auth/session")
if [ "$auth_session" = "null" ]; then
  echo "[PASS] /api/auth/session anonymous returns null"
else
  echo "[FAIL] /api/auth/session expected 'null', got: ${auth_session:0:120}"
  ALL_OK=0
fi

metrics=$(curl -sS "$URL/api/metrics")
if echo "$metrics" | grep -q '"requests_total"'; then
  echo "[PASS] /api/metrics live (proxy → orchestrator)"
else
  echo "[FAIL] /api/metrics shape unexpected: ${metrics:0:120}"
  ALL_OK=0
fi

# 3. Protected routes redirect with callbackUrl preserved.
for path in /dashboard /admin /chat /documents /settings /api/sessions; do
  check_redirect "$path" "$path is auth-gated"
done

# 4. HSTS header present.
if curl -sS -I "$URL/" | grep -qi "^strict-transport-security:"; then
  echo "[PASS] strict-transport-security header present"
else
  echo "[FAIL] strict-transport-security missing"
  ALL_OK=0
fi

echo
if [ "$ALL_OK" = "1" ]; then
  echo "DEPLOY SMOKE: PASS"
  exit 0
else
  echo "DEPLOY SMOKE: FAIL"
  exit 1
fi
