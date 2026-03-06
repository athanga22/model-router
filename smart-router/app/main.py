"""Smart Router API — FastAPI entry point."""
import json
import time
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

from app.models import ChatRequest, ChatResponse, HealthResponse, StatsResponse, RecentRequest
from app.router import route_prompt
from app.classifier import classify_prompt
from app.logger import log_request
from app.database import get_connection
from app.cost import calculate_cost, calculate_cost_saved, MODEL_FOR_TAG

load_dotenv()

app = FastAPI(title="Smart Router", version="1.0.0")

_dashboard_url = (os.getenv("DASHBOARD_URL") or "https://model-router-threeways.streamlit.app").rstrip("/")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_dashboard_url],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

# ─────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────

@app.get("/v1/health", response_model=HealthResponse)
def health():
    db_status = "ok"
    try:
        conn = get_connection()
        conn.close()
    except Exception as e:
        db_status = f"error: {e}"

    classifier_status = "ok"
    try:
        classify_prompt("test")
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

@app.post("/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    start = time.time()
    try:
        result = route_prompt(req.prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    except Exception:
        pass  # logging failure is non-fatal

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

@app.post("/v1/chat/stream")
def chat_stream(req: ChatRequest):
    """
    Streaming endpoint.  Yields metadata first (routing decision),
    then tokens as they arrive, then a final done frame with cost info.
    """

    def _generate():
        start = time.time()
        prompt = req.prompt

        # ── 1. Classify ──────────────────────────────────────────────
        try:
            tag = classify_prompt(prompt)
        except Exception as e:
            yield json.dumps({"type": "error", "message": f"classifier_error: {e}"}) + "\n"
            return

        model = MODEL_FOR_TAG[tag]

        # ── 2. Emit metadata immediately so the UI can show routing ──
        yield json.dumps({
            "type": "metadata",
            "difficulty_tag": tag,
            "model_used": model,
            "escalated": False,          # may be updated in done frame
        }) + "\n"

        # ── 3. Get full response via router (blocking), then stream it ─
        full_text = ""
        input_tokens = 0
        output_tokens = 0
        escalated = False
        final_model = model
        final_tag = tag

        try:
            # Let the existing router handle provider selection + escalation.
            result = route_prompt(prompt)
            full_text = result["response"]
            input_tokens = result.get("input_tokens", 0)
            output_tokens = result.get("output_tokens", 0)
            escalated = result.get("escalated", False)
            final_model = result.get("model_used", model)
            final_tag = result.get("difficulty_tag", tag)

            # Stream the text to the client in small chunks so the UI updates incrementally.
            for chunk in _chunk_text(full_text):
                yield _token_yield(chunk)

        except Exception as e:
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"
            return

        # ── 4. Compute costs and emit done ────────────────────────────
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

        # ── 5. Log to DB (non-fatal) ──────────────────────────────────
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
        except Exception:
            pass

    return StreamingResponse(_generate(), media_type="text/event-stream")


# ─────────────────────────────────────────────
# Per-provider streaming helpers
# Each yields token dicts AND returns (full_text, input_tokens, output_tokens)
# ─────────────────────────────────────────────

def _token_yield(text: str) -> str:
    """Build a JSON token line."""
    return json.dumps({"type": "token", "text": text}) + "\n"


def _chunk_text(text: str, size: int = 80):
    """Yield text in fixed-size chunks for simple streaming."""
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _stream_haiku(prompt: str, emit):
    """Stream claude-haiku-4-5 via Anthropic SDK."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

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
    """Stream llama-3.3-70b via Cerebras SDK."""
    from cerebras.cloud.sdk import Cerebras
    client = Cerebras(api_key=os.getenv("CEREBRAS_API_KEY"))

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
    import openai
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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

@app.get("/v1/stats", response_model=StatsResponse)
def stats():
    try:
        conn = get_connection()
        cur = conn.cursor()
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

        cur.close()
        conn.close()

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


@app.get("/v1/recent", response_model=list[RecentRequest])
def recent_requests(limit: int = 20):
    try:
        conn = get_connection()
        cur = conn.cursor()
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
        cur.close()
        conn.close()

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