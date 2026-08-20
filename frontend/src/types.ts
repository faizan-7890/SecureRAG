export interface Source {
  filename: string;
  excerpt: string;
  page?: number | null;
  chunk_index?: number | null;
  relevance_score?: number | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  sources?: Source[];
  timestamp: string;
}

export interface DocumentRecord {
  document_id: string;
  filename: string;
  chunks: number;
  uploaded_at: string;
  owner_id: string;
  file_extension: string;
  source_sha256: string;
  source_size_bytes: number;
}

export interface ChunkDetail {
  chunk_id: string;
  chunk_index: number;
  content: string;
  page?: number | null;
  allowed_roles?: string | null;
  owner_id?: string | null;
}

export interface DocumentChunksResponse {
  document_id: string;
  filename: string;
  total_chunks: number;
  chunks: ChunkDetail[];
}

export interface UserProfile {
  username: string;
  role: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface EvaluationSample {
  question: string;
  ground_truth: string;
  response: string;
  faithfulness?: number;
  answer_relevancy?: number;
  context_precision?: number;
  context_recall?: number;
  answer_correctness?: number;
}

export interface EvaluationResults {
  timestamp: string;
  duration_seconds: number;
  sample_count: number;
  aggregate_scores: {
    faithfulness?: number;
    answer_relevancy?: number;
    context_precision?: number;
    context_recall?: number;
    answer_correctness?: number;
  };
  per_sample: EvaluationSample[];
}

export interface RuntimeSettings {
  apiUrl: string;
  apiKey: string;
  streaming: boolean;
  hybridSearch: boolean;
  queryExpansion: boolean;
}
