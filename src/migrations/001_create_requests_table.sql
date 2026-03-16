CREATE TABLE IF NOT EXISTS requests (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    raw_prompt      TEXT NOT NULL,
    difficulty_tag  VARCHAR(10) NOT NULL,
    model_used      VARCHAR(50) NOT NULL,
    input_tokens    INTEGER,
    output_tokens   INTEGER,
    cost_usd        NUMERIC(10, 6),
    cost_saved_usd  NUMERIC(10, 6) DEFAULT 0,
    latency_ms      INTEGER,
    escalated       BOOLEAN DEFAULT FALSE
);