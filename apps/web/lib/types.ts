// Mirror of the subset of orchestrator contracts the UI consumes.
// Keep in sync with packages/contracts/src/meridian_contracts/* and
// services/orchestrator/src/meridian_orchestrator/api.py.

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

export interface ModelUsage {
  input_tokens: number;
  output_tokens: number;
  cache_read_input_tokens?: number;
  cache_creation_input_tokens?: number;
}

export interface ModelResponse {
  id: string;
  model: string;
  content: GroundedQAContent | string | Record<string, unknown>;
  usage: ModelUsage;
  latency_ms: number;
}

export interface Classification {
  intent: string;
  confidence: number;
  model_tier: string;
  workflow: string;
}

export interface RetrievalSummary {
  query_rewritten: string;
  chunks_retrieved: number;
  chunks_after_rerank: number;
  top_relevance_score: number;
}

export interface TimingsMs {
  classification?: number;
  retrieval?: number;
  total?: number;
}

export interface OrchestrationState {
  request_id: string;
  current_state: string;
  classification: Classification | null;
  retrieval: RetrievalSummary | null;
  timings_ms: TimingsMs;
  errors: string[];
}

export interface OrchestratorReply {
  request_id: string;
  status: OrchestratorStatus;
  model_response: ModelResponse | null;
  orchestration_state: OrchestrationState;
  error_message?: string | null;
  cost_usd?: number | null;
}

// ---------------------------------------------------------------------------
// Phase 2: server-side sessions
// ---------------------------------------------------------------------------
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

// Client-side representation of a UI message (what the chat renders).
export interface UIMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  reply?: OrchestratorReply;
  pending?: boolean;
  error?: string;
}
