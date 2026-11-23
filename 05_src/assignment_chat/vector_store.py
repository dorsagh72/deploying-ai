"""
Shared ChromaDB settings, used by build_index.py (to create the database)
and by the semantic search tool (to query it).
"""
import os
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

CHROMA_DIR = Path(__file__).resolve().parent / "chroma_db"     # saved on disk (file persistence)
COLLECTION_NAME = "dpd_ingredient_groups"
EMBEDDING_MODEL = "text-embedding-3-small"
GATEWAY_URL = "https://k7uffyg03f.execute-api.us-east-1.amazonaws.com/prod/openai/v1"


def get_embedding_function() -> OpenAIEmbeddingFunction:
    """Turns text into vectors, through the course API gateway (same as lab 04_5_vectordb)."""
    return OpenAIEmbeddingFunction(
        api_key="any value",
        model_name=EMBEDDING_MODEL,
        api_base=GATEWAY_URL,
        default_headers={"x-api-key": os.getenv("API_GATEWAY_KEY")},
    )


def get_chroma_client():
    """A ChromaDB client that stores everything in the chroma_db folder."""
    return chromadb.PersistentClient(path=str(CHROMA_DIR))
