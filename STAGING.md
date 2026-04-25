# Staging

Phase 7 of the execution plan — deploy to a staging environment, run
shadow traffic, validate quality + operations before production.

---

## Two deployment paths

### Path A — Fly.io (free tier, recommended)

```bash
# One-time setup
fly auth login
fly launch --no-deploy --copy-config --name meridian-orch

# Set secrets
fly secrets set \
  ANTHROPIC_API_KEY="sk-ant-..." \
  OPENAI_API_KEY="sk-..." \
  LITELLM_MASTER_KEY="sk-meridian-..." \
  ORCH_INTERNAL_KEY="$(openssl rand -hex 32)" \
  DATABASE_URL="postgresql+psycopg://..." \
  LANGFUSE_PUBLIC_KEY="pk-..." \
  LANGFUSE_SECRET_KEY="sk-lf-..." \
  RAG_BASE_URL="https://rag.example.com" \
  JIRA_EMAIL="svc@company.com" \
  JIRA_API_TOKEN="..." \
  SLACK_BOT_TOKEN="xoxb-..."

# Deploy
scripts/deploy_staging.sh
```

### Path B — docker-compose (dev box / bare-metal staging)

```bash
cp .env.example .env.staging
# ...fill in .env.staging with real staging credentials...
# For compose, set ORCHESTRATOR_DATABASE_URL to the container hostname:
# ORCHESTRATOR_DATABASE_URL=postgresql+psycopg://meridian:meridian@postgres:5432/meridian
# Keep DATABASE_URL=postgresql+psycopg://meridian:meridian@localhost:5432/meridian
# for host-run migration/bootstrap commands.

docker compose \
  --env-file .env.staging \
  -f docker-compose.yml -f docker-compose.staging.yml \
  up -d --build

scripts/deploy_staging.sh --compose
```

Either path runs the orchestrator on port 8080 with `POST /v1/chat`,
`GET /healthz`, `GET /readyz`, `GET /metrics`.

---

## Post-deploy verification (exit criteria)

```bash
export STAGING_URL=https://meridian-orch.fly.dev  # or http://localhost:8080

# 1. Smoke test — 60s sanity check
uv run python scripts/staging_smoke.py

# 2. Shadow replay against anonymized production queries
uv run python scripts/shadow_replay.py \
  --endpoint $STAGING_URL/v1/chat \
  --input logs/anonymized_queries.jsonl \
  --output /tmp/shadow_report.md

# 3. Load test — 50 req/min for 60s
uv run python scripts/load_test.py \
  --endpoint $STAGING_URL/v1/chat \
  --rps 0.83 --duration 60 \
  --output /tmp/load_test.md

# 4. Red-team security suite
uv run python scripts/red_team.py \
  --endpoint $STAGING_URL/v1/chat \
  --output ops/security-review-report.md

# 5. Launch gates (now against real models via the staging endpoint)
uv run python scripts/check_launch_gates.py
```

Each script exits non-zero on failure so you can wire them into a CI
"promote-to-prod" gate.

---

## Rollback

Fly.io:
```bash
fly releases -a meridian-orch     # list releases
fly deploy --image registry.fly.io/meridian-orch:v<N>   # roll back to version N
```

docker-compose:
```bash
# Tag the last-known-good image before deploy:
docker tag meridian-orchestrator:latest meridian-orchestrator:good
# On rollback:
docker compose -f docker-compose.yml -f docker-compose.staging.yml \
  up -d orchestrator --force-recreate
# with image: meridian-orchestrator:good
```

---

## Secrets map

Every secret the staging orchestrator needs. Missing keys cause `/readyz`
to return 503 at startup or degrade gracefully.

| Variable | Used by | Required for |
|---|---|---|
| `ANTHROPIC_API_KEY` | LiteLLM | Primary Claude tier |
| `OPENAI_API_KEY` | LiteLLM | Secondary failover |
| `LITELLM_MASTER_KEY` | Gateway | Orchestrator → LiteLLM auth |
| `LITELLM_BASE_URL` | Gateway | Location of shared proxy |
| `DATABASE_URL` | Registry + evals + audit | Everything DB-backed |
| `ORCH_INTERNAL_KEY` | Orchestrator + web | Shared internal API auth |
| `REDIS_URL` | Session memory + rate limiter | Session continuity |
| `RAG_BASE_URL` + `RAG_API_KEY` | Retrieval | Grounded Q&A |
| `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY` + `LANGFUSE_HOST` | Telemetry | Production trace export |
| `LLAMA_GUARD_BASE_URL` + `LLAMA_GUARD_API_KEY` | Guardrails | Input injection detection |
| `PATRONUS_BASE_URL` + `PATRONUS_API_KEY` | Guardrails | Output faithfulness |
| `JIRA_BASE_URL` + `JIRA_EMAIL` + `JIRA_API_TOKEN` | Tools | Jira tool execution |
| `SLACK_BOT_TOKEN` | Tools | Slack tool execution |
| `OTEL_ENABLED` | Telemetry | Enable OTel span export |
| `MERIDIAN_ENV` | App config | Environment label |

The orchestrator degrades gracefully for any missing optional secret
(guardrails fail-open, retrieval falls back to mock) so staging can run
with a partial set while the team provisions the rest.

---

## First-time setup checklist

- [ ] Fly.io account (or cloud target decided)
- [ ] Supabase / Neon Postgres + `DATABASE_URL`
- [ ] Upstash Redis + `REDIS_URL` (optional)
- [ ] `ORCH_INTERNAL_KEY` generated and set on both orchestrator and Vercel
- [ ] All provider API keys + LiteLLM master key
- [ ] Langfuse v3 stack deployed (or hosted plan) + public/secret keys
- [ ] Data Platform: staging RAG endpoint + API key
- [ ] IT/DevOps: Jira service account + Slack bot install
- [ ] Security: Llama Guard endpoint + Patronus Lynx key + DPA
- [ ] `fly secrets set` all of the above
- [ ] `scripts/deploy_staging.sh`
- [ ] All five verification scripts pass
