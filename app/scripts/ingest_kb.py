# scripts/ingest_kb.py
"""
Build a local FAISS index from a folder of text/markdown files.

Usage:
  python scripts/ingest_kb.py --src data/kb --out data/rag

Outputs:
  - data/rag/index.faiss
  - data/rag/meta.json

Notes:
- Ingests only .txt and .md.
- Keep the corpus free of PII. This index is for FAQs/Policies/How-tos.
"""

import os
import re
import json
import argparse
from typing import List, Dict, Tuple

import numpy as np

try:
    import faiss  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore
except Exception as e:
    raise SystemExit("Install dependencies first: pip install sentence-transformers faiss-cpu") from e


DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")


def read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def clean(text: str) -> str:
    # Light cleanup; keep it simple to avoid losing meaning
    text = text.replace("\r\n", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def chunk(text: str, max_tokens: int = 500, overlap: int = 50) -> List[str]:
    """
    Simple character-based chunking that approximates 4 chars ~ 1 token.
    For production, swap to a tokenizer-aware chunker.
    """
    if not text:
        return []
    max_chars = max_tokens * 4
    ov_chars = overlap * 4
    chunks = []
    i = 0
    while i < len(text):
        j = min(i + max_chars, len(text))
        chunks.append(text[i:j])
        if j == len(text):
            break
        i = max(0, j - ov_chars)  # overlap
    return chunks


def walk_corpus(src_dir: str) -> List[Tuple[str, str]]:
    """
    Return list of (source_id, text) for .txt/.md under src_dir.
    """
    items: List[Tuple[str, str]] = []
    for root, _, files in os.walk(src_dir):
        for name in files:
            if not name.lower().endswith((".txt", ".md")):
                continue
            full = os.path.join(root, name)
            try:
                txt = clean(read_text_file(full))
                if not txt:
                    continue
                rel = os.path.relpath(full, src_dir)
                items.append((rel, txt))
            except Exception as e:
                print(f"[WARN] Skipping {full}: {e}")
    return items


def build_index(src_dir: str, out_dir: str, model_name: str = DEFAULT_EMBEDDING_MODEL):
    os.makedirs(out_dir, exist_ok=True)
    items = walk_corpus(src_dir)
    if not items:
        raise SystemExit(f"No .txt/.md files found under {src_dir}")

    print(f"[INGEST] Files: {len(items)}  |  Model: {model_name}")

    model = SentenceTransformer(model_name)
    meta: List[Dict] = []
    vecs: List[np.ndarray] = []

    for rel, text in items:
        parts = chunk(text, max_tokens=500, overlap=50)
        for i, p in enumerate(parts):
            meta.append({"source": f"{rel}#chunk{i+1}", "text": p})
            vec = model.encode([p], convert_to_numpy=True, normalize_embeddings=True)
            vecs.append(vec[0].astype("float32"))

    if not vecs:
        raise SystemExit("No chunks produced; corpus may be empty.")

    mat = np.vstack(vecs)  # [N, D]
    dim = mat.shape[1]

    # ✅ Correct pattern: create Flat IP, then wrap once with IndexIDMap
    base = faiss.index_factory(dim, "Flat", faiss.METRIC_INNER_PRODUCT)  # type: ignore
    index = faiss.IndexIDMap(base)  # type: ignore

    ids = np.arange(mat.shape[0]).astype("int64")
    index.add_with_ids(mat, ids)  # type: ignore

    faiss.write_index(index, os.path.join(out_dir, "index.faiss"))  # type: ignore
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)

    print(f"[INGEST] Saved {len(meta)} chunks")
    print(f"[INGEST] Index: {os.path.join(out_dir, 'index.faiss')}")
    print(f"[INGEST] Meta : {os.path.join(out_dir, 'meta.json')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/kb", help="Folder with .txt/.md files")
    ap.add_argument("--out", default="data/rag", help="Output folder for index/meta")
    ap.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL, help="Sentence-Transformer model id")
    args = ap.parse_args()
    build_index(args.src, args.out, args.model)


if __name__ == "__main__":
    main()