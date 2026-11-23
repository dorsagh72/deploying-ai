"""
Build the ChromaDB vector database for semantic search (Service 2).

Reads data/dpd_groups.csv (made by prepare_data.py), embeds the "text" column of
every ingredient group with text-embedding-3-small, and saves everything in chroma_db/.

Run once from the 05_src folder:
    python -m assignment_chat.build_index
"""
import os

import pandas as pd
from dotenv import load_dotenv

load_dotenv(".env")
load_dotenv(".secrets")
os.environ["LANGSMITH_TRACING"] = "false"

from assignment_chat.vector_store import (  # noqa: E402  (imported after loading the keys)
    CHROMA_DIR, COLLECTION_NAME, get_chroma_client, get_embedding_function,
)

GROUPS_CSV = CHROMA_DIR.parent / "data" / "dpd_groups.csv"
BATCH_SIZE = 100   # embed 100 descriptions per request


def build():
    groups = pd.read_csv(GROUPS_CSV, dtype=str, keep_default_na=False)
    print(f"Loaded {len(groups)} ingredient groups")

    client = get_chroma_client()

    # Start fresh: delete the old collection if it exists
    if COLLECTION_NAME in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"},   # cosine distance: 0 = same meaning
    )

    for start in range(0, len(groups), BATCH_SIZE):
        batch = groups.iloc[start:start + BATCH_SIZE]
        collection.add(
            ids=batch["group_id"].tolist(),
            documents=batch["text"].tolist(),          # the text that gets embedded
            metadatas=[{
                "atc_code": row["atc_code"],
                "ingredients": row["ingredients"],
                "n_products": int(row["n_products"]),
            } for _, row in batch.iterrows()],
        )
        print(f"  embedded {start + len(batch)} / {len(groups)}")

    print(f"Done: {collection.count()} groups saved in {CHROMA_DIR}")

    # Quick test
    question = "drugs to lower cholesterol"
    results = collection.query(query_texts=[question], n_results=3)
    print(f"\nTest query: {question!r}")
    for doc, dist in zip(results["documents"][0], results["distances"][0]):
        print(f"  distance {dist:.3f} | {doc[:110]}...")


if __name__ == "__main__":
    build()
