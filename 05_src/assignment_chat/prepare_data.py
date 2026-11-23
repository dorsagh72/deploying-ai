"""
Prepare clean data files from Health Canada's Drug Product Database (DPD) extract.

Input : data/raw/*.txt  (the "marketed" DPD extract, allfiles.zip, no header rows)
Output: data/dpd_products.csv  one row per marketed HUMAN product (DIN)
        data/dpd_groups.csv    one row per ingredient group (same ATC + same ingredients),
                               with a text description used for semantic search

Run from the 05_src folder:
    python -m assignment_chat.prepare_data
"""
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_DIR = DATA_DIR / "raw"

# Column names come from Health Canada's "Read Me File - DPD Data Extract".
# We only name the columns we use; the files have no header row.
COLUMNS = {
    "drug.txt":     ["drug_code", "product_categorization", "class", "din", "brand_name"],
    "ingred.txt":   ["drug_code", "ingredient_code", "ingredient", "supplied_ind", "strength", "strength_unit"],
    "ther.txt":     ["drug_code", "atc_code", "atc_name"],
    "form.txt":     ["drug_code", "form_code", "dosage_form"],
    "route.txt":    ["drug_code", "route_code", "route"],
    "comp.txt":     ["drug_code", "mfr_code", "company_code", "company"],
    "schedule.txt": ["drug_code", "schedule"],
}

# ATC level 1 (anatomical main group) names, from the WHO ATC classification
ATC_LEVEL1 = {
    "A": "Alimentary tract and metabolism", "B": "Blood and blood forming organs",
    "C": "Cardiovascular system", "D": "Dermatologicals",
    "G": "Genito-urinary system and sex hormones",
    "H": "Systemic hormonal preparations, excluding sex hormones and insulins",
    "J": "Antiinfectives for systemic use", "L": "Antineoplastic and immunomodulating agents",
    "M": "Musculo-skeletal system", "N": "Nervous system",
    "P": "Antiparasitic products, insecticides and repellents", "R": "Respiratory system",
    "S": "Sensory organs", "V": "Various",
}

# ATC level 2 (therapeutic subgroup) names, from the WHO ATC classification
ATC_LEVEL2 = {
    "A01": "Stomatological preparations", "A02": "Drugs for acid related disorders",
    "A03": "Drugs for functional gastrointestinal disorders", "A04": "Antiemetics and antinauseants",
    "A05": "Bile and liver therapy", "A06": "Drugs for constipation",
    "A07": "Antidiarrheals, intestinal antiinflammatory/antiinfective agents",
    "A08": "Antiobesity preparations", "A09": "Digestives, incl. enzymes",
    "A10": "Drugs used in diabetes", "A11": "Vitamins", "A12": "Mineral supplements",
    "A14": "Anabolic agents for systemic use", "A16": "Other alimentary tract and metabolism products",
    "B01": "Antithrombotic agents", "B02": "Antihemorrhagics", "B03": "Antianemic preparations",
    "B05": "Blood substitutes and perfusion solutions", "B06": "Other hematological agents",
    "C01": "Cardiac therapy", "C02": "Antihypertensives", "C03": "Diuretics",
    "C04": "Peripheral vasodilators", "C05": "Vasoprotectives", "C07": "Beta blocking agents",
    "C08": "Calcium channel blockers", "C09": "Agents acting on the renin-angiotensin system",
    "C10": "Lipid modifying agents",
    "D01": "Antifungals for dermatological use", "D02": "Emollients and protectives",
    "D03": "Preparations for treatment of wounds and ulcers", "D04": "Antipruritics",
    "D05": "Antipsoriatics", "D06": "Antibiotics and chemotherapeutics for dermatological use",
    "D07": "Corticosteroids, dermatological preparations", "D08": "Antiseptics and disinfectants",
    "D09": "Medicated dressings", "D10": "Anti-acne preparations",
    "D11": "Other dermatological preparations",
    "G01": "Gynecological antiinfectives and antiseptics", "G02": "Other gynecologicals",
    "G03": "Sex hormones and modulators of the genital system", "G04": "Urologicals",
    "H01": "Pituitary and hypothalamic hormones and analogues", "H02": "Corticosteroids for systemic use",
    "H03": "Thyroid therapy", "H04": "Pancreatic hormones", "H05": "Calcium homeostasis",
    "J01": "Antibacterials for systemic use", "J02": "Antimycotics for systemic use",
    "J04": "Antimycobacterials", "J05": "Antivirals for systemic use",
    "J06": "Immune sera and immunoglobulins", "J07": "Vaccines",
    "L01": "Antineoplastic agents", "L02": "Endocrine therapy (cancer)",
    "L03": "Immunostimulants", "L04": "Immunosuppressants",
    "M01": "Antiinflammatory and antirheumatic products", "M02": "Topical products for joint and muscular pain",
    "M03": "Muscle relaxants", "M04": "Antigout preparations",
    "M05": "Drugs for treatment of bone diseases", "M09": "Other drugs for disorders of the musculo-skeletal system",
    "N01": "Anesthetics", "N02": "Analgesics", "N03": "Antiepileptics", "N04": "Anti-parkinson drugs",
    "N05": "Psycholeptics (antipsychotics, anxiolytics, hypnotics and sedatives)",
    "N06": "Psychoanaleptics (antidepressants, psychostimulants, anti-dementia drugs)",
    "N07": "Other nervous system drugs",
    "P01": "Antiprotozoals", "P02": "Anthelmintics", "P03": "Ectoparasiticides, incl. scabicides, insecticides and repellents",
    "R01": "Nasal preparations", "R02": "Throat preparations", "R03": "Drugs for obstructive airway diseases",
    "R05": "Cough and cold preparations", "R06": "Antihistamines for systemic use",
    "R07": "Other respiratory system products",
    "S01": "Ophthalmologicals", "S02": "Otologicals", "S03": "Ophthalmological and otological preparations",
    "V01": "Allergens", "V03": "All other therapeutic products", "V04": "Diagnostic agents",
    "V06": "General nutrients", "V07": "All other non-therapeutic products",
    "V08": "Contrast media", "V09": "Diagnostic radiopharmaceuticals", "V10": "Therapeutic radiopharmaceuticals",
}


def read_raw(file_name: str) -> pd.DataFrame:
    """Read one headerless DPD file, keeping only the columns we named."""
    names = COLUMNS[file_name]
    df = pd.read_csv(RAW_DIR / file_name, header=None, dtype=str, keep_default_na=False,
                     usecols=range(len(names)), encoding="utf-8")
    df.columns = names
    return df


def join_unique(values) -> str:
    """'TABLET', 'TABLET', 'CAPSULE' -> 'CAPSULE; TABLET'"""
    return "; ".join(sorted({v for v in values if v}))


def build_products() -> pd.DataFrame:
    drug = read_raw("drug.txt")
    drug = drug[drug["class"] == "Human"]                       # human products only

    ingred = read_raw("ingred.txt")
    ingred["ingredient_strength"] = (ingred["ingredient"] + " " + ingred["strength"] + " "
                                     + ingred["strength_unit"]).str.strip()
    ingredients = ingred.groupby("drug_code").agg(
        ingredients=("ingredient", join_unique),
        ingredients_with_strength=("ingredient_strength", join_unique),
    )

    ther = read_raw("ther.txt").groupby("drug_code").agg(atc_code=("atc_code", "first"),
                                                         atc_name=("atc_name", "first"))
    form = read_raw("form.txt").groupby("drug_code").agg(dosage_form=("dosage_form", join_unique))
    route = read_raw("route.txt").groupby("drug_code").agg(route=("route", join_unique))
    comp = read_raw("comp.txt").groupby("drug_code").agg(company=("company", "first"))
    schedule = read_raw("schedule.txt").groupby("drug_code").agg(schedule=("schedule", join_unique))

    products = (drug[["drug_code", "din", "brand_name"]]
                .merge(ingredients, on="drug_code", how="left")
                .merge(ther, on="drug_code", how="left")
                .merge(form, on="drug_code", how="left")
                .merge(route, on="drug_code", how="left")
                .merge(comp, on="drug_code", how="left")
                .merge(schedule, on="drug_code", how="left")
                .fillna(""))

    products["atc_level1"] = products["atc_code"].str[:1].map(ATC_LEVEL1).fillna("")
    products["atc_level2"] = products["atc_code"].str[:3].map(ATC_LEVEL2).fillna("")
    return products


def build_groups(products: pd.DataFrame) -> pd.DataFrame:
    """One row per (ATC code, ingredient set), with a text description to embed."""
    groups = products.groupby(["atc_code", "ingredients"], as_index=False).agg(
        atc_name=("atc_name", "first"),
        atc_level1=("atc_level1", "first"),
        atc_level2=("atc_level2", "first"),
        n_products=("din", "count"),
        n_companies=("company", "nunique"),
        brands=("brand_name", lambda s: "; ".join(sorted(set(s))[:8])),
        dosage_forms=("dosage_form", join_unique),
        routes=("route", join_unique),
        schedules=("schedule", join_unique),
    )
    groups["text"] = groups.apply(
        lambda g: (
            f"{g['ingredients']}. "
            f"ATC {g['atc_code'] or 'not assigned'} ({g['atc_name']}); "
            f"category: {g['atc_level1']} > {g['atc_level2']}. "
            f"Dosage forms: {g['dosage_forms']}. Routes: {g['routes']}. Schedule: {g['schedules']}. "
            f"Marketed in Canada as {g['n_products']} product(s) from {g['n_companies']} company(ies), "
            f"e.g. {g['brands']}."
        ),
        axis=1,
    )
    groups.insert(0, "group_id", [f"group_{i:04d}" for i in range(len(groups))])
    return groups


if __name__ == "__main__":
    products = build_products()
    products.to_csv(DATA_DIR / "dpd_products.csv", index=False)
    print(f"Saved {len(products)} products to data/dpd_products.csv")

    groups = build_groups(products)
    groups.to_csv(DATA_DIR / "dpd_groups.csv", index=False)
    print(f"Saved {len(groups)} ingredient groups to data/dpd_groups.csv")

    print("\nExample group text:")
    print(groups[groups["ingredients"].str.contains("ATORVASTATIN")]["text"].iloc[0])
