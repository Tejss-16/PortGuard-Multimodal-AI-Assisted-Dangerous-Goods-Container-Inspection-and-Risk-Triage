"""
Run this ON YOUR OWN MACHINE, in the same environment where you already ran
build_chroma_index.py — it adds the 255 investigation-report chunks into your
EXISTING 'maritime_incidents' collection (which currently has 3,372 documents
from the CSV corpus). Mechanics verified against your actual uploaded DB
before you got this script; just swap in the real embedding model on your end.

Prerequisites (should already be true, since you built the first index):
    pip install chromadb sentence-transformers

Usage:
    python3 add_investigation_reports.py

Before running: make sure DB_PATH below matches wherever your chroma_db
folder actually lives locally (the one containing chroma.sqlite3).
"""

import json
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

DB_PATH = "/Users/tejasmestry/Downloads/BE Major Project/project/Output/chroma_db"  # <-- change this to your actual local path if different
REPORTS_CORPUS_PATH = "investigation_reports_corpus.jsonl"

embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"  # MUST match the model used to build the original index
)

client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_collection("maritime_incidents", embedding_function=embedding_fn)
print(f"Existing collection count: {collection.count()}")

docs = [json.loads(l) for l in open(REPORTS_CORPUS_PATH, encoding="utf-8")]
print(f"Loaded {len(docs)} investigation-report chunks to add")


def clean_meta(m):
    return {k: (v if v is not None else "") for k, v in m.items()}


BATCH = 128
for i in range(0, len(docs), BATCH):
    batch = docs[i:i + BATCH]
    collection.add(
        ids=[d["id"] for d in batch],
        documents=[d["text"] for d in batch],
        metadatas=[clean_meta(d["metadata"]) for d in batch],
    )
    print(f"  Added {min(i + BATCH, len(docs))}/{len(docs)}")

print(f"\nNew collection count: {collection.count()}  (should be 3372 + {len(docs)} = {3372 + len(docs)})")

# --- Test: does retrieval now pull from BOTH sources? ---
print("\n=== Test query across merged corpus ===")
results = collection.query(query_texts=["collision between container ship and fishing vessel"], n_results=5)
for doc_id, doc_text, meta, dist in zip(
    results["ids"][0], results["documents"][0], results["metadatas"][0], results["distances"][0]
):
    source = meta.get("doc_type", "csv_occurrence_summary")
    print(f"  [{doc_id}] source={source} distance={dist:.3f}")
    print(f"    {doc_text[:140]}...")
