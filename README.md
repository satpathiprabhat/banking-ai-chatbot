# Banking AI Chatbot

A secure, production-oriented banking AI assistant built with FastAPI, FAISS RAG, and Gemini/OpenAI. It provides grounded, compliance-first responses for customer banking queries — with multi-layer security gates that prevent PII exposure and hallucinated account claims.

---

## Features

- **Intent-aware routing** — classifies queries into `knowledge`, `transactional:login`, or `transactional:feature` and fetches only the context relevant to each
- **RAG grounding** — FAISS vector search over a curated knowledge base; LLM is forbidden from answering knowledge queries outside the retrieved context
- **PII protection** — regex gate blocks and deflects any input containing account numbers, card numbers, OTPs, PAN, Aadhaar, UPI IDs, etc. before reaching the LLM
- **Post-generation compliance** — a guardrail rewrites hallucinated "account locked / wrong credentials" claims if the CBS context doesn't confirm them
- **JWT authentication** — every `/assist` request requires a valid Bearer token (1-hour expiry)
- **Multi-provider LLM** — supports Gemini (default) and OpenAI, switchable via an environment variable
- **Chat UI** — vanilla JS frontend with login, theme toggle, and multi-turn conversation history

---

## Architecture

```
User → /auth/login → JWT token
     → /assist/   → PII Gate → Intent Detection
                             → Context Fetching (RAG / CBS)
                             → Prompt Builder
                             → LLM (Gemini or OpenAI)
                             → Compliance Guardrail
                             → Response
```

| Layer | File |
|---|---|
| API routes | `app/routes/assist.py`, `app/routes/auth_routes.py` |
| Intent detection & safety gates | `app/routes/assist.py` |
| Prompt construction | `app/services/prompt_builder.py` |
| Vector search (RAG) | `app/services/rag_service.py` |
| LLM abstraction | `app/services/llm_stub.py` |
| Post-gen guardrail | `app/services/compliance.py` |
| Mock Core Banking System | `app/services/cbs_adapter.py` |
| JWT auth | `app/services/auth.py` |
| Frontend | `static/` |

---

## Getting Started

### Prerequisites

- Python 3.11
- A Gemini API key ([get one here](https://aistudio.google.com/)) or an OpenAI API key

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Copy the example and fill in your keys:

```bash
cp .env.example apiKey.env
```

Edit `apiKey.env`:

```env
LLM_PROVIDER=gemini          # or: openai
GEMINI_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here # only needed if LLM_PROVIDER=openai

LLM_MODEL_ID=gemini-2.5-flash

EMBEDDING_MODEL=all-MiniLM-L6-v2
RAG_INDEX_PATH=app/data/rag/index.faiss
RAG_META_PATH=app/data/rag/meta.json
RAG_TOP_K=3

SERVICE_TOKEN=test-token
JWT_SECRET_KEY=change-me-in-production
```

### 3. Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

Open [http://localhost:8000/static/login.html](http://localhost:8000/static/login.html)

**Demo credentials:** `admin` / `password123`

---

## Docker

```bash
# Build
docker build -t banking-ai-chatbot .

# Run (pass secrets at runtime — never bake them into the image)
docker run -p 8000:8000 \
  -e GEMINI_API_KEY=your_key_here \
  -e JWT_SECRET_KEY=your_secret_here \
  banking-ai-chatbot

# Or use an env file
docker run -p 8000:8000 --env-file apiKey.env banking-ai-chatbot

# Simulate a locked account (for testing)
docker run -p 8000:8000 -e GEMINI_API_KEY=... -e MOCK_LOCKED_STATUS=true banking-ai-chatbot
```

---

## Rebuilding the Knowledge Base

The FAISS index is pre-built and included. To update it after editing the markdown files in `app/data/kb/`:

```bash
python app/scripts/ingest_kb.py --src app/data/kb --out app/data/rag
```

---

## Running Tests

```bash
pytest tests/ -v
```

Tests mock both the LLM and CBS adapter — no real API keys are needed.

---

## CI/CD

GitHub Actions workflow at `.github/workflows/ci-cd.yml`:

| Job | Trigger | What it does |
|---|---|---|
| **test** | Every push & PR | Runs pytest on Python 3.11 |
| **docker** | Every push & PR | Builds image; pushes to `ghcr.io` on `main` / version tags |
| **scan** | Push to `main` / tags | Trivy CVE scan; uploads results to GitHub Security tab |

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` or `openai` |
| `LLM_MODEL_ID` | `gemini-2.5-flash` | Model to use |
| `GEMINI_API_KEY` | — | Required if provider is Gemini |
| `OPENAI_API_KEY` | — | Required if provider is OpenAI |
| `JWT_SECRET_KEY` | `welcome@123456789` | **Change in production** |
| `ADMIN_USERNAME` | `admin` | Login username |
| `ADMIN_PASSWORD` | `password123` | Login password — **change in production** |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-Transformers model for RAG |
| `RAG_INDEX_PATH` | `app/data/rag/index.faiss` | Path to FAISS index |
| `RAG_META_PATH` | `app/data/rag/meta.json` | Path to index metadata |
| `RAG_TOP_K` | `3` | Number of KB chunks retrieved per query |
| `SERVICE_TOKEN` | `test-token` | Internal token for CBS adapter calls |
| `MOCK_LOCKED_STATUS` | `false` | Set `true` to simulate a locked account |
