/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type ChunksAfterRerank = number;
export type ChunksRetrieved = number;
export type QueryRewritten = string;
export type TopRelevanceScore = number;

export interface RetrievalSummary {
  chunks_after_rerank: ChunksAfterRerank;
  chunks_retrieved: ChunksRetrieved;
  query_rewritten: QueryRewritten;
  top_relevance_score: TopRelevanceScore;
}
