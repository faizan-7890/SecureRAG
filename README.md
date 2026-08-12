# SecureRAG

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Status](https://img.shields.io/badge/status-All%20milestones%20complete-success)](#roadmap)

SecureRAG is a production-style Retrieval-Augmented Generation (RAG) API for asking grounded questions over private documents. It ingests PDF, TXT, and Markdown files, stores their embeddings locally in Chroma, and returns OpenAI-generated answers with traceable source excerpts.

This project is designed as a portfolio-quality foundation for Software Engineer and AI Engineer roles: the code is modular, typed, configurable, and deliberately structured for the upcoming authentication, RBAC, and evaluation milestones.

## Highlights

- Document ingestion for PDF, TXT, Markdown, and `.markdown` files
- Local embeddings using `sentence-transformers/all-MiniLM-L6-v2`
- Persistent Chroma vector store
- Grounded responses generated with OpenAI
- Source citations with filename, excerpt, PDF page, chunk index, and relevance score
- FastAPI endpoints with interactive OpenAPI documentation
- Typed configuration using `pydantic-settings` and `.env`
- Tests covering health, input validation, and text ingestion

## Architecture

```text
Client
  |
  +-- POST /documents/upload --> extract text --> chunk --> embed locally --> Chroma
  |
  +-- POST /chat -------------> retrieve top-k --> OpenAI --> answer + sources
```

## Project structure

```text
securerag/
├── app/
│   ├── api/          # FastAPI route handlers
│   ├── core/         # Configuration, security, and structured logging
│   ├── models/       # Request and response schemas
│   └── services/     # Ingestion and RAG orchestration
├── ui/               # Streamlit chat interface
├── eval/             # Ragas evaluation pipeline
│   └── results/      # Evaluation output (gitignored)
├── data/
│   ├── uploads/      # Uploaded files, created at runtime
│   └── eval/         # Golden dataset and sample document
├── chroma_db/        # Persistent local vector store, created at runtime
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

## Quick start

### 1. Create a virtual environment

Use Python 3.11 or 3.12.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure OpenAI

Copy the example configuration and add your API key.

```powershell
Copy-Item .env.example .env
```

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini
```

### 4. Run the API

```powershell
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to use Swagger UI.

### 5. Launch the Streamlit UI

```powershell
streamlit run ui/app.py
```

Open [http://localhost:8501](http://localhost:8501) to use the chat interface.

## API reference

### Upload a document

```http
POST /documents/upload
Content-Type: multipart/form-data
```

```powershell
curl.exe -X POST "http://127.0.0.1:8000/documents/upload" `
  -F "file=@C:\path\to\policy.pdf"
```

```json
{
  "message": "Document ingested",
  "filename": "policy.pdf",
  "chunks": 42
}
```

### Ask a question (Synchronous)

```http
POST /chat
Content-Type: application/json
```

```powershell
curl.exe -X POST "http://127.0.0.1:8000/chat" `
  -H "Content-Type: application/json" `
  -d "{\"question\": \"What is the leave policy?\", \"session_id\": \"my-session\"}"
```

```json
{
  "answer": "Employees receive 20 days of annual leave.",
  "sources": [
    {
      "filename": "policy.pdf",
      "excerpt": "Employees receive 20 days of annual leave...",
      "page": 2,
      "relevance_score": 0.94
    }
  ],
  "session_id": "my-session"
}
```

### List ingested documents

```http
GET /documents
Authorization: Bearer <token>   # optional when auth is not configured
```

```json
{
  "documents": [
    {
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "policy.pdf",
      "chunks": 42,
      "uploaded_at": "2026-01-15T12:34:56+00:00",
      "owner_id": "alice",
      "file_extension": ".pdf",
      "source_sha256": "abc123...",
      "source_size_bytes": 204800
    }
  ],
  "total": 1
}
```

### Delete a document

```http
DELETE /documents/{document_id}
Authorization: Bearer <token>
```

Removes all Chroma vector chunks, BM25 index entries, and the registry record for the document. Returns `204 No Content` on success. Admins can delete any document; regular users can only delete their own.

### Retrieve session history

```http
GET /chat/history/{session_id}
```

```json
{
  "session_id": "my-session",
  "messages": [
    {"role": "user", "content": "What is the leave policy?"},
    {"role": "assistant", "content": "Employees receive 20 days of annual leave."}
  ],
  "total": 2
}
```

### Clear session history

```http
DELETE /chat/history/{session_id}
```

Clears the in-memory conversation history for the session. Returns `204 No Content`. Idempotent — succeeds even if the session does not exist.

### Ask a question (Real-Time SSE Streaming)

```http
POST /chat/stream
Accept: text/event-stream
Content-Type: application/json
```

```powershell
curl.exe -N -X POST "http://127.0.0.1:8000/chat/stream" `
  -H "Content-Type: application/json" `
  -d "{\"question\": \"What is the leave policy?\"}"
```

Server-Sent Events emitted:
```text
event: sources
data: {"sources":[{"filename":"policy.pdf","excerpt":"...","page":2,"chunk_index":0,"relevance_score":0.94}]}

event: token
data: {"token":"Employees "}

event: token
data: {"token":"receive 20 days of annual leave."}

event: done
data: {"done":true,"total_tokens":8,"session_id":"my-session"}
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | — | Required API key for answer generation |
| `OPENAI_MODEL` | `gpt-4o-mini` | Chat model to use |
| `CHROMA_PATH` | `chroma_db` | Persistent vector-store location |
| `UPLOAD_DIR` | `data/uploads` | Location for source uploads |
| `CHROMA_COLLECTION` | `securerag_documents` | Chroma collection name |
| `TOP_K` | `4` | Number of retrieved chunks |
| `RETRIEVAL_CANDIDATE_K` | `12` | Candidates inspected before filtering |
| `SIMILARITY_THRESHOLD` | `0.35` | Minimum relevance score accepted as context |
| `CITATION_EXCERPT_CHARS` | `350` | Maximum characters in each cited excerpt |
| `CHUNK_SIZE` | `1000` | Maximum chunk size in characters |
| `CHUNK_OVERLAP` | `200` | Overlap between chunks |
| `ENABLE_HYBRID_SEARCH` | `true` | Enable BM25 + Vector Reciprocal Rank Fusion (RRF) |
| `ENABLE_QUERY_EXPANSION` | `false` | Enable LLM multi-query expansion |
| `ENABLE_STREAMING` | `true` | Enable real-time SSE token streaming |
| `MAX_HISTORY_MESSAGES` | `10` | Maximum turns remembered in conversational session |
| `ENABLE_QUERY_RECONTEXTUALIZATION` | `true` | Rewrite multi-turn follow-up questions before retrieval |
| `RRF_K` | `60` | RRF constant parameter |
| `DENSE_WEIGHT` | `0.6` | Weight allocated to vector similarity |
| `SPARSE_WEIGHT` | `0.4` | Weight allocated to BM25 keyword score |
| `MULTI_QUERY_COUNT` | `3` | Number of query variations generated during expansion |
| `LOG_LEVEL` | `INFO` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `RATE_LIMIT_GLOBAL` | `120/minute` | Global request rate limit per IP address |
| `RATE_LIMIT_CHAT` | `20/minute` | Rate limit applied to chat endpoints per IP address |

## Testing

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q
```

The project includes tests for API health, input validation, text ingestion, authentication flows, RBAC filtering, RAG retrieval, BM25 indexing, RRF ranking, multi-query expansion, SSE token streaming, and conversational memory.

## Evaluation

Run the Ragas evaluation pipeline against the bundled golden dataset:

```powershell
.\.venv\Scripts\python.exe -m eval.run_evaluation
```

This will:
1. Ingest the sample policy document into an isolated Chroma collection
2. Query the RAG pipeline for each of the 20 golden questions
3. Evaluate using Ragas metrics (faithfulness, answer relevancy, context precision, context recall, answer correctness)
4. Print a summary table and save detailed results to `eval/results/evaluation_results.json`

Requires `OPENAI_API_KEY` to be set (Ragas uses an LLM as a judge).

## Current scope and roadmap

All milestones are complete:

- [x] Ingestion and local vector storage
- [x] Retrieval and OpenAI answer generation
- [x] Citation-rich chat responses
- [x] FastAPI service and tests
- [x] Relevance-threshold retrieval, richer chunk metadata, and scored citations
- [x] Retrieval tuning and metadata improvements
- [x] JWT authentication and document-level RBAC
- [x] Streamlit interface, structured logging, and expanded tests
- [x] Ragas evaluation with a golden dataset
- [x] Hybrid Search (BM25 + Vector Reciprocal Rank Fusion) and Multi-Query Expansion
- [x] Real-Time Streaming Responses (SSE) and Conversational Multi-Turn Memory
- [x] Document Management API — list and delete ingested documents
- [x] Session History HTTP endpoints — retrieve and clear conversation history
- [x] Request rate limiting via `slowapi` (in-memory, IP-keyed)



## Design notes

- Embeddings run locally to keep ingestion inexpensive and reduce external dependencies.
- Chroma persists on disk, so uploaded knowledge remains available after restart.
- RAG services load lazily, keeping API startup responsive.
- Authentication and RBAC were deferred to Milestone 3 rather than partially implemented in the MVP.
- The Ragas evaluation uses a temporary Chroma collection so it does not pollute production data.

## License

This project is intended for portfolio and learning use. Add a license before distributing it as an open-source package.