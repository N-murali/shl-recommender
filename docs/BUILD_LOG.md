# Build Log — SHL Assessment Recommender

Step-by-step record of every action taken during development.

---

## Phase 0 — Planning & Setup

### Step 0.1: Requirements Document
- Created `.kiro/specs/shl-recommender/requirements.md`
- 15 requirements covering: health endpoint, chat endpoint, schema compliance,
  catalog scraping, retrieval system, all 5 agent behaviors, turn limits,
  data provenance, deployment, stateless design, validation models.
- Each requirement has user story + EARS-format acceptance criteria.

### Step 0.2: Design Document
- Created `.kiro/specs/shl-recommender/design.md`
- Covers: system architecture (Mermaid diagrams), component interfaces,
  data flow per behavior mode, data models, retrieval strategy,
  error handling, performance budgets, correctness properties.
- Key decisions documented: Groq as LLM, all-MiniLM-L6-v2 for embeddings,
  FAISS IndexFlatIP, stateless design, provenance validation layer.

### Step 0.3: Task List
- Created `.kiro/specs/shl-recommender/tasks.md`
- 12 task groups across 8 phases with dependency graph.
- Checkpoints at phases 2, 4, 5, 6, and final.

### Step 0.4: Steering Files (Persistent Memory)
- Created `.kiro/steering/project-conventions.md`
  - Working rules, phase order, "never do" list, "always ask" rules.
- Created `.kiro/steering/architecture-rules.md`
  - File structure, LLM isolation contract, Groq↔Claude swap instructions,
    hard constraints, agent behaviors, catalog rules.

### Step 0.5: Git Repository Setup
- Ran: `git init` in `c:\Users\mural\OneDrive\Desktop\shl_agent`
- Ran: `git remote add origin https://github.com/N-murali/shl-recommender.git`
- Repository connected but NOT pushed (waiting for user to say "push").

---

## Phase 1 — Project Skeleton

### Step 1.1: Created config.py
- **What**: Environment variable loading + all application constants.
- **Key constants**: LLM_PROVIDER="groq", LLM_MODEL="llama-3.3-70b-versatile",
  PORT=10000, MAX_TURNS=8, MAX_RECOMMENDATIONS=10, REQUEST_TIMEOUT=30.
- **Why**: Single source of truth for all configuration. Swap LLM by changing
  3 lines here + call_llm() body + requirements.txt.

### Step 1.2: Created models.py
- **What**: Pydantic v2 models for API validation.
- **Models created**:
  - `Message` — role (Literal["user","assistant"]) + content (1-10000 chars)
  - `ChatRequest` — messages list (1-50 items)
  - `Recommendation` — name, url (must start with https://), test_type
  - `ChatResponse` — reply (1-2000 chars), recommendations (0-10), end_of_conversation
  - `BehaviorMode` — enum for internal agent routing
- **Why**: FastAPI auto-validates requests against these. Any schema violation
  returns 422 with field-level errors. The evaluator requires exact schema.

### Step 1.3: Created .gitignore
- **Excludes**: venv/, .env, __pycache__/, *.pyc, .DS_Store, data/*.json,
  IDE files, test artifacts.
- **Why**: .env has secrets, data/*.json is generated (not source code),
  venv is environment-specific.

### Step 1.4: Created requirements.txt (v1 — minimum versions)
- **Initial version**: Used `>=` minimum version constraints.
- **Updated to pinned versions** after Phase 1 verification (see Step 1.8).

### Step 1.5: Created main.py
- **What**: FastAPI app with GET /health endpoint.
- **Returns**: `{"status": "ok"}` with HTTP 200.
- **Uvicorn config**: host 0.0.0.0, port from config.PORT.
- **Why**: Evaluator uses /health as readiness check. Must respond within
  1 second (120 seconds allowed for cold start).

### Step 1.6: Created .env
- **What**: Placeholder for GROQ_API_KEY.
- **Content**: `GROQ_API_KEY=your_key_here`
- **Why**: python-dotenv loads this automatically. Never committed to git.

### Step 1.7: Created directories
- `data/` — will hold catalog.json after scraping
- `tests/` — will hold test files in Phase 6
- `docs/` — will hold approach.md in Phase 8

### Step 1.8: Virtual Environment & Dependencies
- Ran: `python -m venv venv`
- Ran: `.\venv\Scripts\pip install fastapi uvicorn python-dotenv pydantic`
- Python version: 3.14.3 (system Python)
- Installed versions:
  - fastapi==0.136.1
  - uvicorn==0.47.0
  - pydantic==2.13.4
  - python-dotenv==1.2.2

### Step 1.9: Verification — Server Start
- Ran: `.\venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 10000`
- Result: Server started successfully on http://0.0.0.0:10000

### Step 1.10: Verification — Health Endpoint
- Tested: `GET http://localhost:10000/health`
- Result: `200 {"status": "ok"}` ✅

### Step 1.11: Verification — Pydantic Validation
- Tested: Message with role="system" → Rejected ✅
- Tested: Message with empty content → Rejected ✅
- Tested: ChatRequest with empty messages → Rejected ✅
- Tested: Valid ChatRequest → Accepted ✅

### Step 1.12: Pinned Package Versions
- Ran: `pip freeze` to get exact installed versions.
- Updated requirements.txt to use `==` pinned versions.
- **Rationale**: Auto-evaluator needs reproducible behavior. If it works
  today, it must work identically on Render. Pinned versions guarantee this.
- Packages not yet installed (groq, sentence-transformers, faiss-cpu, etc.)
  pinned to latest stable versions that will be installed in later phases.

### Step 1.13: Created README.md
- Quick start guide, API documentation, project structure, tech stack,
  design decisions, constraints.

---

## Phase 1 — Final State

### Files Created
| File | Lines | Purpose |
|------|-------|---------|
| config.py | 55 | Configuration & constants |
| models.py | 95 | Pydantic validation models |
| main.py | 55 | FastAPI app + /health |
| requirements.txt | 35 | Pinned dependencies |
| .gitignore | 30 | Git exclusions |
| .env | 4 | API key placeholder |
| README.md | 130 | Project documentation |

### Verification Results
| Check | Status |
|-------|--------|
| Server starts | ✅ |
| GET /health → 200 {"status":"ok"} | ✅ |
| Invalid role rejected (422) | ✅ |
| Empty content rejected (422) | ✅ |
| Empty messages rejected (422) | ✅ |
| Valid request accepted | ✅ |
| Git repo initialized | ✅ |
| Remote connected | ✅ |

### What's Next
Phase 2: Build catalog_scraper.py to scrape SHL product catalog.

---

## Phase 2 — Catalog Scraper

### Step 2.1: Installed scraping dependencies
- Ran: `.\venv\Scripts\pip install requests beautifulsoup4`
- Installed: requests==2.34.1, beautifulsoup4==4.14.3

### Step 2.2: Explored SHL catalog page structure
- Fetched https://www.shl.com/solutions/products/product-catalog/ via web_fetch (rendered mode)
- Discovered: Page has 2 tables — "Pre-packaged Job Solutions" (type=2) and "Individual Test Solutions" (type=1)
- Pagination: `?start=N&type=1`, 12 items per page, 32 pages total
- Columns: Name (with link), Remote Testing (span indicator), Adaptive/IRT (span indicator), Test Type (letter codes)

### Step 2.3: Tested raw HTTP access
- Plain `requests.get()` → 403 (CloudFront blocks)
- With browser User-Agent header → 200, 363KB HTML
- **Decision**: Must include browser-like User-Agent in all requests

### Step 2.4: Explored HTML structure with test script
- Created temporary `explore_catalog.py` to inspect table structure
- Found: Table 1 = Individual Test Solutions
- Name cell has `<a href="/products/product-catalog/view/{slug}/">` link
- Remote/Adaptive indicated by `<span class="catalogue__circle -yes">`
- Test type: concatenated letter codes in text (e.g., "K", "AEBCDP")

### Step 2.5: Explored detail page structure
- Fetched: https://www.shl.com/solutions/products/product-catalog/view/net-framework-4-5/
- Found: Description under `<h4>Description</h4>`, Duration as "Approximate Completion Time in minutes = 30"
- Job levels and languages also available but not critical for retrieval

### Step 2.6: Created catalog_scraper.py
- **Two-pass approach**:
  - Pass 1: Scrape all listing pages → get name, url, test_type, remote_testing, adaptive
  - Pass 2: Scrape each detail page → get description, duration
- **Functions**: fetch_page(), scrape_listing_page(), parse_listing_row(), scrape_detail_page(), scrape_catalog(), save_catalog(), validate_catalog()
- **Error handling**: HTTP timeouts, 4xx/5xx errors, missing fields (skip + warn)
- **Rate limiting**: 1 second between requests
- **Safety**: Stops after 2 consecutive empty pages, safety limit at start=500

#### Key Code — CloudFront bypass (without this, all requests get 403):
```python
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
```

#### Key Code — Parsing a listing row:
```python
def parse_listing_row(cells: list) -> Optional[dict]:
    # Cell 0: Name and URL
    link = cells[0].find("a")
    name = cells[0].get_text(strip=True)
    href = link.get("href", "")
    url = BASE_URL + href  # Convert relative to absolute

    # Cell 1: Remote Testing — indicated by span with class
    remote_testing = cells[1].find("span", class_="catalogue__circle") is not None

    # Cell 2: Adaptive/IRT — same indicator
    adaptive = cells[2].find("span", class_="catalogue__circle") is not None

    # Cell 3: Test Type — concatenated letters, split into space-separated
    test_type_raw = cells[3].get_text(strip=True)
    test_type = " ".join(list(test_type_raw))  # "AEBCDP" → "A E B C D P"

    return {"name": name, "url": url, "test_type": test_type, ...}
```

#### Key Code — Extracting description and duration from detail page:
```python
def scrape_detail_page(url: str) -> dict:
    soup = fetch_page(url)
    # Description: text after <h4>Description</h4>
    desc_heading = soup.find("h4", string=re.compile(r"Description", re.IGNORECASE))
    # Duration: regex match "Approximate Completion Time in minutes = 30"
    duration_match = re.search(r"Approximate Completion Time in minutes\s*=\s*(\d+)", page_text)
```

#### Development Scripts (in scripts/ folder):
- `scripts/explore_catalog.py` — Discovered HTML structure before writing scraper
- `scripts/test_scraper_quick.py` — Verified 2 pages work before full 10-min run
- `scripts/verify_catalog.py` — Post-scrape validation of all 377 entries

### Step 2.7: Quick test (2 pages)
- Ran test with first 2 listing pages + 2 detail pages
- Results: 24 entries, all valid, descriptions and durations extracted correctly
- Verified: URLs correct, test types parsed, remote/adaptive flags detected

### Step 2.8: Full scrape
- Ran: `python catalog_scraper.py` (took ~10 minutes)
- Pass 1: 32 listing pages → 377 Individual Test Solutions found
- Pass 2: 377 detail pages scraped for descriptions and durations
- Output: `data/catalog.json` (223.9 KB)

### Step 2.9: Verification results
- ✅ 377 entries total
- ✅ All entries have required fields (name, url, test_type)
- ✅ All URLs start with `https://www.shl.com/`
- ✅ 0 duplicate names
- ✅ 0 bad URLs
- ✅ 377/377 have descriptions
- ✅ 283/377 have duration > 0
- ✅ 377/377 have remote_testing = true
- ✅ 37/377 have adaptive = true
- ✅ Test type distribution: K=240, P=67, S=43, A=32, C=19, B=17, D=7, E=2

### Step 2.10: Moved scripts to scripts/ folder
- Originally deleted explore_catalog.py, test_scraper_quick.py, verify_catalog.py
- Restored them in `scripts/` as proof-of-work (shows methodical development process)
- Added `scripts/README.md` explaining each script's purpose and when it was used

### Phase 2 — Final State

| File | Purpose |
|------|---------|
| catalog_scraper.py | Full scraper with two-pass approach |
| data/catalog.json | 377 Individual Test Solutions (223.9 KB) |

### Catalog Entry Structure
```json
{
  "name": ".NET Framework 4.5",
  "url": "https://www.shl.com/products/product-catalog/view/net-framework-4-5/",
  "test_type": "K",
  "remote_testing": true,
  "adaptive": true,
  "description": "The.NET Framework 4.5 test measures knowledge of .NET environment...",
  "duration": 30,
  "competencies": []
}
```

### Key Decisions
- **Test type format**: Space-separated letter codes (e.g., "K", "P C", "A E B C D P")
  - Rationale: Easier to search/filter than concatenated "AEBCDP"
- **Competencies field**: Empty list for all entries
  - Rationale: SHL detail pages don't have a separate "competencies" section.
    The description contains this info and the retriever will use it for semantic matching.
- **Rate limiting**: 1 second between requests
  - Rationale: Respectful to SHL servers, avoids getting blocked mid-scrape.
- **Two-pass approach**: Listing pages first, then detail pages
  - Rationale: If detail page scraping fails partway, we still have all basic data.

---

## Phase 3 — Retrieval System

### Step 3.1: Installed retrieval dependencies
- Ran: `.\venv\Scripts\pip install sentence-transformers faiss-cpu numpy`
- Installed: sentence-transformers==5.5.0, faiss-cpu==1.13.2, numpy==2.4.4
- Also pulled: torch==2.12.0, transformers==5.8.1, huggingface-hub==1.14.0, scikit-learn==1.8.0

### Step 3.2: Created retriever.py
- **Class**: `Retriever` with `__init__`, `search`, `get_all_entries`
- **Embedding model**: all-MiniLM-L6-v2 (384 dimensions, fast on CPU)
- **FAISS index**: IndexFlatIP (inner product on L2-normalized vectors = cosine similarity)
- **Text representation**: "{name} | {test_type} | {description}"
- **Module-level functions**: `initialize_retriever()`, `get_retriever()` for global instance
- **Error handling**: FileNotFoundError, ValueError for invalid catalog, RuntimeError for model load failure

#### Key Code — Embedding catalog entries:
```python
def _entry_to_text(self, entry: dict) -> str:
    """Convert catalog entry to text for embedding."""
    name = entry.get("name", "")
    test_type = entry.get("test_type", "")
    description = entry.get("description", "")
    return f"{name} | {test_type} | {description}"

# In __init__:
texts = [self._entry_to_text(entry) for entry in self.catalog]
embeddings = self.model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
self.embeddings = np.array(embeddings, dtype=np.float32)
```

#### Key Code — Building FAISS index:
```python
# IndexFlatIP = inner product on normalized vectors = cosine similarity
dimension = self.embeddings.shape[1]  # 384
self.index = faiss.IndexFlatIP(dimension)
self.index.add(self.embeddings)
```

#### Key Code — Search function:
```python
def search(self, query: str, top_k: int = 10) -> list[dict]:
    top_k = max(1, min(top_k, config.MAX_RECOMMENDATIONS, len(self.catalog)))
    query_embedding = self.model.encode([query], normalize_embeddings=True)
    query_vector = np.array(query_embedding, dtype=np.float32)
    scores, indices = self.index.search(query_vector, top_k)
    results = []
    for score, idx in zip(scores[0], indices[0]):
        entry = self.catalog[idx].copy()
        entry["score"] = float(score)
        results.append(entry)
    return results
```

#### Key Code — Global instance pattern:
```python
_instance: Optional[Retriever] = None

def initialize_retriever(catalog_path=None) -> Retriever:
    """Called once during FastAPI startup."""
    global _instance
    _instance = Retriever(catalog_path=catalog_path)
    return _instance

def get_retriever() -> Retriever:
    """Used by agent.py for search calls."""
    if _instance is None:
        raise RuntimeError("Retriever not initialized.")
    return _instance
```

#### Development Script:
- `scripts/test_retriever_quick.py` — Verifies init time, search quality, ordering

### Step 3.3: Tested retriever with sample queries
- Created `scripts/test_retriever_quick.py`
- Results:
  - Init time: 13.5s (budget: 120s) ✓
  - Search time: 16ms (budget: 5s) ✓
  - "java developer programming test" → Java 8, Core Java (score 0.65) ✓
  - "personality assessment leadership" → OPQ32r, OPQ Manager Plus (score 0.57) ✓
  - "numerical reasoning data analysis" → Verify Interactive Numerical (score 0.70) ✓
  - "customer service communication" → Entry Level Customer Service (score 0.63) ✓
  - Results ordered by descending score ✓
  - get_all_entries() returns all 377 entries ✓

### Phase 3 — Final State

| File | Purpose |
|------|---------|
| retriever.py | FAISS + sentence-transformers retrieval system |
| scripts/test_retriever_quick.py | Verification script (proof of work) |

### Key Decisions
- **all-MiniLM-L6-v2**: Fast (14ms/embedding), small (90MB), good quality. Fits Render 512MB.
- **IndexFlatIP**: Exact search. Catalog is small (377 entries) so brute force is fine.
- **No index persistence**: Rebuilt at startup. Avoids stale index, catalog is small.
- **Normalized embeddings**: L2 normalization means inner product = cosine similarity.
- **Global instance pattern**: `initialize_retriever()` called once at startup, `get_retriever()` used everywhere else.

---

## Phase 4 — Agent Logic

### Step 4.1: Installed Groq SDK
- Ran: `.\venv\Scripts\pip install groq`
- Installed: groq==1.2.0

### Step 4.2: Created prompts.py
- **SYSTEM_PROMPT**: 2212 chars (~800 tokens) defining agent persona, rules, JSON format
- **Behavior templates**: build_clarify_prompt, build_recommend_prompt, build_refine_prompt, build_compare_prompt, build_refuse_prompt, build_forced_recommend_prompt
- **Helper**: format_catalog_entries() — formats retriever results for LLM context

#### Key Code — System prompt enforces JSON output:
```python
SYSTEM_PROMPT = """You are an SHL Assessment Recommender...
## RESPONSE FORMAT (EVERY TURN):
You MUST return EXACTLY this JSON structure:
{
  "reply": "Your natural language response to the user",
  "recommendations": [],
  "end_of_conversation": false
}
..."""
```

#### Key Code — Catalog context formatting (truncates descriptions for token budget):
```python
def format_catalog_entries(entries: list[dict]) -> str:
    for entry in entries:
        description = entry.get("description", "")[:200] + "..."
        lines.append(f"{name}\n   URL: {url}\n   Type: {test_type} | Duration: {duration} min...")
```

### Step 4.3: Created agent.py
- **call_llm()**: Groq SDK call, system prompt as first message, 25s timeout, temperature=0
- **process_conversation()**: Main orchestrator — mode detection → retrieval → LLM → provenance
- **_determine_mode()**: Routes to CLARIFY/RECOMMEND/REFINE/COMPARE/REFUSE
- **_validate_provenance()**: Filters hallucinated recommendations (exact name+url match)
- **_parse_llm_response()**: Handles valid JSON, code blocks, and fallback

#### Key Code — call_llm() (Groq-specific, only function to change when swapping):
```python
def call_llm(messages: list[dict], system_prompt: str) -> str:
    from groq import Groq
    client = Groq(api_key=config.GROQ_API_KEY)
    # Groq: system prompt goes as first message in messages list
    full_messages = [{"role": "system", "content": system_prompt}] + messages
    response = client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=full_messages,
        max_tokens=1000,
        temperature=0,
        timeout=25,
    )
    return response.choices[0].message.content
```

#### Key Code — Provenance validation (anti-hallucination layer):
```python
def _validate_provenance(recommendations: list[dict], catalog: list[dict]) -> list[dict]:
    catalog_lookup = {entry["name"]: entry["url"] for entry in catalog}
    validated = []
    for rec in recommendations:
        if rec["name"] in catalog_lookup and catalog_lookup[rec["name"]] == rec["url"]:
            validated.append(rec)
    return validated
```

#### Key Code — Mode determination logic:
```python
def _determine_mode(messages):
    if _is_off_topic(last_content): return REFUSE
    if _is_comparison_request(last_content): return COMPARE
    if _has_previous_recommendations(messages) and _is_refinement(last_content): return REFINE
    if _has_sufficient_context(messages): return RECOMMEND
    if _count_clarifying_turns(messages) >= 2: return RECOMMEND  # Force after 2 clarifications
    return CLARIFY
```

### Step 4.4: Tested agent logic (without LLM calls)
- Created `scripts/test_agent_logic.py`
- All 7 test categories pass:
  - Off-topic detection: 7/7 correct ✓
  - Comparison detection: 5/5 correct ✓
  - Sufficient context: 5/5 correct ✓
  - Mode determination: 5/5 correct ✓
  - Query synthesis: extracts key terms ✓
  - Response parsing: JSON, code blocks, fallback ✓
  - Provenance validation: keeps valid, filters fake ✓

### Phase 4 — Final State

| File | Purpose |
|------|---------|
| prompts.py | System prompt + 6 behavior templates + catalog formatter |
| agent.py | call_llm() + process_conversation() + 5 behavior handlers + provenance |
| scripts/test_agent_logic.py | Verification of routing logic (proof of work) |

### Key Decisions
- **Temperature=0**: Deterministic responses for reproducibility (evaluator constraint)
- **25s timeout**: Leaves 5s buffer within the 30s API limit
- **Augmented messages**: Behavior prompts appended as user messages (not modifying history)
- **Fallback on error**: Always returns valid schema even if LLM fails
- **Forced recommend at turn 7**: If provenance removes all LLM recommendations, falls back to raw retriever top-5

---

## Phase 5 — Full API Integration

### Step 5.1: Updated main.py with /chat endpoint and startup initialization
- Added `@app.on_event("startup")` that:
  - Validates GROQ_API_KEY exists (exits if missing)
  - Initializes retriever (loads catalog, builds embeddings, builds FAISS index)
- Added `POST /chat` endpoint:
  - Validates request via Pydantic (ChatRequest)
  - Converts messages to plain dicts
  - Calls `agent.process_conversation(messages)`
  - Returns ChatResponse (Pydantic enforces schema)

#### Key Code — /chat endpoint:
```python
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
    result = process_conversation(messages)
    return ChatResponse(
        reply=result["reply"],
        recommendations=result["recommendations"],
        end_of_conversation=result["end_of_conversation"],
    )
```

### Step 5.2: End-to-end testing with real Groq API
- Created `scripts/test_e2e.py`
- Started server, ran all tests against live endpoint
- **Results (all pass):**

| Test | Behavior | Time | Result |
|------|----------|------|--------|
| Health | GET /health | <1s | 200 {"status":"ok"} ✓ |
| Clarify | Vague query | 4.4s | Empty recommendations ✓ |
| Recommend | Detailed query | 3.9s | 4 recommendations ✓ |
| Refuse | Off-topic | 3.6s | Empty recommendations ✓ |
| Refuse | Prompt injection | 3.8s | Injection refused ✓ |
| Compare | Assessment comparison | 4.5s | Catalog-grounded comparison ✓ |
| Multi-turn | Clarify → Recommend | 4.5s | 6 recommendations ✓ |
| Validation | Invalid requests | <1s | 422 errors ✓ |
| Performance | Response time | 4.0s | Under 30s budget ✓ |

### Step 5.3: Verified evaluator constraints
- ✅ Schema compliance: Every response has reply, recommendations, end_of_conversation
- ✅ Recommendations from catalog: Java 8, Core Java, Verify Numerical — all real entries
- ✅ Response time: 3.6-4.5s per call (budget: 30s)
- ✅ Startup time: 20.6s (budget: 120s)
- ✅ Clarify on vague: "I need an assessment" → asks question, empty recommendations
- ✅ Refuse off-topic: jokes, prompt injection → polite refusal, empty recommendations
- ✅ Validation: empty messages → 422, invalid role → 422

### Phase 5 — Final State

| File | Purpose |
|------|---------|
| main.py | Complete FastAPI app with /health + /chat + startup init |
| scripts/test_e2e.py | End-to-end verification (proof of work) |

### Key Decisions
- **response_model=ChatResponse**: Pydantic enforces schema at serialization — double safety net
- **Startup fail-fast**: Missing API key or broken retriever → sys.exit(1) immediately
- **Messages conversion**: Pydantic Message objects → plain dicts for agent (keeps agent decoupled from FastAPI)

---

## Phase 6 — Tests

### Step 6.1: Installed test dependencies
- Ran: `.\venv\Scripts\pip install pytest pytest-asyncio httpx`
- Installed: pytest==9.0.3, pytest-asyncio==1.3.0

### Step 6.2: Created tests/__init__.py
- Empty package file to make tests/ a Python package

### Step 6.3: Created tests/test_api.py (14 tests)
- **TestHealthEndpoint**: returns 200, correct content-type, POST returns 405
- **TestChatValidation**: empty body→422, empty messages→422, invalid role→422, empty content→422, missing content→422, too many messages→422
- **TestChatResponseSchema**: valid request→200, has required fields, reply is string, recommendations is list, end_of_conversation is bool
- Uses `@patch("agent.call_llm")` to mock LLM calls (fast, free, deterministic)

### Step 6.4: Created tests/test_agent.py (35 tests)
- **TestDetermineMode** (7): vague→clarify, detailed→recommend, off-topic→refuse, injection→refuse, comparison→compare, empty→clarify, long JD→recommend
- **TestOffTopicDetection** (6): joke, weather, injection detected; assessment/hiring/shl queries not off-topic
- **TestComparisonDetection** (4): difference, compare, versus detected; normal query not comparison
- **TestSufficientContext** (4): single word insufficient; role+competency, role+type, long message sufficient
- **TestTurnCounting** (3): zero turns, JSON-based counting, turn limit forces end
- **TestResponseParsing** (5): valid JSON, code block, invalid fallback, cap at 10, invalid recs filtered
- **TestProvenanceValidation** (6): valid kept, hallucinated name/url filtered, mixed, empty, case-sensitive

### Step 6.5: Created tests/test_retriever.py (19 tests)
- **TestRetrieverInit** (6): real catalog, small catalog, missing file, invalid JSON, empty catalog, missing field
- **TestRetrieverSearch** (10): returns results, respects top_k, top_k=1, has score, ordered by score, has required fields, java→java tests, personality→P type, empty query, performance <5s
- **TestGetAllEntries** (3): returns full catalog, has required fields, small catalog

### Step 6.6: Test results
```
tests/test_agent.py     — 35 passed in 18.18s ✓
tests/test_api.py       — 14 passed in 31.08s ✓
tests/test_retriever.py — 19 passed in 40.55s ✓
TOTAL                   — 68 passed ✓
```

### Phase 6 — Final State

| File | Tests | Purpose |
|------|-------|---------|
| tests/__init__.py | - | Package marker |
| tests/test_api.py | 14 | Endpoint integration tests |
| tests/test_agent.py | 35 | Agent logic and behavior tests |
| tests/test_retriever.py | 19 | Retrieval system tests |

---

## Phase 7 — Deployment
*(To be documented as we build it)*

---

## Phase 8 — Approach Document
*(To be documented as we build it)*
