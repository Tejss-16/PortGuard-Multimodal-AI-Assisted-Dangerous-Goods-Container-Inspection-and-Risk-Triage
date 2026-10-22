"""
Embeds the GISIS RAG corpus into ChromaDB and runs a test query, proving the
retrieval pipeline actually works end to end (not just that the corpus file exists).

Run this once to build the persistent index; your orchestration agent then
just queries the persisted collection at runtime.
"""

import json
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

CORPUS_PATH = Path("/Users/tejasmestry/Downloads/BE Major Project/project/Output/rag_corpus.jsonl")
DB_PATH = "/Users/tejasmestry/Downloads/BE Major Project/project/Output/chroma_db"

docs = [json.loads(l) for l in open(CORPUS_PATH, encoding="utf-8")]
print(f"Loaded {len(docs)} documents from corpus")

embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)

client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_or_create_collection(
    name="maritime_incidents", embedding_function=embedding_fn
)

# Chroma metadata values can't be None — sanitize before insert
def clean_meta(m):
    return {k: (v if v is not None else "") for k, v in m.items()}

BATCH = 256
for i in range(0, len(docs), BATCH):
    batch = docs[i:i + BATCH]
    collection.add(
        ids=[d["id"] for d in batch],
        documents=[d["text"] for d in batch],
        metadatas=[clean_meta(d["metadata"]) for d in batch],
    )
    print(f"  Embedded {min(i + BATCH, len(docs))}/{len(docs)}")

print(f"\nIndex built. Total documents in collection: {collection.count()}")

# --- Test retrieval: simulate what the orchestration agent would query for ---
test_queries = [
    "container ship collision causing cargo delay",
    "vessel fire during port operations",
    "cargo ship grounding near port",
]

print("\n=== Test retrieval queries ===")
for q in test_queries:
    results = collection.query(query_texts=[q], n_results=3)
    print(f"\nQuery: '{q}'")
    for doc_id, doc_text, dist in zip(
        results["ids"][0], results["documents"][0], results["distances"][0]
    ):
        print(f"  [{doc_id}] (distance={dist:.3f}) {doc_text[:140]}...")
