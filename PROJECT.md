# Project: SecureRAG

## Architecture
- SecureRAG is a secure Retrieval-Augmented Generation system with RBAC, vector search, hybrid retrieval, streaming answer generation with source citations, and evaluation pipelines.
- Core packages:
  - `app/api/`: FastAPI REST endpoints and authentication routers.
  - `app/core/`: Security, config, RBAC policies, logging, exceptions.
  - `app/services/`: Document processing, chunking, vector store (Chroma), embedding, hybrid retriever, generator/LLM.
  - `app/models/`: Pydantic schemas and database models.
  - `tests/`: Comprehensive test suite (unit, integration, and adversarial security).
  - `eval/`: Ragas evaluation pipeline and benchmarking scripts.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Document Ingestion & Chunking | Upload PDF, TXT, MD, chunk text with overlap | M1 | ORIGINAL_REQUEST §R1 |
| 2 | Vector Store & Embeddings | Sentence-transformers embeddings, Chroma persistence & deletion | M1 | ORIGINAL_REQUEST §R1 |
| 3 | Hybrid & Semantic Retrieval | Chroma semantic search + BM25/keyword retrieval, score fusion | M2 | ORIGINAL_REQUEST §R2 |
| 4 | LLM Generation & Citations | Grounded context prompt construction, streaming output, citations | M2 | ORIGINAL_REQUEST §R2 |
| 5 | Authentication & RBAC | JWT auth, role-based access control, document permissions | M2 | ORIGINAL_REQUEST §R2 |
| 6 | Full Test Suite Execution | Unit & integration tests in `tests/`, fixing broken tests/mocks | M3 | ORIGINAL_REQUEST §R3 |
| 7 | Ragas Evaluation Pipeline | `eval/run_evaluation.py` evaluation execution with harness/metrics | M4 | ORIGINAL_REQUEST §R3 |
| 8 | Comprehensive Audit Report | Detailed report on tests, security, pipeline health, Ragas scores | M4 | ORIGINAL_REQUEST §R4 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Document Ingestion & Vector Store | Ingestion, chunking, embedding, Chroma management | None | DONE |
| 2 | Retrieval, Generation & Security | Hybrid retrieval, generation with citations, auth/RBAC | M1 | DONE |
| 3 | Test Suite Fixes & Full Execution | Run all tests in `tests/`, fix failures/regressions | M2 | DONE |
| 4 | Ragas Evaluation & Audit Report | Execute `eval/run_evaluation.py`, write audit report | M3 | DONE |

## Interface Contracts
- Ingestion -> VectorStore: Ingested chunks -> embeddings -> Chroma collection with metadata (user_id, role, doc_id)
- Retriever -> Generator: Query + user context -> filtered retrieved chunks with relevance scores -> Generator prompt
- Auth -> Endpoints: Bearer token -> UserContext (user_id, roles) -> RBAC authorization check

## Code Layout
- `app/api/v1/`: API route definitions
- `app/core/`: Core security, config, dependencies
- `app/services/`: Services (retrieval, generation, ingestion, embedding, vector_store)
- `app/models/`: Schemas and data models
- `tests/`: Test suite
- `eval/`: Evaluation scripts
