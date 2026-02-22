from app.database import get_connection

def log_request(
    raw_prompt: str,
    difficulty_tag: str,
    model_used: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    escalated: bool = False
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO requests (
            raw_prompt, difficulty_tag, model_used,
            input_tokens, output_tokens, cost_usd,
            latency_ms, escalated
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        raw_prompt, difficulty_tag, model_used,
        input_tokens, output_tokens, cost_usd,
        latency_ms, escalated
    ))
    conn.commit()
    cur.close()
    conn.close()