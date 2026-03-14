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

import logging
import json
import os
from typing import List, Dict

import numpy as np
from app.config import get_settings

logger = logging.getLogger(__name__)

# Optional imports guarded so app still runs if RAG files not present
try:
    import faiss  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore
    _RAG_DEPS_OK = True
except Exception:
    faiss = None  # type: ignore
    SentenceTransformer = None  # type: ignore
    _RAG_DEPS_OK = False

TOP_K_DEFAULT = get_settings().rag_top_k

# ---------- Globals (lazy) ----------
_model = None
_index = None
_meta: List[Dict] = []


def _load_model():
    global _model
    if _model is None:
        if not _RAG_DEPS_OK:
            raise RuntimeError("RAG dependencies missing. Install sentence-transformers and faiss-cpu.")
        _model = SentenceTransformer(get_settings().embedding_model) # type: ignore
    return _model


def _load_index():
    global _index, _meta
    if _index is not None:
        return _index, _meta

    if not _RAG_DEPS_OK:
        raise RuntimeError("RAG dependencies missing.")

    settings = get_settings()
    if not settings.rag_index_path or not settings.rag_meta_path or not (
        os.path.exists(settings.rag_index_path) and os.path.exists(settings.rag_meta_path)
    ):
        raise FileNotFoundError(
            f"RAG index not found. Expected {settings.rag_index_path} and {settings.rag_meta_path}. "
            "Run scripts/ingest_kb.py first."
        )

    _index = faiss.read_index(settings.rag_index_path)  # type: ignore
    with open(settings.rag_meta_path, "r", encoding="utf-8") as f:
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
        logger.warning("RAG retrieve failed: %s", e)
        return []
