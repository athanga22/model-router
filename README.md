# Smart Model Router

An API that automatically routes LLM prompts to the cheapest
model capable of handling them. Saves up to 90%+ on inference costs without
sacrificing response quality.

**Project directory:** All code and commands below live in [`smart-router/`](smart-router/). After cloning, run commands from `smart-router/` (e.g. `cd smart-router`).

---

## The Problem

GPT-4o costs ~$2.50-10/1M tokens. Most real-world tasks don't need it.
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
┌──────────────────────┐
│  Cerebras Classifier │  ← Llama 3.1 8B via Cerebras (~100ms)
│  (Llama 3.1 8B)      │    Tags prompt: simple / medium / complex
└────────┬─────────────┘
         │
    ┌────┴─────────────────┌──────────────────────┐
    │                      │                      │
    ▼                      ▼                      ▼
┌──────────┐      ┌──────────────┐      ┌──────────────┐
│  Haiku   │      │  Llama 3.3   │      │   GPT-4o     │
│ (Simple) │      │  70B via     │      │  (Complex)   │
│ $1/MTok  │      │  Cerebras    │      │  $2.5/MTok   │
│          │      │ $0.07/MTok   │      │              │
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
| Classifier | Llama 3.1 8B via Cerebras |
| Simple Model | Claude Haiku 4.5 (Anthropic) |
| Medium Model | Llama 3.3 70B (Cerebras) |
| Complex Model | GPT-4o (OpenAI) |
| Database | PostgreSQL (Cloud SQL in prod) |
| Dashboard | Streamlit + Plotly (Streamlit Community Cloud; reads from API only) |
| Tests | pytest |
| CI/CD | GitHub Actions → Cloud Run |

---

## Evaluation

The classifier is evaluated on a labeled set of prompts:

| Metric | Result |
|--------|--------|
| Labeled prompts | 300 |
| Accuracy | 77% |
| Edge cases | Empty, long, non-English |

Run the classifier tests:

```bash
pytest tests/test_classifier.py -v -s
```

---

## Getting Started

### Prerequisites
- Docker + Docker Compose
- Python 3.11+
- API keys: Anthropic, OpenAI, Cerebras

### 1. Clone and install
```bash
git clone <your-repo-url>
cd smart-router
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Dashboard + eval scripts (scikit-learn, datasets, etc.) need the eval extras:
# pip install -r requirements-eval.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in your API keys in .env
```
Environment variables (e.g. `DATABASE_URL`) override values in `.env`. For local runs, if you've set `DATABASE_URL` in your shell, unset it so `.env` is used: `unset DATABASE_URL`.

For the dashboard: it talks to the API only (no direct database access). Locally it defaults to `API_BASE_URL=http://localhost:8000`. To point the dashboard at a remote API (e.g. Cloud Run), set `API_BASE_URL` in `.env` or in Streamlit Community Cloud app secrets.

### 3. Start the database
```bash
docker-compose up -d
```

### 4. Run migrations
```bash
python -m app.database
```

### 5. Start the API
```bash
uvicorn app.main:app --reload --port 8000
```

### 6. Launch the dashboard
```bash
streamlit run dashboard.py
```

---

## API access (auth)

When **`API_KEY`** is set on the server (Cloud Run env), every endpoint **except `GET /v1/health`** requires the same key in the **`X-API-Key`** header. Omit `API_KEY` locally if you want open access for development.

- **Cloud Run:** set `API_KEY` to a long random string (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`).
- **Streamlit Cloud:** set the **same** value in app secrets as `API_KEY`, plus `API_BASE_URL` to your Cloud Run URL. The dashboard calls the API **server-side**, so all dashboard users share one outbound IP — rate limits are set to **60/min** on chat endpoints to avoid blocking demos.

Generate a key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Example with auth (replace `YOUR_CLOUD_RUN_URL` and `<your-key>`):

```bash
curl -X POST https://YOUR_CLOUD_RUN_URL/v1/chat \
  -H "X-API-Key: <your-key>" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain the CAP theorem"}'
```

---

## API Usage

### Route a prompt (blocking)
If `API_KEY` is set, add `-H "X-API-Key: <your-key>"` to all `curl` examples below.

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

### Route a prompt (streaming)
```bash
curl -X POST http://localhost:8000/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain quantum entanglement"}'
```

Streams newline-delimited JSON frames: `metadata` (routing), then `token` (text chunks), then `done` (cost, latency). On classifier or model failure, a single `{"type": "error", "message": "..."}` frame is sent (message is the exception string, e.g. classifier_error or escalation_model_failed).
```
{"type": "metadata", "difficulty_tag": "complex", "model_used": "gpt-4o", "escalated": false}
{"type": "token", "text": "Quantum"}
...
{"type": "done", "cost_usd": 0.000312, "cost_saved_usd": 0.0, "latency_ms": 2100}
```

### Check health
```bash
curl http://localhost:8000/v1/health
```

Response (200): `status` is always `"ok"`. `db` is `"ok"` when the database is reachable, or `"error: <details>"` when not. `classifier` is `"ok"` when the classifier is reachable, or `"error: <details>"` when not.
```json
{"status": "ok", "db": "ok", "classifier": "ok"}
```

### Get cost stats
```bash
curl http://localhost:8000/v1/stats
```

Response (200): JSON with `total_requests`, `total_cost_usd`, `total_cost_saved_usd`, `model_usage`, `escalation_rate`, and `savings_ts` (hourly savings). Returns 500 when the database is unreachable.

### Get recent requests
```bash
curl "http://localhost:8000/v1/recent?limit=20"
```
Response (200): JSON array of recent requests, each with `created_at`, `difficulty_tag`, `model_used`, `cost_usd`, `cost_saved_usd`, `latency_ms`, `escalated`. Returns 500 when the database is unreachable.

### API Docs
Auto-generated OpenAPI docs available at: `http://localhost:8000/docs`

---

## Running Tests

**Unit tests** (mocks for LLM calls), from `smart-router/`:

```bash
pytest tests/test_classifier.py tests/test_escalation.py -v
```

**Integration tests** (real LLM calls; requires API keys in `.env`):

```bash
pytest tests/test_integration.py -v -s
```

Or run everything:

```bash
pytest tests/ -v --tb=short
```

---

## Dashboard

The Streamlit dashboard reads all data from the API (`/v1/stats`, `/v1/recent`, `/v1/chat/stream`). It does not connect to the database directly.

Two tabs:

- **Dashboard** — aggregate cost savings, model usage distribution, savings time series, projected savings at scale, and a table of recent requests
- **Try It Live** — send prompts; routing decision and streaming response from the chosen model

Deployed on Streamlit Community Cloud. For that deployment, set `API_BASE_URL` in the app secrets to your Cloud Run service URL. To run locally (against the API on port 8000 by default):
```bash
streamlit run dashboard.py
```

---

## Deployment

The project deploys automatically via GitHub Actions on push to `main`:

1. Runs tests against a Postgres service container
2. Builds and pushes a Docker image to GCP Artifact Registry
3. Deploys to Cloud Run with Cloud SQL

Required secrets in GitHub and GCP Secret Manager:
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `CEREBRAS_API_KEY`
- `DB_PASSWORD`

For the dashboard on Streamlit Community Cloud, set `API_BASE_URL` in the app's secrets to the Cloud Run service URL so it can call the API.