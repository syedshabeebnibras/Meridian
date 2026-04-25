/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type ChunkId = string;
export type Content = string;
export type Index = number;
export type RelevanceScore = number;
export type RerankScore = number | null;
export type SourceTitle = string;
export type SourceUrl = string;

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
