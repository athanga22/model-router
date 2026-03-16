# TestSprite AI Testing Report (MCP)

---

## 1️⃣ Document Metadata

- **Project Name:** smart-router
- **Date:** 2026-03-16
- **Prepared by:** TestSprite AI + Claude Code
- **Test Type:** Backend API (FastAPI)
- **Server Under Test:** http://localhost:8000
- **Test Scope:** Full codebase — all 6 backend API endpoints
- **Pass Rate:** 4 / 6 (66.67%)

---

## 2️⃣ Requirement Validation Summary

### REQ-01 · Health Check API

#### TC001 — Health check API returns system health status
- **Test Code:** [TC001_health_check_api_returns_system_health_status.py](TC001_health_check_api_returns_system_health_status.py)
- **Test Result:** https://www.testsprite.com/dashboard/mcp/tests/7f6a624b-d797-476e-b7ec-163b9950e525/8e211553-a234-4ecd-9615-ec705a78ea47
- **Status:** ✅ Passed
- **Analysis:** `GET /v1/health` returns HTTP 200 with a JSON body containing `status`, `db`, and `classifier` string fields. All three fields are present and report valid values (`"ok"` for status, component-level values for db/classifier). The endpoint correctly surfaces live database pool health and classifier client reachability without exposing sensitive internals.

---

### REQ-02 · Blocking Chat API

#### TC002 — Blocking chat API routes prompt and returns response with metadata
- **Test Code:** [TC002_blocking_chat_api_routes_prompt_and_returns_response_with_metadata.py](TC002_blocking_chat_api_routes_prompt_and_returns_response_with_metadata.py)
- **Test Result:** https://www.testsprite.com/dashboard/mcp/tests/7f6a624b-d797-476e-b7ec-163b9950e525/62b05cbb-ff35-4e3e-9866-5fad10e700a4
- **Status:** ✅ Passed
- **Analysis:** `POST /v1/chat` with a valid `X-API-Key` and prompt correctly classifies the prompt, routes to the appropriate model tier, optionally escalates on low-confidence responses, and returns all required fields: `response` (str), `model_used` (str), `difficulty_tag` (str), `cost_usd` (float ≥ 0), `latency_ms` (int ≥ 0), `escalated` (bool). The response body is valid JSON and field types match the schema.

---

### REQ-03 · Streaming Chat API

#### TC003 — Streaming chat API streams LLM response with metadata and tokens
- **Test Code:** [TC003_streaming_chat_api_streams_llm_response_with_metadata_and_tokens.py](TC003_streaming_chat_api_streams_llm_response_with_metadata_and_tokens.py)
- **Test Result:** https://www.testsprite.com/dashboard/mcp/tests/7f6a624b-d797-476e-b7ec-163b9950e525/f1121f35-45b0-4ff0-b2dc-3897f32f5220
- **Status:** ❌ Failed
- **Error:**
  ```
  AssertionError: Token frame must include 'token' as string or 'event' as string
  ```
- **Root Cause:** The `POST /v1/chat/stream` endpoint emits token frames as `{"type": "token", "text": "<chunk>"}`, but the TestSprite-generated test (following the PRD) expected the token field to be named `"token"` or `"event"` — not `"text"`. This is an **API contract inconsistency**: the actual wire format uses `text` as the token payload key while the PRD/test expects `token`.
- **Fix Required:** Either update `app/main.py:_token_yield()` to emit `"token"` instead of `"text"`, or update the PRD/documentation to reflect that the field is named `"text"`. The former is recommended for clarity.

---

### REQ-04 · Stats API

#### TC004 — Stats API returns aggregated telemetry data
- **Test Code:** [TC004_stats_api_returns_aggregated_telemetry_data.py](TC004_stats_api_returns_aggregated_telemetry_data.py)
- **Test Result:** https://www.testsprite.com/dashboard/mcp/tests/7f6a624b-d797-476e-b7ec-163b9950e525/49cc8da3-2fdf-4f10-b2f4-d95e0dd8841e
- **Status:** ✅ Passed
- **Analysis:** `GET /v1/stats` returns HTTP 200 with all required fields: `total_requests` (int ≥ 0), `total_cost_usd` (float ≥ 0), `total_cost_saved_usd` (float ≥ 0), `model_usage` (dict), `escalation_rate` (float in [0,1]), `savings_ts` (list). All types and value ranges are correct. The endpoint correctly aggregates across the full requests table.

---

### REQ-05 · Recent Requests API

#### TC005 — Recent requests API returns most recent logged requests
- **Test Code:** [TC005_recent_requests_api_returns_most_recent_logged_requests.py](TC005_recent_requests_api_returns_most_recent_logged_requests.py)
- **Test Result:** https://www.testsprite.com/dashboard/mcp/tests/7f6a624b-d797-476e-b7ec-163b9950e525/b0e33c12-c01d-4394-b41b-8d5134b4c9e2
- **Status:** ✅ Passed
- **Analysis:** `GET /v1/recent` returns a list of request objects ordered by `created_at` descending. Each item contains the required fields with correct types: `created_at` (str/ISO 8601), `difficulty_tag` (str), `model_used` (str), `cost_usd` (float), `cost_saved_usd` (float), `latency_ms` (int), `escalated` (bool). Ordering is verified across all returned items.

---

### REQ-06 · Feedback API

#### TC006 — Feedback API accepts valid feedback and updates aggregates
- **Test Code:** [TC006_feedback_api_accepts_valid_feedback_and_updates_aggregates.py](TC006_feedback_api_accepts_valid_feedback_and_updates_aggregates.py)
- **Test Result:** https://www.testsprite.com/dashboard/mcp/tests/7f6a624b-d797-476e-b7ec-163b9950e525/33de4f55-acb3-44cc-958f-a1edb558672d
- **Status:** ❌ Failed
- **Error:**
  ```
  AssertionError: Cannot find 'id' or 'request_id' field in recent request item as per PRD specification
  ```
- **Root Cause:** `POST /v1/feedback` requires a `request_id` to link feedback to a logged request. However, `GET /v1/recent` does **not** expose the `id` field in its response (`RecentRequest` model in `app/models.py` omits it). This makes the full feedback workflow untestable end-to-end — a client receiving recent requests has no way to submit feedback without a separate lookup.
- **Fix Required:** Add `id: int` to the `RecentRequest` Pydantic model and include it in the SQL query in `GET /v1/recent`. This is a **missing field** in the API contract, not a logic error.

---

## 3️⃣ Coverage & Matching Metrics

**Overall Pass Rate: 66.67% (4/6)**

| Requirement                | Endpoint              | Tests | ✅ Passed | ❌ Failed |
|----------------------------|-----------------------|-------|-----------|----------|
| REQ-01 Health Check        | GET /v1/health        | 1     | 1         | 0        |
| REQ-02 Blocking Chat       | POST /v1/chat         | 1     | 1         | 0        |
| REQ-03 Streaming Chat      | POST /v1/chat/stream  | 1     | 0         | 1        |
| REQ-04 Stats               | GET /v1/stats         | 1     | 1         | 0        |
| REQ-05 Recent Requests     | GET /v1/recent        | 1     | 1         | 0        |
| REQ-06 Feedback            | POST /v1/feedback     | 1     | 0         | 1        |
| **TOTAL**                  |                       | **6** | **4**     | **2**    |

**Endpoints covered:** 6/6 (100% endpoint coverage)
**Auth protection verified:** ✅ (403 on missing/wrong key confirmed in prior run)

---

## 4️⃣ Key Gaps / Risks

### 🔴 Bug: Streaming token frame field name mismatch (TC003)
- **Location:** `app/main.py:351` — `_token_yield()` returns `{"type": "token", "text": "..."}`
- **Risk:** Any client consuming `/v1/chat/stream` that follows the PRD spec will fail to extract token text — they'd look for `frame["token"]` and get `None`.
- **Fix:** Change `"text"` → `"token"` in `_token_yield()`, or update all client-side consumers and docs to use `"text"`.

### 🔴 Bug: Missing `id` field in `/v1/recent` response (TC006)
- **Location:** `app/models.py:33` — `RecentRequest` model, `app/main.py:486` — `/v1/recent` SQL query
- **Risk:** The feedback workflow is broken end-to-end for any client that tries to submit feedback after viewing recent requests. The `request_id` required by `POST /v1/feedback` is invisible to the caller.
- **Fix:** Add `id: int` to `RecentRequest` and `SELECT id, ...` in the recent requests SQL query.

### 🟡 Gap: No test for auth rejection (403)
- The test suite does not include explicit negative tests for missing/invalid `X-API-Key`. Confirmed working in a prior run, but should be a formal test case.

### 🟡 Gap: No test for input validation (422)
- Empty prompt or over-length prompt (>8000 chars) edge cases are not covered. FastAPI's Pydantic validation should return 422, but this is untested.

### 🟡 Gap: `ANTHROPIC_API_KEY` not set
- The `claude-haiku-4-5` model tier will fail on any prompt classified as `simple`. TC002 passed because the prompt was routed to a non-Haiku model, but `simple`-tier requests will error in production until the key is set.

### 🟢 Note: Streaming escalation path untested
- TC003 failed before reaching escalation logic. Once TC003 is fixed, the escalation-in-stream code path (lines 250–293 of `main.py`) should be explicitly tested with a prompt designed to trigger low-confidence escalation.
