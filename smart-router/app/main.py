"""Smart Router API — FastAPI entry point."""
import json
import logging
import time
import os

from fastapi import FastAPI, HTTPException, Security, Request, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.models import ChatRequest, ChatResponse, HealthResponse, StatsResponse, RecentRequest
from app.router import route_prompt
from app.classifier import classify_prompt
from app.logger import log_request
from app.database import get_connection
from app.cost import calculate_cost, calculate_cost_saved, MODEL_FOR_TAG
from app.escalation import should_escalate, get_next_tier

load_dotenv()

# ── Structured logging to stdout ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
_logger = logging.getLogger(__name__)

app = FastAPI(title="Smart Router", version="1.0.0")

# ── Auth (optional when API_KEY unset — set API_KEY on Cloud Run + Streamlit secrets) ──
_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_api_key(key: str | None = Security(_API_KEY_HEADER)):
    expected = os.getenv("API_KEY")
    if not expected:
        return  # no auth when not configured (local dev)
    if key != expected:
        raise HTTPException(status_code=403, detail="invalid_api_key")


@app.on_event("startup")
async def _startup():
    """Validate configuration and log startup status."""
    missing_keys = [v for v in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CEREBRAS_API_KEY") if not os.getenv(v)]
    if missing_keys:
        _logger.error("Missing required API keys: %s — requests will fail until set", missing_keys)

    if not os.getenv("API_KEY"):
        _logger.warning("API_KEY not set — authentication is DISABLED (acceptable for local dev only)")

    if not os.getenv("DASHBOARD_URL"):
        _logger.warning("DASHBOARD_URL not set — CORS using hardcoded default origin")

    _logger.info(
        "Smart Router started | auth=%s | dashboard_origin=%s",
        "enabled" if os.getenv("API_KEY") else "disabled",
        _dashboard_url,
    )


# ── Rate limiter (per IP; Streamlit Cloud shares one IP — use 60/min for demo) ──
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_dashboard_url = (os.getenv("DASHBOARD_URL") or "https://model-router-threeways.streamlit.app").rstrip("/")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_dashboard_url],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────

@app.get("/v1/health", response_model=HealthResponse)
def health():
    db_status = "ok"
    try:
        with get_connection() as conn:
            pass  # verify pool can hand out a connection
    except Exception as e:
        db_status = f"error: {e}"

    classifier_status = "ok"
    try:
        # Avoid a real classification request; just ensure the client can be constructed.
        from app.classifier import _get_client as _get_classifier_client  # type: ignore
        _get_classifier_client()
    except Exception as e:
        classifier_status = f"error: {e}"

    return HealthResponse(
        status="ok",
        db=db_status,
        classifier=classifier_status,
    )


# ─────────────────────────────────────────────
# Blocking chat (original)
# ─────────────────────────────────────────────

@app.post(
    "/v1/chat",
    response_model=ChatResponse,
    dependencies=[Depends(_require_api_key)],
)
@limiter.limit("60/minute")
def chat(req: ChatRequest, request: Request):
    start = time.time()
    try:
        result = route_prompt(req.prompt)
    except Exception as e:
        _logger.error("route_prompt failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="internal_error")

    latency_ms = int((time.time() - start) * 1000)

    try:
        log_request(
            raw_prompt=req.prompt,
            difficulty_tag=result["difficulty_tag"],
            model_used=result["model_used"],
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            cost_usd=result["cost_usd"],
            latency_ms=latency_ms,
            escalated=result["escalated"],
            cost_saved_usd=result["cost_saved_usd"],
        )
    except Exception as log_exc:
        _logger.warning("request logging failed: %s", log_exc)

    return ChatResponse(
        response=result["response"],
        model_used=result["model_used"],
        difficulty_tag=result["difficulty_tag"],
        cost_usd=result["cost_usd"],
        latency_ms=latency_ms,
        escalated=result["escalated"],
    )


# ─────────────────────────────────────────────
# Streaming chat — new endpoint
#
# Wire protocol (newline-delimited JSON, text/event-stream):
#
#   1. {"type": "metadata", "model_used": "...", "difficulty_tag": "...",
#       "escalated": false}
#   2. {"type": "token", "text": "Hello"}   (one per token)
#      {"type": "token", "text": " world"}
#      ...
#   3. {"type": "done", "cost_usd": 0.000012, "cost_saved_usd": 0.000088,
#       "latency_ms": 340, "input_tokens": 18, "output_tokens": 42}
#
# On error:
#   {"type": "error", "message": "..."}
#
# ─────────────────────────────────────────────

@app.post("/v1/chat/stream", dependencies=[Depends(_require_api_key)])
@limiter.limit("60/minute")
def chat_stream(req: ChatRequest, request: Request):
    """
    Streaming endpoint.  Yields metadata first (routing decision),
    then tokens as they arrive, then a final done frame with cost info.
    """

    def _generate():
        start = time.time()
        prompt = req.prompt

        # 1. Classify
        try:
            tag = classify_prompt(prompt)
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"classifier_error: {e}"}) + "\n"
            return

        model = MODEL_FOR_TAG[tag]

        # 2. Buffer first-tier response — needed to check for escalation
        buffered_tokens = []
        full_text = ""
        input_tokens = 0
        output_tokens = 0

        try:
            if model == "claude-haiku-4-5":
                gen = _stream_haiku(prompt, emit=_token_yield)
            elif model == "gpt-oss-120b":
                gen = _stream_cerebras(prompt, model="gpt-oss-120b", emit=_token_yield)
            elif model == "gpt-4o":
                gen = _stream_openai(prompt, emit=_token_yield)
            else:
                yield json.dumps({"type": "error", "message": f"unsupported_model: {model}"}) + "\n"
                return

            try:
                while True:
                    line = next(gen)
                    parsed = json.loads(line)
                    if parsed.get("type") == "token":
                        full_text += parsed.get("text", "")
                    buffered_tokens.append(line)
            except StopIteration as stop:
                if stop.value is not None:
                    full_text, input_tokens, output_tokens = stop.value

        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"
            return

        # 3. Escalation check
        escalated = False
        final_model = model
        final_tag = tag

        if should_escalate(full_text):
            next_result = get_next_tier(tag)
            if next_result:
                next_model, next_tag = next_result
                escalated = True
                final_model = next_model
                final_tag = next_tag

                yield json.dumps({
                    "type": "metadata",
                    "difficulty_tag": final_tag,
                    "model_used": final_model,
                    "escalated": True,
                }) + "\n"

                # True-stream from the escalated model
                try:
                    if final_model == "claude-haiku-4-5":
                        esc_gen = _stream_haiku(prompt, emit=_token_yield)
                    elif final_model == "gpt-oss-120b":
                        esc_gen = _stream_cerebras(prompt, model="gpt-oss-120b", emit=_token_yield)
                    elif final_model == "gpt-4o":
                        esc_gen = _stream_openai(prompt, emit=_token_yield)
                    else:
                        yield json.dumps({"type": "error", "message": f"unsupported_model: {final_model}"}) + "\n"
                        return

                    full_text = ""
                    input_tokens = output_tokens = 0
                    try:
                        while True:
                            line = next(esc_gen)
                            yield line
                            parsed = json.loads(line)
                            if parsed.get("type") == "token":
                                full_text += parsed.get("text", "")
                    except StopIteration as stop:
                        if stop.value is not None:
                            full_text, input_tokens, output_tokens = stop.value

                except Exception as e:
                    yield json.dumps({"type": "error", "message": f"escalation_failed: {e}"}) + "\n"
                    return
            else:
                # Already at top tier — flush buffer as-is
                yield json.dumps({
                    "type": "metadata",
                    "difficulty_tag": tag,
                    "model_used": model,
                    "escalated": False,
                }) + "\n"
                for line in buffered_tokens:
                    yield line
                    time.sleep(0.015)
        else:
            # No escalation — flush buffer
            yield json.dumps({
                "type": "metadata",
                "difficulty_tag": tag,
                "model_used": model,
                "escalated": False,
            }) + "\n"
            for line in buffered_tokens:
                yield line
                time.sleep(0.015)

        # 4. Done frame
        latency_ms = int((time.time() - start) * 1000)
        cost_usd = calculate_cost(final_model, input_tokens, output_tokens)
        cost_saved_usd = calculate_cost_saved(final_model, input_tokens, output_tokens)

        yield json.dumps({
            "type": "done",
            "model_used": final_model,
            "difficulty_tag": final_tag,
            "escalated": escalated,
            "cost_usd": cost_usd,
            "cost_saved_usd": cost_saved_usd,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }) + "\n"

        # 5. Log (non-fatal)
        try:
            log_request(
                raw_prompt=prompt,
                difficulty_tag=final_tag,
                model_used=final_model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                escalated=escalated,
                cost_saved_usd=cost_saved_usd,
            )
        except Exception as log_exc:
            _logger.warning("stream request logging failed: %s", log_exc)

    return StreamingResponse(_generate(), media_type="text/event-stream")


# ─────────────────────────────────────────────
# Per-provider streaming helpers
# Each yields token dicts AND returns (full_text, input_tokens, output_tokens)
# ─────────────────────────────────────────────

def _token_yield(text: str) -> str:
    """Build a JSON token line."""
    return json.dumps({"type": "token", "text": text}) + "\n"


def _stream_haiku(prompt: str, emit):
    """Stream claude-haiku-4-5 via Anthropic SDK."""
    from app.llm import _get_anthropic_client  # reuse lazy singleton
    client = _get_anthropic_client()

    full_text = ""
    input_tokens = 0
    output_tokens = 0

    with client.messages.stream(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            full_text += text
            yield emit(text)          # yield to outer generator

        msg = stream.get_final_message()
        input_tokens = msg.usage.input_tokens
        output_tokens = msg.usage.output_tokens

    return full_text, input_tokens, output_tokens


def _stream_cerebras(prompt: str, model: str, emit):
    """Stream gpt-oss-120b via Cerebras SDK."""
    from app.llm import _get_cerebras_client  # reuse lazy singleton
    client = _get_cerebras_client()

    full_text = ""
    input_tokens = 0
    output_tokens = 0

    stream = client.chat.completions.create(
        model=model,
        max_completion_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            full_text += delta.content
            yield emit(delta.content)

        # Usage available on the final chunk
        if hasattr(chunk, "usage") and chunk.usage:
            input_tokens = getattr(chunk.usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(chunk.usage, "completion_tokens", 0) or 0

    return full_text, input_tokens, output_tokens


def _stream_openai(prompt: str, emit):
    """Stream gpt-4o via OpenAI SDK."""
    from app.llm import _get_openai_client  # reuse lazy singleton
    client = _get_openai_client()

    full_text = ""
    input_tokens = 0
    output_tokens = 0

    stream = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        stream_options={"include_usage": True},
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            text = chunk.choices[0].delta.content
            full_text += text
            yield emit(text)

        if hasattr(chunk, "usage") and chunk.usage:
            input_tokens = chunk.usage.prompt_tokens or 0
            output_tokens = chunk.usage.completion_tokens or 0

    return full_text, input_tokens, output_tokens


# ─────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────

@app.get("/v1/stats", response_model=StatsResponse, dependencies=[Depends(_require_api_key)])
def stats():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) AS total,
                        COALESCE(SUM(cost_usd), 0) AS total_cost,
                        COALESCE(SUM(cost_saved_usd), 0) AS total_saved,
                        COALESCE(AVG(escalated::int), 0) AS escalation_rate
                    FROM requests
                """)
                row = cur.fetchone()

                cur.execute("""
                    SELECT model_used, COUNT(*) FROM requests GROUP BY model_used
                """)
                model_usage = {r[0]: r[1] for r in cur.fetchall()}

                cur.execute("""
                    SELECT DATE_TRUNC('hour', created_at) AS hr,
                           SUM(cost_saved_usd) AS saved
                    FROM requests GROUP BY hr ORDER BY hr
                """)
                savings_rows = cur.fetchall()
                savings_ts = [
                    {"hour": r[0].isoformat(), "saved": float(r[1])}
                    for r in savings_rows
                ]

        return StatsResponse(
            total_requests=row[0],
            total_cost_usd=float(row[1]),
            total_cost_saved_usd=float(row[2]),
            model_usage=model_usage,
            escalation_rate=float(row[3]),
            savings_ts=savings_ts,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/v1/recent", response_model=list[RecentRequest], dependencies=[Depends(_require_api_key)])
def recent_requests(limit: int = 20):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT created_at, difficulty_tag, model_used,
                           cost_usd, cost_saved_usd, latency_ms, escalated
                    FROM requests
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cur.fetchall()

        return [
            RecentRequest(
                created_at=r[0],
                difficulty_tag=r[1],
                model_used=r[2],
                cost_usd=float(r[3]),
                cost_saved_usd=float(r[4]),
                latency_ms=int(r[5]),
                escalated=bool(r[6]),
            )
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────
# Dev runner
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)