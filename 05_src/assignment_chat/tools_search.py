"""
Service 2 (semantic search) and an ATC-based similarity search.

- semantic_product_search: asks ChromaDB for the ingredient groups whose
  descriptions are closest in MEANING to the user's question.
- find_similar_by_atc: exact search with pandas in data/dpd_products.csv,
  using the ATC hierarchy (same first characters = same class).
"""
from pathlib import Path

import pandas as pd
from langchain_core.tools import tool

from assignment_chat.vector_store import COLLECTION_NAME, get_chroma_client, get_embedding_function

PRODUCTS_CSV = Path(__file__).resolve().parent / "data" / "dpd_products.csv"

_collection = None   # opened once, then reused
_products = None     # loaded once, then reused


def get_collection():
    global _collection
    if _collection is None:
        client = get_chroma_client()
        _collection = client.get_collection(COLLECTION_NAME, embedding_function=get_embedding_function())
    return _collection


def get_products() -> pd.DataFrame:
    global _products
    if _products is None:
        _products = pd.read_csv(PRODUCTS_CSV, dtype=str, keep_default_na=False)
    return _products


# ---------------------------------------------------------------------------
# Service 2: semantic search (ChromaDB)
# ---------------------------------------------------------------------------
@tool
def semantic_product_search(question: str, n_results: int = 5) -> dict:
    """
    Search marketed Canadian drug products by MEANING, using a description of what the
    user is looking for, e.g. "drugs for high cholesterol", "extended-release diabetes tablets",
    "injectable products for rheumatoid arthritis", "eye drops for glaucoma".
    Use this when the user describes a condition, a drug class, a use or a type of product
    instead of giving an exact ingredient name or DIN.
    Returns the most relevant ingredient groups (ingredients, ATC code, number of products).
    """
    n_results = max(1, min(int(n_results), 10))
    try:
        results = get_collection().query(query_texts=[question], n_results=n_results)
    except Exception as exc:
        return {"error": f"Semantic search is unavailable ({exc}). Run build_index.py first."}

    matches = []
    for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
        matches.append({
            "ingredients": meta["ingredients"],
            "atc_code": meta["atc_code"],
            "marketed_products": meta["n_products"],
            "relevance_distance": round(dist, 3),   # lower = closer in meaning
            "description": doc,
        })
    return {"question": question, "matches": matches}


# ---------------------------------------------------------------------------
# ATC similarity search (pandas)
# ---------------------------------------------------------------------------
@tool
def find_similar_by_atc(din: str = "", atc_code: str = "", atc_level: int = 4) -> dict:
    """
    Find marketed Canadian products in the same ATC class.
    Give EITHER a DIN (finds products similar to that product) OR an ATC code / prefix
    (e.g. "C10AA" for statins, "A10" for diabetes drugs).
    atc_level sets how broad "similar" is when a DIN is given:
    4 = same chemical subgroup (default, e.g. C10AA statins), 3 = pharmacological subgroup (C10A),
    2 = therapeutic subgroup (C10), 5 = same substance (C10AA05).
    """
    products = get_products()
    level_length = {1: 1, 2: 3, 3: 4, 4: 5, 5: 7}.get(int(atc_level), 5)

    if din:
        din = din.strip().zfill(8)
        match = products[products["din"] == din]
        if match.empty:
            return {"error": f"DIN {din} is not in the marketed human products list."}
        full_atc = match.iloc[0]["atc_code"]
        prefix = full_atc[:level_length]
        source = f"DIN {din} ({match.iloc[0]['brand_name']}, ATC {full_atc})"
    elif atc_code:
        prefix = atc_code.strip().upper()
        source = f"ATC prefix {prefix}"
    else:
        return {"error": "Please give a DIN or an ATC code."}

    if not prefix:
        return {"error": f"No ATC code is recorded for {source}."}

    similar = products[products["atc_code"].str.startswith(prefix)]
    if similar.empty:
        return {"error": f"No marketed products found for ATC prefix {prefix}."}

    return {
        "searched_for": source,
        "atc_prefix": prefix,
        "atc_category": f"{similar.iloc[0]['atc_level1']} > {similar.iloc[0]['atc_level2']}",
        "total_products": len(similar),
        "products_per_ingredient": similar["atc_name"].value_counts().head(15).to_dict(),
        "examples": similar[["din", "brand_name", "ingredients_with_strength", "company"]].head(10).to_dict("records"),
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(".env")
    load_dotenv(".secrets")
    import os
    os.environ["LANGSMITH_TRACING"] = "false"
    print(semantic_product_search.invoke({"question": "drugs for type 2 diabetes", "n_results": 3}))
    print()
    print(find_similar_by_atc.invoke({"din": "02230711"}))
