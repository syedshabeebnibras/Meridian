// Frontend type surface.
//
// Wire types that originate from the Python ``meridian_contracts`` package
// are *generated* — the source of truth lives in Pydantic, schemas are
// emitted by ``scripts/export_schemas.py``, and ``apps/web/scripts/
// generate-types.mjs`` turns them into TypeScript under ``./generated/``.
//
// Anything in this file is either:
//   1. UI-only (renders / state shape that has no Python equivalent).
//   2. Domain types that live on the orchestrator, not the contracts
//      package (e.g. ``OrchestratorReply``, ``GroundedQAContent``).
//
// CI runs ``pnpm gen-types`` and fails on ``git diff --exit-code`` so the
// generated types can never silently drift.

// --- Re-exports from generated contracts ----------------------------------
export type {
  ModelResponse,
  ModelUsage,
  OrchestrationState,
  RetrievalSummary,
  TimingsMs,
  ConversationTurn,
  RetrievedChunk,
  ClassificationResult,
} from "./generated";

// --- Orchestrator-specific (not in contracts) -----------------------------
export type OrchestratorStatus =
  | "ok"
  | "refused"
  | "blocked"
  | "degraded"
  | "failed"
  | "pending_confirmation";

export interface Citation {
  doc_index: number;
  source_title: string;
  relevant_excerpt: string;
}

export interface GroundedQAContent {
  reasoning: string;
  answer: string;
  citations: Citation[];
  confidence: number;
  needs_escalation: boolean;
}

import type {
  ModelResponse as _ModelResponse,
  OrchestrationState as _OrchestrationState,
} from "./generated";

export interface OrchestratorReply {
  request_id: string;
  status: OrchestratorStatus;
  model_response: _ModelResponse | null;
  orchestration_state: _OrchestrationState;
  error_message?: string | null;
  cost_usd?: number | null;
}

// --- Server-side persistence (defined by /v1/sessions endpoints) ----------
export interface ServerSession {
  id: string;
  workspace_id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ServerMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  reply: OrchestratorReply | null;
  created_at: string;
}

// --- UI-only -------------------------------------------------------------
export interface UIMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  reply?: OrchestratorReply;
  pending?: boolean;
  error?: string;
}
