# SHL Assessment Recommender

A conversational AI agent that helps hiring managers find the right SHL assessments through natural multi-turn dialogue. Built as a FastAPI backend service for the SHL Labs AI Intern take-home assignment.

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/N-murali/shl-recommender.git
cd shl-recommender

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
# Windows:
.\venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Create .env file with your API key
echo GROQ_API_KEY=your_key_here > .env

# 6. Run the scraper (one-time, generates data/catalog.json)
python catalog_scraper.py

# 7. Start the server
python -m uvicorn main:app --host 0.0.0.0 --port 10000

# 8. Test health endpoint
curl http://localhost:10000/health
# Expected: {"status": "ok"}
```

## API Endpoints

### GET /health
Returns `{"status": "ok"}` with HTTP 200. Used by the evaluator as a readiness check.

### POST /chat
Stateless conversational endpoint. Full conversation history sent on every call.

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "I need assessments for a Java developer"},
    {"role": "assistant", "content": "What seniority level?"},
    {"role": "user", "content": "Mid-level, about 4 years experience"}
  ]
}
```

**Response:**
```json
{
  "reply": "Here are assessments for a mid-level Java developer...",
  "recommendations": [
    {
      "name": "Java 8 (New)",
      "url": "https://www.shl.com/...",
      "test_type": "K"
    }
  ],
  "end_of_conversation": false
}
```

## Project Structure

```
shl-recommender/
├── main.py              ← FastAPI app, /health and /chat endpoints
├── agent.py             ← Conversational agent logic, contains call_llm()
├── catalog_scraper.py   ← Scrapes SHL catalog, saves to data/catalog.json
├── retriever.py         ← FAISS vector store, embeddings, search
├── models.py            ← Pydantic request/response models
├── prompts.py           ← System prompt and all prompt templates
├── config.py            ← Env loading, constants, LLM config
├── data/
│   └── catalog.json     ← Scraped catalog data
├── tests/
│   ├── test_api.py      ← API endpoint tests
│   ├── test_agent.py    ← Agent behavior tests
│   └── test_retriever.py ← Retrieval quality tests
├── docs/
│   └── approach.md      ← 2-page submission document
├── requirements.txt     ← Pinned dependencies
├── .env                 ← API keys (never committed)
├── .gitignore
├── render.yaml          ← Render deployment config
└── README.md
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| API Framework | FastAPI + Uvicorn | HTTP endpoints, async support |
| LLM | Groq (llama-3.3-70b-versatile) | Conversational AI brain |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Semantic search |
| Vector Store | FAISS (CPU) | Similarity search over catalog |
| Scraping | BeautifulSoup4 + Requests | Extract SHL catalog data |
| Validation | Pydantic v2 | Request/response schema enforcement |
| Deployment | Render (free tier) | Public endpoint hosting |

## Running Tests

```bash
# Activate venv first
.\venv\Scripts\activate

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_api.py -v
```

## Deployment (Render)

1. Push code to GitHub
2. Connect repository to Render
3. Set environment variables in Render dashboard:
   - `GROQ_API_KEY` = your Groq API key
   - `PORT` = 10000 (Render sets this automatically)
4. Deploy — Render uses `render.yaml` for configuration

## Design Decisions

- **Stateless**: No server-side session storage. Full conversation history in every request.
- **LLM Isolation**: All Groq-specific code lives in `call_llm()` in agent.py. Swapping providers requires changing only that function + config.py + requirements.txt.
- **Provenance Validation**: Every recommendation is validated against the scraped catalog before returning. Prevents hallucinated URLs.
- **Pre-computed Embeddings**: FAISS index built at startup from catalog.json. No runtime embedding cost for catalog entries.

## Constraints (Enforced by Auto-Evaluator)

- Maximum 8 turns per conversation
- Maximum 30 second timeout per API call
- Response schema must be exact (reply, recommendations, end_of_conversation)
- All URLs must come from scraped catalog — never invented
- 1-10 recommendations when committing to a shortlist
