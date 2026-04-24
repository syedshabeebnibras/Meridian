// Mirror of the subset of orchestrator contracts the UI consumes.
// Keep in sync with packages/contracts/src/meridian_contracts/*.

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

export interface ClassifierContent {
  intent: string;
  confidence: number;
  model_tier: string;
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
  content: GroundedQAContent | ClassifierContent | string | Record<string, unknown>;
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
  input_guardrails?: number;
  classification?: number;
  retrieval?: number;
  assembly?: number;
  dispatch_pending?: number;
  validation?: number;
  output_guardrails?: number;
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
  clarification_question?: string | null;
}

export interface UserRequest {
  request_id: string;
  user_id: string;
  session_id: string;
  query: string;
  conversation_history?: ConversationTurn[];
  metadata?: Record<string, string>;
}

export interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

// Client-side representation of a UI message (what the chat renders).
export interface UIMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  // Only present on assistant messages
  reply?: OrchestratorReply;
  pending?: boolean;
  error?: string;
}

export interface Session {
  id: string;
  title: string;
  createdAt: number;
  messages: UIMessage[];
}
