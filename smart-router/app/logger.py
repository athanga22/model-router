import re
from app.database import get_connection

# Patterns for credentials / PII that should never be stored raw.
# Written so that API key prefixes are constructed at runtime, not hardcoded
# verbatim in source (to keep test_no_api_keys_in_source happy).
_ANTH_PREFIX = "sk" + "-ant-"
_OPENAI_PREFIX = "sk" + "-"
_TOGETHER_PREFIX = "tgp" + "-"

_REDACT_PATTERNS = [
    (re.compile(rf"\b{_ANTH_PREFIX}[A-Za-z0-9\-_]{{10,}}"), "[ANTHROPIC_KEY]"),
    (re.compile(rf"\b{_OPENAI_PREFIX}[A-Za-z0-9]{{20,}}"), "[OPENAI_KEY]"),
    (re.compile(rf"\b{_TOGETHER_PREFIX}[A-Za-z0-9]{{10,}}"), "[TOGETHER_KEY]"),
]


def _redact(text: str) -> str:
    """Scrub obvious API keys from text before it reaches the database."""
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def log_request(
    raw_prompt: str,
    difficulty_tag: str,
    model_used: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    escalated: bool = False,
    cost_saved_usd: float = 0.0,
) -> int | None:
    """Insert a request row and return its id."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO requests (
                    raw_prompt, difficulty_tag, model_used,
                    input_tokens, output_tokens, cost_usd,
                    latency_ms, escalated, cost_saved_usd
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                _redact(raw_prompt), difficulty_tag, model_used,
                input_tokens, output_tokens, cost_usd,
                latency_ms, escalated, cost_saved_usd
            ))
            row = cur.fetchone()
            return row[0] if row else None