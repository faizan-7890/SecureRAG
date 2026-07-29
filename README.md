# SecureRAG

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Status](https://img.shields.io/badge/status-Milestone%201%20complete-success)](#roadmap)

SecureRAG is a production-style Retrieval-Augmented Generation (RAG) API for asking grounded questions over private documents. It ingests PDF, TXT, and Markdown files, stores their embeddings locally in Chroma, and returns OpenAI-generated answers with traceable source excerpts.

This project is designed as a portfolio-quality foundation for Software Engineer and AI Engineer roles: the code is modular, typed, configurable, and deliberately structured for the upcoming authentication, RBAC, and evaluation milestones.

## Highlights

- Document ingestion for PDF, TXT, Markdown, and `.markdown` files
- Local embeddings using `sentence-transformers/all-MiniLM-L6-v2`
- Persistent Chroma vector store
- Grounded responses generated with OpenAI
- Source citations with filename, excerpt, and PDF page number when available
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
│   ├── core/         # Configuration and future security utilities
│   ├── models/       # Request and response schemas
│   └── services/     # Ingestion and RAG orchestration
├── data/uploads/     # Uploaded files, created at runtime
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

### Ask a question

```http
POST /chat
Content-Type: application/json
```

```powershell
curl.exe -X POST "http://127.0.0.1:8000/chat" `
  -H "Content-Type: application/json" `
  -d "{\"question\": \"What is the leave policy?\"}"
```

```json
{
  "answer": "Employees receive 20 days of annual leave.",
  "sources": [
    {
      "filename": "policy.pdf",
      "excerpt": "Employees receive 20 days of annual leave...",
      "page": 2
    }
  ]
}
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
| `CHUNK_SIZE` | `1000` | Maximum chunk size in characters |
| `CHUNK_OVERLAP` | `200` | Overlap between chunks |

## Testing

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
python -m pytest -q
```

The project currently includes smoke tests for API health, question validation, and text upload/chunking.

## Current scope and roadmap

Milestone 1 is complete:

- [x] Ingestion and local vector storage
- [x] Retrieval and OpenAI answer generation
- [x] Citation-rich chat responses
- [x] FastAPI service and tests

Planned next:

- [ ] Retrieval tuning and metadata improvements
- [ ] JWT authentication and document-level RBAC
- [ ] Ragas evaluation with a golden dataset
- [ ] Streamlit interface, structured logging, and expanded tests

## Design notes

- Embeddings run locally to keep ingestion inexpensive and reduce external dependencies.
- Chroma persists on disk, so uploaded knowledge remains available after restart.
- RAG services load lazily, keeping API startup responsive.
- Authentication and RBAC are intentionally deferred to Milestone 3 rather than partially implemented in the MVP.

## License

This project is intended for portfolio and learning use. Add a license before distributing it as an open-source package.
