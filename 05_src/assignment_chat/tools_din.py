import os
import re
import tempfile

import pandas as pd
import requests
from collections import Counter
from langchain_core.tools import tool

BASE_URL = "https://health-products.canada.ca/api/drug/"
_marketed_cache = None   # will hold {drug_code: product} after the first download


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_marketed_products() -> dict:
    """Download all marketed products once and keep them in memory."""
    global _marketed_cache
    if _marketed_cache is None:
        response = requests.get(BASE_URL + "drugproduct/",
                                params={"status": 2, "lang": "en", "type": "json"}, timeout=60)
        products = response.json()
        _marketed_cache = {p["drug_code"]: p for p in products}
    return _marketed_cache


def _get_list(endpoint: str, drug_code) -> list:
    """Call one detail endpoint (form/, route/, ...) for a drug_code and return a list."""
    response = requests.get(BASE_URL + endpoint,
                            params={"id": drug_code, "lang": "en", "type": "json"}, timeout=30)
    data = response.json()
    if isinstance(data, dict):      # some endpoints return one object instead of a list
        data = [data]
    return data


# ---------------------------------------------------------------------------
# Function 1: ingredient -> marketed products
# ---------------------------------------------------------------------------
def find_marketed_by_ingredient(ingredient: str) -> list[dict]:
    """Return marketed Canadian products that contain the given active ingredient."""
    # Call 1: all products (any status) that contain this ingredient
    response = requests.get(BASE_URL + "activeingredient/",
                            params={"ingredientname": ingredient, "lang": "en", "type": "json"}, timeout=30)
    rows = response.json()

    # Call 2: the marketed products
    marketed = get_marketed_products()

    # Join on drug_code: keep only products that are marketed
    results = []
    for row in rows:
        product = marketed.get(row["drug_code"])
        if product is not None:
            results.append({
                "din": product["drug_identification_number"],
                "brand_name": product["brand_name"],
                "company": product["company_name"],
                "ingredient": row["ingredient_name"],
                "strength": f"{row['strength']} {row['strength_unit']}",
            })
    return results


# ---------------------------------------------------------------------------
# Function 2: DIN -> product details (hop 1 + hop 2)
# ---------------------------------------------------------------------------
def lookup_din(din: str) -> dict:
    """Look up one product by its 8-digit DIN and return its main details."""
    din = din.strip().zfill(8)      # "2230711" -> "02230711"

    # Hop 1: DIN -> product (brand, company, drug_code)
    response = requests.get(BASE_URL + "drugproduct/",
                            params={"din": din, "lang": "en", "type": "json"}, timeout=30)
    products = response.json()
    if not products:
        return {"error": f"No product found for DIN {din}"}
    product = products[0]
    drug_code = product["drug_code"]

    # Hop 2: drug_code -> details
    ingredients = _get_list("activeingredient/", drug_code)
    forms = _get_list("form/", drug_code)
    routes = _get_list("route/", drug_code)
    statuses = _get_list("status/", drug_code)

    return {
        "din": product["drug_identification_number"],
        "brand_name": product["brand_name"],
        "company": product["company_name"],
        "ingredients": [f"{i['ingredient_name']} {i['strength']} {i['strength_unit']}" for i in ingredients],
        "dosage_form": [f["pharmaceutical_form_name"] for f in forms],
        "route": [r["route_of_administration_name"] for r in routes],
        "status": statuses[0]["status"] if statuses else "unknown",
    }


# ---------------------------------------------------------------------------
# Tools for the chatbot (the AI reads the docstrings to decide which one to use)
# ---------------------------------------------------------------------------
@tool
def search_marketed_products(ingredient: str) -> dict:
    """
    Find drug products currently MARKETED in Canada that contain an active ingredient
    (for example 'atorvastatin' or 'metformin'). Use this when the user asks which
    products, brands, companies or strengths are available for an ingredient.
    """
    try:
        results = find_marketed_by_ingredient(ingredient)
    except Exception:
        return {"error": "The Health Canada database could not be reached. Please try again later."}
    if not results:
        return {"ingredient": ingredient, "total_marketed_products": 0}
    return {
        "ingredient": ingredient,
        "total_marketed_products": len(results),
        "products_by_company": dict(Counter(r["company"] for r in results).most_common(10)),
        "examples": results[:15],   # only the first 15, so the answer stays short
    }


@tool
def get_product_by_din(din: str) -> dict:
    """
    Look up a single Canadian drug product by its DIN (Drug Identification Number,
    an 8-digit code such as 02230711). Returns brand name, company, active ingredients
    and strengths, dosage form, route of administration and marketing status.
    """
    try:
        return lookup_din(din)
    except Exception:
        return {"error": "The Health Canada database could not be reached. Please try again later."}


@tool
def export_marketed_products_csv(ingredient: str) -> dict:
    """
    Create a downloadable CSV file listing ALL products currently marketed in Canada
    that contain an active ingredient (columns: din, brand_name, company, ingredient, strength).
    Use this ONLY when the user asks for a CSV, a spreadsheet, a file, a download or an export.
    """
    try:
        results = find_marketed_by_ingredient(ingredient)
    except Exception:
        return {"error": "The Health Canada database could not be reached. Please try again later."}
    if not results:
        return {"error": f"No marketed products found for '{ingredient}', so no file was created."}

    # Safe file name, e.g. "atorvastatin_marketed_products.csv"
    safe_name = re.sub(r"[^a-z0-9]+", "_", ingredient.lower()).strip("_")
    file_path = os.path.join(tempfile.gettempdir(), f"{safe_name}_marketed_products.csv")

    pd.DataFrame(results).to_csv(file_path, index=False)   # list of dicts -> table -> CSV
    return {"file_path": file_path, "rows": len(results), "ingredient": ingredient}


# ---------------------------------------------------------------------------
# Quick tests (only run when you run this file directly)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    found = find_marketed_by_ingredient("atorvastatin")
    print(f"Found {len(found)} marketed atorvastatin products")
    print(found[0])
    print()
    print(lookup_din("02230711"))