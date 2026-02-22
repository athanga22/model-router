import time
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.models import ChatRequest, ChatResponse, HealthResponse, StatsResponse
from app.router import route_prompt
from app.logger import log_request
from app.database import get_connection
from app.classifier import classify_prompt, OLLAMA_BASE_URL
import httpx

app = FastAPI(
    title="Smart Model Router",
    description="Routes prompts to the cheapest model capable of handling them.",
    version="1.0.0"
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "detail": str(exc)}
    )


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    if not request.prompt or not request.prompt.strip():
        raise HTTPException(
            status_code=422,
            detail={"error": "empty_prompt", "detail": "Prompt cannot be empty."}
        )

    start = time.time()

    try:
        result = route_prompt(request.prompt)
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail={"error": "classifier_timeout", "detail": "Classifier did not respond in time."}
        )
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail={"error": "model_call_failed", "detail": str(e)}
        )

    latency_ms = int((time.time() - start) * 1000)

    log_request(
        raw_prompt=request.prompt,
        difficulty_tag=result["difficulty_tag"],
        model_used=result["model_used"],
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        cost_usd=result["cost_usd"],
        latency_ms=latency_ms,
        escalated=result["escalated"],
        cost_saved_usd=result["cost_saved_usd"]
    )

    return ChatResponse(
        response=result["response"],
        model_used=result["model_used"],
        difficulty_tag=result["difficulty_tag"],
        cost_usd=result["cost_usd"],
        latency_ms=latency_ms,
        escalated=result["escalated"]
    )


@app.get("/v1/health", response_model=HealthResponse)
async def health():
    # Check DB
    db_status = "connected"
    try:
        conn = get_connection()
        conn.close()
    except Exception:
        db_status = "disconnected"

    # Check classifier (Ollama)
    classifier_status = "ready"
    try:
        r = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3.0)
        r.raise_for_status()
    except Exception:
        classifier_status = "unavailable"

    return HealthResponse(
        status="ok" if db_status == "connected" and classifier_status == "ready" else "degraded",
        db=db_status,
        classifier=classifier_status
    )


@app.get("/v1/stats", response_model=StatsResponse)
async def stats():
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM requests")
        total_requests = cur.fetchone()[0]

        cur.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM requests")
        total_cost = float(cur.fetchone()[0])

        # Cost saved = what GPT-4o would have cost minus what was actually spent
        cur.execute("""
            SELECT COALESCE(SUM(cost_saved_usd), 0)
            FROM requests
        """)
        total_saved = float(cur.fetchone()[0])

        cur.execute("""
            SELECT model_used, COUNT(*) as count
            FROM requests
            GROUP BY model_used
        """)
        model_usage = {row[0]: row[1] for row in cur.fetchall()}

        cur.execute("""
            SELECT ROUND(
                100.0 * SUM(CASE WHEN escalated THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 2
            )
            FROM requests
        """)
        escalation_rate = float(cur.fetchone()[0] or 0)

        cur.close()
        conn.close()

        return StatsResponse(
            total_requests=total_requests,
            total_cost_usd=round(total_cost, 6),
            total_cost_saved_usd=round(total_saved, 6),
            model_usage=model_usage,
            escalation_rate=escalation_rate
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "stats_query_failed", "detail": str(e)}
        )