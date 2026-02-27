# Banking Chat Agent — CLAUDE.md

## Project Overview

A secure banking AI assistant built with FastAPI, FAISS RAG, and Gemini/OpenAI. It serves a vanilla JS chat frontend and exposes two main routes: JWT login and an `/assist` endpoint that orchestrates intent detection, context fetching, LLM calls, and post-generation compliance enforcement.

---

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start the development server
uvicorn app.main:app --reload --port 8000

# Start with debug logging
LOG_LEVEL=DEBUG uvicorn app.main:app --reload --port 8000

# Rebuild the FAISS knowledge base index (after editing KB markdown files)
python app/scripts/ingest_kb.py --src app/data/kb --out app/data/rag

# Run tests
pytest

# Run specific test file
pytest tests/integrations/test_assist_endpoint.py -v

# Simulate a locked account (for testing transactional:login flow)
MOCK_LOCKED_STATUS=true uvicorn app.main:app --reload --port 8000
```

---

## Architecture

```
app/
├── main.py                   # FastAPI app; mounts /auth, /assist, and /static
├── routes/
│   ├── assist.py             # Core orchestrator — the most important file
│   └── auth_routes.py        # POST /auth/login → JWT token
├── services/
│   ├── auth.py               # JWT create/verify (1-hour expiry)
│   ├── llm_stub.py           # Unified Gemini/OpenAI interface with masking
│   ├── prompt_builder.py     # Builds multi-turn prompts per intent
│   ├── rag_service.py        # FAISS semantic retrieval (fail-open)
│   ├── compliance.py         # Post-gen guardrail: removes hallucinated lock claims
│   └── cbs_adapter.py        # Mock Core Banking System (returns masked account data)
├── scripts/
│   └── ingest_kb.py          # One-time script to build FAISS index from KB markdown
└── data/
    ├── kb/                   # 9 markdown knowledge base documents (edit these for KB changes)
    └── rag/                  # Pre-built FAISS index (index.faiss + meta.json)

static/                       # Vanilla JS frontend (login.html, index.html, script.js, styles.css)
tests/
├── conftest.py               # Shared fixtures: TestClient, mock_cbs_data, mock_llm_response
├── unit/                     # Unit tests for prompt_builder and llm masking
└── integrations/             # Integration tests for the /assist endpoint
```

---

## Request Flow (assist.py)

```
POST /assist/
  1. Verify JWT token
  2. PII Gate — regex detects PII hints or 8+ digit strings → immediate deflection (no CBS/LLM)
  3. Intent Detection (keyword regex):
       transactional:login   → login/OTP/password/locked keywords
       transactional:feature → balance enquiry/transfer/statement/card PIN keywords
       knowledge             → how-to/rates/fees/policy keywords (default when ambiguous)
       transactional         → fallback for other CBS-related queries
  4. History Sanitization — drops PII-containing turns; drops lock-claim turns for feature flow
  5. Context Fetching:
       knowledge             → RAG retrieval only (no CBS)
       transactional:login   → CBS masked status (lock/OTP fields) + optional RAG
       transactional:feature → Benign CBS context + RAG troubleshooting
       transactional         → CBS masked status (no lock fields)
  6. Prompt Building (prompt_builder.py) — system instruction + dynamic rules + context + history
  7. LLM Call (llm_stub.py) — masks messages before sending
  8. Compliance Guardrail (compliance.py) — rewrites unproven lock/credential claims
  9. Return JSON response with status, message, intent, rag_used, sources
```

---

## Key Design Patterns

### Intent-Driven Context (critical — do not mix these up)
- **knowledge**: RAG only. Strict grounding; LLM must not use outside knowledge.
- **transactional:login**: CBS lock/OTP fields + optional RAG. Lock claims allowed only if CBS confirms.
- **transactional:feature**: Benign CBS context + RAG troubleshooting. Lock/credential claims explicitly blocked by compliance guardrail, even if CBS context is present — feature issues happen post-login.

### Security Gates (layered, do not remove any layer)
1. **PII gate** (pre-LLM): Regex on user query — hard stop with safe response.
2. **History sanitization**: Strips PII turns; strips lock claims from feature-flow history.
3. **Message masking** (pre-LLM transmission): `mask_sensitive_info()` runs on all messages before they leave the server.
4. **Post-gen guardrail** (`compliance.py`): Rewrites hallucinated lock/credential claims in LLM output.

### RAG (Fail-Open)
- RAG is wrapped in `try/except` at the route level. If the FAISS index is missing or embedding fails, the app continues without RAG — no crash.
- Do NOT index PII into FAISS. The KB is pure FAQ/policy/procedure markdown.
- RAG is triggered for `knowledge` and `transactional:feature` intents only.

### LLM Provider Selection
- Configured via `LLM_PROVIDER` env var (`gemini` or `openai`). Default: `gemini`.
- Gemini does not support a native `system` role — the system message is merged into the first user message in `_call_gemini()`.
- Model override via `LLM_MODEL_ID`. Default: `gemini-1.5-flash` / `gpt-4o-mini`.

---

## Environment Configuration

Config is loaded from `apiKey.env` (not `.env`). This path is hardcoded in `llm_stub.py` and `rag_service.py`.

Key variables:
```
LLM_PROVIDER=gemini           # or openai
GEMINI_API_KEY=...
OPENAI_API_KEY=...            # also used as fallback for GEMINI_API_KEY
LLM_MODEL_ID=gemini-1.5-flash # optional model override

EMBEDDING_MODEL=all-MiniLM-L6-v2
RAG_INDEX_PATH=app/data/rag/index.faiss
RAG_META_PATH=app/data/rag/meta.json
RAG_TOP_K=3

SERVICE_TOKEN=test-token      # token for internal CBS adapter calls
MOCK_LOCKED_STATUS=false      # set true to simulate a locked account
LOG_LEVEL=INFO                # DEBUG | INFO | WARNING | ERROR
```

Demo credentials (auth_routes.py): `admin` / `password123`

---

## Knowledge Base

KB lives in `app/data/kb/` as markdown files:
- `balance_enquiry.md`, `charges_and_fees.md`, `fd_premature_closure.md`, `fd_rates.md`
- `fund_transfer.md`, `kyc_and_compliance.md`, `login_issues.md`
- `netbanking_troubleshooting.md`, `reset_card_pin.md`

After editing KB files, rebuild the FAISS index:
```bash
python app/scripts/ingest_kb.py --src app/data/kb --out app/data/rag
```

---

## Testing

- `conftest.py` provides `client` (FastAPI `TestClient`), `mock_cbs_data`, and `mock_llm_response` fixtures.
- `pythonpath = .` is set in `pytest.ini` — imports work relative to project root.
- Integration tests hit the real route with the test client; mock the LLM and CBS calls where needed.

---

## Logging

Configured centrally in `app/logger.py`, called once in `app/main.py`. Every module gets its own logger via `logging.getLogger(__name__)` — no `print()` calls anywhere in the app.

**Log format:**
```
2025-08-27 10:30:15 | INFO     | app.routes.assist | [AUDIT] PII-like input detected; request deflected
2025-08-27 10:30:16 | INFO     | app.services.llm_stub | Gemini call completed in 1.23s
2025-08-27 10:30:16 | WARNING  | app.routes.assist | [GUARDRAIL] Output rewritten: {'notes': ['removed_unproven_lock_claim']}
```

**Level conventions:**

| Level | Used for |
|---|---|
| `DEBUG` | Intent, RAG chunk count, masked prompt contents, provider selection |
| `INFO` | LLM call duration, `[AUDIT]` PII deflection events |
| `WARNING` | `[GUARDRAIL]` output rewrites, RAG retrieval failures |
| `ERROR` | LLM call failures — always includes `exc_info=True` for full stack trace |

**Adding logging to new modules:**
```python
import logging
logger = logging.getLogger(__name__)
```

**`[AUDIT]` and `[GUARDRAIL]` prefixes** are kept in the message string intentionally — they make compliance-relevant events easy to grep regardless of log aggregation tool.

**Noisy third-party libs** (`sentence_transformers`, `faiss`, `httpx`, `httpcore`, `urllib3`) are suppressed to `WARNING` in `app/logger.py`.

---

## Important Constraints

- Never feed raw PII or CBS data into the FAISS index.
- Never call CBS (`cbs_adapter`) for `knowledge` intent — only RAG is used there.
- Never include lock/blocked fields in `transactional:feature` CBS context — this prevents false "your account is blocked" responses for post-login feature issues.
- The compliance guardrail in `compliance.py` is the last line of defense against hallucinated lock claims — do not bypass it.
- Never use `print()` — use `logging.getLogger(__name__)` in every module.
