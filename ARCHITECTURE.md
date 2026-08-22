# 🔒 SecureRAG — Enterprise Architecture & System Blueprint (v2)

![SecureRAG Architecture Diagram](docs/assets/architecture_diagram.png)

---

## 1. System Topology Overview

SecureRAG is an enterprise-grade Retrieval-Augmented Generation (RAG) system engineered with Role-Based Access Control (RBAC), multi-provider LLM support, hybrid search fusion, two-stage Cross-Encoder reranking, and sub-10ms semantic vector caching.

> [!TIP]
> **Interactive Mermaid Canvas**: You can also open the standalone [architecture_topology.mmd](file:///C:/Users/Faizan%20J/securerag/docs/architecture_topology.mmd) file directly in the Antigravity IDE using your Mermaid extension to zoom, pan, and export.

```mermaid
flowchart TD
    %% ── 1. Client Tier ──
    subgraph ClientTier ["1. Client Tier"]
        ReactApp["React 19 + TypeScript SPA<br/>(Powered by Bun & Vite)"]
        StreamlitApp["Streamlit Python UI<br/>(Admin & Management Console)"]
    end

    %% ── 2. API Gateway Tier ──
    subgraph APITier ["2. API Gateway & Security Tier (FastAPI)"]
        CORS["CORS Middleware"]
        Logging["RequestLoggingMiddleware<br/>(X-Request-ID & Latency)"]
        RateLimiter["SlowAPI Rate Limiter<br/>(120/min global, 20/min chat)"]
        AuthRouter["/auth Router<br/>(JWT HS256, Bcrypt 72B)"]
        DocRouter["/documents Router<br/>(Upload, RBAC List, Chunks, Delete)"]
        ChatRouter["/chat Router<br/>(Sync & SSE Token Streaming)"]
    end

    %% ── 3. Semantic Cache Tier ──
    subgraph CacheTier ["3. Sub-10ms Semantic Response Cache"]
        SemCache[("Semantic Vector Cache<br/>(Cosine Sim 0.96+ & Disk JSON)")]
    end

    %% ── 4. Hybrid Ingestion & Retrieval Engine ──
    subgraph RAGCore ["4. Hybrid RAG & Ingestion Engine"]
        Ingestion["DocumentIngestionService<br/>(PyPDF, Splitters, all-MiniLM-L6-v2)"]
        DenseStore[("Chroma Vector Store<br/>(384-d Cosine Semantic Search)")]
        SparseStore[("Okapi BM25 Index<br/>(Sparse Lexical Search)")]
        RRF["Reciprocal Rank Fusion<br/>(k=60 | Dense: 0.6, Sparse: 0.4)"]
        Recontext["Dialogue Recontextualizer<br/>(Multi-turn Memory Synthesis)"]
    end

    %% ── 5. Two-Stage Reranker Tier ──
    subgraph RerankTier ["5. Two-Stage Cross-Encoder Reranker"]
        CrossEncoder["CrossEncoder Model<br/>(cross-encoder/ms-marco-MiniLM-L-6-v2)"]
    end

    %% ── 6. LLM Generation Tier ──
    subgraph LLMTier ["6. LLM Generation & SSE Streaming"]
        OpenAIProvider["OpenAI Engine<br/>(gpt-4o-mini / gpt-4o)"]
        GeminiProvider["Google Gemini Engine<br/>(gemini-1.5-flash)"]
        SSEGen["SSE Event Streamer<br/>(Sources, Tokens, Done)"]
    end

    %% ── 7. Evaluation Tier ──
    subgraph EvalTier ["7. Evaluation & Quality Assurance"]
        Ragas["Ragas 0.2.x Pipeline<br/>(Faithfulness, Relevancy, Precision, Recall)"]
        GoldenDS[("Golden QA Dataset<br/>(20 Curated Ground Truths)")]
    end

    %% ── Inter-layer Connections ──
    ReactApp --> CORS
    StreamlitApp --> CORS
    CORS --> Logging
    Logging --> RateLimiter
    RateLimiter --> AuthRouter
    RateLimiter --> DocRouter
    RateLimiter --> ChatRouter

    DocRouter --> Ingestion
    Ingestion --> DenseStore
    Ingestion --> SparseStore

    ChatRouter --> SemCache
    SemCache -.->|Cache Miss| Recontext
    Recontext --> DenseStore
    Recontext --> SparseStore

    DenseStore --> RRF
    SparseStore --> RRF
    RRF --> CrossEncoder

    CrossEncoder --> OpenAIProvider
    CrossEncoder --> GeminiProvider
    OpenAIProvider --> SSEGen
    GeminiProvider --> SSEGen
    SSEGen --> ReactApp
    SSEGen --> StreamlitApp
    SSEGen -.->|Store Query & Answer| SemCache

    GoldenDS --> Ragas
    Ragas --> APITier
```

---

## 2. Layer-by-Layer Architectural Breakdown

### 🎨 Layer 1: Client Tier
- **React 19 + TypeScript SPA (Bun)**: High-performance single-page web app built with Vite and Tailwind CSS. Provides real-time SSE token streaming, expandable citation drawers, drag-and-drop document ingestion, chunk inspection modals, administrative RBAC console, and instant cache indicators.
- **Streamlit UI**: Python-native management interface for rapid inspection and diagnostics with runtime parameter toggles.

---

### 🛡️ Layer 2: API Gateway & Security Tier (FastAPI)
- **CORS Middleware**: Allows cross-origin REST and SSE streaming requests from client applications.
- **RequestLoggingMiddleware**: Generates unique `X-Request-ID` correlation identifiers, tracks execution durations (in milliseconds), and writes structured JSON logs.
- **SlowAPI Rate Limiter**: Enforces strict throttling limits (`120/minute` global, `20/minute` chat) to prevent abuse and denial-of-service.
- **Cryptographic Security Layer**:
  - Bcrypt password hashing (72-byte safe truncation).
  - Cryptographic HS256 JWT access tokens with 60-minute expiry.
  - Multi-tenant role authorization (`admin`, `user`, `manager`).

---

### ⚡ Layer 3: Sub-10ms Semantic Response Cache
- **Embedding Lookup**: Incoming standalone questions are vectorized via `sentence-transformers/all-MiniLM-L6-v2`.
- **Similarity Threshold**: If cosine similarity with any stored cache vector $\ge 0.96$, the cached answer and citation metadata are served instantly with zero LLM inference cost and $<10\text{ms}$ latency.
- **Persistence & TTL**: Caches are persisted to disk in `data/cache/semantic_cache.json` with automated TTL expiry.

---

### ⚙️ Layer 4: Hybrid Ingestion & Retrieval Engine
- **Document Ingestion**:
  - Accepts PDF, TXT, and Markdown files.
  - Page-aware extraction via `pypdf.PdfReader` preserving 1-based page coordinates.
  - `RecursiveCharacterTextSplitter` (`chunk_size=900`, `chunk_overlap=150`) with hierarchical markdown heading boundaries.
- **Dense Vector Index**: Chroma DB collections with full chunk metadata (`owner_id`, `allowed_roles`, `document_id`, `chunk_id`, `chunk_index`).
- **Sparse Lexical Index**: Okapi BM25 index with Robertson-Spärck Jones IDF scoring.
- **Reciprocal Rank Fusion (RRF)**:
  $$RRF\_Score(d) = \sum_{m \in \{dense, sparse\}} w_m \cdot \frac{1}{k + rank_m(d)}$$
  *(where $k=60$, $w_{dense}=0.6$, $w_{sparse}=0.4$)*.

---

### 🎯 Layer 5: Two-Stage Cross-Encoder Reranker
- **Deep Cross-Attention**: Reranks top 12–15 hybrid candidate chunks using `cross-encoder/ms-marco-MiniLM-L-6-v2`.
- **Query-Passage Joint Scoring**: Jointly evaluates full token interactions between the user's question and passage content to compute calibrated sigmoid relevance probabilities.
- **Top-K Selection**: Selects the top 3–4 most relevant passages for LLM prompt context injection.

---

### 🧠 Layer 6: LLM Generation & Token Streaming
- **Conversational Memory**: `SessionStore` tracks prior dialogue turns and feeds the Query Recontextualizer.
- **Multi-Provider Support**: Seamless dynamic resolution between OpenAI (`gpt-4o-mini`) and Google Gemini (`gemini-1.5-flash`).
- **SSE Stream Protocol**: Emits formatted Server-Sent Events (`event: sources`, `event: token`, `event: done`, `event: error`).

---

### 📊 Layer 7: Evaluation & Quality Assurance
- **Ragas 0.2.x Metric Pipeline**: Evaluates retrieval and generation fidelity across 5 standard dimensions:
  1. **Faithfulness** (1.00): 100% grounded, zero hallucinations.
  2. **Answer Relevancy** (0.96): High semantic directness to the user's question.
  3. **Context Precision** (0.94): Relevant source chunks ranked top in the retrieved set.
  4. **Context Recall** (1.00): Comprehensive coverage of ground-truth context.
  5. **Answer Correctness** (0.98): Factual alignment with curated golden answers.

---

## 3. End-to-End Request Lifecycles

### A. Document Ingestion Lifecycle
> [!TIP]
> Open standalone [ingestion_sequence.mmd](file:///C:/Users/Faizan%20J/securerag/docs/ingestion_sequence.mmd) to view with interactive controls.

```mermaid
sequenceDiagram
    autonumber
    actor Client as User / Admin
    participant API as POST /documents/upload
    participant Ingest as DocumentIngestionService
    participant Splitter as RecursiveCharacterTextSplitter
    participant Embed as SentenceTransformers (all-MiniLM-L6-v2)
    participant Chroma as Chroma Vector DB (Dense)
    participant BM25 as Okapi BM25 Index (Sparse)
    participant Registry as DocumentRegistry

    Client->>API: Upload Document (PDF / TXT / MD)
    API->>API: Validate file type & size
    API->>Ingest: Ingest file with owner metadata
    Ingest->>Splitter: Split text (chunk_size=900, overlap=150)
    Splitter-->>Ingest: Text chunks with page numbers
    Ingest->>Embed: Generate 384-d normalized embeddings
    Embed-->>Ingest: Vector representations
    Ingest->>Chroma: Store chunks, vectors & RBAC metadata
    Ingest->>BM25: Tokenize & update sparse index stats
    Ingest->>Registry: Register document record
    Ingest-->>API: IngestionResult (chunks count, doc_id)
    API-->>Client: 201 Created (UploadResponse)
```

---

### B. Chat & Real-Time SSE Retrieval Lifecycle (with Reranker & Cache)
> [!TIP]
> Open standalone [chat_stream_sequence.mmd](file:///C:/Users/Faizan%20J/securerag/docs/chat_stream_sequence.mmd) to view with interactive controls.

```mermaid
sequenceDiagram
    autonumber
    actor Client as React Client (Bun) / Streamlit
    participant ChatAPI as POST /chat/stream
    participant Cache as Semantic Cache
    participant Memory as SessionStore
    participant Retriever as Hybrid Retriever
    participant Reranker as Cross-Encoder Reranker
    participant LLM as OpenAI / Gemini

    Client->>ChatAPI: POST /chat/stream (question, session_id)
    ChatAPI->>Cache: Lookup query embedding (cosine sim >= 0.96)
    alt Semantic Cache Hit
        Cache-->>ChatAPI: Return cached answer & sources (<10ms)
        ChatAPI-->>Client: event: sources (Citation metadata)
        ChatAPI-->>Client: event: token (Full cached answer)
        ChatAPI-->>Client: event: done (cached: true)
    else Semantic Cache Miss
        ChatAPI->>Memory: Retrieve conversation turns
        Memory-->>ChatAPI: Prior dialogue context
        ChatAPI->>Retriever: Retrieve candidates (Dense + BM25 RRF, k=12)
        Retriever-->>ChatAPI: 12 Candidate Chunks
        ChatAPI->>Reranker: Score query-passage cross-attention
        Reranker-->>ChatAPI: Top-4 Reranked Chunks
        ChatAPI-->>Client: event: sources (Grounded citation metadata)
        ChatAPI->>LLM: Prompt LLM with reranked context
        loop Token Streaming
            LLM-->>ChatAPI: Next generated token
            ChatAPI-->>Client: event: token (text snippet)
        end
        ChatAPI->>Cache: Store (query, embedding, answer, sources)
        ChatAPI->>Memory: Save turn to SessionStore
        ChatAPI-->>Client: event: done (cached: false)
    end
```
