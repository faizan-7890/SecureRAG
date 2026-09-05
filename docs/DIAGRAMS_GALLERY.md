# 🎨 SecureRAG — Complete Visual Architecture & Diagram Gallery

This document contains all visual blueprints, system flowcharts, and sequence diagrams for **SecureRAG v5**.

---

## 🖼️ 1. Architecture Infographic Blueprint

![SecureRAG v5 Enterprise Architecture](assets/architecture_v5.png)

---

## 🏗️ 2. System Architecture Topology Flowchart (9-Layer)

> [!TIP]
> Open the standalone [architecture_topology.mmd](architecture_topology.mmd) file directly in the IDE to zoom, pan, and export.

```mermaid
flowchart TD
    %% ── 1. Client & Generative UI Tier ──
    subgraph ClientTier ["1. Client & Generative UI Tier"]
        ThreadSidebar["ThreadSidebar<br/>(Multi-Chat History & Export)"]
        ChatWorkspace["ChatWorkspace<br/>(SSE Streaming, Feedback, Scope)"]
        CitationDrawer["CitationDrawer<br/>(Keyword Glow & Relevance Gauge)"]
        DocManager["DocumentManager<br/>(Uploads & RBAC Registry)"]
        ChunkInspector["ChunkInspector<br/>(Chroma Vector Inspector)"]
        StreamlitApp["Streamlit Python UI<br/>(Admin & Management Console)"]
    end

    %% ── 2. API Gateway Tier ──
    subgraph APITier ["2. API Gateway & Security Tier (FastAPI)"]
        CORS["CORS Middleware"]
        Logging["RequestLoggingMiddleware<br/>(X-Request-ID & Latency)"]
        RateLimiter["SlowAPI Rate Limiter<br/>(Redis & In-Memory Fallback)"]
        AuthRouter["/auth Router<br/>(JWT HS256, Bcrypt 72B)"]
        DocRouter["/documents Router<br/>(Upload, RBAC List, Chunks, Delete)"]
        ChatRouter["/chat Router<br/>(Sync & SSE Token Streaming)"]
    end

    %% ── 3. Enterprise Guardrails Tier ──
    subgraph GuardrailsTier ["3. Enterprise Security Guardrails"]
        InjectionDetector["PromptInjectionDetector<br/>(Jailbreak & Override Scanning)"]
        PIIRedactor["PIIRedactor<br/>(SSN, Credit Card, Email, Phone, IP)"]
        ContextSanitizer["ContextSanitizer<br/>(XML Prompt Hardening)"]
    end

    %% ── 4. Persistence Tier ──
    subgraph PersistenceTier ["4. Production Persistence Layer"]
        PostgresDB[("PostgreSQL 16 / SQLite<br/>(SQLAlchemy 2.0 Models)")]
        AlembicMgr["Alembic Migrations<br/>(Schema Version Control)"]
        RedisStore[("Redis Session Memory<br/>(Multi-turn History TTL: 3600s)")]
    end

    %% ── 5. Semantic Cache Tier ──
    subgraph CacheTier ["5. Sub-10ms Semantic Response Cache"]
        SemCache[("Semantic Vector Cache<br/>(Cosine Sim 0.96+ & Disk JSON)")]
    end

    %% ── 6. Hybrid Ingestion & Retrieval Engine ──
    subgraph RAGCore ["6. Hybrid Ingestion & Retrieval Engine"]
        Ingestion["DocumentIngestionService<br/>(PyPDF, Splitters, all-MiniLM-L6-v2)"]
        DenseStore[("Chroma Vector Store<br/>(384-d Cosine Semantic Search)")]
        SparseStore[("Okapi BM25 Index<br/>(Sparse Lexical Search)")]
        RRF["Reciprocal Rank Fusion<br/>(k=60 | Dense: 0.6, Sparse: 0.4)"]
        Recontext["Dialogue Recontextualizer<br/>(Multi-turn Memory Synthesis)"]
    end

    %% ── 7. Two-Stage Reranker Tier ──
    subgraph RerankTier ["7. Two-Stage Cross-Encoder Reranker"]
        CrossEncoder["CrossEncoder Model<br/>(cross-encoder/ms-marco-MiniLM-L-6-v2)"]
    end

    %% ── 8. LLM Generation Tier ──
    subgraph LLMTier ["8. LLM Generation & SSE Streaming"]
        OpenAIProvider["OpenAI Engine<br/>(gpt-4o-mini / gpt-4o)"]
        GeminiProvider["Google Gemini Engine<br/>(gemini-1.5-flash)"]
        SSEGen["SSE Event Streamer<br/>(Sources, Tokens, Done)"]
    end

    %% ── 9. Evaluation Tier ──
    subgraph EvalTier ["9. Evaluation & Quality Assurance"]
        Ragas["Ragas 0.2.x Pipeline<br/>(Faithfulness, Relevancy, Precision, Recall)"]
        GoldenDS[("Golden QA Dataset<br/>(20 Curated Ground Truths)")]
    end

    %% ── Inter-layer Connections ──
    ChatWorkspace --> CORS
    DocManager --> CORS
    StreamlitApp --> CORS
    CORS --> Logging
    Logging --> RateLimiter
    RateLimiter --> AuthRouter
    RateLimiter --> DocRouter
    RateLimiter --> ChatRouter

    AuthRouter --> PostgresDB
    DocRouter --> PostgresDB
    AlembicMgr --> PostgresDB

    DocRouter --> Ingestion
    Ingestion --> PIIRedactor
    PIIRedactor --> DenseStore
    PIIRedactor --> SparseStore

    ChatRouter --> InjectionDetector
    InjectionDetector -.->|Blocked| ChatWorkspace
    InjectionDetector -->|Safe| SemCache
    ChatRouter <--> RedisStore
    SemCache -.->|Cache Miss| Recontext
    Recontext --> DenseStore
    Recontext --> SparseStore

    DenseStore --> RRF
    SparseStore --> RRF
    RRF --> CrossEncoder

    CrossEncoder --> ContextSanitizer
    ContextSanitizer --> OpenAIProvider
    ContextSanitizer --> GeminiProvider
    OpenAIProvider --> SSEGen
    GeminiProvider --> SSEGen
    SSEGen --> ChatWorkspace
    SSEGen --> StreamlitApp
    SSEGen -.->|Store Query & Answer| SemCache

    ChatWorkspace --> ThreadSidebar
    ChatWorkspace --> CitationDrawer
    DocManager --> ChunkInspector

    GoldenDS --> Ragas
    Ragas --> APITier
```

---

## 📥 3. Document Ingestion & Dual-Indexing Workflow (with PII Scrubbing)

> [!TIP]
> Open the standalone [ingestion_sequence.mmd](ingestion_sequence.mmd) file directly.

```mermaid
sequenceDiagram
    autonumber
    actor Client as User / Admin
    participant API as POST /documents/upload
    participant Ingest as DocumentIngestionService
    participant Splitter as RecursiveCharacterTextSplitter
    participant PII as PIIRedactor
    participant Embed as SentenceTransformers (all-MiniLM-L6-v2)
    participant Chroma as Chroma Vector DB (Dense)
    participant BM25 as Okapi BM25 Index (Sparse)
    participant DB as PostgreSQL / SQLite (DocumentDB)

    Client->>API: Upload Document (PDF / TXT / MD)
    API->>API: Validate file type & size limit
    API->>Ingest: Ingest file with owner metadata
    Ingest->>Splitter: Split text (chunk_size=900, overlap=150)
    Splitter-->>Ingest: Text chunks with 1-based page metadata
    Ingest->>PII: Scan & redact PII (SSN, CC, Email, Phone, IP)
    PII-->>Ingest: Sanitized chunks
    Ingest->>Embed: Generate 384-d normalized embeddings
    Embed-->>Ingest: Vector representations
    Ingest->>Chroma: Store chunks, vectors & RBAC metadata (owner_id, roles)
    Ingest->>BM25: Tokenize & update sparse index stats
    Ingest->>DB: Persist DocumentDB entity record
    Ingest-->>API: IngestionResult (chunks count, doc_id)
    API-->>Client: 201 Created (UploadResponse)
```

---

## 💬 4. Chat & SSE Streaming Lifecycle (with Guardrails, Reranker & Cache)

> [!TIP]
> Open the standalone [chat_stream_sequence.mmd](chat_stream_sequence.mmd) file directly.

```mermaid
sequenceDiagram
    autonumber
    actor Client as React Client (Bun) / Streamlit
    participant ChatAPI as POST /chat/stream
    participant Guard as PromptInjectionDetector
    participant Cache as Semantic Cache
    participant Redis as Redis Session Memory
    participant Retriever as Hybrid Retriever
    participant Reranker as Cross-Encoder Reranker
    participant PII as PIIRedactor & ContextSanitizer
    participant LLM as OpenAI / Gemini

    Client->>ChatAPI: POST /chat/stream (question, session_id)
    ChatAPI->>Guard: Inspect query for prompt injection
    alt Injection Detected (risk_score > threshold)
        Guard-->>ChatAPI: Blocked (threat category & reason)
        ChatAPI-->>Client: event: error (injection detected)
    else Query Safe
        ChatAPI->>Cache: Lookup query embedding (cosine sim >= 0.96)
        alt Semantic Cache Hit (<10ms)
            Cache-->>ChatAPI: Return cached answer & sources
            ChatAPI-->>Client: event: sources (Citation metadata)
            ChatAPI-->>Client: event: token (Full cached answer)
            ChatAPI-->>Client: event: done (cached: true)
        else Semantic Cache Miss
            ChatAPI->>Redis: Retrieve conversation turns (TTL refreshed)
            Redis-->>ChatAPI: Prior dialogue context
            ChatAPI->>Retriever: Retrieve candidates (Dense + BM25 RRF, k=12)
            Retriever-->>ChatAPI: 12 Candidate Chunks
            ChatAPI->>Reranker: Score query-passage cross-attention
            Reranker-->>ChatAPI: Top-4 Reranked Chunks
            ChatAPI-->>Client: event: sources (Grounded citation metadata)
            ChatAPI->>PII: Sanitize context & redact PII from chunks
            PII-->>ChatAPI: Hardened prompt with XML delimiters
            ChatAPI->>LLM: Prompt LLM with sanitized reranked context
            loop Token Streaming
                LLM-->>ChatAPI: Next generated token
                ChatAPI-->>Client: event: token (text snippet)
            end
            ChatAPI->>Cache: Store (query, embedding, answer, sources)
            ChatAPI->>Redis: Save turn with TTL expiration (3600s)
            ChatAPI-->>Client: event: done (cached: false)
        end
    end
```

---

## 📊 5. Key Architecture Specifications Summary

| Component | Technology | Role & Performance Metric |
|:---|:---|:---|
| **Generative UI** | React 19 + TypeScript (Bun) | ThreadSidebar, CitationDrawer, ChatWorkspace — bundled in **1.84s**. |
| **API Gateway** | FastAPI + SlowAPI | REST/SSE endpoints with JWT RBAC and Redis-backed rate limiting. |
| **Security Guardrails** | PromptInjectionDetector + PIIRedactor | 5 threat categories blocked; SSN/CC/Email/Phone/IP redacted with Luhn. |
| **Relational DB** | PostgreSQL 16 / SQLAlchemy 2.0 | `users` and `documents` persistence with Alembic migrations. |
| **Session Memory** | Redis 7 | Multi-turn dialogue history with **3600s TTL**. |
| **Semantic Cache** | Cosine Vector Cache | Sub-10ms instant response cache on high similarity ($\ge 0.96$). |
| **Dense Search** | Chroma DB + `all-MiniLM-L6-v2` | 384-dimensional cosine vector space. |
| **Sparse Search** | Okapi BM25 Index | Robertson-Spärck Jones keyword search. |
| **Rank Fusion** | Reciprocal Rank Fusion (RRF) | Fuses top 12 dense and sparse candidates ($k=60$). |
| **Reranker** | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Deep cross-attention scoring for top-4 chunks. |
| **LLM Engines** | OpenAI `gpt-4o-mini` / Gemini `1.5-flash` | Grounded response generation with citations. |
| **Evaluation** | Ragas 0.2.x | **1.00 Faithfulness**, **0.96 Relevancy**, **0.98 Correctness**. |
