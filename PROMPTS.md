# Prompt Authoring

Every prompt Meridian serves is owned by the **Prompt Registry** (Section 19 D3 of the execution plan) — a Postgres-backed, versioned, immutable store with separate activation rows for zero-downtime rollback. This doc covers the day-to-day authoring flow.

---

## The loop

```
 edit prompts/<name>/v*.yaml
         │
         ▼
 uv run pytest                       # unit tests still green
         │
         ▼
 make bootstrap-prompts              # create a new immutable version
         │
         ▼
 uv run python -m meridian_evaluator.cli \
   --dataset datasets/<name>_v*.yaml \
   --client stub --registry postgres  # offline regression
         │
         ▼
 (for real metric check)
 uv run python -m meridian_evaluator.cli \
   --dataset datasets/<name>_v*.yaml \
   --client live --registry postgres
         │
         ▼
 submit PR with diff + regression output
```

---

## YAML schema

Every prompt lives under `prompts/<name>/v<N>.yaml` with the shape below. The `version` field is **not** declared — the registry auto-increments on `make bootstrap-prompts`.

```yaml
name: <string>                 # matches the directory
model_tier: small | mid | frontier
min_model: <provider model id>  # fallback when routing lacks a tier alias
schema_ref: <schema name>       # points to a JSON schema (future Phase 4 work)
few_shot_dataset: <dataset name or null>
parameters:                     # Jinja vars the template uses
  - user_query
  - company_name

token_budget:                   # per-section caps in tokens
  system: 500
  few_shot: 800
  retrieval: 6000
  history: 2000
  query: 500
  total_max: 16000

cache_control:                  # provider-native cache breakpoints
  breakpoints: [after_system, after_few_shot]
  prefix_stable: true

template: |
  [SYSTEM] ...
  [USER] ...
```

Template syntax is Jinja (autoescape off). Available runtime variables: `user_query`, `retrieved_docs`, `conversation_history`, `few_shot_examples`, plus anything in `context.system_vars`.

Truncation priority when budgets are exceeded (Section 6):

1. System prompt   — never truncated
2. Output schema   — never truncated
3. Few-shot examples — last-to-first
4. Retrieved documents — lowest-relevance-first
5. Conversation history — oldest-first
6. User query — never truncated

---

## Bootstrap and activation

```bash
# Create (if new content) + activate in dev, idempotent.
make bootstrap-prompts

# Hit production — requires explicit flags.
uv run --group bootstrap python scripts/bootstrap_prompts.py \
  --activate --env prod --actor <your-email>
```

The bootstrap script is **idempotent**: a YAML whose content exactly matches the latest stored version is skipped.

---

## Rollback

Any on-call authority can roll back a live template via the registry Python API (the Admin Console wires this up in Phase 6):

```python
registry.rollback("grounded_qa", environment="prod", actor="sre@example.com", reason="faithfulness regression")
```

This archives the current active row and re-activates the most recent archived version. An entry appears in `prompt_audit_log` with `action='rollback'`.

---

## Review and approval (Section 6)

1. Draft a new version in a feature branch.
2. Run the regression suite against it (offline + live if API keys available).
3. Open a PR with the prompt diff, the regression output, and a one-sentence change description.
4. Tech Lead or AI Architect review.
5. Deploy to staging (`bootstrap-prompts --env staging`) and re-run evals.
6. Activate as canary (5%) in prod; monitor 24 h.
7. Promote to 100% if online evals hold; rollback otherwise.
