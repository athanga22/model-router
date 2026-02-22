# Smart Model Router

A production-grade API that automatically routes LLM prompts to the cheapest
model capable of handling them. Saves up to 90%+ on inference costs without
sacrificing response quality.

---

## The Problem

GPT-4o costs ~$5-15/1M tokens. Most real-world tasks don't need it.
This router classifies every prompt and sends it to the right model automatically.

**Why this matters:** Teams often default to one expensive model for everything. This project shows how to cut cost while keeping quality: classify prompt difficulty, route to the cheapest capable model, and auto-escalate when a response is low-confidence. The result is measurable savings (logged per request) and a single API your clients call.

---

## Architecture
```
User Request
     │
     ▼
┌─────────────────┐
│   FastAPI API   │  ← Single endpoint your client calls
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Phi-3 Classifier│  ← Runs locally via Ollama (free, ~120ms)
│  (Ollama local) │    Tags prompt: simple / medium / complex
└────────┬────────┘
         │
    ┌────┴─────────────────┐
    │                      │
    ▼                      ▼                      ▼
┌──────────┐      ┌──────────────┐      ┌──────────────┐
│  Haiku   │      │  Llama 3 70B │      │   GPT-4o     │
│ (Simple) │      │   (Medium)   │      │  (Complex)   │
│ $1/MTok  │      │ $0.06/MTok   │      │  $5/MTok     │
└──────────┘      └──────────────┘      └──────────────┘
         │
         ▼
┌─────────────────┐
│  Escalation     │  ← If model returns low-confidence response,
│  Feedback Loop  │    auto-escalates to next tier
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   PostgreSQL    │  ← Logs every request: model, cost, latency
└─────────────────┘
```

---

## Cost Savings

Based on a realistic production distribution (70% simple, 20% medium, 10% complex):

| Scale | Actual Cost | Always GPT-4o | Monthly Savings |
|-------|-------------|---------------|-----------------|
| 10K requests/mo | ~$1.00 | ~$10.05 | **~$9.05** |
| 100K requests/mo | ~$10.00 | ~$100.47 | **~$90.47** |
| 1M requests/mo | ~$100.00 | ~$1,005 | **~$905** |

---

## Tech Stack

| Layer | Tool |
|-------|------|
| API Framework | FastAPI |
| Classifier | Phi-3 mini via Ollama (local) |
| Simple Model | Claude Haiku 4.5 (Anthropic) |
| Medium Model | Llama 3.3 70B (Groq) |
| Complex Model | GPT-4o (OpenAI) |
| Database | PostgreSQL via Docker |
| Dashboard | Streamlit + Plotly |
| Tests | pytest |

---

## Evaluation

The classifier is evaluated on a labeled set of prompts:

| Metric | Target |
|--------|--------|
| Labeled prompts | 20 (8 simple, 7 medium, 5 complex) |
| Accuracy threshold | ≥ 80% |
| Edge cases | Empty, long, non-English |

Run the classifier tests to see the accuracy report:

```bash
pytest tests/test_classifier.py -v -s
```

---

## Getting Started

### Prerequisites
- Docker + Docker Compose
- Python 3.9+
- Ollama installed ([ollama.ai](https://ollama.ai))

### 1. Clone and install
```bash
git clone <your-repo-url>
cd smart-router
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Pull the classifier model
```bash
ollama pull phi3:mini
```

### 3. Configure environment
```bash
cp .env.example .env
# Fill in your API keys in .env
```

### 4. Start the database
```bash
docker-compose up -d
```

### 5. Run migrations
```bash
python app/database.py
```

### 6. Start the API
```bash
uvicorn app.main:app --reload --port 8000
```

### 7. Launch the dashboard
```bash
streamlit run dashboard.py
```

---

## API Usage

### Route a prompt
```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?"}'
```

Response:
```json
{
  "response": "The capital of France is Paris.",
  "model_used": "claude-haiku-4-5",
  "difficulty_tag": "simple",
  "cost_usd": 0.000064,
  "latency_ms": 1184,
  "escalated": false
}
```

### Check health
```bash
curl http://localhost:8000/v1/health
```

### Get cost stats
```bash
curl http://localhost:8000/v1/stats
```

### API Docs
Auto-generated OpenAPI docs available at: `http://localhost:8000/docs`

---

## Running Tests

**Unit tests** (no API keys; mocks for LLM calls):

```bash
pytest tests/test_classifier.py tests/test_escalation.py -v
```

**Integration tests** (real classifier + LLM calls; requires Ollama + API keys in `.env`):

```bash
pytest tests/test_integration.py -v -s
```

Or run everything except integration:

```bash
pytest tests/ -v -m "not integration"
```

---

## Dashboard

The Streamlit dashboard shows live cost savings, model usage distribution,
and projected savings at scale. Launch with:
```bash
streamlit run dashboard.py
# Opens at http://localhost:8501
```
