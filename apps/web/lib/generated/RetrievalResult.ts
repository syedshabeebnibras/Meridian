/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type Query = string;
export type QueryRewritten = string;
export type ChunkId = string;
export type Content = string;
export type Index = number;
export type RelevanceScore = number;
export type RerankScore = number | null;
export type SourceTitle = string;
export type SourceUrl = string;
export type Results = RetrievedChunk[];
export type RetrievalLatencyMs = number;
export type TotalAfterRerank = number;
export type TotalChunksRetrieved = number;

export interface RetrievalResult {
  query: Query;
  query_rewritten: QueryRewritten;
  results: Results;
  retrieval_latency_ms: RetrievalLatencyMs;
  total_after_rerank: TotalAfterRerank;
  total_chunks_retrieved: TotalChunksRetrieved;
}
export interface RetrievedChunk {
  chunk_id: ChunkId;
  content: Content;
  index: Index;
  metadata?: Metadata;
  relevance_score: RelevanceScore;
  rerank_score?: RerankScore;
  source_title: SourceTitle;
  source_url: SourceUrl;
}
export interface Metadata {
  [k: string]: string;
}
