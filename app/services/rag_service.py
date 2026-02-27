# app/services/rag_service.py
"""
Lightweight, safe Retrieval-Augmented Generation (RAG) service.

- Loads a FAISS index + metadata built by scripts/ingest_kb.py
- Uses Sentence-Transformers for embeddings (default: all-MiniLM-L6-v2)
- Returns top-k chunks with doc text and source for prompting
- On any failure, returns [] so your app keeps working

Security notes:
- This RAG is for *knowledge* queries (FAQ/policy/product info).
- Do NOT index PII. Do NOT feed raw CBS/PII into this index.
"""

import os
import json
from typing import List, Dict, Tuple

import numpy as np
from dotenv import load_dotenv

# Optional imports guarded so app still runs if RAG files not present
try:
    import faiss  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore
    _RAG_DEPS_OK = True
except Exception:
    faiss = None  # type: ignore
    SentenceTransformer = None  # type: ignore
    _RAG_DEPS_OK = False


# --------------------------
# Env setup (compatible with your existing apiKey.env layout)
# --------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(BASE_DIR, "../../apiKey.env")
load_dotenv(dotenv_path=env_path)

# ---------- Configuration ----------
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL")
INDEX_PATH = os.getenv("RAG_INDEX_PATH")
META_PATH = os.getenv("RAG_META_PATH")
TOP_K_DEFAULT = int(os.getenv("RAG_TOP_K", "3"))

# ---------- Globals (lazy) ----------
_model = None
_index = None
_meta: List[Dict] = []


def _load_model():
    global _model
    if _model is None:
        if not _RAG_DEPS_OK:
            raise RuntimeError("RAG dependencies missing. Install sentence-transformers and faiss-cpu.")
        _model = SentenceTransformer(EMBEDDING_MODEL) # type: ignore
    return _model


def _load_index():
    global _index, _meta
    if _index is not None:
        return _index, _meta

    if not _RAG_DEPS_OK:
        raise RuntimeError("RAG dependencies missing.")

    if not INDEX_PATH or not META_PATH or not (os.path.exists(INDEX_PATH) and os.path.exists(META_PATH)):
        raise FileNotFoundError(
            f"RAG index not found. Expected {INDEX_PATH} and {META_PATH}. "
            "Run scripts/ingest_kb.py first."
        )

    _index = faiss.read_index(INDEX_PATH)  # type: ignore
    with open(META_PATH, "r", encoding="utf-8") as f:
        _meta = json.load(f)

    return _index, _meta


def _embed(texts: List[str]) -> np.ndarray:
    model = _load_model()
    vecs = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    if vecs.ndim == 1:
        vecs = vecs.reshape(1, -1)
    return vecs.astype("float32")


def retrieve(query: str, top_k: int = TOP_K_DEFAULT) -> List[Dict]:
    """
    Retrieve top-k chunks from the FAISS index for a user query.

    Returns a list of:
      { "doc": "<chunk text>", "source": "<file#chunk>", "score": <float [0..1]> }

    On any error, returns [].
    """
    try:
        if not query or not query.strip():
            return []
        index, meta = _load_index()
        qv = _embed([query])
        # FAISS returns squared L2 or IP similarity depending on index; we built with IP (cosine via normalized vectors)
        D, I = index.search(qv, min(top_k, len(meta)))  # type: ignore
        scores = D[0]
        ids = I[0]
        out: List[Dict] = []
        for rank, (idx, sc) in enumerate(zip(ids, scores), start=1):
            if idx < 0 or idx >= len(meta):
                continue
            m = meta[idx]
            out.append({
                "doc": m.get("text", "")[:2000],  # safety cap
                "source": m.get("source", f"doc#{idx}"),
                "score": float(sc),
                "rank": rank
            })
        return out
    except Exception as e:
        print(f"[WARN] RAG retrieve failed: {e}")
        return []