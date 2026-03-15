# Smart Model Router

An intelligent API that automatically routes LLM prompts to the most cost-effective model capable of handling them — saving 90%+ on inference costs without sacrificing quality.

---

## How It Works

Every prompt is classified by a fast Gemma 3N model (via Together AI, ~200ms) and routed to the cheapest model that can handle it. If a model returns a low-confidence response, the system automatically escalates to the next tier.

```
User Prompt
    │
    ▼
┌─────────────────────────┐
│      FastAPI API        │  ← Single endpoint your client calls
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   Together AI Classifier│  ← Gemma 3N E4B, tags prompt in ~200ms
│   (google/gemma-3n-E4B) │    simple / medium / complex
└───────────┬─────────────┘
            │
    ┌───────┼───────────────────┐
    ▼       ▼                   ▼
┌────────┐ ┌──────────────────┐ ┌────────┐
│ Haiku  │ │ Llama-3.3-70B    │ │ GPT-4o │
│ Simple │ │ Medium           │ │Complex │
│$1/MTok │ │ $0.88/MTok       │ │$2.5/M  │
└────────┘ └──────────────────┘ └────────┘
            │
            ▼
┌─────────────────────────┐
│   Escalation Logic      │  ← Auto-escalates on low-confidence responses
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│      PostgreSQL         │  ← Logs every request: model, cost, latency
└─────────────────────────┘
```

---

## Cost Savings

Based on a realistic production distribution (70% simple, 20% medium, 10% complex):

| Scale | Smart Router Cost | Always GPT-4o | Monthly Savings |
|-------|:-----------------:|:-------------:|:---------------:|
| 10K requests/mo | ~$1.00 | ~$10.05 | **~$9.05** |
| 100K requests/mo | ~$10.00 | ~$100.47 | **~$90.47** |
| 1M requests/mo | ~$100.00 | ~$1,005 | **~$905** |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI + Uvicorn |
| Classifier | `google/gemma-3n-E4B-it` via Together AI |
| Simple tier | Claude Haiku 4.5 (Anthropic) |
| Medium tier | `meta-llama/Llama-3.3-70B-Instruct-Turbo` (Together AI) |
| Complex tier | GPT-4o (OpenAI) |
| Database | PostgreSQL (Cloud SQL in production) |
| Dashboard | Streamlit + Plotly |
| Tests | pytest |
| CI/CD | GitHub Actions → Google Cloud Run |

---

## Project Structure

```
smart-router/
├── app/
│   ├── main.py          # FastAPI app and all endpoints
│   ├── router.py        # Routing orchestrator
│   ├── classifier.py    # Prompt difficulty classification (Together AI)
│   ├── escalation.py    # Low-confidence detection and escalation
│   ├── llm.py           # LLM client wrappers (Anthropic, OpenAI, Together AI)
│   ├── cost.py          # Cost calculation and savings tracking
│   ├── logger.py        # Request logging with PII redaction
│   ├── database.py      # PostgreSQL connection pool and migrations
│   └── models.py        # Pydantic request/response models
│
├── migrations/          # SQL migration files
├── tests/               # Unit and integration tests
├── scripts/             # Utility scripts (eval, seed data, load testing)
├── data/                # 300-prompt labeled eval set (eval_prompts.csv)
├── dashboard.py         # Streamlit analytics dashboard
├── docker-compose.yml   # Local PostgreSQL setup
└── .env.example         # Environment variable template
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Docker + Docker Compose
- API keys for Anthropic, OpenAI, and Together AI

### 1. Clone and install dependencies

```bash
git clone <your-repo-url>
cd smart-router
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> For the dashboard and evaluation scripts, also run:
> `pip install -r requirements-eval.txt`

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

> If `DATABASE_URL` is set in your shell environment, it will override the value in `.env`. Run `unset DATABASE_URL` locally if needed.

### 3. Start the database

```bash
docker-compose up -d
```

### 4. Run database migrations

```bash
python -m app.database
```

### 5. Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

### 6. (Optional) Launch the analytics dashboard

```bash
streamlit run dashboard.py
```

The dashboard reads all data from the API — it does not connect to the database directly.

---

## Environment Variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key (Claude Haiku 4.5) |
| `OPENAI_API_KEY` | Yes | OpenAI API key (GPT-4o) |
| `TOGETHER_API_KEY` | Yes | Together AI key (classifier + Llama 3.3 70B) |
| `DB_PASSWORD` | Yes | PostgreSQL password |
| `DATABASE_URL` | No | Full connection string (overrides individual DB vars) |
| `API_KEY` | No | Auth key for the API (required in production) |
| `API_BASE_URL` | No | Base URL of the API (used by the dashboard) |
| `LLM_TIMEOUT_SECONDS` | No | LLM request timeout, default `60` |

---

## API Reference

### Authentication

When `API_KEY` is set on the server, all endpoints except `GET /v1/health` require the key in the `X-API-Key` header.

```bash
# Generate a secure key
python -c "import secrets; print(secrets.token_hex(32))"
```

---

### `POST /v1/chat` — Route a prompt (blocking)

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"prompt": "What is the capital of France?"}'
```

**Response:**

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

---

### `POST /v1/chat/stream` — Route a prompt (streaming)

```bash
curl -X POST http://localhost:8000/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain quantum entanglement"}'
```

Streams newline-delimited JSON frames in sequence:

```
{"type": "metadata", "difficulty_tag": "complex", "model_used": "gpt-4o", "escalated": false}
{"type": "token", "text": "Quantum"}
{"type": "token", "text": " entanglement"}
...
{"type": "done", "cost_usd": 0.000312, "cost_saved_usd": 0.0, "latency_ms": 2100, "request_id": 42}
```

On failure, a single `{"type": "error", "message": "..."}` frame is sent.

---

### `GET /v1/health` — Health check

```bash
curl http://localhost:8000/v1/health
```

```json
{"status": "ok", "db": "ok", "classifier": "ok"}
```

---

### `GET /v1/stats` — Aggregated cost statistics

```bash
curl http://localhost:8000/v1/stats
```

Returns: `total_requests`, `total_cost_usd`, `total_cost_saved_usd`, `model_usage`, `escalation_rate`, and `savings_ts` (hourly savings time series).

---

### `GET /v1/recent?limit=20` — Recent requests

```bash
curl "http://localhost:8000/v1/recent?limit=20"
```

Returns an array of recent requests with `created_at`, `difficulty_tag`, `model_used`, `cost_usd`, `cost_saved_usd`, `latency_ms`, and `escalated`.

---

### `POST /v1/feedback` — Submit response feedback

```bash
curl -X POST http://localhost:8000/v1/feedback \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-key>" \
  -d '{"request_id": 42, "feedback": 1}'
```

`feedback` must be `1` (thumbs up) or `-1` (thumbs down). Used by the dashboard to collect quality signals on routed responses.

---

### Interactive API Docs

Auto-generated OpenAPI docs available at: `http://localhost:8000/docs`

---

## Running Tests

**Unit tests** (no API keys required):

```bash
pytest tests/test_classifier.py tests/test_escalation.py -v
```

**Integration tests** (real LLM calls — requires API keys in `.env`):

```bash
pytest tests/test_integration.py -v -s
```

**All tests:**

```bash
pytest tests/ -v --tb=short
```

### Classifier Evaluation

The classifier is evaluated against 300 human-labeled real-world prompts sourced from the LMSYS Chatbot Arena dataset on HuggingFace.

| Metric | Value |
|--------|-------|
| Labeled prompts | 300 |
| Accuracy | ~81.7% |
| Corrected accuracy (after label noise) | ~85% |
| Misrouting pattern | Adjacent tiers only (no simple→complex jumps) |
| Edge cases covered | Empty, long, non-English prompts |

Run the eval:

```bash
python scripts/run_eval.py
```

Outputs accuracy, a confusion matrix, and full details on every misclassified prompt.

---

## Dashboard

The Streamlit dashboard connects to the API only (no direct database access) and has two tabs:

- **Dashboard** — aggregate cost savings, model usage breakdown, savings over time, and a table of recent requests
- **Try It Live** — interactive prompt box with streaming response, routing details, and 👍/👎 feedback buttons

**Running locally:**

```bash
streamlit run dashboard.py
```

**Deployed on Streamlit Community Cloud:** Set `API_BASE_URL` in the app secrets to your Cloud Run service URL, and `API_KEY` to the same key set on the API.

---

## Deployment

The project deploys automatically to Google Cloud Run on push to `main` via GitHub Actions:

1. Runs tests against a PostgreSQL service container
2. Builds and pushes a Docker image to GCP Artifact Registry
3. Deploys to Cloud Run connected to Cloud SQL

**Required secrets** (GitHub Actions + GCP Secret Manager):

- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `TOGETHER_API_KEY`
- `DB_PASSWORD`

For the dashboard on Streamlit Community Cloud, set `API_BASE_URL` in the app secrets to the Cloud Run service URL.

---

## Key Design Decisions

- **Classifier is separate from routing models** — a fast, cheap model (`google/gemma-3n-E4B-it` via Together AI) classifies every prompt before routing, adding ~200ms but enabling significant downstream savings.
- **Escalation is transparent** — when a model returns a low-confidence response (detected via regex patterns like "I don't know", "I'm unable to"), the system silently escalates once to the next tier.
- **Feedback loop built in** — every streamed response returns a `request_id`; the dashboard uses it to POST thumbs up/down signals back to the API, which are stored for future fine-tuning.
- **Dashboard uses the API, not the database** — this keeps the architecture clean and means the dashboard works identically in local and production environments.
- **PII is redacted before logging** — API key patterns and sensitive data are stripped from stored prompts.
- **Rate limiting is tuned for shared IPs** — set to 60 requests/min to handle Streamlit Community Cloud's shared outbound IP during demos.
