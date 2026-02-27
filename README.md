# Banking GenAI Starter

Starter FastAPI project with:
- /assist endpoint
- internal CBS adapter mock
- prompt templating and mask utility
- local LLM stub (for testing without external calls)

Run:
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
