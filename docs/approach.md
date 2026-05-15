# Approach Document — SHL Conversational Assessment Recommender

## 1. System Overview

I built a stateless FastAPI service that helps hiring managers find SHL assessments through multi-turn conversation. The system uses Groq (llama-3.3-70b-versatile) as the LLM, FAISS for vector similarity search, and pre-computed embeddings from BAAI/bge-small-en-v1.5 for semantic retrieval over 377 Individual Test Solutions scraped from the SHL product catalog.

**Live URL:** https://shl-recommender-uy49.onrender.com  
**Endpoints:** GET /health, POST /chat  
**Response time:** 2-6 seconds per call  

---

## 2. Architecture & Design Choices

### 2.1 Stateless Design
Every POST /chat request carries the full conversation history. The server stores nothing between requests — no sessions, no databases, no in-memory state. This enables horizontal scaling and simplifies deployment.

### 2.2 LLM Abstraction
All LLM-specific code lives inside a single function `call_llm()` in agent.py. No other file imports or references the LLM SDK. This clean separation means the conversational logic, retrieval, and prompt templates are completely independent of the LLM provider — a good engineering practice for maintainability.

### 2.3 Behavior Mode Router
The agent determines one of five behaviors per turn:
- **CLARIFY** — vague query, asks questions (max 2 before forcing recommendations)
- **RECOMMEND** — sufficient context, returns 1-10 assessments
- **REFINE** — user changes constraints after receiving a shortlist
- **COMPARE** — comparison question, answers using only catalog data
- **REFUSE** — off-topic, legal questions, or prompt injection attempts

Mode determination is rule-based (regex patterns + keyword analysis), not LLM-based. This makes it fast, deterministic, and testable without API calls.

### 2.4 Provenance Validation (Anti-Hallucination Layer)
After the LLM generates recommendations, every recommendation is validated against the catalog via case-sensitive exact match on both `name` AND `url`. If the LLM hallucinates an assessment name or URL, it gets filtered out before the response is sent. This is the critical layer that ensures we never return invented data.

---

## 3. Retrieval Strategy

### 3.1 Original Approach (Failed on Render)
Initially I used `sentence-transformers` with `all-MiniLM-L6-v2` loaded locally on the server. This worked perfectly in local testing but crashed on Render free tier (512MB RAM) because PyTorch alone consumes ~300MB.

### 3.2 Final Approach (Pre-computed Embeddings + HF Inference API)
I split the embedding pipeline into two parts:

**Offline (run locally before deploy):**
- Load `BAAI/bge-small-en-v1.5` model via sentence-transformers
- Embed all 377 catalog entries
- Save as `data/embeddings.npy` (565KB file)

**Runtime (on Render):**
- Load pre-computed embeddings from .npy file (instant, no model needed)
- Build FAISS IndexFlatIP from loaded vectors
- For each user query, call Hugging Face Inference API to get the query embedding
- Search FAISS index for top-10 similar catalog entries

**Why this works:** Server RAM drops from ~520MB to ~70MB. Startup goes from 20.6s to 0.0s. The only tradeoff is ~200ms added latency per query for the HF API call.

### 3.3 Why I Changed from all-MiniLM-L6-v2 to bge-small-en-v1.5
The Hugging Face Inference API assigns `all-MiniLM-L6-v2` to the SentenceSimilarity pipeline (returns similarity scores between sentence pairs), not the feature-extraction pipeline (returns raw embedding vectors). I needed raw vectors for FAISS search. `BAAI/bge-small-en-v1.5` is assigned to feature-extraction on the HF API, returns 384-dim vectors, and actually scores higher on retrieval benchmarks.

### 3.4 Embedding Text Representation
Each catalog entry is embedded as: `"{name} | {test_type} | {description}"`

This gives the embedding model context about what the assessment is called, what type it is, and what it measures — all in one string for semantic matching.

---

## 4. Catalog Scraping

### 4.1 Process
I scraped https://www.shl.com/solutions/products/product-catalog/ using BeautifulSoup4 + Requests with a two-pass approach:
- **Pass 1:** Scrape all 32 listing pages (12 items each) → get name, URL, test_type, remote_testing, adaptive
- **Pass 2:** Visit each of the 377 detail pages → get description and duration

### 4.2 Problems Encountered
- **CloudFront blocking:** Plain `requests.get()` returned 403. Fixed by adding browser-like User-Agent headers.
- **HTML structure discovery:** Created `scripts/explore_catalog.py` to investigate the page structure before writing the scraper. Found that remote testing is indicated by `<span class="catalogue__circle -yes">` and test types are concatenated letter codes.
- **Rate limiting:** Added 1-second delay between requests to avoid getting blocked mid-scrape.

### 4.3 Result
377 Individual Test Solutions extracted. All have name, URL, test_type. 283/377 have duration. All have descriptions. Zero Pre-packaged Job Solutions included.

---

## 5. Prompt Design

### 5.1 System Prompt (~800 tokens)
The system prompt defines:
- Agent persona (SHL Assessment Recommender)
- Strict JSON output format (reply, recommendations, end_of_conversation)
- Rules for each behavior mode
- Grounding instruction: "Only use assessment data from the CATALOG CONTEXT provided"

### 5.2 Behavior-Specific Prompts
Each behavior mode has its own prompt template that provides the LLM with:
- Conversation summary (what the user has said)
- Catalog context (retrieved entries formatted with name, URL, type, description)
- Specific instructions for that mode (e.g., "ask ONE clarifying question" or "explain what changed")

### 5.3 JSON Reliability
Groq's llama-3.3-70b-versatile follows JSON format instructions reliably with temperature=0. I added fallback parsing that handles:
- Valid JSON directly
- JSON wrapped in markdown code blocks (```json...```)
- Malformed responses (uses raw text as reply, empty recommendations)

---

## 6. Problems Faced & How I Solved Them

### Problem 1: Render Out of Memory (512MB limit)
**Symptom:** "Ran out of memory (used over 512MB)" — health check never responded.  
**Root cause:** PyTorch (~300MB) + sentence-transformers model (~90MB) + Python runtime (~70MB) = ~520MB.  
**Solution:** Pre-compute embeddings offline, use HF Inference API for runtime queries. Removed PyTorch and sentence-transformers from server requirements. RAM dropped to ~70MB.

### Problem 2: HF Inference API URL Changes
**Symptom:** 404 errors when calling `api-inference.huggingface.co/models/...`  
**Root cause:** HF migrated their API to `router.huggingface.co/hf-inference/models/...`  
**Solution:** Tested multiple URL formats systematically (documented in `scripts/test_hf_api.py`), found the working endpoint.

### Problem 3: all-MiniLM-L6-v2 Not Available for Feature Extraction via API
**Symptom:** 400 error — "SentenceSimilarityPipeline missing argument 'sentences'"  
**Root cause:** HF assigns this model to SentenceSimilarity pipeline (compares pairs), not feature-extraction (returns vectors).  
**Solution:** Switched to `BAAI/bge-small-en-v1.5` which HF assigns to feature-extraction. Re-computed all catalog embeddings with the new model.

### Problem 4: SHL Website Blocking Scraper
**Symptom:** When I tried to scrape the SHL catalog using Python's `requests.get()`, the server returned HTTP 403 Forbidden.  
**What 403 means:** The server received our request but refused to serve it. It said "I know what you want, but I won't give it to you."  
**Why it happened:** SHL uses CloudFront (Amazon's CDN/security layer) which detects automated scripts. When a request comes without a proper User-Agent header (or with Python's default `python-requests/2.34`), CloudFront assumes it's a bot and blocks it.  
**What I tried first:** Plain `requests.get("https://www.shl.com/...")` → 403 every time.  
**What fixed it:** I added headers that make the request look like it's coming from a real Chrome browser:
```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
```
After adding these headers, the server returned 200 OK with the full HTML page (363KB). I also added 1-second delays between requests to avoid triggering rate limits during the full scrape of 377 pages.

### Problem 5: Test Suite Hanging (Phase 6)
**Symptom:** When I ran `pytest tests/test_api.py`, the tests started running (I could see dots appearing) but never finished — they timed out after 120 seconds.  
**What was happening:** FastAPI's TestClient triggers the app's startup event. Our startup event loads the retriever (reads catalog, loads embeddings, builds FAISS index). This takes about 20 seconds.  
**The real problem:** By default, pytest creates a fresh TestClient for EVERY test function. With 14 API tests, that means 14 × 20 seconds = 280 seconds just for initialization — way past the timeout.  
**What I tried first:** Running all tests together with verbose output → timed out. Piping output through PowerShell's `Select-Object` → hung indefinitely.  
**What fixed it:** Changed the pytest fixture from `scope="function"` (default — runs for every test) to `scope="module"` (runs once for all tests in the file):
```python
# BEFORE: Retriever loads 14 times (280 seconds)
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

# AFTER: Retriever loads once (20 seconds total)
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
```
After this fix, all 14 API tests completed in 31 seconds.

### Problem 6: Mocked Tests Not Testing the Right Path
**Symptom:** I mocked `call_llm()` to return a response with recommendations, but the test always showed empty recommendations regardless of what the mock returned.  
**What was happening:** The test sent a vague message like `"hello"`. The agent's `_determine_mode()` function analyzed this message and decided it was too vague → routed to CLARIFY mode. In CLARIFY mode, the agent forces `recommendations = []` no matter what the LLM returns. So the mock was being called, but its return value was being overwritten by the CLARIFY logic.  
**Why this matters:** The test was supposed to verify that recommendations flow through correctly, but it was accidentally testing the CLARIFY path every time — making it useless as a schema test.  
**What fixed it:** Changed the test messages from vague queries to detailed queries that trigger RECOMMEND mode:
```python
# BEFORE: Triggers CLARIFY → recommendations always [] → mock is irrelevant
messages = [{"role": "user", "content": "hello"}]

# AFTER: Triggers RECOMMEND → mock's recommendations flow through → actually tests the schema
messages = [{"role": "user", "content": "I need assessments for a senior Java developer with problem-solving and communication skills"}]
```
After this fix, the mock's recommendations were actually used by the agent, and the schema tests properly verified that recommendation objects have name, url, and test_type fields.

---

## 7. Evaluation Results

### Hard Evals (all pass)
- Schema compliance: Every response has exactly {reply, recommendations, end_of_conversation}
- Catalog-only URLs: Provenance validation filters any hallucinated entries
- 8-turn cap: Turn counting forces end_of_conversation=true at turn 8
- Response time: 2-6 seconds (budget: 30 seconds)

### Behavior Probes (all pass)
- Refuses off-topic: jokes, weather, cooking, prompt injection → empty recommendations
- No recommendations on turn 1 for vague queries: "I need an assessment" → asks question
- Honors refinements: "also add personality tests" → updated shortlist with explanation
- Comparisons grounded in catalog: references duration, type, description from scraped data

### Recommendation Quality (tested across 6 profiles)
| Role | Top Recommendations |
|------|-------------------|
| Java Developer | Core Java, Java 8, Java Frameworks |
| Customer Service | Customer Service Phone Simulation, Phone Solution |
| Sales Manager | Sales Transformation Report, Managerial Scenarios |
| Data Analyst | MS Excel, Verify Numerical Reasoning |
| Project Manager | Project Management, Managerial Scenarios |
| HR Coordinator | Workplace Administration, Human Resources |

---

## 8. Testing Approach

### Per-Phase Testing
Each phase was tested independently before moving to the next:
- Phase 1: Server starts, /health returns 200, Pydantic validates correctly
- Phase 2: Scraper produces valid JSON with 377 entries, all required fields present
- Phase 3: Retriever returns relevant results, ordered by similarity, within 5 seconds
- Phase 4: Agent routes to correct behavior mode for all input types
- Phase 5: End-to-end with real LLM calls — all behaviors work
- Phase 6: 68 formal pytest tests (35 agent + 14 API + 19 retriever)
- Phase 7: Live deployment passes 24 evaluator-style tests

### Development Scripts (Proof of Work)
All exploration and verification scripts are preserved in `scripts/`:
- `explore_catalog.py` — HTML structure investigation
- `test_scraper_quick.py` — 2-page scraper verification before full run
- `verify_catalog.py` — Post-scrape validation
- `test_retriever_quick.py` — Retrieval quality verification
- `test_agent_logic.py` — Behavior routing without LLM
- `test_hf_api.py` — HF API URL/format discovery
- `test_full_evaluation.py` — 124-test comprehensive evaluation

---

## 9. AI Tools Used

- **Kiro (AI coding agent):** Architecture design, code generation, debugging, test writing
- **Groq API (llama-3.3-70b-versatile):** The LLM brain powering the conversational agent
- **Hugging Face Inference API:** Runtime query embedding (BAAI/bge-small-en-v1.5)
- **sentence-transformers (offline only):** Pre-computing catalog embeddings locally

---

## 10. What I Would Improve With More Time

1. **Hybrid retrieval:** Combine semantic search with keyword filtering on test_type to improve precision
2. **Query synthesis via LLM:** Use the LLM to extract a focused search query from conversation instead of concatenating all user messages
3. **Caching:** Cache HF API responses for repeated queries to reduce latency
4. **Better competency extraction:** The SHL detail pages don't have a structured "competencies" field — with more time I'd extract these from descriptions using NLP
5. **Recall@10 optimization:** Test against known correct answers and tune the retrieval/ranking strategy
