-- Create sibling databases on the same Postgres instance:
--   meridian   : application state (prompt registry, evals, audit, sem cache)  [default, already created]
--   langfuse   : Langfuse self-hosted metadata
--   litellm    : LiteLLM state (keys, virtual users, budgets)
--
-- pgvector is enabled on the meridian database only; the others do not need it.

SELECT 'CREATE DATABASE langfuse'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse')\gexec

SELECT 'CREATE DATABASE litellm'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'litellm')\gexec

\c meridian
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
