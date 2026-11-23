# DINgs 🔔: a chatbot for Canadian drug products

**DINgs** is a conversational assistant that answers questions about drug products approved and marketed in Canada, using official data from **Health Canada's Drug Product Database (DPD)**.

The name combines **DIN** (*Drug Identification Number*, the 8-digit code Health Canada assigns to every approved drug product) with the **"ding!"** of a bell: DINgs "rings" whenever it finds what you're looking for.

## Why this chatbot?

General chatbots answer drug questions from memory, so they can invent DINs, miss products, or give outdated marketing status. DINgs uses the language model only to **understand questions and explain results**. The **facts** come from Health Canada's live API and from the official DPD data extract. As a result:
- DINs are real.
- Product lists are complete.
- Information is current.

This makes it useful for real-world-evidence and pharmacy data work, where traceable data matters.

## How to run

From the `05_src` folder, with the course environment active (`deploying-ai-env`), and `API_GATEWAY_KEY` in `05_src/.secrets`:

```bash
cd 05_src
python -m assignment_chat.app
```

Then open the local URL printed by Gradio (usually http://127.0.0.1:7860).

The vector database (`chroma_db/`) and the clean data files (`data/*.csv`) are included in the repository, so **no embeddings or data preparation need to be run**.

## Personality

DINgs is upbeat, friendly and a little playful, with a touch of Canadian politeness ("Sorry, eh!").
- It starts answers with **"DINg! 🔔"** when it finds what you asked for.
- It keeps answers short and organised.
- It always reminds users that it gives **product information, not medical advice**.

The personality and all behaviour rules are in `prompts.py`.

## Services

| Service | Tool(s) | Technique | Data source |
|---|---|---|---|
| 1. API calls | `get_product_by_din`, `search_marketed_products` | REST API, rephrased by the LLM | Health Canada DPD API (live) |
| 2. Semantic query | `semantic_product_search` | Embeddings and ChromaDB (persistent) | DPD data extract, ingredient groups |
| 3. Function calling | `export_marketed_products_csv` | Function calling: Python creates a downloadable CSV | Health Canada DPD API |
| Extra | `find_similar_by_atc` | Function calling and pandas | DPD data extract, product table |

All tools are LangChain `@tool` functions bound to `gpt-4o-mini` (through the course API gateway) with `bind_tools`. The model decides which tool to call. `app.py` runs the requested tools, sends the results back to the model as `ToolMessage`s, and repeats until the model writes its final answer.

### Service 1: Health Canada DPD API (`tools_din.py`)

The DPD API (`https://health-products.canada.ca/api/drug/`) is free, needs no key, and is the same data behind Health Canada's public DPD search website.

- **`get_product_by_din(din)`** looks up one product in two hops:
  1. `drugproduct/?din=...` returns the brand, company and internal `drug_code`.
  2. With that `drug_code`, the `activeingredient/`, `form/`, `route/` and `status/` endpoints return the ingredients and strengths, dosage form, route and marketing status.

  DINs typed without the leading zero are padded (`2230711` → `02230711`).
- **`search_marketed_products(ingredient)`** finds all products currently **marketed** for an active ingredient. It does this in two steps:
  1. `activeingredient/?ingredientname=...` returns every product containing the ingredient, in any status.
  2. `drugproduct/?status=2` returns all marketed products. This list is downloaded once and cached in memory.

  The two lists are **joined on `drug_code`**. The tool returns the total count, the number of products per company, and 15 examples.
- **Not verbatim:** the tools return raw JSON-like data. The system prompt tells the model never to copy it, but to rewrite it as a short, friendly summary in DINgs' voice.

### Service 2: semantic search with ChromaDB (`prepare_data.py`, `build_index.py`, `vector_store.py`, `tools_search.py`)

This service lets users search by **meaning** rather than by exact name. For example, "drugs to lower cholesterol" finds statins, even though the word "cholesterol" never appears in their records.

**Dataset.** The Health Canada **DPD data extract for marketed products** (`allfiles.zip`), downloaded on 2026-11-22. The raw files (`data/raw/*.txt`) are not committed. They are listed in `.gitignore`, and they can be downloaded from Health Canada's "DPD data extract" page.

**Embedding process:**

1. **`prepare_data.py`** (pandas) reads the headerless raw files (`drug`, `ingred`, `ther`, `form`, `route`, `comp`, `schedule`). It keeps **human** products only and joins everything on `drug_code`. It produces two files:
   - `data/dpd_products.csv`: one row per marketed human product (DIN). That's **11,487 products**, with ingredients and strengths, ATC code, dosage form, route, company and schedule. It also adds readable ATC level-1 and level-2 names (for example `C10` → "Lipid modifying agents") so the text carries meaning.
   - `data/dpd_groups.csv`: one row per **ingredient group** (same ATC code and same ingredients). That's **2,177 groups**, each with a short text description, for example:
     > *ATORVASTATIN (...). ATC C10AA05; category: Cardiovascular system > Lipid modifying agents. Dosage forms: TABLET. Routes: ORAL. Schedule: PRESCRIPTION. Marketed in Canada as 12 product(s) from 3 company(ies), e.g. APO-ATORVASTATIN; ...*
2. **`build_index.py`** embeds each group description with OpenAI **`text-embedding-3-small`** (through the course gateway, using ChromaDB's `OpenAIEmbeddingFunction`), in batches of 100. It stores them in a **ChromaDB `PersistentClient`** collection (`dpd_ingredient_groups`, cosine distance) in `chroma_db/`. Each entry keeps metadata: ATC code, ingredients and number of products.
3. **`tools_search.py` → `semantic_product_search(question)`** embeds the user's question and returns the closest groups, with their distance. DINgs can then drill down to individual DINs with the Service 1 tools.

**Design decisions:**
- **Why ingredient groups instead of every product?** Dozens of generics with the same ingredient have the same meaning, so embedding them all would add size but no information. Grouping keeps the database small (**`chroma_db` ≈ 26 MB**, under the 40 MB limit) and the results clean.
- **Why add ATC category names?** The DPD only stores the ATC substance name (for example "ATORVASTATIN"). Adding the level-1 and level-2 category names gives the embeddings the therapeutic context needed for questions like "drugs for diabetes".
- No SQLite back end or Docker is used by the app. ChromaDB's file persistence is used as required, and structured data is read with pandas from CSV.

### Service 3: function calling, CSV export (`tools_din.py`)

**`export_marketed_products_csv(ingredient)`** turns the marketed-product search into a **downloadable CSV** with the columns din, brand_name, company, ingredient and strength. The file is written to the system temp folder with pandas. `app.py` detects the `file_path` in the tool result and returns it to Gradio as a `gr.File`, so the user gets a download link in the chat.

**Extra tool: `find_similar_by_atc(din | atc_code)`.** This tool uses the ATC hierarchy with pandas. Given a DIN, it finds that product's ATC code and returns all marketed products sharing the same level-4 prefix. For example, LIPITOR (`C10AA05`) → `C10AA`, which returns 287 statin products. A different level can be chosen, or an ATC prefix can be given directly.

## User interface and memory

- Gradio `ChatInterface` (`app.py`).
- **Memory:** Gradio passes the full chat history on every turn. `dings_chat` converts it to LangChain `HumanMessage` and `AIMessage` objects and sends the whole conversation to the model, so DINgs remembers earlier messages (for example your name, or the drug you asked about). File messages in the history are skipped, because the model only reads text.
- The optional long-conversation memory management was not implemented.

## Guardrails (`guardrails.py`, `prompts.py`)

Three layers protect the chatbot:

1. **Input filter (`check_input`)** runs **before** the model. Regular expressions detect:
   - **restricted topics:** cats or dogs; horoscopes, zodiac signs or astrology; Taylor Swift
   - **prompt attacks:** asking for the system prompt, "ignore previous instructions", "you are now…", "developer mode", and similar

   Blocked messages get a fixed, in-character refusal, and **the model is never called**. Whole-word matching avoids false positives ("category" is not "cat"), and "Cancer" and "Leo" are only blocked next to astrology words.
2. **System prompt rules** repeat the same restrictions for rewordings the patterns miss. They also tell the model never to reveal or change its instructions, and to treat tool output as data, not instructions.
3. **Output filter (`check_output`)** runs **after** the model. If the answer contains a fragment of the system prompt, or mentions a restricted topic, it is replaced by the refusal.

DINgs also refuses **personal medical advice** (for example, whether to stop a medication) and suggests a pharmacist or doctor instead.

## Files

| File | Purpose |
|---|---|
| `app.py` | Gradio chat, tool-calling loop, guardrails |
| `prompts.py` | System prompt: personality, tool rules, restrictions |
| `guardrails.py` | Input and output guardrails |
| `tools_din.py` | Service 1 (DPD API) and Service 3 (CSV export) |
| `tools_search.py` | Service 2 (semantic search) and ATC similarity search |
| `vector_store.py` | Shared ChromaDB and embedding settings |
| `prepare_data.py` | Builds the clean CSVs from the raw DPD extract |
| `build_index.py` | Builds the ChromaDB vector database |
| `data/dpd_products.csv`, `data/dpd_groups.csv` | Clean data (included) |
| `chroma_db/` | Persistent vector database (included) |

## Limitations and notes

- **Different counts in different tools:**
  - The ingredient search (API) also counts **combination products** that contain the ingredient. For example, CADUET contains atorvastatin, so there are 111 marketed atorvastatin products.
  - The ATC search counts products **classified** under that ATC code (87 atorvastatin products under `C10AA05`).
- **Salt forms:** Health Canada records different salt forms (for example "atorvastatin calcium" vs "atorvastatin calcium propylene glycol solvate") as different ingredients, so one substance can appear in several semantic-search groups.
- **Data freshness:** the semantic search and ATC tools use the data extract downloaded on 2026-11-22. The API tools are always live.
- **Keyword guardrails** can occasionally block a harmless message (for example a question mentioning a "hot dog"). This trade-off favours strict compliance with the restricted topics.
- DINgs provides product information only and is **not a substitute for professional medical advice**.
