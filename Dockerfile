# ── Stage 1: dependency installation ──────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .

RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy only the installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application code
COPY app/ ./app/
COPY static/ ./static/

# Non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Runtime env vars (no defaults for secrets — supply via --env-file or -e flags)
ENV LLM_PROVIDER=gemini \
    LLM_MODEL_ID=gemini-2.5-flash \
    MOCK_LOCKED_STATUS=false

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
