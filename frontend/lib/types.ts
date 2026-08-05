// Mirrors backend/app/schemas.py exactly. Keep the two in step.

export type Verdict =
  | "answered"
  | "refused_out_of_scope"
  | "blocked_not_grounded"
  | "not_stated"
  | "error";

export interface Chunk {
  text: string;
  page: number;
  score: number;
  chunk_index: number;
  doc_id: string;
  language: string;
}

export interface Citation {
  page: number;
  quote: string;
  score: number;
}

export interface ScopeTrace {
  verdict: "ALLOW" | "REFUSE";
  reason: string;
  layer: "pattern" | "llm" | "none";
  latency_ms: number;
}

export interface RetrievalTrace {
  chunks: number;
  top_score: number;
  pages: number[];
  latency_ms: number;
}

export interface AnswerTrace {
  model: string;
  repaired: boolean;
  latency_ms: number;
}

export interface GroundingTrace {
  verdict: "GROUNDED" | "NOT_GROUNDED" | "SKIPPED";
  method: "numeric" | "llm" | "citation" | "none";
  latency_ms: number;
}

export interface Trace {
  scope_guard?: ScopeTrace | null;
  retrieval?: RetrievalTrace | null;
  answer?: AnswerTrace | null;
  grounding_guard?: GroundingTrace | null;
  total_latency_ms: number;
}

export interface ChatResponse {
  request_id: string;
  verdict: Verdict;
  answer: string;
  citations: Citation[];
  chunks: Chunk[];
  doc_id: string;
  trace: Trace;
}

export interface DocumentInfo {
  doc_id: string;
  bank: string;
  title: string;
  jurisdiction: string;
  language: string;
  pages: number;
  chunks: number;
  source_url: string;
  is_default: boolean;
}

export interface ReadyResponse {
  ready: boolean;
  collection: string;
  points: number;
  documents: number;
  chat_providers: string[];
  embed_provider: string;
  embed_model: string;
}

export interface DocumentsResponse {
  default_doc_id: string;
  documents: DocumentInfo[];
}

export interface ApiError {
  code: string;
  message: string;
  request_id?: string;
}

export type TraceStage = "scope_guard" | "retrieval" | "answer" | "grounding_guard";
export type StageStatus = "idle" | "running" | "done";

export interface TraceEvent {
  stage: TraceStage;
  status: StageStatus;
  [key: string]: unknown;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  verdict?: Verdict;
  citations?: Citation[];
  chunks?: Chunk[];
  trace?: Trace;
  pending?: boolean;
  requestId?: string;
}
